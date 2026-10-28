"""Small self-contained HTML and terminal summaries of synthetic runs."""

from __future__ import annotations

import html
from collections import Counter

from .audit import AuditChain
from .core import Decision, Portfolio, RiskConfig


def sparkline(values: list[float]) -> str:
    if not values:
        return ""
    sample = values[:: max(1, len(values) // 60)]
    low, high = min(sample), max(sample)
    return "".join(
        "▁▂▃▄▅▆▇█"[int((value - low) / (high - low) * 7)] if high > low else "▁" for value in sample
    )


def print_report(
    pf: Portfolio, audit: AuditChain, rejected: list[Decision], cfg: RiskConfig
) -> None:
    print("\nSynthetic simulation · 收盘报告")
    print(f"Equity: {pf.equity:,.2f} | Cash: {pf.cash:,.2f} | Drawdown: {pf.max_drawdown:.2%}")
    print(
        f"Proposals: {len(audit.records)} | Accepted: {len(audit.records) - len(rejected)} | 裁决驳回: {len(rejected)}"
    )
    print(f"Equity path: {sparkline(pf.equity_history)}")
    print("审计链: 完好 (in-memory receipt)" if audit.verify() is None else "审计链: altered")
    print("Synthetic prices only. This is not investment research or a real trading safety system.")


def html_report(
    pf: Portfolio, audit: AuditChain, rejected: list[Decision], cfg: RiskConfig, agent_name: str
) -> str:
    values = pf.equity_history
    low, high = (min(values), max(values)) if values else (0.0, 1.0)
    points = " ".join(
        f"{10 + i / max(1, len(values) - 1) * 780:.2f},{190 - (v - low) / (high - low or 1) * 170:.2f}"
        for i, v in enumerate(values)
    )
    counts = Counter(
        name for decision in rejected for name, ok, _ in decision.checks if ok is False
    )
    reasons = "".join(
        f"<li>{html.escape(name)}: {count}</li>" for name, count in counts.most_common(8)
    )
    rows = []
    for rec in audit.records[-25:]:
        data = rec["payload"]
        p = data["proposal"]
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in (
                    data["day"],
                    p["source"],
                    p["symbol"],
                    p["side"],
                    p["qty"],
                    p["price"],
                    data["fill_price"],
                    data["approved"],
                )
            )
            + "</tr>"
        )
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>guardrail-agent · synthetic run</title><style>
body{{font:16px/1.6 system-ui,sans-serif;background:#10151e;color:#e5edf6;max-width:1000px;margin:40px auto;padding:20px}}h1{{font-size:30px}}strong{{color:#63d9b1}}svg{{width:100%;height:220px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #344152}}.table{{overflow-x:auto}}small{{color:#b1bfd0}}
</style><h1>guardrail-agent</h1><p>Deterministic synthetic run · proposer: {html.escape(agent_name)}</p>
<p><strong>Equity {pf.equity:,.2f}</strong> · Cash {pf.cash:,.2f} · Max drawdown {pf.max_drawdown:.2%}</p>
<p>{len(audit.records)} proposals · {len(rejected)} rejected</p>
<svg viewBox="0 0 800 210" role="img" aria-label="Synthetic equity path"><polyline points="{points}" fill="none" stroke="#63d9b1" stroke-width="2"/></svg>
<h2>Rule rejections</h2><ul>{reasons}</ul><h2>Recent decisions</h2><div class="table"><table><tr><th>Day</th><th>Source</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Reference</th><th>Fill</th><th>Approved</th></tr>{"".join(rows)}</table></div>
<p>审计链: {"完好 · internal consistency" if audit.verify() is None else "altered"}</p>
<small>Simulation only. The hash chain has no signature or identity guarantee. Keep a trusted receipt independently to detect rewriting or truncation. No real orders, market data, or investment claims.</small></html>'''
