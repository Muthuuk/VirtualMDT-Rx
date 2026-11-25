"""Acceptance targets and release gate.  Run:  python -m vmdt.evaluate

Honest limit: the cases and the rules were written by the same team, so these
numbers show that the engineering controls work as designed. They say nothing
yet about performance on real patients.
"""
from __future__ import annotations

import statistics
import sys
import time

from .audit import AuditLog
from .cases import SUITE
from .orchestrator import hard_checks, run_case, sign_off
from .requirements_trace import REQUIREMENTS


def evaluate() -> list:
    results = [(p, exp, must, run_case(p)) for p, exp, must, _ in SUITE]
    hazards = [(p, must, r) for p, exp, must, r in results if exp in ("RED", "HARD_STOP")]
    recall = sum(r.outcome in ("RED", "HARD_STOP") and set(must) <= {f.code for f in r.findings} for _, must, r in hazards) / len(hazards)
    clean = [r for _, exp, _, r in results if exp in ("GREEN", "AMBER")]
    false_esc = sum(r.outcome in ("RED", "HARD_STOP") for r in clean) / len(clean)
    exact = sum(r.outcome == exp for _, exp, _, r in results) / len(results)

    alts_ok = True
    for p, _, _, r in results:
        if r.alternative:
            pd = p.to_dict(); pd["triage"] = r.triage_signals
            drug = r.alternative.split()[0].lower()
            from . import knowledge as kb
            g = kb.GUIDELINES[p.proposal.indication]["regimen"][drug]
            pd["proposal"] = {"drug": drug, "dose": g[0], "frequency": g[1], "duration_days": None, "indication": p.proposal.indication}
            alts_ok &= not hard_checks(pd)
    no_draft = all(r.draft is None for _, _, _, r in results if r.outcome in ("RED", "HARD_STOP"))

    times = []
    for _ in range(3):
        for p, *_ in SUITE:
            t = time.perf_counter(); run_case(p); times.append(time.perf_counter() - t)
    p95 = statistics.quantiles(times, n=20)[18]

    traceable = all(f.agent and f.code and f.source for _, _, _, r in results for f in r.findings)
    log = AuditLog()
    red = next(r for _, _, _, r in results if r.outcome == "RED")
    blocked = not sign_off(red, "APPROVE", "GP1", "GP", log)[0]
    sign_off(red, "REJECT", "GP1", "GP", log); sign_off(results[0][3], "APPROVE", "GP1", "GP", log)
    chain_ok = log.verify()
    log.records[0]["decision"] = "APPROVE"
    tamper_seen = not log.verify()
    same = all(run_case(p).case_hash == r.case_hash for p, _, _, r in results)
    covered = all(req["tests"] for req in REQUIREMENTS)

    return [
        ("T1", "Seeded hazards detected and escalated", f"{recall:.3f}", ">= 0.95", recall >= 0.95),
        ("T2", "Clean or caution-only cases wrongly escalated", f"{false_esc:.3f}", "<= 0.05", false_esc <= 0.05),
        ("T3", "Outcome matches the expected outcome", f"{exact:.3f}", ">= 0.95", exact >= 0.95),
        ("T4", "Suggested alternatives pass every hard rule", "yes" if alts_ok else "no", "all", alts_ok),
        ("T5", "No draft released on an escalated case", "yes" if no_draft else "no", "all", no_draft),
        ("T6", "Response time, 95th percentile (rules only, no web look-ups)", f"{p95:.3f} s", "<= 2 s", p95 <= 2),
        ("T7", "Every finding traceable to expert, rule and source", "yes" if traceable else "no", "all", traceable),
        ("T8", "Escalated case cannot be approved; tampering with the log is detected", "yes" if blocked and chain_ok and tamper_seen else "no", "all", blocked and chain_ok and tamper_seen),
        ("T9", "Same input gives the same result", "yes" if same else "no", "all", same),
        ("T10", "Every requirement has at least one test", "yes" if covered else "no", "all", covered),
    ]


def main() -> int:
    rows = evaluate()
    print(f"VirtualMDT-Rx acceptance targets ({len(SUITE)} synthetic cases)\n")
    for tid, name, value, target, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {tid:<4} {name:<72} {value:>9}   target {target}")
    failed = [r for r in rows if not r[4]]
    print("\nRelease gate:", "OPEN - all targets met" if not failed else f"BLOCKED - {len(failed)} target(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
