"""Smart contracts: rules the ledger itself enforces.

A smart contract is a small program stored with the ledger. Every organisation
runs the same code, so no single party (and no faulty app) can skip a rule.
Two contracts are modelled here in Python; `contracts/PrescriptionRegistry.sol`
states the same rules in Solidity as a reference for a real deployment.

  ConsentContract       who may look at a patient's record, for what purpose,
                        until when; every look is written to the chain.
  PrescriptionContract  the life of one prescribing request:
                        REQUESTED -> REVIEWED -> SIGNED | REJECTED | OVERRIDDEN
                        It refuses, on-chain, what the app also refuses:
                        approving an escalated case, overriding without a
                        reason, deciding twice, deciding without consent.

Only fingerprints are stored. The contracts never see a name, an NHS number,
a medicine list or a clinician's identity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from .ledger import Ledger, commit

PURPOSE = "virtual MDT medication review"
PRESCRIBER_ROLES = {"GP", "Consultant", "Prescribing pharmacist", "Nurse prescriber"}
ESCALATED = {"RED", "HARD_STOP"}


class ContractError(Exception):
    """Raised when a contract refuses a transaction. Nothing is written."""


class ConsentContract:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.grants = {}        # patient fingerprint -> {"purpose", "expires", "active"}

    def grant(self, patient_c: str, purpose: str = PURPOSE, expires_utc: Optional[str] = None) -> str:
        self.grants[patient_c] = {"purpose": purpose, "expires": expires_utc, "active": True}
        return self.ledger.submit({"type": "CONSENT_GRANTED", "patient": patient_c, "purpose": purpose, "expires": expires_utc})

    def revoke(self, patient_c: str) -> str:
        if patient_c not in self.grants:
            raise ContractError("No consent on record to withdraw.")
        self.grants[patient_c]["active"] = False
        return self.ledger.submit({"type": "CONSENT_REVOKED", "patient": patient_c})

    def allowed(self, patient_c: str, purpose: str = PURPOSE, now: Optional[datetime] = None) -> bool:
        g = self.grants.get(patient_c)
        if not g or not g["active"] or g["purpose"] != purpose:
            return False
        if g["expires"]:
            now = now or datetime.now(timezone.utc)
            return now.isoformat() < g["expires"]
        return True

    def log_access(self, patient_c: str, accessor: str, fields: List[str], purpose: str = PURPOSE) -> str:
        """Record that one expert looked at named categories of data. Refused without consent."""
        if not self.allowed(patient_c, purpose):
            raise ContractError(f"Access refused: no active consent for '{purpose}'.")
        return self.ledger.submit({"type": "ACCESS", "patient": patient_c, "accessor": accessor,
                                   "fields": sorted(fields), "purpose": purpose})


class PrescriptionContract:
    def __init__(self, ledger: Ledger, consent: ConsentContract):
        self.ledger, self.consent = ledger, consent
        self.state = {}         # case fingerprint -> dict

    def request(self, case_c: str, patient_c: str) -> str:
        if not self.consent.allowed(patient_c):
            raise ContractError("Request refused: the patient has not consented to a virtual MDT review.")
        if case_c in self.state:
            raise ContractError("This case is already on the ledger.")
        self.state[case_c] = {"status": "REQUESTED", "patient": patient_c}
        return self.ledger.submit({"type": "RX_REQUESTED", "case": case_c, "patient": patient_c})

    def review(self, case_c: str, outcome: str, experts: int, objections: int, has_alternative: bool) -> str:
        s = self._need(case_c, "REQUESTED")
        s.update(status="REVIEWED", outcome=outcome, has_alternative=has_alternative)
        return self.ledger.submit({"type": "RX_REVIEWED", "case": case_c, "outcome": outcome, "experts": experts,
                                   "objections": objections, "alternative_offered": has_alternative})

    def decide(self, case_c: str, decision: str, role: str, clinician_c: str, rx_c: Optional[str],
               reason_c: Optional[str] = None, acknowledged: bool = False) -> str:
        s = self._need(case_c, "REVIEWED")
        if not self.consent.allowed(s["patient"]):
            raise ContractError("Decision refused: consent has been withdrawn.")
        if role not in PRESCRIBER_ROLES:
            raise ContractError(f"Decision refused: '{role}' is not a prescriber role.")
        escalated = s["outcome"] in ESCALATED
        if escalated and decision in ("APPROVE", "APPROVE_WITH_CHANGES"):
            raise ContractError("Decision refused: an escalated case cannot be approved.")
        if decision == "ACCEPT_ALTERNATIVE" and not s.get("has_alternative"):
            raise ContractError("Decision refused: no safer option was offered.")
        if decision == "OVERRIDE" and (not escalated or not reason_c):
            raise ContractError("Decision refused: an override needs an escalated case and a recorded reason.")
        if decision == "APPROVE" and s["outcome"] == "AMBER" and not acknowledged:
            raise ContractError("Decision refused: the cautions have not been acknowledged.")
        if decision != "REJECT" and not rx_c:
            raise ContractError("Decision refused: no prescription fingerprint supplied.")
        final = {"REJECT": "REJECTED", "OVERRIDE": "OVERRIDDEN"}.get(decision, "SIGNED")
        s.update(status=final, rx=rx_c)
        return self.ledger.submit({"type": "RX_DECIDED", "case": case_c, "status": final, "decision": decision, "role": role,
                                   "clinician": clinician_c, "rx": rx_c, "reason": reason_c})

    def _need(self, case_c: str, status: str) -> dict:
        s = self.state.get(case_c)
        if s is None:
            raise ContractError("Unknown case.")
        if s["status"] != status:
            raise ContractError(f"Refused: the case is {s['status']}, not {status}. A case is decided once only.")
        return s

    def is_valid_prescription(self, rx_text: str, salt: str) -> bool:
        """What a pharmacy would ask: was exactly this prescription signed, and is the chain intact?"""
        c = commit(rx_text, salt)
        return self.ledger.verify_chain() and any(e.get("rx") == c and e["status"] in ("SIGNED", "OVERRIDDEN")
                                                  for e in self.ledger.events("RX_DECIDED"))


class Notary:
    """Glue used by the app: runs a reviewed case through both contracts and returns a receipt."""

    def __init__(self):
        self.ledger = Ledger()
        self.consent = ConsentContract(self.ledger)
        self.rx = PrescriptionContract(self.ledger, self.consent)

    def record_review(self, result, salt: str, consent_given: bool = True) -> str:
        from .agents import SCOPE
        patient_c = commit(result.patient.ref, salt)
        case_c = commit(result.case_hash, salt)
        if consent_given and not self.consent.allowed(patient_c):
            self.consent.grant(patient_c)
        self.rx.request(case_c, patient_c)                      # raises without consent
        for c in result.convened:
            self.consent.log_access(patient_c, c["agent"], SCOPE.get(c["agent"], []))
        objections = sum(1 for r in result.reports if r.worst == "RED")
        self.rx.review(case_c, result.outcome, len(result.convened), objections, bool(result.alternative))
        self.ledger.seal()
        return case_c

    def record_decision(self, result, record: dict, salt: str, role: str, clinician_id: str, acknowledged: bool) -> dict:
        case_c = commit(result.case_hash, salt)
        rx_text = record.get("final_prescription")
        tx = self.rx.decide(case_c, record["decision"], role, commit(clinician_id, salt),
                            commit(rx_text, salt) if rx_text else None,
                            commit(record.get("reason", ""), salt) if record.get("reason") else None, acknowledged)
        self.ledger.seal()
        receipt = self.ledger.prove(tx)
        receipt["salt"] = salt
        return receipt
