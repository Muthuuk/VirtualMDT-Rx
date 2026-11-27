"""A learned priority score for long patient lists (machine learning, optional).

Why it exists: the rule-based experts take a few milliseconds per patient, but a
practice list can hold tens of thousands of repeat prescriptions, and a
pharmacist can only look at so many. This model learns, from cases the experts
have already reviewed, which requests are most likely to be escalated, and
puts those at the top of the list.

What it is NOT: it never decides anything. The rules still review every
request; the score only changes the ORDER in which a human looks.

Honest limit: here it is trained on invented patients labelled by our own
rules, so it learns to imitate the rules. The reported accuracy shows the
plumbing works. It is not evidence of clinical performance.

Model: gradient-boosted decision trees (scikit-learn). Chosen because the
inputs are a small table of mixed numbers and yes/no flags, where tree
ensembles are a strong default, train in seconds on a laptop and expose which
inputs mattered.
"""
from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from . import knowledge as kb
from .batch import review_frame, row_to_patient, synthetic_cohort

RISK_CLASSES = ["anticoagulant", "nsaid", "opioid", "acei_arb", "diuretic", "ssri", "antifolate", "steroid", "sglt2",
                "sulfonylurea", "antibiotic", "cytotoxic", "benzodiazepine", "raises_potassium", "qt_prolonging"]
FEATURES = (["age", "egfr", "egfr_missing", "n_meds", "pregnant", "male", "cognitive", "falls", "frail", "uti_courses",
             "abx_days", "clear_cultures", "culture_no_infection", "has_allergy", "freq_per_day", "dose_ratio"]
            + [f"new_{c}" for c in RISK_CLASSES] + [f"cur_{c}" for c in RISK_CLASSES])


def features(p) -> List[float]:
    from .models import FREQ_PER_DAY
    drug = kb.normalise(p.proposal.drug)
    new_cls = set(kb.classes(drug))
    cur_cls = {c for m in p.current_meds for c in kb.classes(m)}
    lim, parsed = kb.DOSE_LIMITS.get(drug), kb.parse_dose_mg(p.proposal.dose)
    per_day = FREQ_PER_DAY.get(p.proposal.frequency, 1)
    ratio = (parsed[1] * per_day / lim["max"]) if (lim and parsed and not lim.get("weekly")) else 0.0
    row = [p.age, p.egfr if p.egfr is not None else 90, int(p.egfr is None), len(p.current_meds), int(p.pregnant),
           int(p.sex == "male"), int(p.cognitive_impairment), int(p.falls_history), int(p.frail), p.uti_courses_6m,
           p.antibiotic_days_12m, p.clear_cultures_12m, int(p.urine_culture == "no infection found"), int(bool(p.allergies)),
           per_day, ratio]
    return row + [int(c in new_cls) for c in RISK_CLASSES] + [int(c in cur_cls) for c in RISK_CLASSES]


def _dataset(n: int, seed: int) -> Tuple[pd.DataFrame, pd.Series]:
    df = synthetic_cohort(n, seed=seed)
    out = review_frame(df)
    X = pd.DataFrame([features(row_to_patient(r)) for r in df.to_dict("records")], columns=FEATURES)
    y = out["outcome"].isin(["RED", "HARD_STOP"]).astype(int)
    return X, y


def train_and_evaluate(n_train: int = 3000, n_test: int = 1500, seed: int = 11) -> dict:
    """Train on one set of invented patients, test on a different set. Returns the model and its scores."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score
    Xtr, ytr = _dataset(n_train, seed)
    Xte, yte = _dataset(n_test, seed + 1)
    model = GradientBoostingClassifier(random_state=0).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    order = pd.Series(p).sort_values(ascending=False).index
    top = max(1, len(order) // 10)
    found = int(yte.iloc[order[:top]].sum())
    imp = sorted(zip(FEATURES, model.feature_importances_), key=lambda t: -t[1])[:6]
    return {"model": model, "n_train": n_train, "n_test": n_test, "escalated_in_test": int(yte.sum()),
            "auc": float(roc_auc_score(yte, p)), "average_precision": float(average_precision_score(yte, p)),
            "found_in_top_10pct": found, "share_found_in_top_10pct": found / max(1, int(yte.sum())),
            "top_features": [(f, round(float(v), 3)) for f, v in imp]}


def score(model, patients) -> List[float]:
    X = pd.DataFrame([features(p) for p in patients], columns=FEATURES)
    return [float(v) for v in model.predict_proba(X)[:, 1]]
