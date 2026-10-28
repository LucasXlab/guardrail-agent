"""Offline simulation and trusted-receipt verification entry points."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import stat
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from .audit import AuditChain, verify_document
from .core import (
    Broker,
    ChaoticAgent,
    Market,
    MomentumAgent,
    Portfolio,
    RiskConfig,
    RiskGate,
    integer,
)
from .report import html_report, print_report
from .version import __version__

MAX_DOCUMENT = 20_000_000


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the finite float range")
    return number


def read_json(path: str) -> dict:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure file input requires a POSIX platform")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT:
            raise ValueError("input must be a regular JSON file under 20 MB")
        raw = handle.read(MAX_DOCUMENT + 1)
    if len(raw) > MAX_DOCUMENT:
        raise ValueError("JSON input too large")
    try:
        data = json.loads(
            raw,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            object_pairs_hook=_unique_object,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON document must be an object")
    return data


def write_outputs(outputs: dict[str, str]) -> None:
    paths = [Path(path).absolute() for path in outputs]
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("output paths must be distinct")
    staged: list[tuple[Path, Path]] = []
    try:
        for path, text in zip(paths, outputs.values(), strict=True):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError("output target must be a regular file, not a symlink")
            if not path.parent.is_dir():
                raise ValueError("output parent directory does not exist")
            fd, name = tempfile.mkstemp(prefix=".guardrail-", dir=path.parent)
            temp = Path(name)
            staged.append((temp, path))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, path in staged:
            if path.is_symlink():
                raise ValueError("output target became a symlink")
            os.replace(temp, path)
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)


def simulate(
    days: int, seed: int, agent_name: str
) -> tuple[Portfolio, AuditChain, list, RiskConfig]:
    integer(days, "days", 1)
    if days > 10_000:
        raise ValueError("days must be between 1 and 10000")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    cfg = RiskConfig()
    market = Market(cfg.symbols, seed)
    pf = Portfolio(cash=cfg.start_cash, equity=cfg.start_cash)
    gate, broker = RiskGate(cfg), Broker(cfg)
    if agent_name not in ("momentum", "chaotic"):
        raise ValueError("only deterministic offline proposers are supported")
    agent = ChaoticAgent(market, seed + 1) if agent_name == "chaotic" else MomentumAgent(market)
    audit = AuditChain({"config": asdict(cfg), "days": days, "seed": seed, "agent": agent_name})
    rejected = []
    for _ in range(days):
        prices = market.step()
        pf.new_day()
        pf.revalue(prices)
        for proposal in agent.propose(prices, pf):
            decision = gate.evaluate(proposal, pf, prices)
            fill = broker.execute(decision, pf, prices) if decision.approved else None
            if not decision.approved:
                rejected.append(decision)
            audit.add(
                {
                    "day": pf.day,
                    "proposal": asdict(proposal),
                    "approved": decision.approved,
                    "checks": [
                        {"rule": n, "pass": ok, "detail": detail}
                        for n, ok, detail in decision.checks
                    ],
                    "fill_price": fill,
                }
            )
        pf.mark(prices)
    if audit.verify() is not None:
        raise ValueError("generated audit failed full verification")
    return pf, audit, rejected, cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic synthetic proposal/gate/execution simulator; no real trading"
    )
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agent", choices=("momentum", "chaotic"), default="momentum")
    parser.add_argument("--json", dest="json_out", help="write audit document")
    parser.add_argument("--html", dest="html_out", help="write standalone synthetic report")
    parser.add_argument("--receipt-out", help="write receipt; store a trusted copy independently")
    parser.add_argument(
        "--verify", metavar="AUDIT_JSON", help="verify using a separately trusted receipt"
    )
    parser.add_argument("--receipt", metavar="RECEIPT_JSON")
    parser.add_argument("--tamper-demo", action="store_true")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="print all decisions after the summary"
    )
    parser.add_argument("--version", action="version", version=f"guardrail-agent {__version__}")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if not args.receipt or any(
                (args.json_out, args.html_out, args.receipt_out, args.tamper_demo, args.verbose)
            ):
                raise ValueError("--verify requires --receipt and cannot write simulation outputs")
            result = verify_document(read_json(args.verify), read_json(args.receipt))
            print(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
            return 0 if result.ok else 1
        if args.receipt:
            raise ValueError("--receipt is only valid with --verify")
        pf, audit, rejected, cfg = simulate(args.days, args.seed, args.agent)
        outputs = {}
        for path, data in ((args.json_out, audit.document()), (args.receipt_out, audit.receipt())):
            if path:
                if path in outputs:
                    raise ValueError("output paths must be distinct")
                text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                if len(text.encode("utf-8")) > MAX_DOCUMENT:
                    raise ValueError("audit export exceeds 20 MB; use a shorter run")
                outputs[path] = text
        if args.html_out:
            if args.html_out in outputs:
                raise ValueError("output paths must be distinct")
            outputs[args.html_out] = html_report(pf, audit, rejected, cfg, args.agent)
        write_outputs(outputs)
        print_report(pf, audit, rejected, cfg)
        if args.verbose:
            for rec in audit.records:
                p = rec["payload"]
                print(
                    f"D{p['day']} {p['proposal']['side']} {p['proposal']['qty']} {p['proposal']['symbol']} approved={p['approved']}"
                )
        if args.tamper_demo and audit.records:
            damaged = copy.deepcopy(audit.document())
            damaged["records"][0]["payload"]["approved"] = not damaged["records"][0]["payload"][
                "approved"
            ]
            result = verify_document(damaged, audit.receipt())
            print(f"Tamper demo: detected={not result.ok}; index={result.index}; {result.reason}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f"guardrail-agent: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def run_cli() -> None:
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        os._exit(0)
