"""The interactive MDT meeting.

After the experts have reviewed a request, the prescriber can:
  * hear the chair's opening summary,
  * ask any expert a question (what did you find, what do you advise, what
    should the patient be told, can I speak to a person),
  * go round the table for every expert's position,
  * put a change to the team (another medicine, dose, frequency or length) and
    see who changes position,
  * and close the meeting with a decision, which produces a written conclusion.

The experts answer from their recorded findings and the rules. They are not
language models and cannot answer free-text questions; the fixed questions keep
every answer traceable to a rule.
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import List, Optional, Tuple

from . import knowledge as kb
from . import medreview
from .models import AMBER, INFO, RED, CaseResult, Proposal
from .orchestrator import DECISIONS, _format_rx, run_case

POSITION = {RED: "Objects", AMBER: "Agrees with cautions", INFO: "Agrees"}
QUESTIONS = ["What did you find?", "What do you advise?", "What should the patient be told?", "Can I speak to a person?"]
CHAIR = {"agent": "chair", "name": "Chair (orchestrator)", "colour": "#22304a"}


def positions(result: CaseResult) -> List[dict]:
    by = {r.agent: r for r in result.reports}
    out = []
    for c in result.convened:
        level = by[c["agent"]].worst if c["agent"] in by else INFO
        out.append({"agent": c["agent"], "name": c["name"], "colour": c["colour"], "level": level, "position": POSITION[level]})
    return out


def tally(result: CaseResult) -> str:
    pos = positions(result)
    n = lambda lv: sum(p["level"] == lv for p in pos)
    return f"{n(INFO)} agree, {n(AMBER)} agree with cautions, {n(RED)} object"


def _mine(result: CaseResult, agent: str):
    mine = [f for f in result.findings if f.agent == agent]
    return [f for f in mine if f.level != INFO], [f for f in mine if f.level == INFO]


def chair_opening(result: CaseResult) -> str:
    rx = _format_rx(result.patient.to_dict()["proposal"])
    text = (f"We are reviewing a request for {rx}. {len(result.convened)} experts have looked at it: {tally(result)}. "
            f"{result.headline}")
    if result.alternative:
        text += f" The safer option that passes every rule is {result.alternative}."
    text += " Ask any expert a question, go round the table, or put a change to the team. The decision is yours."
    return text


def answer(result: CaseResult, agent: str, question: str) -> str:
    """One expert's reply to one of the fixed questions."""
    conv = next((c for c in result.convened if c["agent"] == agent), None)
    if conv is None:
        return "That expert was not called in for this request."
    notable, notes = _mine(result, agent)
    drug = kb.normalise(result.patient.proposal.drug)
    if question == QUESTIONS[0]:
        if not notable and not notes:
            return "I looked at this request from my area and found nothing of concern."
        parts = [f"{'STOP' if f.level == RED else 'Caution'}: {f.title}. {f.detail}" for f in notable]
        parts += [f"For information: {f.title}. {f.detail}" for f in notes]
        return " ".join(f"({i + 1}) {p}" for i, p in enumerate(parts))
    if question == QUESTIONS[1]:
        reds = [f for f in notable if f.level == RED]
        if reds:
            text = "I object to this prescription as it stands, because: " + "; ".join(f.title for f in reds) + "."
            if result.alternative:
                text += f" I would support the safer option: {result.alternative}."
            elif any(f.signal == "red_flag" for f in reds):
                text += " A different medicine would not solve this; the problem needs to be looked into first."
            return text
        if notable:
            return "I can support it, provided these points are dealt with: " + "; ".join(f.title for f in notable) + "."
        return "I support the prescription as requested. I have no conditions from my area."
    if question == QUESTIONS[2]:
        if agent == "side_effects":
            fx = medreview.effect_list(drug)
            if not fx:
                return "I hold no side-effect list for this medicine in the demo set, so use the patient leaflet."
            return (f"The main side effects of {drug} to mention are: {', '.join(fx)}. Ask the patient to report anything new or "
                    "worrying, and give the patient leaflet. This is a short list, not the full product information.")
        if agent == "pharmacist":
            return f"How to take it: {_format_rx(result.patient.to_dict()['proposal'])}. {medreview.dose_summary(result.patient)}"
        tips = [f.detail for f in notable + notes if f.level != RED]
        return " ".join(tips) if tips else "Nothing specific from my area beyond the usual advice for this medicine."
    if question == QUESTIONS[3]:
        if not conv.get("human"):
            return "I am a reference expert, so there is no named person behind me. Use the published guidance or ask the pharmacist."
        how = ("They can be reached now." if conv["available"] else "They are off duty at the moment, so a request would wait.")
        return (f"My human counterpart is the {conv['human'].lower()}. {conv['note']}. {how} "
                "Tick my name under 'log a request for human advice' when you record your decision and it goes into the log.")
    return "Please choose one of the listed questions."


def round_table(result: CaseResult) -> List[Tuple[dict, str]]:
    out = []
    for p in positions(result):
        notable, _ = _mine(result, p["agent"])
        reason = notable[0].title if notable else "nothing of concern in my area"
        out.append((p, f"{p['position']}: {reason}."))
    return out


def what_if(result: CaseResult, drug: str, dose: str, frequency: str, days: Optional[int],
            when: Optional[datetime] = None) -> Tuple[CaseResult, str]:
    """Put a changed prescription to the team. Returns the new review and the chair's summary of what changed."""
    p = copy.deepcopy(result.patient)
    p.proposal = Proposal((drug or "").strip(), (dose or "").strip(), frequency or "once daily",
                          int(days) if days else None, result.patient.proposal.indication)
    new = run_case(p, when=when)
    before = {x["agent"]: x for x in positions(result)}
    changes = []
    for x in positions(new):
        old = before.get(x["agent"])
        if old is None:
            changes.append(f"{x['name']} has joined the meeting ({x['position'].lower()})")
        elif old["position"] != x["position"]:
            changes.append(f"{x['name']}: {old['position'].lower()} -> {x['position'].lower()}")
    left = [v["name"] for k, v in before.items() if k not in {x["agent"] for x in positions(new)}]
    changes += [f"{n} is no longer needed and has left" for n in left]
    text = (f"Revised proposal: {_format_rx(new.patient.to_dict()['proposal'])}. The team now stands at: {tally(new)}. "
            f"{new.headline} " + ("Changes of position: " + "; ".join(changes) + "." if changes else "No expert changed position."))
    return new, text


def conclusion(result: CaseResult, record: dict, role: str) -> dict:
    """The written outcome of the meeting, built only after a clinician has decided."""
    cautions = [f.title for f in result.findings if f.level == AMBER]
    stops = [f.title for f in result.findings if f.level == RED]
    drug = kb.normalise((record.get("final_prescription") or "").split(" ")[0]) if record.get("final_prescription") else ""
    return {
        "decision": DECISIONS[record["decision"]],
        "final_prescription": record.get("final_prescription") or "No prescription issued",
        "decided_by": role, "time_utc": record["time_utc"], "team": tally(result),
        "stops": stops, "cautions": cautions,
        "tell_patient": medreview.effect_list(drug) if drug else [],
        "reason": record.get("reason", ""), "human_advice": record.get("human_advice_requested", []),
        "log_record": record["hash"][:16], "case": result.case_hash[:16],
    }


def conclusion_text(c: dict) -> str:
    lines = ["VIRTUAL MDT MEETING - FINAL CONCLUSION", "Research demonstrator on invented data. Not a medical device.", "",
             f"Decision: {c['decision']}", f"Final prescription: {c['final_prescription']}",
             f"Decided by: {c['decided_by']} at {c['time_utc']} (UTC)", f"Team position at close: {c['team']}", ""]
    if c["reason"]:
        lines += [f"Reason recorded: {c['reason']}", ""]
    if c["stops"]:
        lines += ["Objections raised:"] + [f"  - {s}" for s in c["stops"]] + [""]
    if c["cautions"]:
        lines += ["Cautions to act on:"] + [f"  - {s}" for s in c["cautions"]] + [""]
    if c["tell_patient"]:
        lines += ["Side effects to mention to the patient: " + ", ".join(c["tell_patient"]), ""]
    if c["human_advice"]:
        lines += ["Human advice requested from: " + "; ".join(c["human_advice"]), ""]
    lines += [f"Decision log record: {c['log_record']}   Case fingerprint: {c['case']}"]
    return "\n".join(lines)


def key_points(result: CaseResult, limit: int = 5) -> List[tuple]:
    """The few things to read before deciding: the worst findings first."""
    return [(f.level, f.title) for f in result.findings if f.level != INFO][:limit]


def patient_summary(result: CaseResult) -> dict:
    """A plain-words draft for the prescriber to read out or adapt. It carries no clinical
    reasoning and never tells the patient to take anything: nothing is prescribed until the
    prescriber decides."""
    prop = result.patient.to_dict()["proposal"]
    requested = _format_rx(prop)
    escalated = result.outcome in (RED, "HARD_STOP")
    if not escalated:
        considering, drug = requested, kb.normalise(prop["drug"])
        opening = f"The medicine being considered for you is {requested}."
    elif result.alternative:
        considering, drug = result.alternative, kb.normalise(result.alternative_proposal["drug"])
        opening = (f"The medicine first suggested ({prop['drug']}) does not look suitable for you. "
                   f"Another option being considered is {result.alternative}.")
    else:
        considering, drug = "", ""
        opening = (f"The medicine first suggested ({prop['drug']}) does not look suitable for you. "
                   "Your prescriber is looking into what would be best instead.")
    n = len([f for f in result.findings if f.level != INFO])
    return {
        "opening": opening, "considering": considering,
        "look_out_for": medreview.effect_list(drug) if drug else [],
        "being_checked": n,
        "closing": "Nothing is prescribed until your prescriber has decided. Please ask them or your pharmacist about anything that worries you.",
    }
