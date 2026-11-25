"""Tamper-evident audit log (SE principle 6: observability and audit).

Each record stores the hash of the record before it, like links in a chain.
Changing or deleting any earlier record breaks every hash after it, which
`verify()` detects. Patient and clinician references are stored only as salted
hashes, so the log holds no identifiers.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

GENESIS = "0" * 64
SALT = os.environ.get("VMDT_AUDIT_SALT", "vmdt-demo-salt")


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pseudonym(value: str) -> str:
    return h(SALT + "|" + (value or ""))[:16]


class AuditLog:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.records: List[dict] = []
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self.records = [json.loads(line) for line in fh if line.strip()]

    def append(self, event: str, **fields) -> dict:
        prev = self.records[-1]["hash"] if self.records else GENESIS
        body = {"seq": len(self.records) + 1,
                "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event": event, **fields, "prev_hash": prev}
        body["hash"] = h(json.dumps(body, sort_keys=True))
        self.records.append(body)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, sort_keys=True) + "\n")
        return body

    def verify(self) -> bool:
        prev = GENESIS
        for rec in self.records:
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev_hash") != prev or h(json.dumps(body, sort_keys=True)) != rec.get("hash"):
                return False
            prev = rec["hash"]
        return True
