import copy
import math

import pytest

from guardrail_agent import AuditChain, verify_document


def sample():
    chain = AuditChain({"config": {"limit": 100}, "seed": 42})
    for i in range(4):
        chain.add({"number": i, "approved": True})
    return chain


@pytest.mark.parametrize(
    "alter", ["seq", "payload", "middle", "tail", "empty", "order", "extra", "context"]
)
def test_tampering_and_truncation_fail_against_trusted_receipt(alter):
    chain = sample()
    doc, receipt = chain.document(), chain.receipt()
    if alter == "seq":
        doc["records"][1]["seq"] = 999
    elif alter == "payload":
        doc["records"][1]["payload"]["number"] = 999
    elif alter == "middle":
        del doc["records"][1]
    elif alter == "tail":
        doc["records"].pop()
    elif alter == "empty":
        doc["records"].clear()
    elif alter == "order":
        doc["records"].reverse()
    elif alter == "context":
        doc["context"]["config"]["limit"] = 200
    else:
        doc["records"][0]["ignored"] = "extra"
    assert not verify_document(doc, receipt).ok


def test_complete_rewrite_is_only_detectable_with_independent_trusted_receipt():
    chain = sample()
    other = AuditChain(chain.context)
    for i in range(4):
        other.add({"number": i, "approved": False})
    internal = verify_document(other.document())
    assert internal.ok and not internal.anchored
    assert not verify_document(other.document(), chain.receipt()).ok


def test_empty_chain_and_external_head_count():
    chain = AuditChain()
    assert chain.verify() is None
    assert verify_document(chain.document(), chain.receipt()).ok
    chain.add({"a": 1})
    assert chain.verify(expected_count=0) == 0
    assert chain.verify(expected_head="f" * 64) == 0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, object()])
def test_non_json_payload_does_not_mutate_chain(value):
    chain = sample()
    original = chain.document()
    with pytest.raises((ValueError, TypeError)):
        chain.add({"value": value})
    assert chain.document() == original


def test_payload_and_return_value_are_detached():
    chain = AuditChain()
    payload = {"items": [1]}
    rec = chain.add(payload)
    payload["items"].append(2)
    rec["payload"]["items"].append(3)
    assert chain.records[0]["payload"] == {"items": [1]}
    assert chain.verify() is None


def test_in_memory_anchor_catches_tail_and_empty_mutation():
    chain = sample()
    chain.records.pop()
    assert chain.verify() is not None
    with pytest.raises(ValueError):
        chain.add({"later": True})
    chain.records.clear()
    assert chain.verify() is not None


@pytest.mark.parametrize(
    "document,receipt",
    [
        ({}, None),
        ({"schema": "bad"}, {}),
        (None, {}),
        ({"schema": "guardrail-audit-v1", "context": {}, "records": []}, {}),
    ],
)
def test_invalid_documents_return_structured_failures(document, receipt):
    result = verify_document(document, receipt)
    assert not result.ok and result.index == 0


def test_invalid_receipt_and_record_shape():
    chain = sample()
    for key, value in (
        ("count", True),
        ("count", -1),
        ("head", "bad"),
        ("context_digest", "bad"),
        ("schema", "bad"),
    ):
        receipt = chain.receipt()
        receipt[key] = value
        assert not verify_document(chain.document(), receipt).ok
    document = copy.deepcopy(chain.document())
    document["records"][0]["payload"] = []
    assert not verify_document(document, chain.receipt()).ok
