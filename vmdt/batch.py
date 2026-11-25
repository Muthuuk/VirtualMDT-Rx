"""Review many patients at once ("doubly parallel": across experts and across patients).

Works on a CSV of current and proposed medicines. A synthetic cohort generator is
included so the tool can be tried without any real data.

CSV columns (only patient_ref, age, sex and proposed_drug are required):
  patient_ref, age, sex, egfr, pregnant, trimester, conditions, allergies,
  current_meds, proposed_drug, dose, frequency, duration_days, indication,
  uti_courses_6m, culture_resistant_to, cognitive_impairment, dexterity_problem,
  falls_history, frail, notes, urine_culture, clear_cultures_12m, antibiotic_days_12m
Lists use ';' between items. Allergies use 'substance:reaction', e.g. 'penicillin:anaphylaxis'.
"""
from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
from typing import List

import pandas as pd

from .models import Allergy, Patient, Proposal
from .orchestrator import run_case


def _split(v) -> List[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [x.strip() for x in str(v).split(";") if x.strip()]


def _flag(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y")


def _num(v):
    try:
        return None if v is None or pd.isna(v) or str(v).strip() == "" else float(v)
    except (TypeError, ValueError):
        return None


def row_to_patient(r: dict) -> Patient:
    al = []
    for item in _split(r.get("allergies")):
        sub, _, reac = item.partition(":")
        al.append(Allergy(sub.strip(), reac.strip() or "unknown"))
    dur, tri = _num(r.get("duration_days")), _num(r.get("trimester"))
    return Patient(
        ref=str(r.get("patient_ref", "")), age=int(_num(r.get("age")) or 0), sex=str(r.get("sex", "female")).strip().lower(),
        proposal=Proposal(str(r.get("proposed_drug", "")), str(r.get("dose", "") if not pd.isna(r.get("dose", "")) else ""),
                          str(r.get("frequency") or "once daily") if not pd.isna(r.get("frequency", "once daily")) else "once daily",
                          int(dur) if dur else None, str(r.get("indication") or "other")),
        egfr=_num(r.get("egfr")), pregnant=_flag(r.get("pregnant")), trimester=int(tri) if tri else None,
        conditions=_split(r.get("conditions")), allergies=al, current_meds=_split(r.get("current_meds")),
        uti_courses_6m=int(_num(r.get("uti_courses_6m")) or 0), culture_resistant_to=_split(r.get("culture_resistant_to")),
        cognitive_impairment=_flag(r.get("cognitive_impairment")), dexterity_problem=_flag(r.get("dexterity_problem")),
        falls_history=_flag(r.get("falls_history")), frail=_flag(r.get("frail")),
        urine_culture=(str(r.get("urine_culture")).strip().lower() if r.get("urine_culture") is not None and not pd.isna(r.get("urine_culture")) and str(r.get("urine_culture")).strip() else "not recorded"),
        clear_cultures_12m=int(_num(r.get("clear_cultures_12m")) or 0), antibiotic_days_12m=int(_num(r.get("antibiotic_days_12m")) or 0),
        notes="" if pd.isna(r.get("notes", "")) else str(r.get("notes", "")),
    )


def review_frame(df: pd.DataFrame, workers: int = 8) -> pd.DataFrame:
    patients = [row_to_patient(r) for r in df.to_dict("records")]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_case, patients))
    rows, titles = [], {}
    for p, res in zip(patients, results):
        notable = [f for f in res.findings if f.level != "INFO"]
        for f in notable:
            titles.setdefault(f.code, f.title)
        rows.append({
            "patient_ref": p.ref, "indication": p.proposal.indication, "proposed": p.proposal.drug,
            "outcome": res.outcome, "red": sum(f.level == "RED" for f in notable),
            "amber": sum(f.level == "AMBER" for f in notable),
            "top_finding": notable[0].title if notable else "",
            "rule_codes": ";".join(f.code for f in notable),
            "safer_option": res.alternative or "",
        })
    out = pd.DataFrame(rows)
    out.attrs["titles"] = titles   # rule code -> example wording, for summaries
    return out


def synthetic_cohort(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Invented patients for demonstration. Proportions are made up, NOT epidemiology."""
    rng = random.Random(seed)
    plans = {
        "uti": (["nitrofurantoin", "trimethoprim", "pivmecillinam", "fosfomycin", "cefalexin", "ciprofloxacin"],
                ["twice daily", "twice daily", "three times daily", "single dose", "twice daily", "twice daily"]),
        "type2_diabetes": (["metformin", "gliclazide", "dapagliflozin", "sitagliptin", "pioglitazone", "glibenclamide"],
                           ["twice daily", "once daily", "once daily", "once daily", "once daily", "once daily"]),
        "cancer_care": (["tamoxifen", "letrozole", "morphine", "ondansetron", "dexamethasone", "methotrexate"],
                        ["once daily", "once daily", "twice daily", "twice daily", "once daily", "once weekly"]),
    }
    doses = {"nitrofurantoin": "100 mg modified-release", "trimethoprim": "200 mg", "pivmecillinam": "400 mg then 200 mg",
             "fosfomycin": "3 g", "cefalexin": "500 mg", "ciprofloxacin": "500 mg", "metformin": "500 mg", "gliclazide": "40 mg",
             "dapagliflozin": "10 mg", "sitagliptin": "100 mg", "pioglitazone": "15 mg", "glibenclamide": "5 mg", "tamoxifen": "20 mg",
             "letrozole": "2.5 mg", "morphine": "10 mg modified-release", "ondansetron": "8 mg", "dexamethasone": "4 mg",
             "methotrexate": "10 mg"}
    background = ["amlodipine", "atorvastatin", "ramipril", "omeprazole", "paracetamol", "bisoprolol", "levothyroxine",
                  "sertraline", "paroxetine", "warfarin", "furosemide", "spironolactone", "methotrexate", "simvastatin",
                  "senna", "prednisolone", "citalopram", "metformin", "ibuprofen"]
    rows = []
    for i in range(n):
        ind = rng.choice(list(plans))
        k = rng.randrange(len(plans[ind][0]))
        drug, freq = plans[ind][0][k], plans[ind][1][k]
        age = rng.randint(22, 92)
        sex = "female" if (ind == "uti" and rng.random() < 0.8) or rng.random() < 0.5 else "male"
        egfr = max(12, min(110, round(rng.gauss(95 - max(0, age - 40) * 0.8, 16))))
        meds = rng.sample(background, k=rng.choice([0, 1, 2, 2, 3, 4, 6, 8]))
        conds = {"uti": [], "type2_diabetes": ["type 2 diabetes"], "cancer_care": [rng.choice(["breast cancer", "prostate cancer", "bowel cancer"])]}[ind]
        if rng.random() < 0.08:
            conds.append("heart failure")
        allergies = "penicillin:" + rng.choice(["rash", "anaphylaxis", "intolerance"]) if rng.random() < 0.10 else ""
        days = {"uti": rng.choice([3, 3, 3, 7]), "type2_diabetes": "", "cancer_care": ""}[ind]
        rows.append({
            "patient_ref": f"SYN-{i + 1:04d}", "age": age, "sex": sex, "egfr": egfr,
            "pregnant": "yes" if sex == "female" and 20 <= age <= 40 and ind == "uti" and rng.random() < 0.08 else "no",
            "trimester": 1, "conditions": ";".join(conds), "allergies": allergies, "current_meds": ";".join(meds),
            "proposed_drug": drug, "dose": doses[drug], "frequency": freq, "duration_days": days, "indication": ind,
            "uti_courses_6m": rng.choice([0, 0, 0, 1, 2, 3]) if ind == "uti" else 0, "culture_resistant_to": "",
            "cognitive_impairment": "yes" if age > 75 and rng.random() < 0.2 else "no", "dexterity_problem": "no",
            "falls_history": "yes" if age > 75 and rng.random() < 0.25 else "no", "frail": "yes" if age > 80 and rng.random() < 0.4 else "no",
            "notes": "",
        })
    return pd.DataFrame(rows)
