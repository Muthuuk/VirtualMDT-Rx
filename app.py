"""VirtualMDT-Rx web app.  Run:  python app.py   (Colab, Hugging Face Spaces or a laptop)

Research demonstrator on invented data. NOT a medical device. Do not enter real
patient details. A qualified clinician makes every prescribing decision.
"""
from __future__ import annotations

import inspect
import json
import os
import tempfile
from datetime import datetime
from html import escape

import gradio as gr
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from vmdt import __version__, knowledge as kb, medreview, meeting, opendata, room3d
from vmdt.audit import AuditLog
from vmdt.contracts import ContractError, Notary
from vmdt.ledger import new_salt
from vmdt.batch import review_frame, synthetic_cohort
from vmdt.cases import PRESETS, SUITE
from vmdt.evaluate import evaluate
from vmdt.models import AMBER, INFO, RED, Allergy, Patient, Proposal
from vmdt.orchestrator import DECISIONS, run_case, sign_off
from vmdt.requirements_trace import REQUIREMENTS

INDICATIONS = {"Urine infection (UTI)": "uti", "Type 2 diabetes": "type2_diabetes", "Cancer care": "cancer_care", "Other": "other"}
IND_LABEL = {v: k for k, v in INDICATIONS.items()}
CULTURE_CHOICES = ["not recorded", "not sent", "awaited", "infection confirmed", "no infection found"]
FREQS = ["once daily", "twice daily", "three times daily", "four times daily", "once weekly", "single dose", "as needed"]
FUNCTION_FLAGS = {"Memory or thinking problems": "cognitive_impairment", "Hand or grip problems": "dexterity_problem",
                  "Swallowing difficulty": "swallowing_difficulty", "Poor eyesight": "visual_impairment",
                  "History of falls": "falls_history", "Frail": "frail"}
STATUS = {"GREEN": ("#0aac23", "#eaf7ec", "Ready for sign-off"), "AMBER": ("#fbb315", "#fff6df", "Ready, with cautions"),
          "RED": ("#dc3c3d", "#fdecec", "Flag and escalate"), "HARD_STOP": ("#dc3c3d", "#fdecec", "Hard stop")}
LEVEL_STYLE = {RED: ("#dc3c3d", "#fdecec", "✕ STOP"), AMBER: ("#b77900", "#fff6df", "▲ CAUTION"), INFO: ("#1b64be", "#eaf2fd", "ℹ NOTE")}
SERIES = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2", "#ec4647"]  # fixed order, never cycled

CSS = """
.gradio-container{font-size:18px !important}
.gradio-container label span,.gradio-container .prose,.gradio-container input,.gradio-container textarea,
.gradio-container select,.gradio-container button{font-size:1.02rem !important}
.gradio-container .prose h1{font-size:2rem !important}.gradio-container .prose h2{font-size:1.5rem !important}
.gradio-container .prose h3{font-size:1.25rem !important}
.gradio-container table{font-size:1rem !important}
.vm-banner{border-radius:14px;padding:16px 20px;border-left:10px solid var(--c);background:var(--bg);color:#191919}
.vm-banner .big{font-size:1.5rem;font-weight:750}.vm-banner .line{font-size:1.12rem;margin-top:4px}
.vm-card{border-radius:12px;padding:12px 16px;margin:10px 0;border-left:8px solid var(--c);background:var(--bg);color:#191919}
.vm-card .t{font-size:1.14rem;font-weight:700}.vm-card .d{font-size:1.05rem;margin-top:3px;line-height:1.4}
.vm-card .s{font-size:.9rem;color:#4d4d4d;margin-top:5px}
.vm-tag{display:inline-block;font-size:.85rem;font-weight:800;letter-spacing:.04em;color:#fff;background:var(--c);border-radius:6px;padding:1px 8px;margin-right:8px}
.vm-check{font-size:1.05rem;line-height:1.7;color:inherit}
.vm-warn{background:#fff6df;color:#191919;border:1px solid #f2a600;border-radius:12px;padding:10px 16px;font-size:1.05rem}
/* ---- 3D colour buttons ---- */
.vm-tiles{gap:26px !important;margin:6px 4px 30px !important;perspective:1200px}
button.vm-tile,.vm-tile button{min-height:150px;border-radius:22px !important;border:none !important;color:#fff !important;
  font-size:1.32rem !important;font-weight:750 !important;line-height:1.45 !important;white-space:pre-line !important;text-align:left !important;
  justify-content:flex-start !important;padding:22px 26px !important;text-shadow:0 2px 3px rgba(0,0,0,.35);
  background:linear-gradient(150deg,var(--hi),var(--base) 55%,var(--lo)) !important;
  box-shadow:0 12px 0 var(--edge),0 26px 34px rgba(0,0,0,.28),inset 0 3px 0 rgba(255,255,255,.45),inset 0 -6px 12px rgba(0,0,0,.18) !important;
  transform:rotateX(8deg) translateY(0);transform-origin:50% 100%;transition:transform .16s ease,box-shadow .16s ease,filter .16s ease !important}
button.vm-tile:hover,.vm-tile button:hover{transform:rotateX(0deg) translateY(-6px);filter:brightness(1.07);
  box-shadow:0 16px 0 var(--edge),0 34px 40px rgba(0,0,0,.30),inset 0 3px 0 rgba(255,255,255,.5),inset 0 -6px 12px rgba(0,0,0,.18) !important}
button.vm-tile:active,.vm-tile button:active{transform:rotateX(0deg) translateY(10px);
  box-shadow:0 2px 0 var(--edge),0 6px 10px rgba(0,0,0,.3),inset 0 3px 8px rgba(0,0,0,.25) !important}
.t1{--hi:#35d0ba;--base:#0f9d8a;--lo:#0b7f70;--edge:#075a50}
.t2{--hi:#6ea2ff;--base:#2f6fde;--lo:#2459b8;--edge:#183f86}
.t3{--hi:#ffab52;--base:#d9730d;--lo:#b55f09;--edge:#834405}
.t4{--hi:#a98bf5;--base:#7b4fd6;--lo:#6540b6;--edge:#462a85}
.t5{--hi:#f47aa9;--base:#d6457f;--lo:#b43568;--edge:#822148}
.t6{--hi:#63cf78;--base:#2e9e44;--lo:#258238;--edge:#175a25}
.t7{--hi:#5fd3f0;--base:#1596b8;--lo:#117a96;--edge:#0b5468}
.vm-receipt{border-radius:16px;padding:16px 22px;background:linear-gradient(160deg,#e6f6fb,#dff0f7);border:2px solid #1596b8;color:#191919;margin-top:10px}
.vm-receipt .big{font-size:1.3rem;font-weight:800}.vm-receipt .line{font-size:1.03rem;margin-top:5px;word-break:break-word}
.vm-receipt code{background:#fff;padding:1px 6px;border-radius:6px;font-size:.92rem}
button.vm-wide,.vm-wide button{min-height:84px !important;text-align:center !important;justify-content:center !important;margin:18px 4px 26px !important}
button.vm-home,.vm-home button{border-radius:14px !important;border:none !important;color:#fff !important;font-weight:700 !important;
  min-width:150px !important;background:linear-gradient(150deg,#56657f,#2f3b52) !important;
  box-shadow:0 6px 0 #1b2333,0 12px 16px rgba(0,0,0,.25),inset 0 2px 0 rgba(255,255,255,.3) !important;transition:transform .12s ease,box-shadow .12s ease !important}
button.vm-home:active,.vm-home button:active{transform:translateY(5px);box-shadow:0 1px 0 #1b2333,0 3px 6px rgba(0,0,0,.3) !important}
/* ---- display controls, steps and panels ---- */
:root{--vm-zoom:1}
.vm-off{display:none !important}
.vm-bar{margin:-6px 0 0 !important;align-items:center !important}
.vm-bar .block{padding:6px 10px !important}
.vm-title h1{font-size:1.7rem !important;margin:0 !important}.vm-title p{margin:0 !important;font-size:1.02rem !important}
.vm-thin{padding:6px 14px !important;font-size:.95rem !important}
.vm-seg label{border-radius:999px !important}
.vm-steps{display:flex;gap:10px;margin:4px 0 10px}
.vm-stepc{flex:1;text-align:center;padding:10px 8px;border-radius:12px;font-weight:700;font-size:1.05rem;background:#e3e8ef;color:#4d4d4d}
.vm-stepc.now{background:linear-gradient(150deg,#35d0ba,#0f9d8a);color:#fff;box-shadow:0 5px 0 #075a50}
.vm-stepc.done{background:#cdeee8;color:#075a50}
button.vm-next,.vm-next button{background:linear-gradient(150deg,#6ea2ff,#2f6fde) !important;box-shadow:0 6px 0 #183f86,0 12px 16px rgba(0,0,0,.25),inset 0 2px 0 rgba(255,255,255,.3) !important}
.vm-fit{max-height:calc((100vh - 250px) / var(--vm-zoom));overflow-y:auto;border-radius:18px}
.vm-panel .vm-talk{max-height:calc((100vh - 470px) / var(--vm-zoom));min-height:240px}
.vm-patient{border-radius:16px;padding:18px 22px;background:#eaf2fd;border:2px solid #2f6fde;color:#191919}
.vm-patient .big{font-size:1.4rem;font-weight:800;margin-bottom:6px}.vm-patient p{font-size:1.15rem;line-height:1.5;margin:8px 0}
/* ---- high-contrast colours ---- */
body.vm-hc .gradio-container{--body-text-color:#000;--block-label-text-color:#000;--block-title-text-color:#000;--body-background-fill:#fff;--background-fill-primary:#fff}
body.vm-hc textarea,body.vm-hc input[type=number],body.vm-hc .wrap-inner,body.vm-hc label.selected{border:2px solid #000 !important}
body.vm-hc .vm-card,body.vm-hc .vm-banner,body.vm-hc .vm-seat,body.vm-hc .vm-bub,body.vm-hc .vm-warn,body.vm-hc .vm-final,body.vm-hc .vm-patient,body.vm-hc .vm-stepc{
  background:#fff !important;color:#000 !important;border:2px solid #000 !important}
body.vm-hc .vm-pill,body.vm-hc .vm-tag{background:#000 !important;color:#fff !important;border-color:#000 !important}
body.vm-hc .vm-stepc.now{background:#000 !important;color:#fff !important;box-shadow:none}
body.vm-hc .vmdt-room{background:#000 !important}body.vm-hc .vx .face{background:#0b0b0b !important;border:2px solid #fff !important}
body.vm-hc button.vm-tile,body.vm-hc .vm-tile button,body.vm-hc button.vm-home,body.vm-hc .vm-home button{outline:3px solid #000;text-shadow:none}
/* ---- meeting ---- */
.vm-talk{max-height:560px;overflow-y:auto;background:#f3f5f9;border:1px solid #d5dbe5;border-radius:14px;padding:12px;}
.vm-msg{display:flex;gap:10px;margin:8px 0;align-items:flex-start}
.vm-msg.you{flex-direction:row-reverse}
.vm-av{flex:0 0 40px;height:40px;border-radius:50%;color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;
  box-shadow:inset -4px -4px 8px rgba(0,0,0,.3),0 3px 6px rgba(0,0,0,.25)}
.vm-bub{background:#fff;color:#191919;border-radius:14px;padding:10px 14px;font-size:1.05rem;line-height:1.45;max-width:86%;box-shadow:0 1px 3px rgba(0,0,0,.12)}
.vm-msg.you .vm-bub{background:#dff5f0}
.vm-who{font-weight:750;font-size:.95rem;margin-bottom:2px}
.vm-seat{background:#fff;color:#191919;border:1px solid #d9d9d9;border-radius:10px;padding:8px 12px;margin:6px 0;font-size:1.03rem}
.vm-dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:8px}
.vm-final{border-radius:16px;padding:20px 24px;background:linear-gradient(160deg,#eaf7ec,#dff5f0);border:2px solid #2e9e44;color:#191919;margin-top:8px}
.vm-final .big{font-size:1.5rem;font-weight:800}.vm-final .rx{font-size:1.6rem;font-weight:800;margin:8px 0;color:#175a25}
.vm-final .line{font-size:1.08rem;margin-top:5px}
.vm-chip{display:inline-block;background:#eaf2fd;color:#191919;border:1px solid #9ec0ee;border-radius:999px;padding:2px 12px;margin:4px 6px 0 0;font-size:1rem}
.vm-table{width:100%;border-collapse:collapse;margin-top:10px;font-size:1.02rem !important}
.vm-table th{text-align:left;background:#22304a;color:#fff;padding:8px 10px;font-size:.98rem}
.vm-table td{padding:8px 10px;border-bottom:1px solid #d9d9d9;vertical-align:top;background:#fff;color:#191919}
.vm-pill{display:inline-block;border-radius:999px;padding:2px 10px;font-weight:700;font-size:.92rem;white-space:nowrap}
"""


# ---------------------------------------------------------------- helpers
def _lines(text: str) -> list:
    return [x.strip() for x in (text or "").replace("\n", ";").split(";") if x.strip()]


def build_patient(ref, age, sex, egfr, pregnant, trimester, indication, drug, dose, freq, days, meds, conds,
                  allergies, allergy_recorded, function, courses, resistant, missed, notes,
                  culture="not recorded", clear_tests=0, abx_days=0) -> Patient:
    al = []
    for item in _lines(allergies):
        sub, _, reac = item.partition(":")
        al.append(Allergy(sub.strip(), reac.strip() or "unknown"))
    flags = {v: (k in (function or [])) for k, v in FUNCTION_FLAGS.items()}
    return Patient(
        ref=(ref or "CASE").strip(), age=int(age or 0), sex=sex or "female",
        proposal=Proposal((drug or "").strip(), (dose or "").strip(), freq or "once daily",
                          int(days) if days else None, INDICATIONS.get(indication, "other")),
        egfr=float(egfr) if egfr not in (None, "") else None, pregnant=bool(pregnant),
        trimester=int(trimester) if pregnant and trimester else None, conditions=_lines(conds), allergies=al,
        allergy_status_recorded=bool(allergy_recorded),
        current_meds=[m.strip() for m in (meds if isinstance(meds, list) else _lines(meds)) if m and m.strip()],
        uti_courses_6m=int(courses or 0), culture_resistant_to=_lines(resistant), missed_collections=int(missed or 0),
        notes=notes or "", urine_culture=(culture or "not recorded").lower(), clear_cultures_12m=int(clear_tests or 0),
        antibiotic_days_12m=int(abx_days or 0), **flags)


def load_preset(name):
    p = PRESETS[name]
    return (p.ref, p.age, p.sex, p.egfr, p.pregnant, p.trimester or 1, IND_LABEL[p.proposal.indication], p.proposal.drug,
            p.proposal.dose, p.proposal.frequency, p.proposal.duration_days, list(p.current_meds), "; ".join(p.conditions),
            "; ".join(f"{a.substance}:{a.reaction}" for a in p.allergies), p.allergy_status_recorded,
            [k for k, v in FUNCTION_FLAGS.items() if getattr(p, v)], p.uti_courses_6m, "; ".join(p.culture_resistant_to),
            p.missed_collections, p.notes, p.urine_culture, p.clear_cultures_12m, p.antibiotic_days_12m)


def banner(res) -> str:
    c, bg, word = STATUS[res.outcome]
    extra = ""
    if res.draft:
        extra = f"<div class='line'><b>Draft for your decision:</b> {escape(res.draft)}</div>"
    if res.alternative:
        extra = f"<div class='line'><b>Safer option suggested:</b> {escape(res.alternative)}</div>"
    if res.triage_signals:
        extra += f"<div class='line'>Picked up from the notes: {escape(', '.join(s.replace('_', ' ') for s in res.triage_signals))}</div>"
    return (f"<div class='vm-banner' style='--c:{c};--bg:{bg}'><div class='big'>{word}</div>"
            f"<div class='line'>{escape(res.headline)}</div>{extra}</div>")


def findings_html(res) -> str:
    names = {c["agent"]: c["name"] for c in res.convened}
    out = []
    for f in res.findings:
        c, bg, tag = LEVEL_STYLE[f.level]
        out.append(f"<div class='vm-card' style='--c:{c};--bg:{bg}'><div class='t'><span class='vm-tag'>{tag}</span>{escape(f.title)}</div>"
                   f"<div class='d'>{escape(f.detail)}</div>"
                   f"<div class='s'>Raised by: {escape(names.get(f.agent, f.agent))} · Rule {escape(f.code)} · Source: {escape(f.source)}</div></div>")
    checks = "".join(f"<div>{'✅' if ok else '❌'} {escape(k)}</div>" for k, ok in res.safety_check.items())
    opt = "".join(f"<li>{escape(o)}</li>" for o in res.optimisation) or "<li>No simpler regimen identified.</li>"
    return ("<h3>What the experts found</h3>" + "".join(out) +
            f"<h3>Safety double-check</h3><div class='vm-check'>{checks}</div>"
            f"<h3>Making it easier to take</h3><ul class='vm-check'>{opt}</ul>"
            f"<p class='vm-check' style='font-size:.9rem'>Case fingerprint: {res.case_hash[:16]}…</p>")


def med_review_html(res) -> str:
    """Side effects of the new medicine, then one row for every existing medicine."""
    p = res.patient
    drug = kb.normalise(p.proposal.drug)
    fx = medreview.effect_list(drug)
    if not kb.known(drug):
        fx_html = "<div class='vm-warn'>This medicine is not in the demo knowledge base, so its side effects could not be listed or checked.</div>"
    else:
        chips = "".join(f"<span class='vm-chip'>{escape(e)}</span>" for e in fx) or "None listed in the demo set."
        fx_html = f"<div class='vm-check'><b>Main recognised side effects of {escape(drug)}:</b><br>{chips}</div>"
    fx_html += f"<div class='vm-check' style='margin-top:8px'><b>Dose check:</b> {escape(medreview.dose_summary(p))}</div>"
    rows = medreview.review_table(drug, p.current_meds)
    if not rows:
        table = "<div class='vm-check'>No existing medicines were entered, so there was nothing to check the new medicine against.</div>"
    else:
        style = {"STOP": ("#dc3c3d", "#fdecec"), "CAUTION": ("#b77900", "#fff6df"), "NOT CHECKED": ("#666666", "#eeeeee"), "No clash found": ("#008a17", "#eaf7ec")}
        body = ""
        for r in rows:
            c, bg = style[r["verdict"]]
            body += (f"<tr><td><b>{escape(r['medicine'])}</b></td><td>{escape(r['interaction'])}</td><td>{escape(r['shared'])}</td>"
                     f"<td><span class='vm-pill' style='background:{bg};color:{c};border:1px solid {c}'>{escape(r['verdict'])}</span></td>"
                     f"<td>{escape(r['note'])}</td></tr>")
        table = ("<table class='vm-table'><thead><tr><th>Existing medicine</th><th>Named interaction with the new medicine</th>"
                 "<th>Side effects both cause</th><th>Result</th><th>What to do</th></tr></thead><tbody>" + body + "</tbody></table>")
    return (f"<h3>New medicine checked against each existing medicine ({len(rows)})</h3>{fx_html}{table}"
            "<p class='vm-check' style='font-size:.9rem'>Side effects and interactions come from a short illustrative list, not the full "
            "product information. 'No clash found' means none in this list.</p>")


PAGES = ["home", "request", "meeting", "list", "data", "assurance", "log", "ledger", "about"]
# Runs in the browser before a page change. It must hand the inputs back unchanged.
SCROLL_TOP = "(...args) => { window.scrollTo({top: 0, behavior: 'smooth'}); return args; }"


HIDE = False   # a page that is not the current one is taken off the screen entirely


def nav(page: str):
    """Show one page and hide the rest (each feature has its own page)."""
    return [gr.update(visible=True if p == page else HIDE) for p in PAGES]


def say(transcript, who: dict, text: str, you: bool = False):
    return (transcript or []) + [{"name": who["name"], "colour": who["colour"], "text": text, "you": you}]


YOU = {"name": "You (prescriber)", "colour": "#0f766e"}


def transcript_html(transcript) -> str:
    if not transcript:
        return "<div class='vm-talk'><div class='vm-check'>The meeting has not started.</div></div>"
    rows = ""
    for m in reversed(transcript):          # newest first, so the latest answer is always in view
        side = "you" if m["you"] else "them"
        rows += (f"<div class='vm-msg {side}'><div class='vm-av' style='background:{m['colour']}'>{escape(m['name'][0])}</div>"
                 f"<div class='vm-bub'><div class='vm-who' style='color:{m['colour']}'>{escape(m['name'])}</div>{escape(m['text'])}</div></div>")
    return f"<div class='vm-talk' id='vm-talk'>{rows}</div>"


def board_html(res) -> str:
    """Where each expert stands, and the team's overall position."""
    col = {RED: ("#dc3c3d", "#fdecec"), AMBER: ("#b77900", "#fff6df"), INFO: ("#008a17", "#eaf7ec")}
    cells = ""
    for p in meeting.positions(res):
        c, bg = col[p["level"]]
        cells += (f"<div class='vm-seat'><span class='vm-dot' style='background:{p['colour']}'></span><b>{escape(p['name'])}</b>"
                  f"<span class='vm-pill' style='background:{bg};color:{c};border:1px solid {c};float:right'>{room3d.SHAPE[p['level']]} {escape(p['position'])}</span></div>")
    return (f"<h3>Where the team stands</h3><div class='vm-check'><b>{escape(meeting.tally(res))}</b></div>{cells}")


PANELS = ["Talk", "Team board", "Try a change", "Details", "Patient summary", "Decide"]
STEPS = ["1 · The patient", "2 · The medicine", "3 · Tests and history"]
OFF = "vm-off"


def show_only(names, chosen, base):
    """Switch sections on and off by style, so every field stays loaded and keeps its value."""
    return [gr.update(elem_classes=[base] if n == chosen else [base, OFF]) for n in names]


def step_bar(i: int) -> str:
    cells = "".join(f"<div class='vm-stepc {'done' if k < i else ''} {'now' if k == i else ''}'>{escape(s)}</div>" for k, s in enumerate(STEPS))
    return f"<div class='vm-steps'>{cells}</div>"


def go_step(i: int):
    i = max(0, min(len(STEPS) - 1, int(i)))
    return [i, step_bar(i)] + show_only(range(len(STEPS)), i, "vm-step") + \
           [gr.update(visible=i > 0), gr.update(visible=i < len(STEPS) - 1)]


def set_view(view: str):
    """Quick view hides the room and goes straight to the decision; full view shows everything."""
    quick = view == "Quick view"
    panel = "Decide" if quick else "Talk"
    return [gr.update(elem_classes=["vm-left", OFF] if quick else ["vm-left"]), gr.update(value=panel)] + show_only(PANELS, panel, "vm-panel")


def keypoints_html(res) -> str:
    pts = meeting.key_points(res)
    if not pts:
        body = "<div class='vm-seat'>✓ No cautions or objections from the team.</div>"
    else:
        body = "".join(f"<div class='vm-seat'><b style='color:{LEVEL_STYLE[lv][0]}'>{LEVEL_STYLE[lv][2]}</b> &nbsp;{escape(t)}</div>" for lv, t in pts)
    return f"<h3>Key points before you decide</h3><div class='vm-check'><b>{escape(meeting.tally(res))}</b></div>{body}"


def patient_html(res) -> str:
    s = meeting.patient_summary(res)
    look = ("<p><b>Things to look out for:</b> " + escape(", ".join(s["look_out_for"])) + ".</p>") if s["look_out_for"] else ""
    checking = (f"<p>Your prescriber is checking {s['being_checked']} point(s) before deciding.</p>" if s["being_checked"] else "")
    return ("<div class='vm-patient'><div class='big'>Summary in plain words</div>"
            f"<p>{escape(s['opening'])}</p>{look}{checking}<p>{escape(s['closing'])}</p></div>"
            "<p class='vm-check' style='font-size:.9rem'>A draft for the prescriber to read out or adapt. It is not advice from a computer to a patient.</p>")


def spotlight_click(res, when, name):
    if res is None:
        return gr.update()
    who = _expert(res, name)
    return room3d.render(res, when.strftime("%a %d %b %Y, %H:%M") if when else "", spotlight=who["agent"] if who else "")


def _meeting_outputs(res, when, transcript):
    humans = [f"{c['name']}: {c['note']}" for c in res.convened if c["human"]]
    escalated = res.outcome in ("RED", "HARD_STOP")
    allowed = [v for k, v in DECISIONS.items() if (k in ("ACCEPT_ALTERNATIVE", "OVERRIDE", "REJECT") if escalated
                                                    else k in ("APPROVE", "APPROVE_WITH_CHANGES", "REJECT"))]
    if escalated and not res.alternative:
        allowed.remove(DECISIONS["ACCEPT_ALTERNATIVE"])
    names = [c["name"] for c in res.convened]
    pr = res.patient.proposal
    return (res, when, transcript, banner(res), room3d.render(res, when.strftime("%a %d %b %Y, %H:%M")), transcript_html(transcript),
            board_html(res), med_review_html(res) + findings_html(res),
            gr.update(choices=names, value=None), gr.update(choices=allowed, value=None), gr.update(choices=humans, value=[]),
            gr.update(visible=res.outcome == "AMBER", value=False),
            pr.drug, pr.dose, pr.frequency, pr.duration_days, gr.update(visible=bool(res.alternative_proposal)), "", None,
            keypoints_html(res), patient_html(res))


def convene_click(notary, consent, time_mode, custom_time, live, delay, *fields):
    try:
        p = build_patient(*fields)
    except (TypeError, ValueError) as exc:
        raise gr.Error(f"Please check the numbers entered: {exc}")
    if not p.proposal.drug:
        raise gr.Error("Enter the medicine you want to prescribe.")
    when = datetime.now()
    if time_mode != "Now":
        try:
            when = datetime.strptime((custom_time or "").strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise gr.Error("Write the time like this: 2026-11-28 02:30")
    notary = notary or {"n": Notary(), "salt": new_salt(), "last": None}
    if not consent:
        raise gr.Error("The consent smart contract refused the request: tick the box in step 3 to record that the patient has agreed to a virtual MDT review.")
    res = run_case(p, when=when, live_evidence=bool(live), demo_delay=bool(delay))
    note = _to_ledger(notary, res)
    transcript = say([], meeting.CHAIR, meeting.chair_opening(res) + note)
    return _meeting_outputs(res, when, transcript) + (notary,) + tuple(nav("meeting"))


def _to_ledger(notary, res) -> str:
    """Write consent, each expert's access and the review outcome to the ledger (fingerprints only)."""
    try:
        notary["n"].record_review(res, notary["salt"])
        b = notary["n"].ledger.blocks[-1]
        return f" Recorded on the ledger in block {b['index']}: consent, {len(res.convened)} access records and the review outcome, as fingerprints only."
    except ContractError as exc:
        return f" Ledger note: {exc}"


def _expert(res, name):
    return next((c for c in res.convened if c["name"] == name), None)


def ask_click(res, transcript, name, question):
    if res is None:
        raise gr.Error("Convene the virtual team first.")
    who = _expert(res, name)
    if who is None or not question:
        raise gr.Error("Choose an expert under 'Speak to', then a question.")
    transcript = say(transcript, YOU, f"{name}: {question}", you=True)
    transcript = say(transcript, who, meeting.answer(res, who["agent"], question))
    return transcript, transcript_html(transcript)


SIZE_JS = """(v) => { const z = {'Compact': 0.78, 'Comfortable': 1, 'Large': 1.18}[v] || 1;
  document.body.style.zoom = z;   // same effect as the browser's own zoom, but one click
  document.documentElement.style.setProperty('--vm-zoom', z);
  try { localStorage.setItem('vmdt-size', v); } catch (e) {} return v; }"""
THEME_JS = """(v) => { const b = document.body; b.classList.toggle('dark', v === 'Dark'); b.classList.toggle('vm-hc', v === 'High contrast');
  try { localStorage.setItem('vmdt-theme', v); } catch (e) {} return v; }"""
LOAD_JS = """() => { let s = 'Comfortable', t = 'Light';
  try { s = localStorage.getItem('vmdt-size') || s; t = localStorage.getItem('vmdt-theme') || t; } catch (e) {}
  const z = {'Compact': 0.78, 'Comfortable': 1, 'Large': 1.18}[s] || 1;
  document.body.style.zoom = z;   // same effect as the browser's own zoom, but one click
  document.documentElement.style.setProperty('--vm-zoom', z);
  document.body.classList.toggle('dark', t === 'Dark'); document.body.classList.toggle('vm-hc', t === 'High contrast');
  return [s, t]; }"""


def round_click(res, transcript):
    if res is None:
        raise gr.Error("Convene the virtual team first.")
    transcript = say(transcript, YOU, "Can we go round the table? Where does each of you stand?", you=True)
    for p, text in meeting.round_table(res):
        transcript = say(transcript, p, text)
    transcript = say(transcript, meeting.CHAIR, f"That is {meeting.tally(res)}. {res.headline}")
    return transcript, transcript_html(transcript)


def whatif_click(notary, res, when, transcript, drug, dose, freq, days):
    if res is None:
        raise gr.Error("Convene the virtual team first.")
    if not (drug or "").strip():
        raise gr.Error("Enter the medicine to try.")
    transcript = say(transcript, YOU, f"What if I prescribe {drug} {dose}, {freq}" + (f", for {int(days)} days" if days else "") + "?", you=True)
    new, text = meeting.what_if(res, drug, dose, freq, days, when=when)
    notary = notary or {"n": Notary(), "salt": new_salt(), "last": None}
    transcript = say(transcript, meeting.CHAIR, text + _to_ledger(notary, new))
    return _meeting_outputs(new, when, transcript) + (notary,)


def safer_click(notary, res, when, transcript):
    if res is None or not res.alternative_proposal:
        raise gr.Error("No safer option is on the table for this request.")
    alt = res.alternative_proposal
    return whatif_click(notary, res, when, transcript, alt["drug"], alt["dose"], alt["frequency"], alt["duration_days"])


def conclusion_html(c: dict) -> str:
    li = lambda xs: "".join(f"<li>{escape(x)}</li>" for x in xs)
    extra = ""
    if c["reason"]:
        extra += f"<div class='line'><b>Reason recorded:</b> {escape(c['reason'])}</div>"
    if c["stops"]:
        extra += f"<div class='line'><b>Objections raised:</b><ul>{li(c['stops'])}</ul></div>"
    if c["cautions"]:
        extra += f"<div class='line'><b>Cautions to act on:</b><ul>{li(c['cautions'])}</ul></div>"
    if c["tell_patient"]:
        extra += f"<div class='line'><b>Side effects to mention to the patient:</b> {escape(', '.join(c['tell_patient']))}</div>"
    if c["human_advice"]:
        extra += f"<div class='line'><b>Human advice requested from:</b> {escape('; '.join(c['human_advice']))}</div>"
    return (f"<div class='vm-final'><div class='big'>Final conclusion of the meeting</div>"
            f"<div class='rx'>{escape(c['final_prescription'])}</div>"
            f"<div class='line'><b>Decision:</b> {escape(c['decision'])} · <b>Decided by:</b> {escape(c['decided_by'])} · {escape(c['time_utc'])} UTC</div>"
            f"<div class='line'><b>Team position at close:</b> {escape(c['team'])}</div>{extra}"
            f"<div class='line' style='font-size:.9rem'>Decision log record {escape(c['log_record'])} · case {escape(c['case'])}</div></div>")


def sign_click(notary, res, log, transcript, clinician, role, decision_label, ack, changes, reason, advice):
    if res is None:
        raise gr.Error("Convene the virtual team first.")
    log = log or AuditLog()
    key = next((k for k, v in DECISIONS.items() if v == decision_label), "")
    ok, msg, rec = sign_off(res, key, clinician, role, log, reason=reason, changes=changes, acknowledged=bool(ack), human_advice=advice)
    if not ok:
        box = f"<div class='vm-banner' style='--c:#dc3c3d;--bg:#fdecec'><div class='line'>{escape(msg)}</div></div>"
        return log, transcript, transcript_html(transcript), box, None, audit_table(log), audit_file(log), log_status(log), notary
    c = meeting.conclusion(res, rec, role)
    receipt_html = ""
    if notary:
        try:
            r = notary["n"].record_decision(res, rec, notary["salt"], role, clinician, bool(ack))
            notary["last"] = {"rx": rec.get("final_prescription") or "", "code": notary["salt"], "receipt": r}
            receipt_html = receipt_card(notary, r, rec)
        except ContractError as exc:
            receipt_html = f"<div class='vm-warn'>The smart contract did not record this decision: {escape(str(exc))}</div>"
    transcript = say(transcript, YOU, f"My decision: {decision_label}.", you=True)
    transcript = say(transcript, meeting.CHAIR, f"Recorded. Final prescription: {c['final_prescription']}. The meeting is closed.")
    path = os.path.join(tempfile.mkdtemp(), "vmdt_meeting_conclusion.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(meeting.conclusion_text(c))
    return log, transcript, transcript_html(transcript), conclusion_html(c) + receipt_html, path, audit_table(log), audit_file(log), log_status(log), notary


def receipt_card(notary, r, rec) -> str:
    ok = notary["n"].ledger.verify_receipt(r)
    rx = rec.get("final_prescription")
    check = (f"<div class='line'><b>For the pharmacy:</b> prescription text <code>{escape(rx)}</code> with verification code "
             f"<code>{escape(notary['salt'])}</code> can be checked on the Blockchain ledger page.</div>") if rx else ""
    return ("<div class='vm-receipt'><div class='big'>⛓ Blockchain receipt</div>"
            f"<div class='line'><b>Block</b> {r['block']} · <b>record fingerprint</b> <code>{r['tx_hash'][:24]}…</code></div>"
            f"<div class='line'><b>Signed by</b> {escape(', '.join(r['signed_by']))} · <b>proof</b> {len(r['proof'])} step(s) · "
            f"<b>checked</b> {'✓ valid' if ok else '✕ INVALID'}</div>{check}"
            "<div class='line' style='font-size:.9rem'>Only fingerprints are on the chain: no patient, clinician or medicine details.</div></div>")


def ledger_view(notary):
    """Tables for the Blockchain ledger page."""
    if not notary or not notary["n"].ledger.blocks:
        return "No blocks yet. Convene a virtual MDT and the first block is written.", pd.DataFrame(), pd.DataFrame()
    L = notary["n"].ledger
    blocks = pd.DataFrame([{"Block": b["index"], "Time (UTC)": b["time_utc"], "Proposed by": b["proposer"],
                            "Signed by": ", ".join(sorted(b["signatures"])), "Records": b["tx_count"],
                            "Block fingerprint": b["hash"][:16] + "…", "Previous block": b["prev_hash"][:16] + "…"} for b in L.blocks])
    short = lambda v: (v[:12] + "…") if isinstance(v, str) and len(v) == 64 else v
    ev = pd.DataFrame([{"Block": e["block"], "Record type": e["type"], "Patient": short(e.get("patient", "")),
                        "Case": short(e.get("case", "")), "Detail": e.get("accessor") or e.get("outcome") or e.get("status") or e.get("purpose") or "",
                        "Prescription": short(e.get("rx") or "")} for e in L.events()])
    n_rec = sum(b["tx_count"] for b in L.blocks)
    return (f"**{len(L.blocks)} block(s), {n_rec} record(s).** Chain check: {'✓ intact, every block signed by a quorum' if L.verify_chain() else '✕ BROKEN'}.",
            blocks, ev)


def tamper_test(notary):
    """Change one old record on a COPY of the chain and show that the change is caught."""
    import copy
    if not notary or not notary["n"].ledger.blocks:
        raise gr.Error("There is nothing on the ledger yet.")
    forged = copy.deepcopy(notary["n"].ledger)
    tx = forged.blocks[0]["transactions"][0]["tx"]
    before = tx.get("type")
    tx["type"] = "FORGED"
    return (f"<div class='vm-banner' style='--c:#dc3c3d;--bg:#fdecec'><div class='line'><b>Tamper test on a copy:</b> the first record in block 0 was "
            f"changed from {escape(str(before))} to FORGED. Chain check on the copy: <b>{'still passes (problem!)' if forged.verify_chain() else '✕ fails, so the change is detected'}</b>. "
            f"The real ledger is untouched: {'✓ intact' if notary['n'].ledger.verify_chain() else '✕ broken'}.</div></div>")


def pharmacy_check(notary, rx_text, code):
    if not notary:
        raise gr.Error("There is nothing on the ledger yet.")
    ok = notary["n"].rx.is_valid_prescription((rx_text or "").strip(), (code or "").strip())
    c, bg, msg = (("#0aac23", "#eaf7ec", "✓ Genuine: exactly this prescription was signed by a prescriber and the chain is intact.") if ok else
                  ("#dc3c3d", "#fdecec", "✕ Not found: this text and code do not match any signed prescription. It may have been altered or never signed."))
    return f"<div class='vm-banner' style='--c:{c};--bg:{bg}'><div class='line'>{msg}</div></div>"


def last_receipt(notary):
    if not notary or not notary.get("last"):
        return "", ""
    return notary["last"]["rx"], notary["last"]["code"]


def log_status(log) -> str:
    if not log or not log.records:
        return "No decisions recorded in this session yet."
    return f"**{len(log.records)} decision(s) recorded.** Chain check: {'intact' if log.verify() else 'BROKEN - the log has been altered'}."


def audit_table(log) -> pd.DataFrame:
    rows = [{"No.": r["seq"], "Time (UTC)": r["time_utc"], "Role": r["role"], "Outcome": r["outcome"], "Decision": r["decision"],
             "Final prescription": r["final_prescription"] or "none", "Reason": r["reason"], "Record hash": r["hash"][:12]}
            for r in (log.records if log else [])]
    return pd.DataFrame(rows)


def audit_file(log):
    if not log or not log.records:
        return None
    path = os.path.join(tempfile.mkdtemp(), "vmdt_audit_log.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in log.records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return path


# ------------------------------------------------------------- charts
def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c2c2c2")
    ax.tick_params(colors="#666666", labelsize=13)
    ax.grid(axis="y" if ax.name == "rectilinear" else "both", color="#e7e7e7", linewidth=0.8)
    ax.set_axisbelow(True)


def batch_run(file, use_synth, rank=False):
    if file is not None and not use_synth:
        df = pd.read_csv(file if isinstance(file, str) else file.name)
        label = f"your file ({len(df)} rows)"
    else:
        df = synthetic_cohort(200)
        label = "200 invented patients (made-up proportions, not real epidemiology)"
    missing = {"patient_ref", "age", "sex", "proposed_drug"} - set(df.columns)
    if missing:
        raise gr.Error(f"The file is missing these columns: {', '.join(sorted(missing))}")
    out = review_frame(df)
    ml_note = ""
    if rank:
        try:
            from vmdt import riskmodel
            from vmdt.batch import row_to_patient
            m = riskmodel.train_and_evaluate()
            out["priority"] = [round(v, 3) for v in riskmodel.score(m["model"], [row_to_patient(r) for r in df.to_dict("records")])]
            out = out.sort_values("priority", ascending=False).reset_index(drop=True)
            ml_note = (f"\n\n**Learned priority score.** A small machine-learning model was trained on {m['n_train']:,} invented patients and tested on "
                       f"{m['n_test']:,} others: it placed {m['found_in_top_10pct']} of the {m['escalated_in_test']} escalated requests in the top tenth of the list "
                       f"(AUC {m['auc']:.2f}). It only orders the list; the rules still reviewed every request. Because the patients are invented and "
                       "labelled by the same rules, this shows the method works, not clinical accuracy.")
        except Exception as exc:
            ml_note = f"\n\nThe learned priority score could not be produced ({type(exc).__name__}); the list is in its original order."
    order = ["GREEN", "AMBER", "RED", "HARD_STOP"]
    names = {"GREEN": "Ready", "AMBER": "Ready with cautions", "RED": "Escalated", "HARD_STOP": "Hard stop"}
    cols = {"GREEN": "#0aac23", "AMBER": "#fbb315", "RED": "#dc3c3d", "HARD_STOP": "#7a1c1d"}
    tab = out.groupby(["indication", "outcome"]).size().unstack(fill_value=0).reindex(columns=order, fill_value=0)
    tab.index = [IND_LABEL.get(i, i) for i in tab.index]
    fig, ax = plt.subplots(figsize=(10, 1.2 + 0.9 * len(tab)), dpi=110)
    left = pd.Series(0, index=tab.index)
    for o in order:
        if tab[o].sum() == 0:
            continue
        bars = ax.barh(tab.index, tab[o], left=left, color=cols[o], edgecolor="white", linewidth=2, label=names[o], height=0.55)
        for b, v in zip(bars, tab[o]):
            if v >= max(3, 0.04 * tab.sum(axis=1).max()):
                ax.text(b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2, str(v), ha="center", va="center",
                        fontsize=13, color="#0b0b0b" if o == "AMBER" else "white", fontweight="bold")
        left = left + tab[o]
    _style(ax); ax.grid(False); ax.invert_yaxis()
    ax.set_xlabel("Number of prescribing requests", fontsize=13, color="#666666")
    ax.set_title("Outcome of the virtual MDT review, by condition", fontsize=16, loc="left", color="#191919")
    ax.legend(frameon=False, fontsize=12, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.28 if len(tab) > 1 else -0.6))
    fig.tight_layout()
    codes = out["rule_codes"].str.split(";").explode()
    codes = codes[codes.astype(bool)]
    top = codes.value_counts().head(10).rename_axis("Rule code").reset_index(name="Times raised")
    titles = out.attrs.get("titles", {})
    top["Example"] = top["Rule code"].map(titles).fillna("")
    n = len(out)
    esc = int(out["outcome"].isin(["RED", "HARD_STOP"]).sum())
    summary = (f"### Reviewed {label}\n\n**{esc} of {n}** requests ({esc / n:.0%}) were escalated, "
               f"**{int((out['outcome'] == 'AMBER').sum())}** carry cautions and **{int((out['outcome'] == 'GREEN').sum())}** were clear. "
               "Every row still needs a clinician's decision." + ml_note)
    path = os.path.join(tempfile.mkdtemp(), "vmdt_batch_review.csv")
    out.to_csv(path, index=False)
    show = out.rename(columns={"patient_ref": "Case", "indication": "Treating", "proposed": "Medicine", "outcome": "Outcome",
                               "priority": "Priority score", "red": "Stops", "amber": "Cautions", "top_finding": "Main finding", "rule_codes": "Rule codes",
                               "safer_option": "Safer option"})
    return summary, fig, top, show, path


def trends(ind_label, file=None):
    ind = INDICATIONS[ind_label]
    if file:
        df, msg = opendata.trends_from_csv(file if isinstance(file, str) else file.name)
    else:
        df, msg = opendata.nhsbsa_trends(ind)
    if df.empty:
        return f"<div class='vm-warn'>{escape(msg)}</div>", None, pd.DataFrame()
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=110)
    order = df.groupby("medicine")["items"].sum().sort_values(ascending=False).index[:8]
    for i, med in enumerate(order):
        d = df[df["medicine"] == med].sort_values("date")
        ax.plot(d["date"], d["items"] / 1000, color=SERIES[i], linewidth=2, label=med)
        ax.annotate(med.split()[0], (d["date"].iloc[-1], d["items"].iloc[-1] / 1000), xytext=(6, 0), textcoords="offset points",
                    fontsize=11, color="#191919", va="center")
    _style(ax)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Items prescribed per month (thousands)", fontsize=13, color="#666666")
    ax.set_title("Items in your uploaded file" if file else f"{opendata.CONDITION_LABEL[ind]}: items prescribed in English primary care",
                 fontsize=16, loc="left", color="#191919")
    ax.legend(frameon=False, fontsize=12, ncol=3, loc="upper left", bbox_to_anchor=(0, -0.1))
    ax.margins(x=0.12)
    fig.tight_layout()
    return f"<div class='vm-check'>{escape(msg)}</div>", fig, opendata.summarise(df)


def run_targets():
    rows = evaluate()
    df = pd.DataFrame([{"Target": t, "What is measured": n, "Result": v, "Required": req, "Met": "Yes" if ok else "NO"} for t, n, v, req, ok in rows])
    gate = "Release gate OPEN: all targets met." if all(r[4] for r in rows) else "Release gate BLOCKED: at least one target failed."
    return df, gate


# ------------------------------------------------------------------ layout
ABOUT = f"""
## What this is
**VirtualMDT-Rx v{__version__}** turns the idea in *A Multiagent AI Framework for Parallelised Prescription Decision Support in
Primary Care* (Rajagopal, Jagini and Ramachandran, ABH 2026) into something you can try. In hospital, a prescription is often looked
at by a team: the multidisciplinary team, or MDT. A GP usually prescribes alone. This tool gathers a **virtual** team for every
request, runs all the experts at the same moment, and hands the prescriber a checked draft with the reasons.

## What is new compared with the paper
1. **The team changes with the case.** Six core experts always attend, including a side-effect check. A microbiologist, urologist, diabetologist, oncologist,
   kidney physician or geriatrician is called in only when the case needs them.
2. **An interactive meeting.** After the review you can question any expert, go round the table, put a changed prescription
   to the team and see who changes position, then close the meeting with a written conclusion.
3. **A 3D consulting room with an availability rota.** Each expert shows whether its human counterpart can be reached right now,
   and the prescriber can log a request for human advice.
3. **A stronger human-in-the-loop step.** Nothing is issued without a named clinician's decision. An escalated case cannot simply be
   approved: the clinician picks the safer option, declines, or overrides with a written reason.
4. **A safety double-check that does not trust the experts.** The hard rules are re-run separately; anything an expert missed is added back.
5. **A medicine-by-medicine check.** The new medicine's side effects are listed, and it is checked against every existing
   medicine for named interactions and for side effects that add up. Anything that cannot be checked is shown as not checked.
6. **Dose, infection and exposure checks.** The dose is compared with the usual and maximum dose. An antibiotic is not drafted
   when the lab test found no infection; repeated clear tests point the prescriber towards inflammation instead. Total days of
   antibiotics over 12 months are counted, with a warning for heavy exposure and long-term nitrofurantoin.
7. **Whole-list review.** A practice list can be reviewed in one run, and live NHS open data shows what is actually being prescribed.
8. **Blockchain for privacy and trust.** Consent, each expert's access, the review outcome and the decision are written to a
   permissioned ledger as fingerprints only. Two smart contracts enforce consent and the sign-off rules independently of the app, each
   decision gets a receipt with a short proof, and a pharmacy can confirm a prescription is genuine.
9. **A learned priority score (optional).** On a long list, a small machine-learning model puts the requests most likely to be escalated
   first. It only orders the list; the rules still review every request.
10. **Built with a software engineering method.** Twenty-eight requirements traced to tests, ten acceptance targets, a release gate and a
   tamper-evident log (the same approach as UroAgent).

## Limits you must know
* The medicine rules are a **small, paraphrased, illustrative set** written for a demonstration. They are incomplete and are not kept
  up to date. They are **not** the BNF, NICE guidance or a licensed drug database.
* All patients are **invented**. The acceptance results show the engineering controls work; they say nothing about real patients.
* The experts are rule-based programs, not language models and not real clinicians. The 3D figures are drawings.
* This is **not a medical device** and must not be used to make real prescribing decisions. Do not enter real patient details.
"""

PRINCIPLES = pd.DataFrame([
    ["1 Goal-driven, testable requirements", f"{len(REQUIREMENTS)} requirements, each naming the tests that prove it"],
    ["2 Safety rules outside the model", "Rules are plain data in knowledge.py; an independent double-check re-runs them; smart contracts enforce sign-off rules again"],
    ["3 One agent, one job", "12 single-purpose experts; each sees only its own slice of the record, and each look is logged on the ledger"],
    ["4 Least-privilege tools", "Web look-ups are read-only and carry only medicine and condition names"],
    ["5 Explicit state, reproducible", "Fixed route through the orchestrator; same case gives the same fingerprint"],
    ["6 Observability and audit", "Per-expert timing and reasons on screen; hash-chained decision log; blockchain ledger with receipts"],
    ["7 Evaluate before trusting", f"{len(SUITE)} synthetic cases, 10 acceptance targets, release gate in continuous integration"],
    ["8 Human in the loop", "Named clinician decision on every case; escalations cannot be approved"],
    ["9 Ethics and privacy by design", "No identifiers held; references stored as salted hashes; honest limits stated on screen"],
], columns=["Principle", "How this tool applies it"])


def _theme():
    return gr.themes.Soft(primary_hue="teal", text_size="lg", font=["system-ui", "Segoe UI", "Arial", "sans-serif"])


# Gradio 6 takes the theme and styles in launch(); Gradio 4 and 5 take them in Blocks().
_THEME_IN_LAUNCH = "theme" in inspect.signature(gr.Blocks.launch).parameters


TILES = [  # (page, label, colour class)
    ("request", "🩺  Convene the virtual MDT\nEnter a prescription and meet the experts", "t1"),
    ("list", "📋  Review a patient list\nCheck many prescriptions in one run", "t2"),
    ("data", "📈  What is being prescribed\nLive NHS prescribing figures", "t3"),
    ("assurance", "🛠️  Engineering and assurance\nRequirements, tests and targets", "t4"),
    ("log", "🔏  Decision log\nEvery decision, tamper-evident", "t5"),
    ("ledger", "⛓  Blockchain ledger\nSmart contracts, proofs and privacy", "t7"),
    ("about", "ℹ️  About and limits\nWhat is new, and what it cannot do", "t6"),
]


def build() -> gr.Blocks:
    extra = {} if _THEME_IN_LAUNCH else {"theme": _theme(), "css": CSS}
    if "fill_width" in inspect.signature(gr.Blocks.__init__).parameters:
        extra["fill_width"] = True          # use the whole window, so Compact really shows more
    with gr.Blocks(title="VirtualMDT-Rx", **extra) as demo:
        with gr.Row(elem_classes=["vm-bar"]):
            gr.Markdown("# VirtualMDT-Rx\nA virtual multidisciplinary team for safer prescribing", elem_classes=["vm-title"])
            size = gr.Dropdown(["Compact", "Comfortable", "Large"], label="Display size", value="Comfortable", scale=0, min_width=200)
            theme_pick = gr.Dropdown(["Light", "Dark", "High contrast"], label="Colours", value="Light", scale=0, min_width=200)
        gr.HTML("<div class='vm-warn vm-thin'><b>Research demonstrator on invented data. Not a medical device.</b> "
                "Do not enter real patient details. The rules are a small illustrative set, not the BNF or NICE guidance. "
                "A qualified clinician makes every prescribing decision.</div>")
        state, log_state, when_state, talk_state = gr.State(None), gr.State(None), gr.State(None), gr.State([])
        notary_state = gr.State(None)
        homes = []

        def home_button():
            b = gr.Button("⬅  Home", elem_classes=["vm-home"], scale=0)
            homes.append(b)
            return b

        # ------------------------------------------------------------ HOME
        with gr.Column(visible=True, elem_classes=["vm-page"]) as pg_home:
            gr.Markdown("### Choose what you want to do")
            tiles = {}
            for row in (TILES[:4], TILES[4:]):
                with gr.Row(elem_classes=["vm-tiles"]):
                    for page, label, cls in row:
                        tiles[page] = gr.Button(label, elem_classes=["vm-tile", cls])

        # --------------------------------------------------------- REQUEST
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_request:
            with gr.Row():
                home_button()
                gr.Markdown("## The prescribing request")
            preset = gr.Dropdown(list(PRESETS), label="Try an example case (fills in all three steps)", value=None)
            step_state = gr.State(0)
            step_html = gr.HTML(step_bar(0))
            with gr.Column(elem_classes=["vm-step"]) as st0:
                with gr.Row():
                    ref = gr.Textbox(label="Case reference (no names)", value="CASE-001")
                    age = gr.Number(label="Age", value=60, precision=0)
                    sex = gr.Radio(["female", "male"], label="Sex", value="female")
                    egfr = gr.Number(label="Kidney function (eGFR)", value=90)
                with gr.Row():
                    pregnant = gr.Checkbox(label="Pregnant")
                    trimester = gr.Dropdown([1, 2, 3], label="Trimester", value=1)
                    allergies = gr.Textbox(label="Allergies, as substance:reaction", placeholder="penicillin:anaphylaxis", scale=2)
                    allergy_rec = gr.Checkbox(label="Allergy status recorded", value=True)
                meds = gr.Dropdown(sorted(kb.DRUGS), label="Existing medicines (pick from the list, or type a name and press Enter)",
                                   multiselect=True, allow_custom_value=True, value=[])
                with gr.Row():
                    conds = gr.Textbox(label="Conditions (separate with ;)")
                    function = gr.CheckboxGroup(list(FUNCTION_FLAGS), label="Day-to-day function", value=[])
            with gr.Column(elem_classes=["vm-step", OFF]) as st1:
                with gr.Row():
                    indication = gr.Dropdown(list(INDICATIONS), label="Treating", value="Urine infection (UTI)")
                    drug = gr.Dropdown(sorted(kb.DRUGS), label="Medicine to prescribe", allow_custom_value=True, value="nitrofurantoin")
                with gr.Row():
                    dose = gr.Textbox(label="Dose", value="100 mg modified-release")
                    freq = gr.Dropdown(FREQS, label="How often", value="twice daily")
                    days = gr.Number(label="Days (blank = ongoing)", value=3, precision=0)
                notes = gr.Textbox(label="Free-text notes (screened for warning phrases)", lines=2)
            with gr.Column(elem_classes=["vm-step", OFF]) as st2:
                with gr.Row():
                    culture = gr.Dropdown(CULTURE_CHOICES, label="Latest urine lab test (culture)", value="not recorded")
                    clear_tests = gr.Number(label="Lab tests in 12 months that found NO infection", value=0, precision=0)
                    abx_days = gr.Number(label="Total days of antibiotics in 12 months", value=0, precision=0)
                with gr.Row():
                    courses = gr.Number(label="Antibiotic courses for UTI in 6 months", value=0, precision=0)
                    resistant = gr.Textbox(label="Recent culture resistant to (separate with ;)")
                    missed = gr.Number(label="Prescriptions not collected recently", value=0, precision=0)
                consent = gr.Checkbox(label="The patient has agreed to a virtual MDT review of their medicines (recorded on the ledger by the consent smart contract)", value=True)
                with gr.Accordion("Time of consultation and options", open=False):
                    time_mode = gr.Radio(["Now", "Choose a time"], label="Show expert availability for", value="Now")
                    custom_time = gr.Textbox(label="Time (YYYY-MM-DD HH:MM)", value="2026-11-28 02:30")
                    live = gr.Checkbox(label="Search PubMed for recent safety papers (sends the medicine and condition names only)")
                    delay = gr.Checkbox(label="Add made-up 'thinking time' to each expert, to show the benefit of working in parallel")
            with gr.Row():
                back_step = gr.Button("⬅  Back", elem_classes=["vm-home"], visible=False, scale=0)
                next_step = gr.Button("Next  ➜", elem_classes=["vm-home", "vm-next"], scale=0)
                go = gr.Button("🩺  Convene the virtual MDT  ➜  open the meeting room", elem_classes=["vm-tile", "t1", "vm-wide"], elem_id="convene-btn")

        # --------------------------------------------------------- MEETING
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_meeting:
            with gr.Row():
                home_button()
                back_req = gr.Button("✏️  Edit request", elem_classes=["vm-home"], scale=0)
                gr.Markdown("## The virtual MDT meeting")
                view = gr.Dropdown(["Full view", "Quick view"], label="View", value="Full view", scale=0, min_width=200)
            out_banner = gr.HTML()
            with gr.Row(equal_height=False):
                with gr.Column(scale=7, min_width=420, elem_classes=["vm-left"]) as left_col:
                    out_room = gr.HTML(room3d.empty_room(), elem_classes=["vm-fit"])
                with gr.Column(scale=5, min_width=380):
                    panel = gr.Radio(PANELS, label="Show", value="Talk", elem_classes=["vm-seg"])
                    with gr.Column(elem_classes=["vm-panel"]) as p_talk:
                        with gr.Row():
                            who = gr.Dropdown([], label="Speak to (lit up in the room)")
                            question = gr.Dropdown(meeting.QUESTIONS, label="Ask", value=meeting.QUESTIONS[0])
                        with gr.Row():
                            ask = gr.Button("Ask this expert", variant="primary")
                            around = gr.Button("Go round the table")
                        out_talk = gr.HTML()
                    with gr.Column(elem_classes=["vm-panel", OFF]) as p_board:
                        out_board = gr.HTML()
                    with gr.Column(elem_classes=["vm-panel", OFF]) as p_change:
                        gr.Markdown("### Put a change to the team")
                        with gr.Row():
                            w_drug = gr.Dropdown(sorted(kb.DRUGS), label="Medicine", allow_custom_value=True)
                            w_dose = gr.Textbox(label="Dose")
                        with gr.Row():
                            w_freq = gr.Dropdown(FREQS, label="How often")
                            w_days = gr.Number(label="Days (blank = ongoing)", precision=0)
                        w_go = gr.Button("Ask the team to review this change", variant="primary")
                        w_safer = gr.Button("Try the team's safer option", visible=False)
                        gr.Markdown("The room and the team board update straight away. The chair's summary of who changed position is under **Talk**.")
                    with gr.Column(elem_classes=["vm-panel", OFF]) as p_details:
                        out_findings = gr.HTML(elem_classes=["vm-fit"])
                    with gr.Column(elem_classes=["vm-panel", OFF]) as p_patient:
                        out_patient = gr.HTML()
                    with gr.Column(elem_classes=["vm-panel", OFF]) as p_decide:
                        out_keys = gr.HTML()
                        with gr.Row():
                            clinician = gr.Textbox(label="Your clinician ID or initials")
                            role = gr.Dropdown(["GP", "Consultant", "Prescribing pharmacist", "Nurse prescriber"], label="Role", value="GP")
                        decision = gr.Radio([], label="Decision")
                        ack = gr.Checkbox(label="I have read the cautions above", visible=False)
                        changes = gr.Textbox(label="If approving with changes: the prescription as you want it")
                        reason = gr.Textbox(label="Reason (required for an override)")
                        with gr.Accordion("Also log a request for human advice", open=False):
                            advice = gr.CheckboxGroup([], label="Ask for advice from", value=[])
                        sign = gr.Button("✅  Record my decision and close the meeting", elem_classes=["vm-tile", "t6", "vm-wide"], elem_id="sign-btn")
                        out_final = gr.HTML()
                        final_dl = gr.File(label="Download the written conclusion")

        # ------------------------------------------------------------ LIST
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_list:
            with gr.Row():
                home_button()
                gr.Markdown("## Review a patient list")
            gr.Markdown("Upload a CSV of current and proposed medicines, or use the built-in list of invented patients. "
                        "Column names are listed in the README. **Do not upload identifiable patient data.**")
            with gr.Row():
                up = gr.File(label="CSV file", file_types=[".csv"], type="filepath")
                with gr.Column():
                    synth = gr.Checkbox(label="Use the 200 invented patients instead", value=True)
                    rank = gr.Checkbox(label="Put the riskiest first, using a learned priority score (machine learning; adds about 20 seconds)", value=False)
            run_b = gr.Button("Review the list", variant="primary")
            b_sum = gr.Markdown()
            b_plot = gr.Plot(label="Outcomes by condition")
            b_top = gr.Dataframe(label="Rules raised most often", interactive=False, wrap=True)
            b_tab = gr.Dataframe(label="Every request (table view of the chart)", interactive=False, wrap=True)
            b_dl = gr.File(label="Download the results")
            run_b.click(batch_run, [up, synth, rank], [b_sum, b_plot, b_top, b_tab, b_dl])

        # ------------------------------------------------------------ DATA
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_data:
            with gr.Row():
                home_button()
                gr.Markdown("## What is being prescribed")
            gr.Markdown("Monthly counts of items prescribed in English primary care, read from the official **NHS Business Services Authority** "
                        "open data portal (English Prescribing Dataset, Open Government Licence). No patient-level data is involved. "
                        "Needs internet access and can take up to a minute. If the portal cannot be reached, upload a CSV file with columns for the "
                        "month, the medicine and the number of items.")
            with gr.Row():
                t_ind = gr.Dropdown([k for k in INDICATIONS if k != "Other"], label="Medicine group", value="Urine infection (UTI)")
                t_file = gr.File(label="Or chart your own CSV file", file_types=[".csv"], type="filepath")
            t_go = gr.Button("Show the figures", variant="primary")
            t_msg = gr.HTML()
            t_plot = gr.Plot(label="Trend")
            t_tab = gr.Dataframe(label="Latest month compared with a year earlier (table view of the chart)", interactive=False, wrap=True)
            t_go.click(trends, [t_ind, t_file], [t_msg, t_plot, t_tab])

        # ------------------------------------------------------- ASSURANCE
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_assurance:
            with gr.Row():
                home_button()
                gr.Markdown("## Engineering and assurance")
            gr.Markdown("Nine principles, a V-model that pairs every requirement with a test, and a release gate: "
                        "the tool may not be released if any target fails.")
            gr.Dataframe(PRINCIPLES, interactive=False, wrap=True, label="Nine principles for healthcare AI agents")
            e_go = gr.Button("Run the 10 acceptance targets now", variant="primary")
            e_gate = gr.Markdown()
            e_tab = gr.Dataframe(interactive=False, wrap=True, label=f"Acceptance targets ({len(SUITE)} invented cases)")
            e_go.click(run_targets, None, [e_tab, e_gate])
            gr.Dataframe(pd.DataFrame([{"Requirement": r["id"], "Goal": r["goal"], "Statement": r["text"], "Principle": r["principle"],
                                        "Proved by tests": ", ".join(r["tests"])} for r in REQUIREMENTS]),
                         interactive=False, wrap=True, label="Requirements traced to tests")
            gr.Markdown("**Honest limit:** the cases and the rules were written by the same team, so a perfect score shows the controls "
                        "work as designed, not that the tool is clinically accurate. Independent cases and real, anonymised data come next.")

        # ------------------------------------------------------------- LOG
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_log:
            with gr.Row():
                home_button()
                gr.Markdown("## Decision log")
            gr.Markdown("Every decision recorded in this session. Each record carries the fingerprint of the one before it, so a change "
                        "to any earlier record is detected. Patient and clinician references are stored only as scrambled codes.")
            log_msg = gr.Markdown("No decisions recorded in this session yet.")
            audit_df = gr.Dataframe(label="Decisions in this session", interactive=False)
            audit_dl = gr.File(label="Download the decision log")

        # ---------------------------------------------------------- LEDGER
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_ledger:
            with gr.Row():
                home_button()
                gr.Markdown("## Blockchain ledger")
            gr.Markdown("A shared record that no single organisation can quietly change. **Only fingerprints are stored**: scrambled codes that "
                        "prove a record existed without showing the patient, the clinician or the medicine. Two smart contracts (rules the ledger "
                        "enforces itself) check consent and the prescribing decision. Each block is signed by two of three organisations "
                        "(GP practice, community pharmacy, ICB audit office). This is a single-computer demonstration, not a live network.")
            with gr.Row():
                l_refresh = gr.Button("Show the ledger", variant="primary")
                l_tamper = gr.Button("Tamper test (on a copy)")
            l_msg = gr.Markdown()
            l_tamper_out = gr.HTML()
            l_blocks = gr.Dataframe(label="Blocks", interactive=False, wrap=True)
            l_events = gr.Dataframe(label="Records inside the blocks (fingerprints only)", interactive=False, wrap=True)
            gr.Markdown("### Pharmacy check\nA pharmacy holding the prescription text and its verification code can confirm that exactly this "
                        "prescription was signed. Change one character and the check fails.")
            with gr.Row():
                l_rx = gr.Textbox(label="Prescription text, exactly as signed")
                l_code = gr.Textbox(label="Verification code")
            with gr.Row():
                l_fill = gr.Button("Fill in the last signed prescription")
                l_check = gr.Button("Check this prescription", variant="primary")
            l_check_out = gr.HTML()
            l_refresh.click(ledger_view, notary_state, [l_msg, l_blocks, l_events])
            l_tamper.click(tamper_test, notary_state, l_tamper_out)
            l_fill.click(last_receipt, notary_state, [l_rx, l_code])
            l_check.click(pharmacy_check, [notary_state, l_rx, l_code], l_check_out)

        # ----------------------------------------------------------- ABOUT
        with gr.Column(visible=HIDE, elem_classes=["vm-page"]) as pg_about:
            with gr.Row():
                home_button()
                gr.Markdown("## About and limits")
            gr.Markdown(ABOUT)

        # ---------------------------------------------------------- wiring
        pages = [pg_home, pg_request, pg_meeting, pg_list, pg_data, pg_assurance, pg_log, pg_ledger, pg_about]
        for page, btn in tiles.items():
            btn.click(lambda page=page: nav(page), None, pages, js=SCROLL_TOP)
        for b in homes:
            b.click(lambda: nav("home"), None, pages, js=SCROLL_TOP)
        back_req.click(lambda: nav("request"), None, pages, js=SCROLL_TOP)

        inputs = [ref, age, sex, egfr, pregnant, trimester, indication, drug, dose, freq, days, meds, conds, allergies,
                  allergy_rec, function, courses, resistant, missed, notes, culture, clear_tests, abx_days]
        preset.change(load_preset, preset, inputs)
        steps_out = [step_state, step_html, st0, st1, st2, back_step, next_step]
        next_step.click(lambda i: go_step(i + 1), step_state, steps_out)
        back_step.click(lambda i: go_step(i - 1), step_state, steps_out)
        tiles["request"].click(lambda: go_step(0), None, steps_out)

        panels = [p_talk, p_board, p_change, p_details, p_patient, p_decide]
        panel.change(lambda name: show_only(PANELS, name, "vm-panel"), panel, panels)
        view.change(set_view, view, [left_col, panel] + panels)
        meeting_out = [state, when_state, talk_state, out_banner, out_room, out_talk, out_board, out_findings, who, decision,
                       advice, ack, w_drug, w_dose, w_freq, w_days, w_safer, out_final, final_dl, out_keys, out_patient]
        go.click(convene_click, [notary_state, consent, time_mode, custom_time, live, delay] + inputs, meeting_out + [notary_state] + pages, js=SCROLL_TOP)
        who.change(spotlight_click, [state, when_state, who], out_room)
        ask.click(ask_click, [state, talk_state, who, question], [talk_state, out_talk])
        around.click(round_click, [state, talk_state], [talk_state, out_talk])
        w_go.click(whatif_click, [notary_state, state, when_state, talk_state, w_drug, w_dose, w_freq, w_days], meeting_out + [notary_state])
        w_safer.click(safer_click, [notary_state, state, when_state, talk_state], meeting_out + [notary_state])
        sign.click(sign_click, [notary_state, state, log_state, talk_state, clinician, role, decision, ack, changes, reason, advice],
                   [log_state, talk_state, out_talk, out_final, final_dl, audit_df, audit_dl, log_msg, notary_state])
        tiles["ledger"].click(ledger_view, notary_state, [l_msg, l_blocks, l_events])

        size.change(None, size, None, js=SIZE_JS)
        theme_pick.change(None, theme_pick, None, js=THEME_JS)
        demo.load(None, None, [size, theme_pick], js=LOAD_JS)
    return demo


def launch(**kwargs):
    demo = build()
    if _THEME_IN_LAUNCH:
        return demo.launch(theme=_theme(), css=CSS, **kwargs)
    return demo.launch(**kwargs)


if __name__ == "__main__":
    launch()
