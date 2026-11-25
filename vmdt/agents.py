"""The virtual experts.

Each expert is a small, single-purpose function (SE principle 3: one agent, one
job). It receives ONLY the fields listed in its SCOPE (the paper's "task-scoped
context window") and returns a list of findings. Experts never see each other's
output while they run.

Why rules and not a large language model? The inputs are short, structured
facts, the answers must repeat exactly, and a clinician must be able to read the
reason. A language model can be plugged into any slot later (same input/output
contract) once it has been evaluated; it should be used where language is the
problem, not to decide safety.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from . import knowledge as kb
from .models import AMBER, FREQ_PER_DAY, INFO, RED, Finding


def F(code, level, signal, title, detail, source) -> Finding:
    return Finding(code=code, level=level, signal=signal, title=title, detail=detail, source=source)


def _has_condition(p: dict, name: str) -> bool:
    return any(name in c.lower() for c in p.get("conditions", []))


# ---------------------------------------------------------------- core five
def pharmacist(p: dict) -> List[Finding]:
    """Interactions, dose for kidney function and age, duplicates, monitoring."""
    out: List[Finding] = []
    drug = kb.normalise(p["proposal"]["drug"])
    meds = [kb.normalise(m) for m in p.get("current_meds", []) if m.strip()]

    if not kb.known(drug):
        out.append(F("PH-UNK-001", AMBER, "data_gap", f"'{drug}' is not in the demo knowledge base",
                     "No automated checks were possible for this medicine. Review it manually.", "System"))
    for m in meds:
        if not kb.known(m):
            out.append(F("PH-UNK-002", AMBER, "data_gap", f"Current medicine '{m}' is not in the demo knowledge base",
                         "Interactions with this medicine were NOT checked. Review manually.", "System"))

    seen = set()
    for rule in kb.INTERACTIONS:
        for m in meds:
            if m == drug:
                continue
            hit = (kb.matches(drug, rule["a"]) and kb.matches(m, rule["b"])) or \
                  (kb.matches(drug, rule["b"]) and kb.matches(m, rule["a"]))
            if hit and (rule["id"], m) not in seen:
                seen.add((rule["id"], m))
                out.append(F(rule["id"], rule["level"], "interaction", f"{rule['title']} ({drug} + {m})",
                             rule["detail"], rule["source"]))

    # "Triple whammy": anti-inflammatory + ACE inhibitor/ARB + diuretic.
    everything = meds + [drug]
    if all(any(c in kb.classes(x) for x in everything) for c in ("nsaid", "acei_arb", "diuretic")) \
            and any(c in kb.classes(drug) for c in ("nsaid", "acei_arb", "diuretic")):
        out.append(F("PH-INT-020", RED, "interaction", "Anti-inflammatory + ACE inhibitor/ARB + diuretic",
                     "This three-way combination can cause sudden kidney injury. Avoid.", "MHRA/NICE AKI guidance (paraphrased)"))

    egfr = p.get("egfr")
    renal_rules = [r for r in kb.RENAL if kb.matches(drug, r["drug"])]
    if egfr is None:
        if renal_rules:
            out.append(F("PH-REN-000", AMBER, "data_gap", "No recent kidney function (eGFR) on record",
                         f"The dose or safety of {drug} depends on kidney function. Check eGFR before prescribing.", "System"))
    else:
        fired = [r for r in renal_rules if egfr < r["below"]]
        if fired:  # keep only the strictest rule for this medicine
            r = min(fired, key=lambda r: r["below"])
            out.append(F(r["id"], r["level"], "dosing", f"{r['title']} (eGFR {egfr:g})", r["detail"], r["source"]))

    for r in kb.CONDITION_RULES:
        if kb.matches(drug, r["drug"]) and _has_condition(p, r["condition"]):
            out.append(F(r["id"], r["level"], "contraindication", r["title"], r["detail"], r["source"]))

    if p.get("pregnant"):
        for r in kb.PREGNANCY:
            if kb.matches(drug, r["drug"]) and (r["trimester"] is None or r["trimester"] == p.get("trimester")):
                out.append(F(r["id"], r["level"], "contraindication", r["title"], r["detail"], r["source"]))

    # Methotrexate must be weekly. A daily instruction is a well-known cause of fatal error.
    if drug == "methotrexate" and p["proposal"].get("frequency") != "once weekly":
        out.append(F("PH-DOS-001", RED, "dosing", "Methotrexate must be taken ONCE A WEEK",
                     f"The request says '{p['proposal'].get('frequency')}'. Daily dosing has caused deaths. Correct the frequency and state the day of the week.",
                     "MHRA drug safety advice; NHS never-event guidance (paraphrased)"))

    # Duplicate treatment: same medicine or same class already being taken.
    if drug in meds:
        out.append(F("PH-DUP-001", AMBER, "dosing", f"{drug} is already on the medicine list",
                     "Check this is a dose change and not a duplicate.", "Medication record"))
    for cls, label in (("nsaid", "anti-inflammatories"), ("ssri", "SSRI antidepressants"), ("acei_arb", "ACE inhibitors/ARBs"),
                       ("sulfonylurea", "sulfonylureas"), ("sglt2", "SGLT2 inhibitors"), ("dpp4", "gliptins"), ("opioid", "opioids")):
        if cls in kb.classes(drug) and any(cls in kb.classes(m) for m in meds if m != drug):
            out.append(F("PH-DUP-002", AMBER, "dosing", f"Two {label} together",
                         "Two medicines from the same group add side effects without much extra benefit. Check this is intended.",
                         "BNF (paraphrased)"))

    if "opioid" in kb.classes(drug) and not any("laxative" in kb.classes(m) for m in meds):
        out.append(F("PH-MON-001", AMBER, "guideline", "Regular opioid without a laxative",
                     "Constipation is almost universal with regular opioids. Co-prescribe a laxative.",
                     "NICE CG140; STOPP criteria (paraphrased)"))
    if "sglt2" in kb.classes(drug):
        out.append(F("PH-MON-002", INFO, "guideline", "Give 'sick day' advice",
                     "Tell the patient to pause this medicine when vomiting, dehydrated or not eating (risk of ketoacidosis).",
                     "MHRA drug safety advice (paraphrased)"))
    if drug in kb.SUPPLY_ALERTS:
        out.append(F("PH-SUP-001", AMBER, "supply", f"Supply problem reported for {drug}", kb.SUPPLY_ALERTS[drug], "Supply feed"))
    return out


def ptot(p: dict) -> List[Finding]:
    """Physiotherapy / occupational therapy view: can this person actually take it as prescribed?"""
    out: List[Finding] = []
    drug = kb.normalise(p["proposal"]["drug"])
    freq = p["proposal"].get("frequency", "once daily")
    n_meds = len([m for m in p.get("current_meds", []) if m.strip()]) + 1
    per_day = FREQ_PER_DAY.get(freq, 1)

    if p.get("cognitive_impairment") and per_day >= 3:
        out.append(F("OT-001", RED, "deliverability", "Dosing schedule too complex for this person to manage alone",
                     f"Memory or thinking problems are recorded and the request is '{freq}' on top of {n_meds - 1} other medicines. Choose a once- or twice-daily option, or arrange a carer, reminders or a pharmacy-filled pack first.",
                     "Patient profile; NICE NG5 medicines optimisation (paraphrased)"))
    elif p.get("cognitive_impairment"):
        out.append(F("OT-002", AMBER, "deliverability", "Memory or thinking problems recorded",
                     "Check who helps with medicines; consider a pharmacy-filled pack or reminders.", "Patient profile"))
    if p.get("dexterity_problem") and ("insulin" in kb.classes(drug) or "glp1" in kb.classes(drug)):
        out.append(F("OT-003", RED, "deliverability", "Injection device with poor hand function",
                     "Hand or grip problems are recorded. Confirm the person (or a carer) can use the pen safely before prescribing.",
                     "Patient profile"))
    elif p.get("dexterity_problem"):
        out.append(F("OT-004", AMBER, "deliverability", "Hand or grip problems recorded",
                     "Ask the pharmacy for easy-open containers; avoid small tablets and fiddly packs.", "Patient profile"))
    if p.get("visual_impairment") and ("insulin" in kb.classes(drug)):
        out.append(F("OT-005", AMBER, "deliverability", "Insulin with poor eyesight",
                     "Check the person can read the dose dial; consider a pen with audible clicks or carer support.", "Patient profile"))
    if p.get("swallowing_difficulty"):
        out.append(F("OT-006", AMBER, "deliverability", "Swallowing difficulty recorded",
                     "Check a liquid or dispersible form is available. Modified-release tablets must not be crushed.",
                     "Patient profile; BNF (paraphrased)"))
    if p.get("falls_history") and any(c in kb.classes(drug) for c in ("opioid", "benzodiazepine", "sulfonylurea")):
        out.append(F("OT-007", AMBER, "deliverability", "History of falls",
                     "This medicine can cause drowsiness, dizziness or low blood sugar and may raise the risk of falls.",
                     "STOPP criteria (paraphrased)"))
    if per_day >= 4 and not p.get("cognitive_impairment"):
        out.append(F("OT-008", INFO, "deliverability", "Four-times-a-day dosing is hard to keep up",
                     "A twice-daily or once-daily option, if one exists, is usually taken more reliably.", "Adherence evidence (general)"))
    return out


def allergy_safety(p: dict) -> List[Finding]:
    """Cross-reactivity, true allergy versus intolerance, record gaps."""
    out: List[Finding] = []
    drug = kb.normalise(p["proposal"]["drug"])
    if not p.get("allergy_status_recorded", True):
        out.append(F("AL-000", AMBER, "data_gap", "Allergy status is not recorded",
                     "Ask about allergies and update the record before prescribing.", "Allergy record"))
    for a in p.get("allergies", []):
        sub, reaction = a["substance"].strip().lower(), a.get("reaction", "unknown").strip().lower()
        for r in kb.ALLERGY_RULES:
            if r["allergy"] in sub and kb.matches(drug, r["drug"]):
                level, detail = r["level"], r["detail"]
                if reaction == "intolerance":
                    level = AMBER
                    detail = ("The record describes an intolerance (a side effect such as nausea), not a true allergy. "
                              "Confirm with the patient; if it was only a side effect the medicine may still be an option.")
                elif r["level"] == AMBER and reaction in kb.SEVERE_REACTIONS:
                    level = RED
                    detail = f"The previous reaction was severe ({reaction}). Avoid medicines that can cross-react."
                out.append(F(r["id"], level, "allergy", r["title"], f"{detail} Recorded reaction: {reaction}.", r["source"]))
    if "rash" in p.get("triage", []) and p.get("current_meds"):
        out.append(F("AL-010", AMBER, "safety_signal", "New rash, blistering or mouth ulcers mentioned in the notes",
                     "This could be a delayed drug reaction to a current medicine. Examine before adding another medicine.",
                     "Free-text triage; MHRA Yellow Card guidance (general)"))
    return out


def guidance(p: dict) -> List[Finding]:
    """Match to national guidance; structured checks for older adults."""
    out: List[Finding] = []
    prop = p["proposal"]
    drug, ind = kb.normalise(prop["drug"]), prop.get("indication", "other")
    g = kb.GUIDELINES.get(ind)
    meds = [kb.normalise(m) for m in p.get("current_meds", [])]

    if g and ind == "uti":
        expected = g["duration"]["pregnant" if p.get("pregnant") else p.get("sex", "female")]
        if drug not in g["first_line"] + g["second_line"]:
            out.append(F("GU-001", AMBER, "guideline", f"{drug} is not a usual first or second choice for a lower urine infection",
                         f"Usual first choices: {', '.join(g['first_line'])}. Second choices: {', '.join(g['second_line'])}. Check culture results or local advice.",
                         g["name"]))
        d = prop.get("duration_days")
        if d and drug != "fosfomycin" and d != expected:
            out.append(F("GU-002", AMBER, "guideline", f"Course length is {d} days; the usual length here is {expected} days",
                         "Longer courses add side effects and resistance; shorter ones may fail. Check this is intended.", g["name"]))
        if "fluoroquinolone" in kb.classes(drug):
            out.append(F("GU-003", AMBER, "guideline", "Fluoroquinolone restrictions apply",
                         "Use only when other commonly recommended antibiotics are inappropriate, because of rare but disabling side effects.",
                         "MHRA drug safety advice (paraphrased)"))
    if g and ind == "type2_diabetes":
        if drug != "metformin" and "metformin" not in meds and (p.get("egfr") is None or p["egfr"] >= 30):
            out.append(F("GU-010", AMBER, "guideline", "Metformin is the usual first medicine",
                         "No metformin is recorded and no reason against it was found. Check whether it was tried or not tolerated.", g["name"]))
        if drug in ("metformin", "gliclazide", "sitagliptin", "linagliptin") and \
                any(_has_condition(p, c) for c in ("heart failure", "chronic kidney disease", "cardiovascular disease")) and \
                not any("sglt2" in kb.classes(m) for m in meds):
            out.append(F("GU-011", INFO, "guideline", "Consider an SGLT2 inhibitor for heart or kidney protection",
                         "Guidance suggests offering one in people with heart failure, heart disease or kidney disease, if suitable.", g["name"]))
    if drug in kb.SPECIALIST_INITIATED:
        out.append(F("GU-020", AMBER if ind == "cancer_care" else AMBER, "guideline",
                     f"{drug} is normally started or changed by a specialist",
                     "Check there is a shared-care agreement and that blood monitoring is up to date before continuing in primary care.",
                     "Shared-care guidance (paraphrased)"))

    if p.get("age", 0) >= 65:  # STOPP/START-style checks (illustrative subset)
        if "long_acting_sulfonylurea" in kb.classes(drug):
            out.append(F("GU-030", AMBER, "guideline", "Long-acting sulfonylurea in an older adult",
                         "Higher risk of prolonged low blood sugar. A shorter-acting option is preferred.", "STOPP/START v3 (paraphrased)"))
        if "anticholinergic" in kb.classes(drug) and (p.get("cognitive_impairment") or _has_condition(p, "dementia")):
            out.append(F("GU-031", RED, "contraindication", "Anticholinergic bladder medicine with memory problems",
                         "Can worsen confusion. Avoid; consider a non-anticholinergic option.", "STOPP/START v3 (paraphrased)"))
        if "benzodiazepine" in kb.classes(drug) and p.get("falls_history"):
            out.append(F("GU-032", AMBER, "guideline", "Benzodiazepine in an older adult who falls",
                         "Raises the risk of falls and fractures.", "STOPP/START v3 (paraphrased)"))
        if "nsaid" in kb.classes(drug) and p.get("egfr") is not None and p["egfr"] < 50:
            out.append(F("GU-033", AMBER, "guideline", "Anti-inflammatory with reduced kidney function in an older adult",
                         "Risk of worsening kidney function.", "STOPP/START v3 (paraphrased)"))
        if "steroid" in kb.classes(drug) and not any("bone_protection" in kb.classes(m) for m in meds) \
                and (prop.get("duration_days") or 0) >= 90:
            out.append(F("GU-034", AMBER, "guideline", "Long steroid course without bone protection",
                         "Consider bone protection for courses of three months or more.", "STOPP/START v3 (paraphrased)"))
    return out


def literature(p: dict) -> List[Finding]:
    """Latest evidence. Off by default; when switched on it searches PubMed with the
    medicine and condition names only (never patient details) under a fixed time budget."""
    if not p.get("live_evidence"):
        return [F("LI-000", INFO, "evidence", "Live evidence search is switched off",
                  "Tick 'Search PubMed' to list recent safety papers. Only the medicine name and condition are sent.", "System")]
    from .opendata import pubmed_recent
    drug = kb.normalise(p["proposal"]["drug"])
    papers, note = pubmed_recent(drug, p["proposal"].get("indication", ""))
    if not papers:
        return [F("LI-001", INFO, "evidence", "No live evidence returned", note, "PubMed (NCBI E-utilities)")]
    lines = "; ".join(f"{t} (PMID {pmid}, {year})" for pmid, t, year in papers)
    return [F("LI-002", INFO, "evidence", f"{len(papers)} recent safety papers found for {drug}",
              f"Titles only, not graded or summarised, for the clinician to read: {lines}", "PubMed (NCBI E-utilities)")]


# ------------------------------------------------------- consultants on call
def microbiology(p: dict) -> List[Finding]:
    out: List[Finding] = []
    drug = kb.normalise(p["proposal"]["drug"])
    if "antibiotic" not in kb.classes(drug):
        return out
    if drug in [kb.normalise(x) for x in p.get("culture_resistant_to", [])]:
        out.append(F("MB-001", RED, "stewardship", f"Recent urine culture shows resistance to {drug}",
                     "This antibiotic is unlikely to work. Choose one the organism is sensitive to.", "Culture result on record"))
    if p.get("uti_courses_6m", 0) >= 2:
        out.append(F("MB-002", AMBER, "stewardship", f"{p['uti_courses_6m']} antibiotic courses for urine infection in 6 months",
                     "Send a urine culture before treating, review past results, and consider why infections keep returning.",
                     "NICE NG112 recurrent UTI (paraphrased)"))
    return out


def urology(p: dict) -> List[Finding]:
    out: List[Finding] = []
    if "visible_haematuria" in p.get("triage", []) and p.get("age", 0) >= 45:
        out.append(F("UR-001", RED, "red_flag", "Visible blood in the urine, aged 45 or over",
                     "If there is no infection, or bleeding continues after treatment, this needs an urgent suspected-cancer referral, not repeat antibiotics.",
                     "NICE NG12 suspected cancer (paraphrased)"))
    if p.get("sex") == "male" and p.get("uti_courses_6m", 0) >= 2:
        out.append(F("UR-002", AMBER, "red_flag", "Recurrent urine infection in a man",
                     "Consider referral to look for an underlying cause.", "NICE NG112 (paraphrased)"))
    if "flank_pain" in p.get("triage", []) and "fever" in p.get("triage", []):
        out.append(F("UR-003", RED, "red_flag", "Fever with loin pain",
                     "This suggests a kidney infection, not a simple bladder infection. A lower-UTI course is not enough; assess for same-day treatment or admission.",
                     "NICE NG111 pyelonephritis (paraphrased)"))
    return out


def diabetes(p: dict) -> List[Finding]:
    out: List[Finding] = []
    drug = kb.normalise(p["proposal"]["drug"])
    if "sulfonylurea" in kb.classes(drug) and (p.get("age", 0) >= 75 or p.get("frail")):
        out.append(F("DM-001", AMBER, "dosing", "Sulfonylurea in an older or frail person",
                     "Low blood sugar is more likely and more dangerous. Start low, agree a relaxed target and check the person can recognise a 'hypo'.",
                     "NICE NG28 (paraphrased)"))
    if "sglt2" in kb.classes(drug) and "sick_day" in p.get("triage", []):
        out.append(F("DM-002", RED, "safety_signal", "SGLT2 inhibitor while vomiting, dehydrated or not eating",
                     "Risk of diabetic ketoacidosis even with normal blood sugar. Do not start now; check ketones if unwell.",
                     "MHRA drug safety advice (paraphrased)"))
    if "glitazone" in kb.classes(drug) and "visible_haematuria" in p.get("triage", []):
        out.append(F("DM-003", RED, "contraindication", "Pioglitazone with unexplained blood in the urine",
                     "Do not start until the bleeding has been investigated.", "MHRA; BNF (paraphrased)"))
    return out


def oncology(p: dict) -> List[Finding]:
    out: List[Finding] = []
    meds = [kb.normalise(m) for m in p.get("current_meds", [])] + [kb.normalise(p["proposal"]["drug"])]
    on_chemo = any("cytotoxic" in kb.classes(m) for m in meds) or any("chemotherapy" in c.lower() for c in p.get("conditions", []))
    if on_chemo and "fever" in p.get("triage", []):
        out.append(F("ON-001", RED, "red_flag", "Fever in a person on chemotherapy",
                     "Treat as possible neutropenic sepsis: this is an emergency needing same-day hospital assessment, not a routine prescription.",
                     "NICE CG151 neutropenic sepsis (paraphrased)"))
    return out


def renal(p: dict) -> List[Finding]:
    out: List[Finding] = []
    if p.get("egfr") is not None and p["egfr"] < 30:
        out.append(F("RN-001", INFO, "dosing", f"Severely reduced kidney function (eGFR {p['egfr']:g})",
                     "Many medicines need a lower dose. Check every medicine on the list, not only the new one.", "Renal Drug Database (general)"))
    return out


def geriatrics(p: dict) -> List[Finding]:
    out: List[Finding] = []
    n = len([m for m in p.get("current_meds", []) if m.strip()]) + 1
    if n >= 10:
        out.append(F("GE-001", AMBER, "guideline", f"{n} medicines in total",
                     "Ten or more medicines greatly raises the chance of harm. Book a structured medication review and look for medicines to stop.",
                     "NICE NG56 multimorbidity (paraphrased)"))
    return out


# Field scopes: what each expert is allowed to see (bounded context).
_COMMON = ["age", "sex", "proposal", "triage"]
SCOPE: Dict[str, List[str]] = {
    "pharmacist": _COMMON + ["egfr", "pregnant", "trimester", "conditions", "current_meds"],
    "ptot": _COMMON + ["current_meds", "dexterity_problem", "cognitive_impairment", "swallowing_difficulty",
                       "visual_impairment", "falls_history", "frail", "missed_collections"],
    "allergy": _COMMON + ["allergies", "allergy_status_recorded", "current_meds"],
    "guidance": _COMMON + ["egfr", "pregnant", "conditions", "current_meds", "cognitive_impairment", "falls_history"],
    "literature": ["proposal", "live_evidence"],
    "microbiology": _COMMON + ["uti_courses_6m", "culture_resistant_to"],
    "urology": _COMMON + ["uti_courses_6m", "conditions"],
    "diabetes": _COMMON + ["frail", "conditions", "egfr"],
    "oncology": _COMMON + ["conditions", "current_meds"],
    "renal": _COMMON + ["egfr"],
    "geriatrics": _COMMON + ["current_meds", "frail"],
}

REGISTRY: Dict[str, dict] = {
    "pharmacist": {"fn": pharmacist, "name": "Pharmacist", "role": "Interactions, kidney dose, duplicates", "core": True, "colour": "#2E7D6B"},
    "ptot": {"fn": ptot, "name": "Physio / OT", "role": "Can the person manage this regimen?", "core": True, "colour": "#3B6FB6"},
    "allergy": {"fn": allergy_safety, "name": "Allergy Safety", "role": "Cross-reactions, allergy vs side effect", "core": True, "colour": "#B5562B"},
    "guidance": {"fn": guidance, "name": "Guidance", "role": "NICE, STOPP/START, shared care", "core": True, "colour": "#6A4C93"},
    "literature": {"fn": literature, "name": "Literature", "role": "Recent published safety evidence", "core": True, "colour": "#4A6572"},
    "microbiology": {"fn": microbiology, "name": "Microbiologist", "role": "Cultures, resistance, repeat courses", "core": False, "colour": "#8A6D1F"},
    "urology": {"fn": urology, "name": "Urologist", "role": "Red flags behind urinary symptoms", "core": False, "colour": "#1F6F8A"},
    "diabetes": {"fn": diabetes, "name": "Diabetologist", "role": "Low sugar risk, sick-day rules", "core": False, "colour": "#7A3E6A"},
    "oncology": {"fn": oncology, "name": "Oncologist", "role": "Chemotherapy emergencies and shared care", "core": False, "colour": "#9A3B3B"},
    "renal": {"fn": renal, "name": "Kidney physician", "role": "Dosing with poor kidney function", "core": False, "colour": "#3F7A3F"},
    "geriatrics": {"fn": geriatrics, "name": "Geriatrician", "role": "Many medicines, frailty", "core": False, "colour": "#5B5B8A"},
}

AgentFn = Callable[[dict], List[Finding]]
