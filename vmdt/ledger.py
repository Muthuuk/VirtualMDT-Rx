"""A small permissioned blockchain for prescribing decisions (demonstrator).

What goes ON the chain: only fingerprints (hash commitments) and status codes.
What stays OFF the chain: the patient record, the prescription text and the
clinician's identity. A fingerprint cannot be turned back into the original
without the secret "salt" kept with the off-chain record, so the chain can be
shared between organisations without sharing personal data.

Three ideas, each a few lines of plain Python:
  1. Commitment    sha256(salt | value): proves later that a value existed,
                   without revealing it now.
  2. Merkle tree   one fingerprint (the root) for a whole block of records,
                   plus a short proof that ONE record is in the block, without
                   showing the others.
  3. Proof of authority  a block is valid only if a quorum of named validator
                   organisations has signed it (here 2 of 3). No mining, so
                   almost no energy use.

This is a single-process simulation for teaching and evaluation. It is not a
distributed network: there is no peer-to-peer layer and the validator keys are
demo keys held in memory. A deployment would use a real permissioned platform.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

GENESIS = "0" * 64
DEMO_VALIDATORS = {"GP practice": "demo-key-gp", "Community pharmacy": "demo-key-pharmacy", "ICB audit office": "demo-key-icb"}
QUORUM = 2


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(16)


def commit(value: str, salt: str) -> str:
    """Fingerprint of a private value. Same value + same salt -> same fingerprint."""
    return sha(salt + "|" + (value or ""))


def canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------ Merkle
def _pair(a: str, b: str) -> str:
    return sha(a + b)


def merkle_root(leaves: List[str]) -> str:
    if not leaves:
        return sha("")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaves: List[str], index: int) -> List[dict]:
    """The sibling fingerprints needed to rebuild the root from one leaf."""
    proof, level, i = [], list(leaves), index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sib = i ^ 1
        proof.append({"hash": level[sib], "side": "right" if sib > i else "left"})
        level = [_pair(level[k], level[k + 1]) for k in range(0, len(level), 2)]
        i //= 2
    return proof


def verify_merkle(leaf: str, proof: List[dict], root: str) -> bool:
    h = leaf
    for step in proof:
        h = _pair(h, step["hash"]) if step["side"] == "right" else _pair(step["hash"], h)
    return h == root


# ------------------------------------------------------------------- chain
class Ledger:
    def __init__(self, validators: Optional[Dict[str, str]] = None, quorum: int = QUORUM):
        self.validators = dict(validators or DEMO_VALIDATORS)
        self.quorum = quorum
        self.blocks: List[dict] = []
        self.pending: List[dict] = []

    # -- transactions
    def submit(self, tx: dict) -> str:
        """Queue a transaction (already free of personal data). Returns its fingerprint."""
        tx = dict(tx)
        tx.setdefault("time_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        tx["nonce"] = secrets.token_hex(4)
        tx_hash = sha(canonical(tx))
        self.pending.append({"tx": tx, "hash": tx_hash})
        return tx_hash

    def _sign(self, validator: str, block_hash: str) -> str:
        return hmac.new(self.validators[validator].encode(), block_hash.encode(), hashlib.sha256).hexdigest()

    def seal(self, signers: Optional[List[str]] = None) -> Optional[dict]:
        """Close the pending transactions into a block signed by a quorum of validators."""
        if not self.pending:
            return None
        names = list(self.validators)
        proposer = names[len(self.blocks) % len(names)]
        signers = signers or [proposer] + [n for n in names if n != proposer][: self.quorum - 1]
        header = {"index": len(self.blocks), "prev_hash": self.blocks[-1]["hash"] if self.blocks else GENESIS,
                  "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "merkle_root": merkle_root([p["hash"] for p in self.pending]), "proposer": proposer,
                  "tx_count": len(self.pending)}
        block_hash = sha(canonical(header))
        block = {**header, "hash": block_hash, "transactions": self.pending,
                 "signatures": {s: self._sign(s, block_hash) for s in signers if s in self.validators}}
        self.blocks.append(block)
        self.pending = []
        return block

    # -- verification
    def verify_block(self, b: dict, prev_hash: str) -> bool:
        header = {k: b[k] for k in ("index", "prev_hash", "time_utc", "merkle_root", "proposer", "tx_count")}
        if b["prev_hash"] != prev_hash or sha(canonical(header)) != b["hash"]:
            return False
        if any(sha(canonical(t["tx"])) != t["hash"] for t in b["transactions"]):
            return False
        if merkle_root([t["hash"] for t in b["transactions"]]) != b["merkle_root"]:
            return False
        good = [s for s, sig in b["signatures"].items() if s in self.validators and hmac.compare_digest(sig, self._sign(s, b["hash"]))]
        return len(good) >= self.quorum

    def verify_chain(self) -> bool:
        prev = GENESIS
        for b in self.blocks:
            if not self.verify_block(b, prev):
                return False
            prev = b["hash"]
        return True

    # -- proofs
    def find(self, tx_hash: str):
        for b in self.blocks:
            for i, t in enumerate(b["transactions"]):
                if t["hash"] == tx_hash:
                    return b, i
        return None, -1

    def prove(self, tx_hash: str) -> Optional[dict]:
        """A portable receipt: enough to check one record without seeing any other."""
        b, i = self.find(tx_hash)
        if b is None:
            return None
        return {"tx_hash": tx_hash, "block": b["index"], "block_hash": b["hash"], "merkle_root": b["merkle_root"],
                "proof": merkle_proof([t["hash"] for t in b["transactions"]], i), "signed_by": sorted(b["signatures"])}

    def verify_receipt(self, receipt: dict) -> bool:
        if not receipt or receipt["block"] >= len(self.blocks):
            return False
        b = self.blocks[receipt["block"]]
        return (b["hash"] == receipt["block_hash"] and b["merkle_root"] == receipt["merkle_root"]
                and verify_merkle(receipt["tx_hash"], receipt["proof"], receipt["merkle_root"]) and self.verify_chain())

    def events(self, kind: Optional[str] = None) -> List[dict]:
        out = []
        for b in self.blocks:
            for t in b["transactions"]:
                if kind is None or t["tx"].get("type") == kind:
                    out.append({**t["tx"], "block": b["index"], "tx_hash": t["hash"]})
        return out
