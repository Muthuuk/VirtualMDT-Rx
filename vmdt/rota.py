"""Who is available right now?

The virtual experts (software) answer at any hour. Each one also has a HUMAN
counterpart whose working hours are held in a rota. The screen shows whether
that person can be reached now, so the prescriber knows whether a quick human
second opinion is possible or whether an advice request will wait.

The hours below are a DEMO rota. Replace ROTA with your own team's hours.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

WEEKDAYS = {0, 1, 2, 3, 4}
ALL_DAYS = {0, 1, 2, 3, 4, 5, 6}

# agent key -> (human counterpart, days, start hour, end hour); None = no named person
ROTA = {
    "pharmacist": ("Practice pharmacist", WEEKDAYS, 8.0, 18.5),
    "ptot": ("Community therapy team", WEEKDAYS, 9.0, 17.0),
    "allergy": ("Allergy advice line", WEEKDAYS, 9.0, 17.0),
    "side_effects": ("Practice pharmacist", WEEKDAYS, 8.0, 18.5),
    "guidance": None,
    "literature": None,
    "microbiology": ("Duty microbiologist", ALL_DAYS, 0.0, 24.0),
    "urology": ("Urology advice and guidance", WEEKDAYS, 9.0, 17.0),
    "diabetes": ("Diabetes specialist team", WEEKDAYS, 9.0, 17.0),
    "oncology": ("Acute oncology line", ALL_DAYS, 0.0, 24.0),
    "renal": ("Kidney team advice", WEEKDAYS, 8.0, 18.0),
    "geriatrics": ("Frailty team", WEEKDAYS, 9.0, 17.0),
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hhmm(h: float) -> str:
    return f"{int(h):02d}:{int(round((h % 1) * 60)):02d}"


def status(agent: str, when: Optional[datetime] = None) -> dict:
    """Return {'human', 'available', 'note'} for an expert at a given time."""
    when = when or datetime.now()
    entry = ROTA.get(agent)
    if entry is None:
        return {"human": None, "available": False, "note": "Reference expert: no human counterpart"}
    human, days, start, end = entry
    hour = when.hour + when.minute / 60
    if when.weekday() in days and start <= hour < end:
        until = "all day" if end >= 24 else f"until {_hhmm(end)}"
        return {"human": human, "available": True, "note": f"{human} reachable now ({until})"}
    # find the next opening
    for add in range(0, 8):
        d = when + timedelta(days=add)
        if d.weekday() in days and (add > 0 or hour < start):
            return {"human": human, "available": False,
                    "note": f"{human} off duty; back {DAY_NAMES[d.weekday()]} {_hhmm(start)}"}
    return {"human": human, "available": False, "note": f"{human} off duty"}
