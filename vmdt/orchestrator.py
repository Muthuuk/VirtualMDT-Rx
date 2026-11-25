"""The orchestrator: the 'chair' of the virtual MDT.

Fixed route (a workflow, not a free-roaming agent), so every step can be
inspected and tested:

  1. Triage     screen the free-text notes for safety phrases (ignoring "no fever")
  2. Convene    core five experts + the consultants this case needs
  3. Fan out    give each expert only its own slice of the record; run all at once
  4. Aggregate  collect findings; a RED safety signal always escalates
  5. Optimise   suggest simpler regimens (annotated options, never blocks)
  6. Double-check  re-run the hard safety rules independently of the experts
  7. Hand over  draft + reasons to the clinician, or Flag & Escalate with a safe
                alternative. The system never prescribes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from typing import Dict, List, Optional

from . import agents as ag
from . import knowledge as kb
from . import rota
from .models import (AMBER, ESCALATION_SIGNALS, FREQ_PER_DAY, INFO, LEVEL_ORDER, RED,
                     AgentReport, CaseResult, Finding, Patient)

AGENT_TIMEOUT_S = 8.0
CRITICAL_AGENTS = {"pharmacist", "allergy"}   # if one fails, the case goes to manual review
# Fixed, made-up 'thinking times' used only when the demo delay is switched on.
DEMO_DELAY_S = {"pharmacist": 0.9, "ptot": 0.5, "allergy": 0.6, "guidance": 0.8, "literature": 1.0,
                "microbiology": 0.7, "urology": 0.6, "diabetes": 0.6, "oncology": 0.6, "renal": 0.4, "geriatrics": 0.4}


# ------------------------------------------------------------------ 1. triage
def triage(notes: str) -> List[str]:
    """Bounded screen-and-route step: find safety phrases, skip negated ones.

    A negation only counts inside the same clause ("no fever"), so "No dysuria.
    Fever since Monday." still raises fever. When wording is ambiguous the phrase
    is flagged: a false alarm costs a moment, a missed fever can cost a life.
    """
    import re
    clauses = [" " + c.strip() + " " for c in re.split(r"[.;,!?\n]| but ", (notes or "").lower()) if c.strip()]
    found: List[str] = []
    for signal, phrases in kb.TRIAGE_PHRASES.items():
        for clause in clauses:
            for ph in phrases:
                i = clause.find(ph)
                if i != -1 and not any(neg in clause[:i] for neg in kb.NEGATIONS):
                    found.append(signal)
                    break
            if signal in found:
                break
    return found


# ----------------------------------------------------------------- 2. convene
def convene(p: Patient, signals: List[str]) -> List[str]:
    drug = kb.normalise(p.proposal.drug)
    meds = [kb.normalise(m) for m in p.current_meds]
    conds = " ".join(p.conditions).lower()
    team = [k for k, v in ag.REGISTRY.items() if v["core"]]
    if "antibiotic" in kb.classes(drug):
        team.append("microbiology")
    if p.proposal.indication == "uti" or {"visible_haematuria", "flank_pain"} & set(signals) or "bladder" in conds or "prostate" in conds:
        team.append("urology")
    if p.proposal.indication == "type2_diabetes" or "diabetes" in conds:
        team.append("diabetes")
    if p.proposal.indication == "cancer_care" or "cancer" in conds or "chemotherapy" in conds or \
            any("cytotoxic" in kb.classes(m) for m in meds + [drug]):
        team.append("oncology")
    if p.egfr is not None and p.egfr < 45:
        team.append("renal")
    if p.age >= 75 or p.frail or len(p.current_meds) >= 8:
        team.append("geriatrics")
    return team


# ---------------------------------------------------------------- 3. fan out
def _payload(pd: dict, agent: str) -> dict:
    return {k: copy.deepcopy(pd[k]) for k in ag.SCOPE[agent] if k in pd}


def _run_agent(agent: str, payload: dict, registry: dict, delay: float) -> AgentReport:
    meta = registry[agent]
    t0 = time.perf_counter()
    rep = AgentReport(agent=agent, role=meta["role"], saw=sorted(payload.keys()))
    try:
        if delay:
            time.sleep(delay)
        rep.findings = list(meta["fn"](payload))
    except Exception as exc:  # an expert that crashes must never crash the case
        rep.status = "failed"
        rep.findings = [Finding("SYS-FAIL", AMBER, "data_gap", f"{meta['name']} could not complete its review",
                                f"Technical problem ({type(exc).__name__}). This check was NOT done; review manually.", "System")]
    rep.ms = (time.perf_counter() - t0) * 1000
    for f in rep.findings:
        f.agent = agent
    return rep


# ---------------------------------------------------- 6. independent hard rules
def hard_checks(pd: dict) -> List[Finding]:
    """Re-run every rule-based expert in a plain loop, with the FULL record and no
    scoping, and keep the RED results. Used (a) as the safety double-check and
    (b) to test whether a suggested alternative is itself safe."""
    full = dict(pd)
    full.setdefault("triage", [])
    full["live_evidence"] = False
    reds: List[Finding] = []
    for key, meta in ag.REGISTRY.items():
        if key == "literature":
            continue
        for f in meta["fn"](full):
            if f.level == RED:
                f.agent = key
                reds.append(f)
    return reds


def _alternative(p: Patient, pd: dict) -> Optional[dict]:
    g = kb.GUIDELINES.get(p.proposal.indication)
    if not g or not g.get("regimen"):
        return None
    current = kb.normalise(p.proposal.drug)
    for cand in g["first_line"] + g["second_line"]:
        if cand == current or cand not in g["regimen"]:
            continue
        dose, freq = g["regimen"][cand]
        alt = copy.deepcopy(pd)
        dur = None
        if "duration" in g and cand != "fosfomycin":
            dur = g["duration"]["pregnant" if p.pregnant else p.sex]
        alt["proposal"] = {"drug": cand, "dose": dose, "frequency": freq, "duration_days": dur,
                           "indication": p.proposal.indication}
        if not hard_checks(alt):
            return alt["proposal"]
    return None


def _format_rx(prop: dict) -> str:
    s = f"{prop['drug'].capitalize()} {prop.get('dose', '')}".strip() + f", {prop.get('frequency', '')}"
    if prop.get("duration_days"):
        s += f", for {prop['duration_days']} days"
    return s


# --------------------------------------------------------------- 5. optimise
def optimise(p: Patient) -> List[str]:
    notes: List[str] = []
    drug = kb.normalise(p.proposal.drug)
    meds = {kb.normalise(m) for m in p.current_meds}
    for pair, msg in kb.COMBINATIONS:
        if pair <= (meds | {drug}) and drug in pair:
            notes.append(msg + " Check formulary and supply first.")
    if drug in kb.ONCE_DAILY_OPTION and FREQ_PER_DAY.get(p.proposal.frequency, 1) >= 2:
        notes.append(kb.ONCE_DAILY_OPTION[drug])
    if p.missed_collections >= 2:
        notes.append(f"{p.missed_collections} recent prescriptions were not collected. This is a prompt for a conversation "
                     "about what makes medicines hard to get or take, not a judgement. Collection records cannot show whether medicines were taken.")
    doses = FREQ_PER_DAY.get(p.proposal.frequency, 1)
    total = len(p.current_meds) + 1
    if total >= 6:
        notes.append(f"This would make {total} regular medicines. Ask whether any can be stopped.")
    if doses >= 3 and not notes:
        notes.append("Dosing three or more times a day lowers the chance the course is completed; mention linking doses to meals or routines.")
    return notes


# ---------------------------------------------------------------------- run
def run_case(p: Patient, when: Optional[datetime] = None, live_evidence: bool = False,
             demo_delay: bool = False, registry: Optional[dict] = None) -> CaseResult:
    registry = registry or ag.REGISTRY
    when = when or datetime.now()
    t0 = time.perf_counter()
    pd = p.to_dict()
    signals = triage(p.notes)
    pd["triage"] = signals
    pd["live_evidence"] = live_evidence
    team = convene(p, signals)

    reports: List[AgentReport] = []
    with ThreadPoolExecutor(max_workers=len(team)) as pool:
        futures = {a: pool.submit(_run_agent, a, _payload(pd, a), registry, DEMO_DELAY_S.get(a, 0.5) if demo_delay else 0.0)
                   for a in team}
        for a, fut in futures.items():
            try:
                reports.append(fut.result(timeout=AGENT_TIMEOUT_S))
            except FutureTimeout:
                rep = AgentReport(agent=a, role=registry[a]["role"], status="timed_out", ms=AGENT_TIMEOUT_S * 1000)
                rep.findings = [Finding("SYS-TIME", AMBER, "data_gap", f"{registry[a]['name']} ran out of time",
                                        "This check was NOT done; review manually.", "System", agent=a)]
                reports.append(rep)

    # 4. aggregate (drop exact repeats; worst first)
    findings: List[Finding] = []
    seen = set()
    for rep in reports:
        for f in rep.findings:
            if (f.code, f.title) not in seen:
                seen.add((f.code, f.title))
                findings.append(f)
    findings.sort(key=lambda f: -LEVEL_ORDER[f.level])

    # 6. safety double-check
    independent = hard_checks(pd)
    reported_red = {(f.code, f.title) for f in findings if f.level == RED}
    missed = [f for f in independent if (f.code, f.title) not in reported_red]
    for f in missed:  # an expert missed or was unable to report a hard rule: add it back
        f.detail += " (Added by the safety double-check.)"
        findings.insert(0, f)
    failed = [r.agent for r in reports if r.status != "ok"]
    reds = [f for f in findings if f.level == RED]
    safety = {
        "No allergy conflict": not any(f.signal == "allergy" for f in reds),
        "No contraindication": not any(f.signal == "contraindication" for f in reds),
        "No dosing alert": not any(f.signal == "dosing" for f in reds),
        "No dangerous interaction": not any(f.signal == "interaction" for f in reds),
        "No red-flag symptom": not any(f.signal in ("red_flag", "safety_signal", "stewardship", "deliverability") for f in reds),
        "No supply problem": not any(f.signal == "supply" for f in findings),
        "Every expert reported": not failed,
        "Experts and double-check agree": not missed,
    }

    escalate = [f for f in reds if f.signal in ESCALATION_SIGNALS]
    critical_down = bool(set(failed) & CRITICAL_AGENTS)
    optimisation = optimise(p)
    draft, alternative = None, None
    if escalate or critical_down:
        outcome = RED
        only_red_flags = any(f.signal == "red_flag" for f in escalate)  # a red flag outranks any drug swap
        alt = None if (only_red_flags or critical_down) else _alternative(p, pd)
        if critical_down:
            headline = "Manual review needed: a critical safety check could not be completed. No draft produced."
        elif only_red_flags:
            headline = "Flag & Escalate: a red-flag symptom means a prescription alone is not the right action."
        elif alt:
            alternative = _format_rx(alt)
            headline = "Flag & Escalate: the requested medicine is not safe here. A safer option is suggested."
        elif kb.GUIDELINES.get(p.proposal.indication, {}).get("regimen"):
            outcome = "HARD_STOP"
            headline = "Hard stop: the request is unsafe and every usual alternative also fails a safety rule. The clinician must resolve this."
        else:
            headline = "Flag & Escalate: the requested medicine is not safe here. No automatic alternative; seek specialist advice."
    elif any(f.level == AMBER for f in findings):
        outcome = AMBER
        headline = "Draft ready, with cautions to read before sign-off."
        draft = _format_rx(pd["proposal"])
    else:
        outcome = "GREEN"
        headline = "Draft ready. No safety concerns were found by the virtual team."
        draft = _format_rx(pd["proposal"])

    convened = []
    for a in team:
        st = rota.status(a, when)
        convened.append({"agent": a, "name": registry[a]["name"], "role": registry[a]["role"],
                         "colour": registry[a]["colour"], "core": registry[a]["core"], **st})

    canon = json.dumps({"patient": p.to_dict(), "codes": sorted(f.code + f.level for f in findings),
                        "outcome": outcome}, sort_keys=True)
    return CaseResult(patient=p, outcome=outcome, headline=headline, reports=reports, findings=findings,
                      triage_signals=signals, optimisation=optimisation, safety_check=safety, draft=draft,
                      alternative=alternative, total_ms=(time.perf_counter() - t0) * 1000,
                      sequential_ms=sum(r.ms for r in reports), convened=convened,
                      case_hash=hashlib.sha256(canon.encode()).hexdigest())


# ------------------------------------------------------------ human sign-off
DECISIONS = {
    "APPROVE": "Approve the draft",
    "APPROVE_WITH_CHANGES": "Approve with my changes",
    "ACCEPT_ALTERNATIVE": "Prescribe the suggested safer option",
    "OVERRIDE": "Override the escalation (reason required)",
    "REJECT": "Do not prescribe",
}


def sign_off(result: CaseResult, decision: str, clinician_id: str, role: str, audit,
             reason: str = "", changes: str = "", acknowledged: bool = False,
             human_advice: Optional[List[str]] = None) -> tuple:
    """The only way anything leaves the system. Returns (ok, message, audit_record)."""
    reason, changes = (reason or "").strip(), (changes or "").strip()
    if decision not in DECISIONS:
        return False, "Choose a decision.", None
    if len((clinician_id or "").strip()) < 2:
        return False, "Enter your clinician ID or initials: every decision must be attributable.", None
    escalated = result.outcome in (RED, "HARD_STOP")
    if escalated and decision in ("APPROVE", "APPROVE_WITH_CHANGES"):
        return False, ("This case was escalated, so there is no draft to approve. Choose the safer option, "
                       "do not prescribe, or override with a written reason."), None
    if decision == "ACCEPT_ALTERNATIVE" and not result.alternative:
        return False, "No safer option was suggested for this case.", None
    if decision == "OVERRIDE":
        if not escalated:
            return False, "Nothing to override: this case was not escalated.", None
        if len(reason) < 20:
            return False, "An override needs a clear clinical reason (at least 20 characters).", None
    if decision == "APPROVE" and result.outcome == AMBER and not acknowledged:
        return False, "Tick the box to confirm you have read the cautions.", None
    if decision == "APPROVE_WITH_CHANGES" and len(changes) < 3:
        return False, "Describe the change you are making.", None

    final = {"APPROVE": result.draft, "APPROVE_WITH_CHANGES": changes, "ACCEPT_ALTERNATIVE": result.alternative,
             "OVERRIDE": _format_rx(result.patient.to_dict()["proposal"]), "REJECT": None}[decision]
    from .audit import pseudonym
    rec = audit.append(
        "SIGN_OFF", case_hash=result.case_hash, patient=pseudonym(result.patient.ref),
        clinician=pseudonym(clinician_id), role=role, outcome=result.outcome, decision=decision,
        final_prescription=final, reason=reason,
        findings=[{"code": f.code, "level": f.level, "agent": f.agent} for f in result.findings if f.level != INFO],
        human_advice_requested=human_advice or [],
    )
    msg = {"REJECT": "Recorded: no prescription issued."}.get(decision, f"Recorded. Final prescription: {final}")
    return True, msg, rec
