"""Offline synthetic guardrail mechanism simulator."""

from .audit import AuditChain, Verification, verify_document
from .cli import main, simulate
from .core import (
    Broker,
    ChaoticAgent,
    Decision,
    Market,
    MomentumAgent,
    Portfolio,
    Proposal,
    RiskConfig,
    RiskGate,
    execution_quote,
)
from .report import html_report, print_report, sparkline
from .version import __version__

__all__ = [
    "__version__",
    "AuditChain",
    "Verification",
    "verify_document",
    "main",
    "simulate",
    "Broker",
    "ChaoticAgent",
    "Decision",
    "Market",
    "MomentumAgent",
    "Portfolio",
    "Proposal",
    "RiskConfig",
    "RiskGate",
    "execution_quote",
    "html_report",
    "print_report",
    "sparkline",
]
