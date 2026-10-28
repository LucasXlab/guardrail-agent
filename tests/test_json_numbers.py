"""Finite-number validation applies even to ignored JSON extension fields."""

import json
import subprocess
import sys

import pytest

from guardrail_agent import AuditChain
from guardrail_agent.cli import main, read_json


def encoded_with_number(document, literal, nested):
    document = dict(document)
    marker = "__synthetic_number_literal__"
    document["extension"] = {"items": [marker]} if nested else marker
    return json.dumps(document).replace('"' + marker + '"', literal)


@pytest.mark.parametrize("literal", ["1e309", "-1e309", "1e+309", "-1E+309"])
@pytest.mark.parametrize("nested", [False, True])
def test_reader_rejects_exponent_overflow_at_any_depth(tmp_path, literal, nested):
    path = tmp_path / "numbers.json"
    path.write_text(encoded_with_number({}, literal, nested))
    with pytest.raises(ValueError, match="finite"):
        read_json(str(path))


@pytest.mark.parametrize("target", ["audit", "receipt"])
@pytest.mark.parametrize("literal", ["1e309", "-1e309"])
@pytest.mark.parametrize("nested", [False, True])
def test_valid_chain_cannot_hide_overflow_in_audit_or_receipt_extensions(
    tmp_path, capsys, target, literal, nested
):
    chain = AuditChain({"synthetic": True})
    chain.add({"approved": True})
    audit, receipt = tmp_path / "audit.json", tmp_path / "receipt.json"
    documents = {"audit": chain.document(), "receipt": chain.receipt()}
    audit.write_text(json.dumps(documents["audit"]))
    receipt.write_text(json.dumps(documents["receipt"]))
    path = audit if target == "audit" else receipt
    path.write_text(encoded_with_number(documents[target], literal, nested))
    assert main(["--verify", str(audit), "--receipt", str(receipt)]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "finite" in output.err


@pytest.mark.parametrize(
    "literal",
    ["1.7976931348623157e308", "-1e308", "1e-308", "-1e-308", "5e-324", "1e-9999", "0e9999"],
)
def test_finite_number_conversions_preserve_verification(tmp_path, capsys, literal):
    chain = AuditChain({"synthetic": True})
    chain.add({"approved": True})
    audit, receipt = tmp_path / "audit.json", tmp_path / "receipt.json"
    audit.write_text(encoded_with_number(chain.document(), literal, True))
    receipt.write_text(encoded_with_number(chain.receipt(), literal, True))
    assert main(["--verify", str(audit), "--receipt", str(receipt)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


@pytest.mark.parametrize("target", ["audit", "receipt"])
def test_actual_cli_rejects_overflow_without_claiming_receipt_mismatch(tmp_path, target):
    chain = AuditChain({"synthetic": True})
    chain.add({"approved": True})
    audit, receipt = tmp_path / "audit.json", tmp_path / "receipt.json"
    audit.write_text(json.dumps(chain.document()))
    receipt.write_text(json.dumps(chain.receipt()))
    path, document = (audit, chain.document()) if target == "audit" else (receipt, chain.receipt())
    path.write_text(encoded_with_number(document, "-1e309", True))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "guardrail_agent",
            "--verify",
            str(audit),
            "--receipt",
            str(receipt),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert "finite" in result.stderr
