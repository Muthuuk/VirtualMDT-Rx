"""Illustrative knowledge base.

IMPORTANT: every rule here is a short PARAPHRASE written for a research
demonstrator. The set is small, incomplete and not kept up to date. It is not a
substitute for the BNF, the product information (SmPC), NICE guidance or local
formulary, and it must not be used for real prescribing. Before any clinical
pilot the content has to be replaced by licensed, maintained sources and signed
off by a pharmacist (see README, "Route to clinical use").

Rules are DATA, not code (SE principle 2: safety rules live outside any model).
A pharmacist can read and change this file without reading the agents.
"""
from __future__ import annotations

from typing import Dict, List

# --------------------------------------------------------------------------
# Drug catalogue: name -> classes and facts used by the rules.
# --------------------------------------------------------------------------
DRUGS: Dict[str, dict] = {
    # --- urinary tract infection (UTI) antibiotics ---
    "nitrofurantoin": {"cls": ["antibiotic"], "ind": ["uti"]},
    "trimethoprim": {"cls": ["antibiotic", "raises_potassium"], "ind": ["uti"]},
    "pivmecillinam": {"cls": ["antibiotic", "penicillin"], "ind": ["uti"]},
    "fosfomycin": {"cls": ["antibiotic"], "ind": ["uti"]},
    "cefalexin": {"cls": ["antibiotic", "cephalosporin"], "ind": ["uti"]},
    "amoxicillin": {"cls": ["antibiotic", "penicillin"], "ind": ["uti"]},
    "co-amoxiclav": {"cls": ["antibiotic", "penicillin"], "ind": ["uti"]},
    "ciprofloxacin": {"cls": ["antibiotic", "fluoroquinolone", "qt_prolonging"], "ind": ["uti"]},
    "co-trimoxazole": {"cls": ["antibiotic", "sulfonamide", "raises_potassium"], "ind": ["uti"]},
    "clarithromycin": {"cls": ["antibiotic", "macrolide", "qt_prolonging"], "ind": []},
    # --- type 2 diabetes ---
    "metformin": {"cls": ["biguanide"], "ind": ["type2_diabetes"]},
    "gliclazide": {"cls": ["sulfonylurea"], "ind": ["type2_diabetes"]},
    "glibenclamide": {"cls": ["sulfonylurea", "long_acting_sulfonylurea"], "ind": ["type2_diabetes"]},
    "dapagliflozin": {"cls": ["sglt2"], "ind": ["type2_diabetes"]},
    "empagliflozin": {"cls": ["sglt2"], "ind": ["type2_diabetes"]},
    "sitagliptin": {"cls": ["dpp4"], "ind": ["type2_diabetes"]},
    "linagliptin": {"cls": ["dpp4"], "ind": ["type2_diabetes"]},
    "pioglitazone": {"cls": ["glitazone"], "ind": ["type2_diabetes"]},
    "insulin glargine": {"cls": ["insulin"], "ind": ["type2_diabetes"]},
    "semaglutide": {"cls": ["glp1"], "ind": ["type2_diabetes"]},
    # --- cancer care (hormone treatment, shared-care and supportive medicines) ---
    "tamoxifen": {"cls": ["hormone_therapy"], "ind": ["cancer_care"]},
    "letrozole": {"cls": ["hormone_therapy", "aromatase_inhibitor"], "ind": ["cancer_care"]},
    "anastrozole": {"cls": ["hormone_therapy", "aromatase_inhibitor"], "ind": ["cancer_care"]},
    "methotrexate": {"cls": ["antifolate", "cytotoxic"], "ind": ["cancer_care"]},
    "capecitabine": {"cls": ["cytotoxic"], "ind": ["cancer_care"]},
    "morphine": {"cls": ["opioid"], "ind": ["cancer_care"]},
    "oxycodone": {"cls": ["opioid"], "ind": ["cancer_care"]},
    "ondansetron": {"cls": ["antiemetic", "qt_prolonging"], "ind": ["cancer_care"]},
    "dexamethasone": {"cls": ["steroid"], "ind": ["cancer_care"]},
    "metoclopramide": {"cls": ["antiemetic"], "ind": ["cancer_care"]},
    # --- common medicines a patient may already take ---
    "warfarin": {"cls": ["anticoagulant", "vitamin_k_antagonist"]},
    "apixaban": {"cls": ["anticoagulant"]},
    "ramipril": {"cls": ["acei_arb"]},
    "lisinopril": {"cls": ["acei_arb"]},
    "losartan": {"cls": ["acei_arb"]},
    "spironolactone": {"cls": ["diuretic", "raises_potassium"]},
    "furosemide": {"cls": ["diuretic"]},
    "bendroflumethiazide": {"cls": ["diuretic"]},
    "ibuprofen": {"cls": ["nsaid"]},
    "naproxen": {"cls": ["nsaid"]},
    "simvastatin": {"cls": ["statin", "statin_cyp3a4"]},
    "atorvastatin": {"cls": ["statin"]},
    "paroxetine": {"cls": ["ssri", "strong_cyp2d6_inhibitor"]},
    "fluoxetine": {"cls": ["ssri", "strong_cyp2d6_inhibitor"]},
    "sertraline": {"cls": ["ssri"]},
    "citalopram": {"cls": ["ssri", "qt_prolonging"]},
    "tramadol": {"cls": ["opioid", "serotonergic"]},
    "prednisolone": {"cls": ["steroid"]},
    "oxybutynin": {"cls": ["anticholinergic"]},
    "diazepam": {"cls": ["benzodiazepine"]},
    "lithium": {"cls": ["lithium"]},
    "digoxin": {"cls": []},
    "amlodipine": {"cls": []},
    "bisoprolol": {"cls": []},
    "omeprazole": {"cls": []},
    "levothyroxine": {"cls": []},
    "alendronic acid": {"cls": ["bone_protection"]},
    "paracetamol": {"cls": []},
    "senna": {"cls": ["laxative"]},
    "macrogol": {"cls": ["laxative"]},
    "lactulose": {"cls": ["laxative"]},
}

ALIASES = {
    "cephalexin": "cefalexin", "coamoxiclav": "co-amoxiclav", "cotrimoxazole": "co-trimoxazole",
    "insulin": "insulin glargine", "alendronate": "alendronic acid", "glyburide": "glibenclamide",
    "acetaminophen": "paracetamol",
}


def normalise(name: str) -> str:
    """Turn 'Metformin 500mg tablets' into 'metformin'. Unknown names are returned
    lower-cased so the caller can flag them (an unknown drug is never silently passed)."""
    n = (name or "").strip().lower()
    if not n:
        return ""
    for key in sorted(DRUGS, key=len, reverse=True):
        if n.startswith(key):
            return key
    first = n.split()[0].replace(",", "")
    if first in ALIASES:
        return ALIASES[first]
    for alias, target in ALIASES.items():
        if n.startswith(alias):
            return target
    return n


def classes(name: str) -> List[str]:
    return DRUGS.get(normalise(name), {}).get("cls", [])


def known(name: str) -> bool:
    return normalise(name) in DRUGS


def matches(name: str, token: str) -> bool:
    """token is either a drug name or 'cls:<class>'."""
    n = normalise(name)
    if token.startswith("cls:"):
        return token[4:] in classes(n)
    return n == token


# --------------------------------------------------------------------------
# Interactions: proposed drug (a) against a current medicine (b), or the reverse.
# --------------------------------------------------------------------------
INTERACTIONS = [
    {"id": "PH-INT-001", "a": "trimethoprim", "b": "methotrexate", "level": "RED",
     "title": "Trimethoprim with methotrexate",
     "detail": "Both block folate. Together they can dangerously lower blood cell counts. Avoid; choose another antibiotic.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-001", "a": "co-trimoxazole", "b": "methotrexate", "level": "RED",
     "title": "Co-trimoxazole with methotrexate",
     "detail": "Both block folate. Together they can dangerously lower blood cell counts. Avoid.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-002", "a": "cls:raises_potassium", "b": "cls:acei_arb", "level": "AMBER",
     "title": "Risk of high potassium",
     "detail": "This medicine and an ACE inhibitor/ARB both raise potassium. Risk is higher in older people and with reduced kidney function. Check potassium or choose another option.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-002", "a": "trimethoprim", "b": "spironolactone", "level": "AMBER",
     "title": "Risk of high potassium",
     "detail": "Trimethoprim with spironolactone can raise potassium. Check potassium or choose another antibiotic.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-003", "a": "cls:nsaid", "b": "cls:anticoagulant", "level": "RED",
     "title": "Anti-inflammatory with an anticoagulant",
     "detail": "Raises the risk of serious bleeding. Avoid the combination.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-004", "a": "cls:macrolide", "b": "cls:statin_cyp3a4", "level": "RED",
     "title": "Clarithromycin with simvastatin",
     "detail": "Clarithromycin raises simvastatin levels and the risk of muscle damage. The combination is contraindicated; pause the statin or use another antibiotic.",
     "source": "MHRA drug safety advice; BNF (paraphrased)"},
    {"id": "PH-INT-005", "a": "tamoxifen", "b": "cls:strong_cyp2d6_inhibitor", "level": "RED",
     "title": "Antidepressant may weaken tamoxifen",
     "detail": "Paroxetine and fluoxetine block the enzyme that activates tamoxifen, which may reduce its benefit. Avoid where possible; discuss an alternative antidepressant.",
     "source": "MHRA drug safety advice (paraphrased)"},
    {"id": "PH-INT-006", "a": "capecitabine", "b": "warfarin", "level": "RED",
     "title": "Capecitabine with warfarin",
     "detail": "Can markedly increase the effect of warfarin and cause bleeding. Needs oncology and anticoagulation advice before prescribing.",
     "source": "Product information; BNF (paraphrased)"},
    {"id": "PH-INT-007", "a": "cls:antibiotic", "b": "warfarin", "level": "AMBER",
     "title": "Antibiotic may change warfarin effect",
     "detail": "Antibiotics can alter the INR. Arrange an INR check during and after the course.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-008", "a": "methotrexate", "b": "cls:nsaid", "level": "AMBER",
     "title": "Anti-inflammatory with methotrexate",
     "detail": "Anti-inflammatories can reduce methotrexate clearance. Monitor blood counts and kidney function.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-009", "a": "cls:serotonergic", "b": "cls:ssri", "level": "AMBER",
     "title": "Tramadol with an SSRI antidepressant",
     "detail": "Raises the risk of serotonin syndrome and seizures. Consider another pain medicine.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-010", "a": "cls:qt_prolonging", "b": "cls:qt_prolonging", "level": "AMBER",
     "title": "Two medicines that affect heart rhythm",
     "detail": "Both can lengthen the QT interval. Consider an ECG or an alternative.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-011", "a": "cls:steroid", "b": "cls:fluoroquinolone", "level": "AMBER",
     "title": "Steroid with a fluoroquinolone",
     "detail": "Raises the risk of tendon damage, especially over 60. Avoid if another antibiotic is suitable.",
     "source": "MHRA drug safety advice (paraphrased)"},
    {"id": "PH-INT-012", "a": "cls:nsaid", "b": "lithium", "level": "RED",
     "title": "Anti-inflammatory with lithium",
     "detail": "Can raise lithium to toxic levels. Avoid, or monitor lithium closely under specialist advice.",
     "source": "BNF interactions (paraphrased)"},
    {"id": "PH-INT-013", "a": "cls:sulfonylurea", "b": "cls:insulin", "level": "AMBER",
     "title": "Two medicines that can cause low blood sugar",
     "detail": "Sulfonylurea with insulin increases the risk of hypoglycaemia. Review doses and glucose monitoring.",
     "source": "NICE NG28 (paraphrased)"},
]

# --------------------------------------------------------------------------
# Kidney function (eGFR) rules for the proposed medicine.
# --------------------------------------------------------------------------
RENAL = [
    {"id": "PH-REN-001", "drug": "nitrofurantoin", "below": 45, "level": "RED",
     "title": "Nitrofurantoin with reduced kidney function",
     "detail": "Avoid if eGFR is below 45: it may not work and side effects rise. (A short course at eGFR 30-44 is only for resistant infections when benefit outweighs risk.)",
     "source": "BNF; NICE NG109 (paraphrased)"},
    {"id": "PH-REN-002", "drug": "metformin", "below": 30, "level": "RED",
     "title": "Metformin with eGFR below 30",
     "detail": "Avoid: risk of lactic acidosis.", "source": "BNF; NICE NG28 (paraphrased)"},
    {"id": "PH-REN-003", "drug": "metformin", "below": 45, "level": "AMBER",
     "title": "Metformin with eGFR below 45",
     "detail": "Review the dose and monitor kidney function.", "source": "BNF; NICE NG28 (paraphrased)"},
    {"id": "PH-REN-004", "drug": "trimethoprim", "below": 30, "level": "AMBER",
     "title": "Trimethoprim with eGFR below 30",
     "detail": "Dose reduction is needed; check potassium.", "source": "BNF (paraphrased)"},
    {"id": "PH-REN-005", "drug": "cls:nsaid", "below": 30, "level": "RED",
     "title": "Anti-inflammatory with eGFR below 30",
     "detail": "Avoid: risk of further kidney damage.", "source": "BNF (paraphrased)"},
    {"id": "PH-REN-006", "drug": "cls:sglt2", "below": 45, "level": "AMBER",
     "title": "SGLT2 inhibitor with eGFR below 45",
     "detail": "Blood-sugar lowering is reduced at this kidney function; check the indication and product advice.",
     "source": "Product information (paraphrased)"},
    {"id": "PH-REN-007", "drug": "morphine", "below": 30, "level": "AMBER",
     "title": "Morphine with eGFR below 30",
     "detail": "Morphine by-products build up. Reduce the dose or consider another opioid on specialist advice.",
     "source": "BNF; palliative care guidance (paraphrased)"},
    {"id": "PH-REN-008", "drug": "sitagliptin", "below": 45, "level": "AMBER",
     "title": "Sitagliptin with eGFR below 45",
     "detail": "A lower dose is needed.", "source": "BNF (paraphrased)"},
]

# --------------------------------------------------------------------------
# Condition contraindications for the proposed medicine.
# --------------------------------------------------------------------------
CONDITION_RULES = [
    {"id": "PH-CON-001", "drug": "pioglitazone", "condition": "heart failure", "level": "RED",
     "title": "Pioglitazone with heart failure", "detail": "Contraindicated: can worsen fluid retention.",
     "source": "MHRA; BNF (paraphrased)"},
    {"id": "PH-CON-002", "drug": "pioglitazone", "condition": "bladder cancer", "level": "RED",
     "title": "Pioglitazone with a history of bladder cancer", "detail": "Contraindicated.",
     "source": "MHRA; BNF (paraphrased)"},
    {"id": "PH-CON-003", "drug": "cls:nsaid", "condition": "heart failure", "level": "RED",
     "title": "Anti-inflammatory with heart failure", "detail": "Avoid: can worsen heart failure.",
     "source": "BNF (paraphrased)"},
    {"id": "PH-CON-004", "drug": "cls:steroid", "condition": "type 2 diabetes", "level": "AMBER",
     "title": "Steroid in a person with diabetes",
     "detail": "Steroids raise blood sugar. Agree a glucose-monitoring plan.", "source": "JBDS guidance (paraphrased)"},
    {"id": "PH-CON-005", "drug": "cls:aromatase_inhibitor", "condition": "osteoporosis", "level": "AMBER",
     "title": "Aromatase inhibitor with osteoporosis",
     "detail": "These medicines thin the bones. Check bone density and bone protection.",
     "source": "NICE NG101 (paraphrased)"},
    {"id": "PH-CON-006", "drug": "cls:sglt2", "condition": "recurrent uti", "level": "AMBER",
     "title": "SGLT2 inhibitor with recurrent urine infections",
     "detail": "These medicines increase sugar in the urine and genital/urinary infections are more common. Weigh benefit and risk.",
     "source": "Product information (paraphrased)"},
    {"id": "PH-CON-007", "drug": "metoclopramide", "condition": "parkinson's disease", "level": "RED",
     "title": "Metoclopramide with Parkinson's disease", "detail": "Avoid: worsens movement symptoms.",
     "source": "BNF (paraphrased)"},
]

PREGNANCY = [
    {"id": "PH-PRG-001", "drug": "trimethoprim", "trimester": 1, "level": "RED",
     "title": "Trimethoprim in early pregnancy",
     "detail": "Avoid in the first trimester (it blocks folate).", "source": "BNF; NICE NG109 (paraphrased)"},
    {"id": "PH-PRG-002", "drug": "nitrofurantoin", "trimester": 3, "level": "AMBER",
     "title": "Nitrofurantoin near term",
     "detail": "Avoid at term because of a risk to the newborn's red blood cells.", "source": "BNF; NICE NG109 (paraphrased)"},
    {"id": "PH-PRG-003", "drug": "methotrexate", "trimester": None, "level": "RED",
     "title": "Methotrexate in pregnancy", "detail": "Contraindicated.", "source": "BNF (paraphrased)"},
    {"id": "PH-PRG-004", "drug": "tamoxifen", "trimester": None, "level": "RED",
     "title": "Tamoxifen in pregnancy", "detail": "Avoid.", "source": "BNF (paraphrased)"},
    {"id": "PH-PRG-005", "drug": "cls:fluoroquinolone", "trimester": None, "level": "RED",
     "title": "Fluoroquinolone in pregnancy", "detail": "Avoid.", "source": "BNF (paraphrased)"},
    {"id": "PH-PRG-006", "drug": "cls:nsaid", "trimester": 3, "level": "RED",
     "title": "Anti-inflammatory in late pregnancy", "detail": "Avoid in the third trimester.",
     "source": "BNF (paraphrased)"},
]

# --------------------------------------------------------------------------
# Allergy cross-reactivity.
# --------------------------------------------------------------------------
ALLERGY_RULES = [
    {"id": "AL-001", "allergy": "penicillin", "drug": "cls:penicillin", "level": "RED",
     "title": "Penicillin allergy: this medicine is a penicillin",
     "detail": "Contraindicated in true penicillin allergy.", "source": "BNF (paraphrased)"},
    {"id": "AL-002", "allergy": "penicillin", "drug": "cls:cephalosporin", "level": "AMBER",
     "title": "Penicillin allergy: possible cross-reaction with cephalosporins",
     "detail": "Avoid if the penicillin reaction was immediate or severe; otherwise use with caution.",
     "source": "BNF (paraphrased)"},
    {"id": "AL-003", "allergy": "sulfonamide", "drug": "cls:sulfonamide", "level": "RED",
     "title": "Sulfonamide allergy: this medicine contains a sulfonamide",
     "detail": "Contraindicated.", "source": "BNF (paraphrased)"},
    {"id": "AL-004", "allergy": "nsaid", "drug": "cls:nsaid", "level": "RED",
     "title": "Allergy to anti-inflammatories", "detail": "Contraindicated.", "source": "BNF (paraphrased)"},
    {"id": "AL-005", "allergy": "trimethoprim", "drug": "trimethoprim", "level": "RED",
     "title": "Recorded trimethoprim allergy", "detail": "Contraindicated.", "source": "Allergy record"},
    {"id": "AL-005", "allergy": "trimethoprim", "drug": "co-trimoxazole", "level": "RED",
     "title": "Trimethoprim allergy: co-trimoxazole contains trimethoprim", "detail": "Contraindicated.",
     "source": "Allergy record"},
    {"id": "AL-006", "allergy": "nitrofurantoin", "drug": "nitrofurantoin", "level": "RED",
     "title": "Recorded nitrofurantoin allergy", "detail": "Contraindicated.", "source": "Allergy record"},
]
SEVERE_REACTIONS = {"anaphylaxis", "angioedema", "severe rash", "sjs", "dress"}

# --------------------------------------------------------------------------
# Guideline summaries (illustrative, paraphrased).
# --------------------------------------------------------------------------
GUIDELINES = {
    "uti": {
        "name": "NICE NG109 lower urinary tract infection (paraphrased summary)",
        "first_line": ["nitrofurantoin", "trimethoprim"],
        "second_line": ["pivmecillinam", "fosfomycin"],
        "duration": {"female": 3, "male": 7, "pregnant": 7},
        "regimen": {
            "nitrofurantoin": ("100 mg modified-release", "twice daily"),
            "trimethoprim": ("200 mg", "twice daily"),
            "pivmecillinam": ("400 mg first dose then 200 mg", "three times daily"),
            "fosfomycin": ("3 g", "single dose"),
        },
    },
    "type2_diabetes": {
        "name": "NICE NG28 type 2 diabetes in adults (paraphrased summary)",
        "first_line": ["metformin"],
        "second_line": ["dapagliflozin", "empagliflozin", "sitagliptin", "linagliptin", "gliclazide"],
        "regimen": {
            "metformin": ("500 mg, increased gradually", "once daily"),
            "linagliptin": ("5 mg", "once daily"),
            "sitagliptin": ("100 mg (lower if kidney function is reduced)", "once daily"),
            "gliclazide": ("40-80 mg", "once daily"),
            "dapagliflozin": ("10 mg", "once daily"),
            "empagliflozin": ("10 mg", "once daily"),
        },
    },
    "cancer_care": {
        "name": "Shared-care and supportive-care guidance (paraphrased summary)",
        "first_line": [], "second_line": [], "regimen": {},
    },
}

# Medicines that should normally be started or changed only by, or with, a specialist.
SPECIALIST_INITIATED = {"tamoxifen", "letrozole", "anastrozole", "methotrexate", "capecitabine"}

# Combination or simpler options the optimisation layer may suggest (availability must be checked).
COMBINATIONS = [
    ({"metformin", "sitagliptin"}, "A combined metformin + sitagliptin tablet exists and could cut the number of tablets."),
    ({"metformin", "dapagliflozin"}, "A combined metformin + dapagliflozin tablet exists and could cut the number of tablets."),
    ({"metformin", "empagliflozin"}, "A combined metformin + empagliflozin tablet exists and could cut the number of tablets."),
    ({"metformin", "linagliptin"}, "A combined metformin + linagliptin tablet exists and could cut the number of tablets."),
]
ONCE_DAILY_OPTION = {
    "metformin": "A modified-release metformin taken once daily may be easier to take and gentler on the stomach.",
}

# Demo supply feed. Empty on purpose: we do not invent shortages. A real deployment
# would read the NHS supply and MHRA shortage feeds at run time (paper, section 3.2).
SUPPLY_ALERTS: Dict[str, str] = {}

# Free-text phrases screened by the orchestrator's triage pass.
TRIAGE_PHRASES = {
    "visible_haematuria": ["blood in urine", "blood in the urine", "visible haematuria", "haematuria", "hematuria", "red urine"],
    "fever": ["fever", "febrile", "temperature of 38", "rigors", "shivering"],
    "rash": ["rash", "blistering", "skin peeling", "mouth ulcers"],
    "confusion": ["confused", "confusion", "delirium"],
    "flank_pain": ["flank pain", "loin pain"],
    "sick_day": ["vomiting", "not eating", "dehydrated", "diarrhoea"],
}
NEGATIONS = ["no ", "not ", "denies ", "without ", "nil "]
