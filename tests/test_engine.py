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
