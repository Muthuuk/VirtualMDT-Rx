"""Verification side of the V-model. Each test name is referenced from
vmdt/requirements_trace.py, so requirements and tests cannot drift apart."""
import copy
from datetime import datetime

import pytest

from vmdt import agents as ag
from vmdt import opendata
from vmdt.audit import AuditLog
from vmdt.batch import review_frame, synthetic_cohort
from vmdt.cases import SUITE
from vmdt.evaluate import evaluate
from vmdt.models import Finding
from vmdt.orchestrator import _payload, hard_checks, run_case, sign_off, triage
from vmdt.rota import status

CASES = {c[0].ref: c for c in SUITE}


def case(ref):
    return copy.deepcopy(CASES[ref][0])


@pytest.mark.parametrize("ref", list(CASES))
def test_suite_outcomes(ref):
    p, expected, must, not_red = CASES[ref]
    r = run_case(copy.deepcopy(p))
    assert r.outcome == expected
    assert set(must) <= {f.code for f in r.findings}
    assert not set(not_red) & {f.code for f in r.findings if f.level == "RED"}


def test_target_hazard_recall():
    assert next(row for row in evaluate() if row[0] == "T1")[4]


def test_all_targets_met():
    failed = [row[0] for row in evaluate() if not row[4]]
    assert not failed, f"release gate blocked by {failed}"


def test_double_check_catches_a_faulty_expert():
    """Swap in a pharmacist that sees nothing. The independent re-check must still stop the case."""
    registry = copy.deepcopy(ag.REGISTRY)
    registry["pharmacist"]["fn"] = lambda payload: []
    r = run_case(case("UTI-03"), registry=registry)   # trimethoprim + methotrexate
    assert r.outcome == "RED"
    assert "PH-INT-001" in {f.code for f in r.findings}
    assert r.safety_check["Experts and double-check agree"] is False


def test_scoped_payloads():
    pd = case("UTI-05").to_dict(); pd["triage"] = []; pd["live_evidence"] = False
    assert "allergies" not in _payload(pd, "ptot")
    assert "notes" not in _payload(pd, "pharmacist")          # free text goes through triage only
    assert set(_payload(pd, "literature")) == {"proposal", "live_evidence"}
    for agent in ag.REGISTRY:
        assert "ref" not in _payload(pd, agent)


def test_outbound_queries_have_no_patient_data(monkeypatch):
    sent = []

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"esearchresult": {"idlist": []}}

    monkeypatch.setattr(opendata.requests, "get", lambda url, **kw: sent.append((url, kw.get("params"))) or Resp())
    p = case("UTI-09"); p.ref = "SECRET-REF-123"
    run_case(p, live_evidence=True)
    assert sent, "the literature expert should have searched"
    blob = str(sent)
    assert "SECRET-REF-123" not in blob and "blood in urine" not in blob and "67" not in blob
    assert "nitrofurantoin" in blob


def test_deterministic():
    assert run_case(case("DM-04")).case_hash == run_case(case("DM-04")).case_hash


def test_audit_chain_detects_tampering():
    log = AuditLog()
    sign_off(run_case(case("UTI-01")), "APPROVE", "GP7", "GP", log)
    sign_off(run_case(case("UTI-02")), "REJECT", "GP7", "GP", log)
    assert log.verify()
    log.records[0]["final_prescription"] = "something else"
    assert not log.verify()


def test_audit_has_no_identifiers():
    log = AuditLog()
    p = case("UTI-01"); p.ref = "Jane-Example-1955"
    sign_off(run_case(p), "APPROVE", "dr.smith", "GP", log)
    assert "Jane-Example-1955" not in str(log.records) and "dr.smith" not in str(log.records)


def test_escalated_case_cannot_be_approved():
    r = run_case(case("UTI-03"))
    for d in ("APPROVE", "APPROVE_WITH_CHANGES"):
        assert sign_off(r, d, "GP7", "GP", AuditLog(), changes="x y z")[0] is False


def test_override_needs_reason():
    r = run_case(case("UTI-02"))
    assert sign_off(r, "OVERRIDE", "GP7", "GP", AuditLog(), reason="because")[0] is False
    ok, _, rec = sign_off(r, "OVERRIDE", "GP7", "GP", AuditLog(), reason="Culture shows resistance to all alternatives; microbiology advised a 3-day course.")
    assert ok and rec["decision"] == "OVERRIDE"


def test_amber_needs_acknowledgement():
    r = run_case(case("UTI-04"))
    assert sign_off(r, "APPROVE", "GP7", "GP", AuditLog())[0] is False
    assert sign_off(r, "APPROVE", "GP7", "GP", AuditLog(), acknowledged=True)[0] is True


def test_signoff_needs_clinician():
    assert sign_off(run_case(case("UTI-01")), "APPROVE", "", "GP", AuditLog())[0] is False


def test_no_draft_when_escalated():
    for p, expected, *_ in SUITE:
        r = run_case(copy.deepcopy(p))
        if r.outcome in ("RED", "HARD_STOP"):
            assert r.draft is None


def test_alternatives_are_safe():
    assert next(row for row in evaluate() if row[0] == "T4")[4]
    r = run_case(case("UTI-02"))
    assert r.alternative and r.alternative.lower().startswith("trimethoprim")
    assert run_case(case("UTI-17")).alternative is None       # every option blocked


def test_unknown_drug_is_flagged():
    r = run_case(case("SY-01"))
    assert r.outcome == "AMBER" and "PH-UNK-001" in {f.code for f in r.findings}
    p = case("UTI-01"); p.current_meds = ["mysterydrug 5mg"]
    assert "PH-UNK-002" in {f.code for f in run_case(p).findings}


def test_failed_expert_is_contained():
    def boom(payload):
        raise RuntimeError("feed down")
    reg = copy.deepcopy(ag.REGISTRY); reg["ptot"]["fn"] = boom
    r = run_case(case("UTI-01"), registry=reg)
    assert r.outcome == "AMBER" and r.safety_check["Every expert reported"] is False
    reg = copy.deepcopy(ag.REGISTRY); reg["allergy"]["fn"] = boom
    r = run_case(case("UTI-01"), registry=reg)
    assert r.outcome == "RED" and r.draft is None            # critical expert down: manual review


def test_triage_ignores_negation():
    assert triage("No fever, no blood in urine, denies rash.") == []
    assert set(triage("Fever overnight and visible haematuria")) == {"fever", "visible_haematuria"}
    assert "fever" in triage("No dysuria. Fever since Monday.")          # negation must not cross a sentence
    assert "fever" in triage("No dysuria, fever since Monday")           # ambiguous wording is flagged, not dropped
    assert triage("No fever or rigors") == []


def test_findings_are_traceable():
    for p, *_ in SUITE:
        for f in run_case(copy.deepcopy(p)).findings:
            assert isinstance(f, Finding) and f.agent in ag.REGISTRY and f.code and f.source and f.detail


def test_irrelevant_details_do_not_change_outcome():
    a = run_case(case("DM-02"))
    b_p = case("DM-02"); b_p.ref = "another-reference"; b_p.sex = "female"
    b = run_case(b_p)
    assert a.outcome == b.outcome and [f.code for f in a.findings] == [f.code for f in b.findings]


def test_rota_hours():
    assert status("urology", datetime(2026, 11, 25, 11, 0))["available"] is True      # Wednesday morning
    night = status("urology", datetime(2026, 11, 28, 2, 30))                           # Saturday 02:30
    assert night["available"] is False and "Mon 09:00" in night["note"]
    assert status("microbiology", datetime(2026, 11, 28, 2, 30))["available"] is True  # 24-hour cover
    assert status("guidance")["human"] is None


def test_batch_review():
    out = review_frame(synthetic_cohort(60, seed=1))
    assert len(out) == 60 and set(out["outcome"]) <= {"GREEN", "AMBER", "RED", "HARD_STOP"}
    assert review_frame(synthetic_cohort(60, seed=1)).equals(out)


def test_side_effect_checks():
    r = run_case(case("SE-02"))                                # morphine added to diazepam, patient falls
    titles = " | ".join(f.title for f in r.findings)
    assert "morphine and tramadol both cause" in titles and "drowsiness" in titles
    assert "Opioid with a benzodiazepine" in titles                       # named rule for the diazepam pair...
    assert "morphine and diazepam both cause" not in titles               # ...so it is not reported a second time
    assert any(f.code == "SE-020" for f in r.findings)
    listed = next(f for f in r.findings if f.code == "SE-000")
    assert "constipation" in listed.detail.lower() and "drowsiness" in listed.detail.lower()
    assert any(f.code == "SE-030" for f in run_case(case("SE-03")).findings)   # existing medicine behind the infections
    # a pair with a named interaction rule is not reported twice
    assert sum(f.code == "SE-010" and "warfarin" in f.title for f in run_case(case("CA-05")).findings) == 0


def test_every_existing_medicine_is_listed():
    from vmdt.medreview import review_table
    meds = ["methotrexate", "ramipril", "paracetamol", "mysterydrug 5mg", "trimethoprim"]
    rows = review_table("trimethoprim", meds)
    assert [r["medicine"] for r in rows] == meds                # one row each, same order, nothing dropped
    by = {r["medicine"]: r for r in rows}
    assert by["methotrexate"]["verdict"] == "STOP"
    assert by["ramipril"]["verdict"] == "CAUTION"
    assert by["paracetamol"]["verdict"] == "No clash found"
    assert by["mysterydrug 5mg"]["verdict"] == "NOT CHECKED"
    assert by["trimethoprim"]["verdict"] == "CAUTION"            # duplicate
    assert all(r["verdict"] == "NOT CHECKED" for r in review_table("zzzmycin", ["ramipril"]))


def test_side_effect_data_is_complete():
    from vmdt import knowledge as kb
    assert set(kb.SIDE_EFFECTS) == set(kb.DRUGS)
    used = {e for fx in kb.SIDE_EFFECTS.values() for e in fx}
    assert used <= set(kb.EFFECT_LABEL)
    assert set(kb.ADDITIVE_FAMILY) <= set(kb.EFFECT_LABEL)


def test_dose_parsing():
    from vmdt import knowledge as kb
    assert kb.parse_dose_mg("100 mg modified-release") == (100, 100)
    assert kb.parse_dose_mg("1 g") == (1000, 1000)
    assert kb.parse_dose_mg("400 mg then 200 mg") == (400, 200)
    assert kb.parse_dose_mg("40-80 mg") == (80, 80)
    assert kb.parse_dose_mg("1250 mg/m2") is None and kb.parse_dose_mg("one tablet") is None and kb.parse_dose_mg("") is None
    for drug, lim in kb.DOSE_LIMITS.items():
        assert drug in kb.DRUGS and lim["usual"] <= lim["max"]


def test_dose_checks():
    over = run_case(case("DOSE-02"))                          # nitrofurantoin 200 mg four times a day = 800 mg
    f = next(x for x in over.findings if x.code == "DO-001")
    assert over.outcome == "RED" and over.draft is None and "800 mg" in f.title and "400 mg" in f.title
    assert over.alternative and "trimethoprim" in over.alternative.lower()
    assert run_case(case("DOSE-01")).outcome == "AMBER"       # 400 mg a day: allowed, but above usual
    assert not any(x.code.startswith("DO-00") and x.level != "INFO" for x in run_case(case("UTI-01")).findings)  # standard dose passes
    old, young = case("DOSE-04"), case("DOSE-04")
    young.age = 50
    assert run_case(old).outcome == "RED"                      # citalopram 40 mg: over the limit from age 65
    assert not any(x.code == "DO-001" for x in run_case(young).findings)
    assert any(x.code == "DO-004" for x in run_case(case("DOSE-06")).findings)   # unreadable dose is said to be unchecked
    assert any(x.code == "DO-005" for x in run_case(case("CA-03")).findings)     # no limit held: said to be unchecked
    assert any(x.code == "DO-003" for x in run_case(case("DOSE-07")).findings)   # single dose too large


def test_no_antibiotic_without_infection():
    r = run_case(case("INF-01"))
    assert r.outcome == "RED" and r.draft is None
    assert r.alternative is None                               # swapping to another antibiotic would repeat the mistake
    assert any(f.code == "MB-010" for f in r.findings) and any(f.code == "UR-004" for f in r.findings)
    assert "inflammation" in next(f for f in r.findings if f.code == "MB-010").detail
    assert sign_off(r, "APPROVE", "GP7", "GP", AuditLog())[0] is False
    ok = run_case(case("INF-05"))                              # infection confirmed: goes ahead
    assert ok.outcome == "GREEN" and ok.draft


def test_antibiotic_exposure():
    r = run_case(case("INF-03"))
    assert {"MB-013", "MB-014"} <= {f.code for f in r.findings}
    assert "120 days" in next(f for f in r.findings if f.code == "MB-013").title
    light = case("INF-05"); light.antibiotic_days_12m = 6
    assert not any(f.code in ("MB-013", "MB-014") for f in run_case(light).findings)


def test_meeting_interaction():
    from vmdt import meeting
    r = run_case(case("UTI-02"))                               # nitrofurantoin with poor kidney function
    pos = {p["agent"]: p["position"] for p in meeting.positions(r)}
    assert pos["pharmacist"] == "Objects" and pos["allergy"] == "Agrees"
    assert "1 object" in meeting.tally(r) and "safer option" in meeting.chair_opening(r)
    for c in r.convened:                                       # every expert answers every question
        for q in meeting.QUESTIONS:
            assert len(meeting.answer(r, c["agent"], q)) > 20
    assert "object" in meeting.answer(r, "pharmacist", meeting.QUESTIONS[1]).lower()
    assert "support" in meeting.answer(r, "allergy", meeting.QUESTIONS[1]).lower()
    assert "feeling or being sick" in meeting.answer(r, "side_effects", meeting.QUESTIONS[2])
    assert "not called in" in meeting.answer(r, "oncology", meeting.QUESTIONS[0])
    assert len(meeting.round_table(r)) == len(r.convened)


def test_meeting_what_if():
    from vmdt import meeting
    r = run_case(case("UTI-02"))
    assert r.alternative_proposal and r.alternative_proposal["drug"] == "trimethoprim"
    alt = r.alternative_proposal
    new, text = meeting.what_if(r, alt["drug"], alt["dose"], alt["frequency"], alt["duration_days"])
    assert new.outcome in ("GREEN", "AMBER") and new.draft          # the team now accepts it
    assert "Pharmacist: objects -> " in text
    worse, text2 = meeting.what_if(r, "nitrofurantoin", "200 mg", "four times daily", 3)
    assert worse.outcome == "RED" and any(f.code == "DO-001" for f in worse.findings)
    assert r.patient.proposal.drug == "nitrofurantoin" and r.patient.proposal.dose.startswith("100")   # original untouched


def test_meeting_conclusion_needs_a_decision():
    from vmdt import meeting
    r = run_case(case("UTI-02"))
    log = AuditLog()
    ok, _, rec = sign_off(r, "APPROVE", "GP7", "GP", log)
    assert not ok and rec is None                                   # no decision, so no conclusion can be written
    ok, _, rec = sign_off(r, "ACCEPT_ALTERNATIVE", "GP7", "GP", log)
    c = meeting.conclusion(r, rec, "GP")
    assert ok and c["final_prescription"].lower().startswith("trimethoprim") and c["stops"]
    text = meeting.conclusion_text(c)
    assert "FINAL CONCLUSION" in text and "GP7" not in text and rec["hash"][:16] in text


def test_patient_summary_and_key_points():
    from vmdt import meeting, room3d
    red = run_case(case("UTI-02"))
    s = meeting.patient_summary(red)
    assert "does not look suitable" in s["opening"] and "Trimethoprim" in s["opening"]
    assert "rash" in s["look_out_for"]                           # side effects of the option now on the table
    assert "Nothing is prescribed until" in s["closing"]
    blocked = meeting.patient_summary(run_case(case("INF-01")))   # no infection found: no medicine is named as an option
    assert blocked["considering"] == "" and blocked["look_out_for"] == []
    ok = meeting.patient_summary(run_case(case("UTI-01")))
    assert ok["opening"].startswith("The medicine being considered for you is Nitrofurantoin")
    assert meeting.key_points(red)[0][0] == "RED" and len(meeting.key_points(red, limit=2)) <= 2
    html = room3d.render(red, spotlight="pharmacist")
    assert "✕ Stop" in html and "✓ No concern" in html           # shape as well as colour
    assert html.count('class="vx red on"') == 1 and 'vmdt-row spot' in html


def test_open_data_parsing(monkeypatch):
    """The live NHS data path, exercised with a canned reply (no internet needed)."""
    rows = [{"type": "chemical", "id": "0501130R0", "name": "Nitrofurantoin"},
            {"type": "product", "id": "0501130R0AA", "name": "Nitrofurantoin (generic)"}]
    assert opendata.pick_chemical(rows, "nitrofurantoin") == ("0501130R0", "Nitrofurantoin")
    assert opendata.pick_chemical([{"type": "chemical", "id": "X", "name": "Metformin hydrochloride/sitagliptin"}], "metformin") is None

    class Resp:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data

    def fake_get(url, params=None, **kw):
        if "bnf_code" in url:
            return Resp([{"type": "chemical", "id": "C" + params["q"][:3], "name": params["q"].capitalize()}])
        return Resp([{"date": "2025-09-01", "items": 100, "quantity": 1, "actual_cost": 50.0},
                     {"date": "2026-09-01", "items": 120, "quantity": 1, "actual_cost": 60.0}])
    monkeypatch.setattr(opendata.requests, "get", fake_get)
    df, msg = opendata.condition_trends("uti")
    assert df["medicine"].nunique() == 5 and "OpenPrescribing" in msg
    assert opendata.summarise(df)["Change over 12 months (%)"].iloc[0] == 20.0
