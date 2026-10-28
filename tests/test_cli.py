import copy
import json
import os

import pytest

from guardrail_agent import main, simulate, sparkline
from guardrail_agent.cli import read_json, write_outputs
from guardrail_agent.report import html_report


def test_export_verify_tamper_and_verbose(tmp_path, capsys):
    audit, receipt, report = (tmp_path / n for n in ("audit.json", "receipt.json", "report.html"))
    assert (
        main(
            [
                "--days",
                "30",
                "--agent",
                "chaotic",
                "--json",
                str(audit),
                "--receipt-out",
                str(receipt),
                "--html",
                str(report),
                "--verbose",
                "--tamper-demo",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Tamper demo: detected=True" in out
    data, anchor = json.loads(audit.read_text()), json.loads(receipt.read_text())
    assert anchor["count"] == len(data["records"])
    assert all("seq" in r and "context_digest" in r for r in data["records"])
    assert main(["--verify", str(audit), "--receipt", str(receipt)]) == 0
    assert json.loads(capsys.readouterr().out)["anchored"] is True
    data["records"].pop()
    audit.write_text(json.dumps(data))
    assert main(["--verify", str(audit), "--receipt", str(receipt)]) == 1
    assert not json.loads(capsys.readouterr().out)["ok"]


@pytest.mark.parametrize(
    "args",
    [
        ["--days", "0"],
        ["--days", "-1"],
        ["--days", "10001"],
        ["--receipt", "missing"],
        ["--verify", "missing"],
        ["--verify", "missing", "--receipt", "missing", "--verbose"],
    ],
)
def test_invalid_cli_returns_controlled_error(args, capsys):
    assert main(args) == 2
    assert "guardrail-agent:" in capsys.readouterr().err


def test_unknown_removed_llm_options_fail():
    with pytest.raises(SystemExit) as exc:
        main(["--agent", "llm"])
    assert exc.value.code == 2


def test_output_aliases_are_rejected_without_overwriting(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("preserve")
    assert main(["--days", "1", "--json", str(p), "--html", str(p)]) == 2
    assert p.read_text() == "preserve"
    assert (
        main(["--days", "1", "--json", str(p), "--receipt-out", str(tmp_path / "." / "out.json")])
        == 2
    )
    assert p.read_text() == "preserve"


def test_missing_parent_validates_all_outputs_before_replacing(tmp_path):
    one = tmp_path / "one.json"
    one.write_text("original")
    assert (
        main(["--days", "1", "--json", str(one), "--html", str(tmp_path / "missing" / "two.html")])
        == 2
    )
    assert one.read_text() == "original"
    assert not list(tmp_path.glob(".guardrail-*"))


def test_output_symlink_cannot_modify_sentinel(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("original")
    link = tmp_path / "report"
    link.symlink_to(sentinel)
    assert main(["--days", "1", "--html", str(link)]) == 2
    assert sentinel.read_text() == "original"


@pytest.mark.parametrize(
    "raw", ["[]", '{"a":NaN}', '{"a":1,"a":2}', "{broken", "[" * 1500 + "]" * 1500]
)
def test_strict_json_reads_reject_invalid_input(tmp_path, raw):
    p = tmp_path / "input.json"
    p.write_text(raw)
    with pytest.raises(ValueError):
        read_json(str(p))


def test_read_symlink_fifo_and_oversize_are_bounded(tmp_path):
    normal = tmp_path / "normal.json"
    normal.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(normal)
    with pytest.raises(OSError):
        read_json(str(link))
    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        read_json(str(fifo))
    huge = tmp_path / "huge.json"
    with huge.open("wb") as handle:
        handle.truncate(20_000_001)
    with pytest.raises(ValueError):
        read_json(str(huge))


def test_simulations_deterministic_and_html_escaped():
    first = simulate(60, 42, "momentum")
    second = simulate(60, 42, "momentum")
    assert first[1].document() == second[1].document()
    assert first[0].equity_history == second[0].equity_history
    pf, audit, rejected, cfg = first
    original = copy.deepcopy(audit.document())
    audit.records[0]["payload"]["proposal"]["source"] = '<script>alert("synthetic")</script>'
    report = html_report(pf, audit, rejected, cfg, '<img onerror="synthetic">')
    assert "<script>" not in report and "<img onerror" not in report
    assert "&lt;script&gt;" in report and "altered" in report
    assert original["records"] != audit.records


def test_small_and_empty_sparklines_and_empty_output_plan():
    assert sparkline([]) == ""
    assert sparkline([1.0, 1.0]) == "▁▁"
    assert len(sparkline(list(range(240)))) == 60
    write_outputs({})


def test_simulate_rejects_invalid_types():
    for args in ((True, 1, "momentum"), (1, True, "momentum"), (1, 1, "llm")):
        with pytest.raises(ValueError):
            simulate(*args)
