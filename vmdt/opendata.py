"""Live open data: what is actually being prescribed, and what has been published.

1. OpenPrescribing (Bennett Institute, University of Oxford): monthly counts of
   items prescribed in English general practice, built from NHS Business
   Services Authority data. No patient-level data.
2. PubMed (US National Library of Medicine, E-utilities): recent paper titles.

Only medicine names and BNF codes are ever sent. If a site cannot be reached the
functions return an empty result and a plain message; no figures are invented.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd
import requests

OP = "https://openprescribing.net/api/1.0"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = {"User-Agent": "VirtualMDT-Rx research demonstrator (github.com/Muthuuk)"}

CONDITION_DRUGS = {
    "uti": ["nitrofurantoin", "trimethoprim", "pivmecillinam", "fosfomycin", "cefalexin"],
    "type2_diabetes": ["metformin", "gliclazide", "dapagliflozin", "empagliflozin", "sitagliptin", "linagliptin"],
    "cancer_care": ["tamoxifen", "letrozole", "anastrozole", "methotrexate", "morphine"],
}
CONDITION_LABEL = {"uti": "Urine infection antibiotics", "type2_diabetes": "Type 2 diabetes medicines",
                   "cancer_care": "Cancer care medicines (hormone, shared-care and pain)"}
PUBMED_TERM = {"uti": "urinary tract infection", "type2_diabetes": "type 2 diabetes", "cancer_care": "cancer"}


def pick_chemical(rows: list, query: str) -> Optional[Tuple[str, str]]:
    """From OpenPrescribing's search results choose the single-ingredient chemical
    whose name starts with the query; the shortest name wins (avoids combinations)."""
    q = query.lower()
    cands = [r for r in rows if str(r.get("type", "")).lower() == "chemical"
             and str(r.get("name", "")).lower().startswith(q) and "/" not in str(r.get("name", ""))]
    if not cands:
        return None
    best = min(cands, key=lambda r: len(r["name"]))
    return best["id"], best["name"]


def find_chemical(name: str, timeout: float = 12) -> Optional[Tuple[str, str]]:
    r = requests.get(f"{OP}/bnf_code/", params={"q": name, "format": "json"}, headers=UA, timeout=timeout)
    r.raise_for_status()
    return pick_chemical(r.json(), name)


def spending(code: str, timeout: float = 20) -> pd.DataFrame:
    r = requests.get(f"{OP}/spending/", params={"code": code, "format": "json"}, headers=UA, timeout=timeout)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def condition_trends(indication: str) -> Tuple[pd.DataFrame, str]:
    """Monthly items for each medicine in a condition group. Returns (long table, message)."""
    frames, problems = [], []
    for name in CONDITION_DRUGS.get(indication, []):
        try:
            found = find_chemical(name)
            if not found:
                problems.append(f"{name}: not found")
                continue
            code, label = found
            df = spending(code)
            if df.empty:
                problems.append(f"{name}: no data")
                continue
            df["medicine"], df["bnf_code"] = label, code
            frames.append(df[["date", "medicine", "bnf_code", "items", "actual_cost"]])
        except Exception as exc:
            problems.append(f"{name}: {type(exc).__name__}")
    if not frames:
        return pd.DataFrame(), ("Could not reach OpenPrescribing from this computer, so no chart is shown "
                                "(nothing is made up). Details: " + "; ".join(problems))
    msg = "Source: OpenPrescribing.net, Bennett Institute for Applied Data Science, University of Oxford. England, general practice."
    if problems:
        msg += " Missing: " + "; ".join(problems)
    return pd.concat(frames, ignore_index=True), msg


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Latest month, the same month a year earlier, and the change."""
    if df.empty:
        return df
    latest = df["date"].max()
    prior = latest - pd.DateOffset(years=1)
    now = df[df["date"] == latest].set_index("medicine")
    then = df[df["date"] == prior].set_index("medicine")
    out = pd.DataFrame({"BNF code": now["bnf_code"], f"Items, {latest:%b %Y}": now["items"].astype(int),
                        f"Items, {prior:%b %Y}": then["items"].reindex(now.index)})
    a, b = out.iloc[:, 1], out.iloc[:, 2]
    out["Change over 12 months (%)"] = ((a - b) / b * 100).round(1)
    out["Share of group (%)"] = (a / a.sum() * 100).round(1)
    out[f"Cost, {latest:%b %Y} (GBP)"] = now["actual_cost"].round(0)
    return out.sort_values(out.columns[1], ascending=False).reset_index()


def pubmed_recent(drug: str, indication: str = "", n: int = 3, timeout: float = 4) -> Tuple[List[tuple], str]:
    """Titles of the newest safety papers. Returns ([(pmid, title, year)], message)."""
    term = f'{drug}[Title/Abstract] AND (safety[Title/Abstract] OR "adverse"[Title/Abstract])'
    if indication in PUBMED_TERM:
        term += f' AND {PUBMED_TERM[indication]}[Title/Abstract]'
    try:
        r = requests.get(f"{EUTILS}/esearch.fcgi", headers=UA, timeout=timeout,
                         params={"db": "pubmed", "term": term, "retmode": "json", "retmax": n, "sort": "date"})
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return [], "PubMed returned no matching papers."
        s = requests.get(f"{EUTILS}/esummary.fcgi", headers=UA, timeout=timeout,
                         params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        s.raise_for_status()
        res = s.json().get("result", {})
        return [(i, res[i].get("title", "").rstrip("."), res[i].get("pubdate", "")[:4]) for i in ids if i in res], "ok"
    except Exception as exc:
        return [], f"PubMed could not be reached within the time limit ({type(exc).__name__}). The other experts were not delayed."
