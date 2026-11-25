"""Data structures shared by every part of the system.

Keeping these in one small file is deliberate (SE principle 5: explicit state).
Every agent receives and returns these plain objects, so an agent can be swapped
or retrained without touching the orchestrator (the paper's "standardised
input/output contract").
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# Severity levels, in rising order of concern.
INFO, AMBER, RED = "INFO", "AMBER", "RED"
LEVEL_ORDER = {INFO: 0, AMBER: 1, RED: 2}

# Signal types that always go to "Flag & Escalate" when RED (paper, section 3.3).
ESCALATION_SIGNALS = {
    "interaction", "contraindication", "dosing", "allergy",
    "deliverability", "safety_signal", "red_flag", "stewardship",
}

FREQ_PER_DAY = {
    "single dose": 1, "once daily": 1, "twice daily": 2, "three times daily": 3,
    "four times daily": 4, "once weekly": 1 / 7, "as needed": 1,
}


@dataclass
class Allergy:
    substance: str            # e.g. "penicillin"
    reaction: str = "unknown"  # "anaphylaxis", "rash", "intolerance" (e.g. nausea), "unknown"


@dataclass
class Proposal:
    drug: str
    dose: str = ""
    frequency: str = "once daily"
    duration_days: Optional[int] = None
    indication: str = "other"   # "uti", "type2_diabetes", "cancer_care", "other"


@dataclass
class Patient:
    """One prescribing request. No names, addresses or NHS numbers are held:
    `ref` is a local case reference only (SE principle 9: privacy by design)."""
    ref: str
    age: int
    sex: str                       # "female" / "male"
    proposal: Proposal
    egfr: Optional[float] = None   # kidney function, mL/min/1.73m2
    pregnant: bool = False
    trimester: Optional[int] = None
    conditions: List[str] = field(default_factory=list)
    allergies: List[Allergy] = field(default_factory=list)
    allergy_status_recorded: bool = True
    current_meds: List[str] = field(default_factory=list)
    # Function (PT/OT view)
    dexterity_problem: bool = False
    cognitive_impairment: bool = False
    swallowing_difficulty: bool = False
    visual_impairment: bool = False
    falls_history: bool = False
    frail: bool = False
    # History
    uti_courses_6m: int = 0
    culture_resistant_to: List[str] = field(default_factory=list)
    missed_collections: int = 0
    # Infection evidence and antibiotic exposure
    urine_culture: str = "not recorded"   # not recorded / not sent / awaited / infection confirmed / no infection found
    clear_cultures_12m: int = 0            # lab tests in the last 12 months that found NO infection
    antibiotic_days_12m: int = 0           # total days of antibiotics in the last 12 months
    notes: str = ""                # free text; screened by the triage step

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    code: str          # stable rule id, e.g. "PH-INT-003" (traceable to a test)
    level: str         # INFO / AMBER / RED
    signal: str        # interaction, contraindication, dosing, allergy, ...
    title: str         # one plain-English line
    detail: str        # why it matters and what to do
    source: str        # knowledge source the rule paraphrases
    agent: str = ""    # filled in by the orchestrator

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentReport:
    agent: str
    role: str
    findings: List[Finding] = field(default_factory=list)
    ms: float = 0.0
    saw: List[str] = field(default_factory=list)   # which patient fields this agent was given
    status: str = "ok"                               # ok / failed / timed_out

    @property
    def worst(self) -> str:
        if self.status != "ok":
            return AMBER
        lv = INFO
        for f in self.findings:
            if LEVEL_ORDER[f.level] > LEVEL_ORDER[lv]:
                lv = f.level
        return lv


@dataclass
class CaseResult:
    patient: Patient
    outcome: str                  # GREEN / AMBER / RED / HARD_STOP
    headline: str
    reports: List[AgentReport]
    findings: List[Finding]
    triage_signals: List[str]
    optimisation: List[str]
    safety_check: Dict[str, bool]
    draft: Optional[str]          # None when escalated: no draft for direct sign-off
    alternative: Optional[str]
    total_ms: float
    sequential_ms: float
    convened: List[dict]
    case_hash: str = ""
