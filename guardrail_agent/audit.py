"""Hash-chain consistency and receipts; no signatures or identity guarantees."""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import asdict, dataclass

from .core import canonical

SCHEMA = "guardrail-audit-v1"
RECEIPT_SCHEMA = "guardrail-receipt-v1"
GENESIS = "0" * 64
HASH = re.compile(r"[0-9a-f]{64}\Z")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Verification:
    ok: bool
    index: int | None
    reason: str
    anchored: bool

    def to_dict(self) -> dict:
        return asdict(self)


def verify_document(document: dict, expected_receipt: dict | None = None) -> Verification:
    """A supplied receipt must already be trusted and kept independently."""
    anchored = expected_receipt is not None

    def fail(index: int, reason: str) -> Verification:
        return Verification(False, index, reason, anchored)

    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        return fail(0, "unsupported document schema")
    context, records = document.get("context"), document.get("records")
    if not isinstance(context, dict) or not isinstance(records, list):
        return fail(0, "context must be an object and records must be a list")
    try:
        context_hash = digest(context)
    except (ValueError, TypeError, OverflowError):
        return fail(0, "context is not strict JSON")
    if document.get("context_digest") != context_hash:
        return fail(0, "context digest mismatch")
    receipt = document.get("receipt")
    if not isinstance(receipt, dict):
        return fail(0, "missing internal receipt")
    for candidate in (receipt, expected_receipt) if anchored else (receipt,):
        if not isinstance(candidate, dict) or candidate.get("schema") != RECEIPT_SCHEMA:
            return fail(0, "invalid receipt schema")
        if type(candidate.get("count")) is not int or candidate["count"] < 0:
            return fail(0, "invalid receipt count")
        if not isinstance(candidate.get("head"), str) or not HASH.fullmatch(candidate["head"]):
            return fail(0, "invalid receipt head")
        if candidate.get("context_digest") != context_hash:
            return fail(0, "receipt context mismatch")
        if candidate["count"] != len(records):
            return fail(min(candidate["count"], len(records)), "record count mismatch")
    prev = GENESIS
    for index, rec in enumerate(records):
        if not isinstance(rec, dict) or set(rec) != {
            "schema",
            "seq",
            "context_digest",
            "payload",
            "prev",
            "hash",
        }:
            return fail(index, "invalid record shape")
        if rec["schema"] != SCHEMA or type(rec["seq"]) is not int or rec["seq"] != index:
            return fail(index, "record schema or sequence mismatch")
        if rec["context_digest"] != context_hash or rec["prev"] != prev:
            return fail(index, "record context or previous hash mismatch")
        if not isinstance(rec["payload"], dict):
            return fail(index, "payload must be an object")
        try:
            expected = digest({key: value for key, value in rec.items() if key != "hash"})
        except (TypeError, ValueError, OverflowError):
            return fail(index, "payload is not strict JSON")
        if rec["hash"] != expected:
            return fail(index, "record hash mismatch")
        prev = rec["hash"]
    if receipt["head"] != prev or (anchored and expected_receipt["head"] != prev):
        return fail(max(0, len(records) - 1), "head mismatch")
    return Verification(
        True,
        None,
        "matches trusted receipt"
        if anchored
        else "internal consistency only; no trusted external anchor",
        anchored,
    )


class AuditChain:
    GENESIS = GENESIS

    def __init__(self, context: dict | None = None):
        self.context = copy.deepcopy(context if context is not None else {})
        if not isinstance(self.context, dict):
            raise ValueError("context must be an object")
        self.context_digest = digest(self.context)
        self.records: list[dict] = []
        self._prev = GENESIS
        self._count = 0

    @staticmethod
    def _digest(rec: dict) -> str:
        return digest({key: value for key, value in rec.items() if key != "hash"})

    def receipt(self) -> dict:
        return {
            "schema": RECEIPT_SCHEMA,
            "count": self._count,
            "head": self._prev,
            "context_digest": self.context_digest,
        }

    def document(self) -> dict:
        return {
            "schema": SCHEMA,
            "context": copy.deepcopy(self.context),
            "context_digest": self.context_digest,
            "records": copy.deepcopy(self.records),
            "receipt": self.receipt(),
        }

    def add(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        # Full verification is explicit and performed before CLI export. Checking
        # the append position here avoids quadratic rescans of long simulations.
        tail_ok = not self.records or (
            isinstance(self.records[-1], dict)
            and self.records[-1].get("hash") == self._prev
            and self._digest(self.records[-1]) == self._prev
        )
        if (
            len(self.records) != self._count
            or not tail_ok
            or digest(self.context) != self.context_digest
        ):
            raise ValueError("cannot append to an altered audit chain")
        rec = {
            "schema": SCHEMA,
            "seq": self._count,
            "context_digest": self.context_digest,
            "payload": copy.deepcopy(payload),
            "prev": self._prev,
        }
        rec["hash"] = self._digest(rec)
        self.records.append(rec)
        self._prev, self._count = rec["hash"], self._count + 1
        return copy.deepcopy(rec)

    def verify(
        self, *, expected_head: str | None = None, expected_count: int | None = None
    ) -> int | None:
        receipt = self.receipt()
        if expected_head is not None:
            receipt["head"] = expected_head
        if expected_count is not None:
            receipt["count"] = expected_count
        result = verify_document(self.document(), receipt)
        return result.index if not result.ok else None
