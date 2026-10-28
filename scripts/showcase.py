"""Run real installed CLI/API scenarios on synthetic data; retain all outputs.

The simulator and API cost example are educational, not real orders or returns.
Use --out to select the output directory. No network or model is used.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path


def costs() -> int:
    """Actual public API calls, distinct from the built-in CLI report."""
    from guardrail_agent.core import (
        Broker,
        Portfolio,
        Proposal,
        RiskConfig,
        RiskGate,
        execution_quote,
    )

    cfg = RiskConfig()
    prices = {"AAPL": 100.0}
    portfolio = Portfolio(cash=5000.0, equity=5000.0)
    proposal = Proposal("AAPL", "BUY", 10, 100.0, "Synthetic cost example", "showcase")
    decision = RiskGate(cfg).evaluate(proposal, portfolio, prices)
    assert decision.approved
    quote = execution_quote(proposal, prices, cfg)
    before = portfolio.cash
    fill = Broker(cfg).execute(decision, portfolio, prices)
    assert fill == quote.fill
    assert math.isclose(before - portfolio.cash, quote.notional + quote.fee)
    too_large = Proposal("AAPL", "BUY", 1000, 100.0, "Synthetic rejection", "showcase")
    rejected = RiskGate(cfg).evaluate(too_large, portfolio, prices)
    assert not rejected.approved
    state = asdict(portfolio)
    try:
        Broker(cfg).execute(rejected, portfolio, prices)
    except ValueError as exc:
        rejection = str(exc)
    else:
        raise AssertionError("A rejected decision executed")
    assert asdict(portfolio) == state
    print("Actual public Python API results; synthetic single-threaded execution only.")
    result = {
        "proposal": {"symbol": proposal.symbol, "side": proposal.side, "qty": proposal.qty},
        "reference_and_market_price": 100.0,
        "gate_approved": decision.approved,
        "slippage_rate": cfg.slippage,
        "fee_rate": cfg.fee_rate,
        "execution_quote": asdict(quote),
        "actual_fill": fill,
        "cash_before": before,
        "cash_after": portfolio.cash,
        "oversize_gate_approved": rejected.approved,
        "rejected_execution": rejection,
        "rejection_preserved_portfolio": asdict(portfolio) == state,
    }
    for key, value in result.items():
        print(f"{key}: " + json.dumps(value, ensure_ascii=False, allow_nan=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("assets"))
    parser.add_argument("--costs", action="store_true", help="run the actual public API example")
    args = parser.parse_args()
    if args.costs:
        return costs()
    destination = args.out.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="guardrail-showcase-") as temporary:
        working = Path(temporary)
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env["NO_COLOR"] = "1"

        def run(name, arguments, expected, *, api=False):
            if api:
                argv = [sys.executable, str(Path(__file__).absolute()), "--costs"]
                display = ["python", "scripts/showcase.py", "--costs"]
            else:
                argv = [sys.executable, "-m", "guardrail_agent", *arguments]
                display = ["guardrail-agent", *arguments]
            result = subprocess.run(
                argv, cwd=working, env=env, capture_output=True, text=True, timeout=60
            )
            records.append(
                {
                    "name": name,
                    "kind": "public-python-api" if api else "installed-cli",
                    "command": display,
                    "expected_exit_code": expected,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            if result.returncode != expected:
                raise RuntimeError(f"{name}: expected exit {expected}, got {result.returncode}")
            print(f"=== CASE: {name} ===", flush=True)
            print("$ " + shlex.join(display), flush=True)
            print((result.stdout + result.stderr).strip(), flush=True)
            print(f"[exit {result.returncode}; expected {expected}]", flush=True)
            return result.stdout

        run(
            "simulation",
            [
                "--days",
                "12",
                "--seed",
                "7",
                "--agent",
                "chaotic",
                "--json",
                "audit.json",
                "--receipt-out",
                "receipt.json",
                "--html",
                "report.html",
                "--tamper-demo",
            ],
            0,
        )
        document = json.loads((working / "audit.json").read_text())
        assert any(record["payload"]["approved"] for record in document["records"])
        assert any(not record["payload"]["approved"] for record in document["records"])
        run("costs", [], 0, api=True)
        clean = run("receipt", ["--verify", "audit.json", "--receipt", "receipt.json"], 0)
        assert json.loads(clean)["ok"] is True and json.loads(clean)["anchored"] is True
        damaged = copy.deepcopy(document)
        damaged["records"].pop()
        (working / "truncated.json").write_text(json.dumps(damaged, ensure_ascii=False))
        refused = run("tamper", ["--verify", "truncated.json", "--receipt", "receipt.json"], 1)
        assert json.loads(refused)["ok"] is False
        for source, target in [
            ("audit.json", "synthetic-audit.json"),
            ("receipt.json", "synthetic-receipt.json"),
            ("report.html", "synthetic-report.html"),
            ("truncated.json", "synthetic-truncated.json"),
        ]:
            (destination / target).write_bytes((working / source).read_bytes())
    (destination / "showcase-raw.json").write_text(
        json.dumps(
            {"schema": "guardrail-showcase-v1", "synthetic_only": True, "calls": records},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    print(
        "Trusted receipt must be kept independently; rewriting both files is not authenticated.",
        flush=True,
    )
    print("No real orders, live market, model, financial return claim or network call.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
