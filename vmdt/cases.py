"""Synthetic cases. Every patient here is invented; none is a real person.

PRESETS feed the demo buttons. SUITE is the evaluation set: each case states the
outcome a pharmacist-style reviewer would expect and the rule codes that must
(or must not) fire. The suite is how requirements become tests.
"""
from __future__ import annotations

from typing import List

from .models import Allergy, Patient, Proposal


def P(ref, age, sex, drug, dose, freq, days, ind, **kw) -> Patient:
    al = [Allergy(*a) if isinstance(a, tuple) else Allergy(a) for a in kw.pop("allergies", [])]
    return Patient(ref=ref, age=age, sex=sex, proposal=Proposal(drug, dose, freq, days, ind), allergies=al, **kw)


# (case, expected outcome, codes that must fire, codes that must NOT be RED)
SUITE: List[tuple] = [
    # ---- urinary tract infection
    (P("UTI-01", 34, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=95), "GREEN", [], []),
    (P("UTI-02", 78, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=38,
       current_meds=["amlodipine", "atorvastatin"]), "RED", ["PH-REN-001"], []),
    (P("UTI-03", 66, "female", "trimethoprim", "200 mg", "twice daily", 3, "uti", egfr=70,
       current_meds=["methotrexate", "paracetamol"], conditions=["rheumatoid arthritis"]), "RED", ["PH-INT-001"], []),
    (P("UTI-04", 72, "male", "trimethoprim", "200 mg", "twice daily", 7, "uti", egfr=55,
       current_meds=["ramipril", "amlodipine"]), "AMBER", ["PH-INT-002"], []),
    (P("UTI-05", 45, "female", "pivmecillinam", "400 mg then 200 mg", "three times daily", 3, "uti", egfr=90,
       allergies=[("penicillin", "anaphylaxis")]), "RED", ["AL-001"], []),
    (P("UTI-06", 45, "female", "pivmecillinam", "400 mg then 200 mg", "three times daily", 3, "uti", egfr=90,
       allergies=[("penicillin", "intolerance")]), "AMBER", ["AL-001"], ["AL-001"]),
    (P("UTI-07", 29, "female", "trimethoprim", "200 mg", "twice daily", 7, "uti", egfr=100, pregnant=True, trimester=1), "RED", ["PH-PRG-001"], []),
    (P("UTI-08", 58, "female", "trimethoprim", "200 mg", "twice daily", 3, "uti", egfr=80, uti_courses_6m=3,
       culture_resistant_to=["trimethoprim"]), "RED", ["MB-001", "MB-002"], []),
    (P("UTI-09", 67, "male", "nitrofurantoin", "100 mg modified-release", "twice daily", 7, "uti", egfr=75,
       notes="Third course this year. Reports visible blood in urine last week, no fever."), "RED", ["UR-001"], []),
    (P("UTI-10", 52, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=85,
       notes="Dysuria and frequency. No fever, no blood in urine, no loin pain."), "GREEN", [], ["UR-001", "UR-003"]),
    (P("UTI-11", 61, "female", "trimethoprim", "200 mg", "twice daily", 3, "uti", egfr=80,
       current_meds=["capecitabine"], conditions=["bowel cancer on chemotherapy"],
       notes="Feels shivery with a fever since last night."), "RED", ["ON-001"], []),
    (P("UTI-12", 70, "female", "ciprofloxacin", "500 mg", "twice daily", 3, "uti", egfr=70, current_meds=["prednisolone"]),
     "AMBER", ["GU-003", "PH-INT-011"], []),
    (P("UTI-13", 40, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 7, "uti", egfr=90), "AMBER", ["GU-002"], []),
    (P("UTI-14", 81, "female", "nitrofurantoin", "50 mg", "four times daily", 3, "uti", egfr=62, cognitive_impairment=True,
       current_meds=["amlodipine", "atorvastatin", "levothyroxine", "omeprazole", "paracetamol", "bisoprolol", "alendronic acid"]),
     "RED", ["OT-001"], []),
    (P("UTI-15", 39, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=None), "AMBER", ["PH-REN-000"], []),
    (P("UTI-16", 55, "female", "cefalexin", "500 mg", "twice daily", 3, "uti", egfr=88, allergies=[("penicillin", "anaphylaxis")]),
     "RED", ["AL-002"], []),
    # every usual option blocked -> hard stop
    (P("UTI-17", 76, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=28,
       allergies=[("penicillin", "anaphylaxis"), ("trimethoprim", "rash")], culture_resistant_to=["fosfomycin"]),
     "HARD_STOP", ["PH-REN-001"], []),
    # ---- type 2 diabetes
    (P("DM-01", 54, "male", "metformin", "500 mg", "once daily", None, "type2_diabetes", egfr=88, conditions=["type 2 diabetes"]), "GREEN", [], []),
    (P("DM-02", 71, "male", "metformin", "1 g", "twice daily", None, "type2_diabetes", egfr=26, conditions=["type 2 diabetes"]), "RED", ["PH-REN-002"], []),
    (P("DM-03", 68, "female", "pioglitazone", "15 mg", "once daily", None, "type2_diabetes", egfr=70,
       current_meds=["metformin"], conditions=["type 2 diabetes", "heart failure"]), "RED", ["PH-CON-001"], []),
    (P("DM-04", 83, "female", "glibenclamide", "5 mg", "once daily", None, "type2_diabetes", egfr=58, frail=True, falls_history=True,
       current_meds=["metformin"], conditions=["type 2 diabetes"]), "AMBER", ["GU-030", "DM-001"], []),
    (P("DM-05", 59, "male", "dapagliflozin", "10 mg", "once daily", None, "type2_diabetes", egfr=74, current_meds=["metformin"],
       conditions=["type 2 diabetes"], notes="Two days of vomiting and not eating."), "RED", ["DM-002"], []),
    (P("DM-06", 63, "female", "gliclazide", "40 mg", "once daily", None, "type2_diabetes", egfr=80, conditions=["type 2 diabetes"]),
     "AMBER", ["GU-010"], []),
    (P("DM-07", 66, "male", "insulin glargine", "10 units", "once daily", None, "type2_diabetes", egfr=65, dexterity_problem=True,
       current_meds=["metformin"], conditions=["type 2 diabetes", "rheumatoid arthritis"]), "RED", ["OT-003"], []),
    (P("DM-08", 57, "male", "sitagliptin", "100 mg", "once daily", None, "type2_diabetes", egfr=82, current_meds=["metformin"],
       conditions=["type 2 diabetes"]), "GREEN", [], []),
    (P("DM-09", 62, "male", "ibuprofen", "400 mg", "three times daily", 7, "other", egfr=64,
       current_meds=["ramipril", "furosemide", "metformin"], conditions=["type 2 diabetes"]), "RED", ["PH-INT-020"], []),
    # ---- cancer care
    (P("CA-01", 52, "female", "tamoxifen", "20 mg", "once daily", None, "cancer_care", egfr=90, current_meds=["paroxetine"],
       conditions=["breast cancer"]), "RED", ["PH-INT-005"], []),
    (P("CA-02", 64, "female", "methotrexate", "10 mg", "once daily", None, "cancer_care", egfr=80, conditions=["cancer"]),
     "RED", ["PH-DOS-001"], []),
    (P("CA-03", 70, "male", "morphine", "10 mg modified-release", "twice daily", None, "cancer_care", egfr=66,
       conditions=["prostate cancer"], current_meds=["paracetamol"]), "AMBER", ["PH-MON-001"], []),
    (P("CA-04", 70, "male", "morphine", "10 mg modified-release", "twice daily", None, "cancer_care", egfr=66,
       conditions=["prostate cancer"], current_meds=["paracetamol", "senna"]), "GREEN", [], []),
    (P("CA-05", 66, "female", "capecitabine", "1250 mg/m2", "twice daily", 14, "cancer_care", egfr=72, current_meds=["warfarin"],
       conditions=["bowel cancer"]), "RED", ["PH-INT-006"], []),
    (P("CA-06", 69, "female", "letrozole", "2.5 mg", "once daily", None, "cancer_care", egfr=77, conditions=["breast cancer", "osteoporosis"]),
     "AMBER", ["PH-CON-005", "GU-020"], []),
    (P("CA-07", 58, "male", "dexamethasone", "8 mg", "once daily", 5, "cancer_care", egfr=85, conditions=["lung cancer", "type 2 diabetes"],
       current_meds=["metformin"]), "AMBER", ["PH-CON-004"], []),
    # ---- side effects and clashes with existing medicines
    (P("SE-01", 56, "female", "ibuprofen", "400 mg", "three times daily", 5, "other", egfr=88, current_meds=["sertraline", "omeprazole"]),
     "AMBER", ["SE-000", "SE-010"], []),
    (P("SE-02", 79, "female", "morphine", "5 mg modified-release", "twice daily", None, "cancer_care", egfr=70, falls_history=True,
       conditions=["breast cancer"], current_meds=["diazepam", "tramadol", "senna", "amlodipine"]), "AMBER", ["PH-INT-014", "SE-010", "SE-020"], []),
    (P("SE-03", 61, "female", "nitrofurantoin", "100 mg modified-release", "twice daily", 3, "uti", egfr=82,
       current_meds=["metformin", "dapagliflozin"], conditions=["type 2 diabetes"]), "AMBER", ["SE-030"], []),
    (P("SE-04", 74, "male", "oxybutynin", "5 mg", "twice daily", None, "other", egfr=70, conditions=["enlarged prostate"],
       current_meds=["amlodipine"]), "AMBER", ["SE-024"], []),
    (P("SE-05", 68, "male", "gliclazide", "40 mg", "once daily", None, "type2_diabetes", egfr=75, conditions=["type 2 diabetes"],
       current_meds=["metformin", "bisoprolol"]), "GREEN", ["SE-027"], []),
    # ---- system behaviour
    (P("SY-01", 50, "female", "zzzmycin", "1 tablet", "once daily", 5, "other", egfr=90), "AMBER", ["PH-UNK-001"], []),
    (P("SY-02", 48, "male", "metformin", "500 mg", "once daily", None, "type2_diabetes", egfr=90, allergy_status_recorded=False,
       conditions=["type 2 diabetes"]), "AMBER", ["AL-000"], []),
]

_BY_REF = {c[0].ref: c[0] for c in SUITE}
PRESETS = {
    "Simple urine infection (no concerns)": _BY_REF["UTI-01"],
    "Older woman, reduced kidney function, nitrofurantoin requested": _BY_REF["UTI-02"],
    "Urine infection while taking methotrexate": _BY_REF["UTI-03"],
    "Man with repeat infections and blood in urine": _BY_REF["UTI-09"],
    "Fever during chemotherapy": _BY_REF["UTI-11"],
    "Every usual antibiotic blocked (hard stop)": _BY_REF["UTI-17"],
    "Diabetes: metformin with poor kidney function": _BY_REF["DM-02"],
    "Diabetes: frail 83-year-old, long-acting sulfonylurea": _BY_REF["DM-04"],
    "Breast cancer: tamoxifen with paroxetine": _BY_REF["CA-01"],
    "Cancer pain: morphine without a laxative": _BY_REF["CA-03"],
    "Methotrexate written as daily": _BY_REF["CA-02"],
    "Side effects add up: morphine with diazepam in a person who falls": _BY_REF["SE-02"],
    "Existing medicine may be causing the infections": _BY_REF["SE-03"],
}
