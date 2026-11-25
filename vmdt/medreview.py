"""Medicine-by-medicine review.

For the medicine being prescribed this module answers three plain questions:
  1. What are its main recognised side effects?
  2. Does it clash with each medicine the patient already takes, either through
     a named interaction or because both cause the same side effect?
  3. Is the patient someone for whom one of those side effects matters more?

`review_table()` returns one row for EVERY existing medicine, including any the
knowledge base does not know (marked "Not checked"), so nothing is left out.
"""
from __future__ import annotations

from typing import Dict, List

from . import knowledge as kb


def interaction_hits(new: str, existing: str) -> List[dict]:
    new, existing = kb.normalise(new), kb.normalise(existing)
    hits = []
    for r in kb.INTERACTIONS:
        if (kb.matches(new, r["a"]) and kb.matches(existing, r["b"])) or (kb.matches(new, r["b"]) and kb.matches(existing, r["a"])):
            if r["id"] not in [h["id"] for h in hits]:
                hits.append(r)
    return hits


def shared_effects(new: str, existing: str) -> List[str]:
    """Families of side effect that both medicines cause and that add up."""
    fam_new = {kb.ADDITIVE_FAMILY[e] for e in kb.side_effects(new) if e in kb.ADDITIVE_FAMILY}
    fam_old = {kb.ADDITIVE_FAMILY[e] for e in kb.side_effects(existing) if e in kb.ADDITIVE_FAMILY}
    return sorted(fam_new & fam_old)


def review_table(new: str, current_meds: List[str]) -> List[Dict[str, str]]:
    new_n = kb.normalise(new)
    rows = []
    for raw in current_meds:
        if not raw.strip():
            continue
        m = kb.normalise(raw)
        if not kb.known(m) or not kb.known(new_n):
            rows.append({"medicine": raw.strip(), "interaction": "Not checked", "shared": "Not checked", "verdict": "NOT CHECKED",
                         "note": "This medicine (or the new one) is not in the demo knowledge base. Review by hand."})
            continue
        if m == new_n:
            rows.append({"medicine": raw.strip(), "interaction": "Same medicine", "shared": "", "verdict": "CAUTION",
                         "note": "Already on the list: check this is a dose change, not a duplicate."})
            continue
        hits = interaction_hits(new_n, m)
        shared = shared_effects(new_n, m)
        if any(h["level"] == "RED" for h in hits):
            verdict = "STOP"
        elif hits or shared:
            verdict = "CAUTION"
        else:
            verdict = "No clash found"
        rows.append({"medicine": raw.strip(),
                     "interaction": "; ".join(h["title"] for h in hits) or "None in the rule set",
                     "shared": ", ".join(shared) or "None",
                     "verdict": verdict,
                     "note": " ".join(h["detail"] for h in hits) or
                             (f"Both cause {' and '.join(shared)}; the effects add up. Consider a lower dose or closer monitoring." if shared else "")})
    return rows


def effect_list(new: str) -> List[str]:
    return [kb.EFFECT_LABEL[e] for e in kb.side_effects(new)]
