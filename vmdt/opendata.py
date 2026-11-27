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


# ----------------------------------------------------------------------------
# NHS Business Services Authority (NHSBSA) Open Data Portal: the official source.
# OpenPrescribing stopped serving automated third-party requests in 2026 (they are
# turned away by its web filter), so the tool now reads the English Prescribing
# Dataset directly from NHSBSA, published under the Open Government Licence.
# ----------------------------------------------------------------------------
NHSBSA = "https://opendata.nhsbsa.net/api/3/action"
EPD_PACKAGE = "english-prescribing-dataset-epd-with-snomed-code"
EPD_NAMES = {  # how each medicine starts in the dataset's chemical-substance description
    "uti": ["Nitrofurantoin", "Trimethoprim", "Pivmecillinam", "Fosfomycin", "Cefalexin"],
    "type2_diabetes": ["Metformin", "Gliclazide", "Dapagliflozin", "Empagliflozin", "Sitagliptin", "Linagliptin"],
    "cancer_care": ["Tamoxifen", "Letrozole", "Anastrozole", "Methotrexate", "Morphine"],
}


def epd_resources(timeout: float = 20) -> list:
    """Monthly tables of the dataset, newest first: [(name such as EPD_SNOMED_202609, yyyymm)]."""
    import re
    r = requests.get(f"{NHSBSA}/package_show", params={"id": EPD_PACKAGE}, headers=UA, timeout=timeout)
    r.raise_for_status()
    out = []
    for res in r.json()["result"]["resources"]:
        m = re.search(r"(\d{6})$", str(res.get("name", "")))
        if m:
            out.append((res["name"], m.group(1)))
    return sorted(set(out), key=lambda t: t[1], reverse=True)


def pick_columns(columns: list) -> dict:
    """Find the three columns we need, whatever exact names this month's table uses."""
    up = {c.upper(): c for c in columns}
    chem = next((up[c] for c in up if "CHEMICAL" in c and "DESC" in c), None) or next((up[c] for c in up if "CHEMICAL" in c and "CODE" not in c), None)
    items = up.get("ITEMS") or next((up[c] for c in up if c.endswith("ITEMS")), None)
    cost = up.get("ACTUAL_COST") or next((up[c] for c in up if "COST" in c), None)
    if not (chem and items):
        raise ValueError(f"Could not find the medicine and items columns in: {columns[:12]}")
    return {"chem": chem, "items": items, "cost": cost}


def _sql(resource: str, sql: str, timeout: float = 60) -> list:
    r = requests.get(f"{NHSBSA}/datastore_search_sql", params={"resource_id": resource, "sql": sql}, headers=UA, timeout=timeout)
    r.raise_for_status()
    result = r.json().get("result", {})
    if "records" in result:
        return result["records"]
    inner = result.get("result", {})          # large answers are returned as a file to download
    if isinstance(inner, dict) and inner.get("records"):
        return inner["records"]
    urls = result.get("gc_urls") or (inner.get("gc_urls") if isinstance(inner, dict) else None)
    if urls:
        import io
        return pd.read_csv(io.StringIO(requests.get(urls[0]["url"], headers=UA, timeout=timeout).text)).to_dict("records")
    return []


def nhsbsa_trends(indication: str, months: int = 6) -> Tuple[pd.DataFrame, str]:
    """National monthly items for each medicine in a group, from the official NHS dataset."""
    names = EPD_NAMES.get(indication, [])
    try:
        resources = epd_resources()[:months]
        if not resources:
            return pd.DataFrame(), "The NHS open data portal listed no monthly tables."
        cols = pick_columns(list(_sql(resources[0][0], f"SELECT * FROM `{resources[0][0]}` LIMIT 1")[0].keys()))
        where = " OR ".join(f"{cols['chem']} LIKE '{n}%'" for n in names)
        cost = f", SUM({cols['cost']}) AS ACTUAL_COST" if cols["cost"] else ""
        frames = []
        for name, ym in resources:
            rows = _sql(name, f"SELECT {cols['chem']} AS MEDICINE, SUM({cols['items']}) AS ITEMS{cost} FROM `{name}` WHERE {where} GROUP BY {cols['chem']}")
            for row in rows:
                frames.append({"date": pd.to_datetime(ym + "01", format="%Y%m%d"), "medicine": str(row["MEDICINE"]),
                               "bnf_code": "", "items": float(row["ITEMS"]), "actual_cost": float(row.get("ACTUAL_COST") or 0)})
    except Exception as exc:
        return pd.DataFrame(), (f"The NHS open data portal could not be read from this computer ({type(exc).__name__}: {str(exc)[:160]}). "
                                "No chart is shown and nothing is made up. You can upload a file instead.")
    if not frames:
        return pd.DataFrame(), "The NHS open data portal returned no rows for these medicines."
    df = pd.DataFrame(frames)
    df["medicine"] = df["medicine"].apply(lambda s: next((n for n in names if s.lower().startswith(n.lower())), s))
    df = df.groupby(["date", "medicine", "bnf_code"], as_index=False)[["items", "actual_cost"]].sum()   # e.g. two salts of one medicine
    return df, ("Source: NHS Business Services Authority, English Prescribing Dataset (Open Government Licence v3.0). "
                f"England, primary care, latest {len(resources)} months.")


def trends_from_csv(path: str) -> Tuple[pd.DataFrame, str]:
    """Chart a file the user downloaded by hand. Needs columns for month, medicine and items (names are matched loosely)."""
    raw = pd.read_csv(path)
    low = {c.lower().strip(): c for c in raw.columns}
    find = lambda *keys: next((low[c] for c in low if any(k in c for k in keys)), None)
    date_c, med_c, items_c, cost_c = find("date", "month", "year_month"), find("medicine", "chemical", "name", "drug"), find("items"), find("cost")
    if not (date_c and med_c and items_c):
        return pd.DataFrame(), f"The file needs columns for the month, the medicine and the number of items. Found: {list(raw.columns)[:10]}"
    d = raw[date_c].astype(str).str.strip()
    dates = pd.to_datetime(d.where(~d.str.fullmatch(r"\d{6}"), d + "01"), errors="coerce", format="mixed")
    df = pd.DataFrame({"date": dates, "medicine": raw[med_c].astype(str), "bnf_code": "",
                       "items": pd.to_numeric(raw[items_c], errors="coerce"),
                       "actual_cost": pd.to_numeric(raw[cost_c], errors="coerce") if cost_c else 0.0}).dropna(subset=["date", "items"])
    df = df.groupby(["date", "medicine", "bnf_code"], as_index=False)[["items", "actual_cost"]].sum()
    return df, f"Source: your uploaded file ({len(df)} rows after grouping)."


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Latest month against a year earlier (or the earliest month held), with each medicine's share."""
    if df.empty:
        return df
    latest = df["date"].max()
    prior = latest - pd.DateOffset(years=1)
    if df[df["date"] == prior].empty:            # less than a year of data: compare with the earliest month held
        prior = df["date"].min()
    now = df[df["date"] == latest].groupby("medicine")[["items", "actual_cost"]].sum()
    out = pd.DataFrame({f"Items, {latest:%b %Y}": now["items"].astype(int)})
    a = out.iloc[:, 0]
    if prior != latest:
        b = df[df["date"] == prior].groupby("medicine")["items"].sum().reindex(now.index)
        out[f"Items, {prior:%b %Y}"] = b
        out["Change (%)"] = ((a - b) / b * 100).round(1)
    out["Share of group (%)"] = (a / a.sum() * 100).round(1)
    out[f"Cost, {latest:%b %Y} (GBP)"] = now["actual_cost"].round(0)
    return out.sort_values(out.columns[0], ascending=False).reset_index()


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
