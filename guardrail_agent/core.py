"""Deterministic teaching simulator; no network, broker, or model integration."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
from dataclasses import asdict, dataclass, field

SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,15}\Z")
MAX_QTY = 1_000_000_000


def finite(value: object, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"{name} is outside its finite range")
    return number


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_QTY:
        raise ValueError(f"{name} must be an integer in [{minimum}, {MAX_QTY}]")
    return value


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


@dataclass(frozen=True)
class Proposal:
    """A reference quote, not a limit order or an execution capability."""

    symbol: str
    side: str
    qty: int
    price: float
    reason: str
    source: str

    def validate(self) -> None:
        if not isinstance(self.symbol, str) or not SYMBOL.fullmatch(self.symbol):
            raise ValueError("invalid symbol")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        integer(self.qty, "qty", 1)
        if finite(self.price, "reference price", minimum=0) == 0:
            raise ValueError("reference price must be positive")
        for name, maximum in (("reason", 500), ("source", 64)):
            text = getattr(self, name)
            if (
                not isinstance(text, str)
                or len(text) > maximum
                or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text)
            ):
                raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class RiskConfig:
    symbols: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "SPY")
    start_cash: float = 100_000.0
    max_notional: float = 25_000.0
    min_notional: float = 800.0
    max_price_deviation: float = 0.02
    max_position_value: float = 40_000.0
    max_gross_exposure: float = 80_000.0
    max_orders_per_day: int = 6
    max_daily_loss: float = 8_000.0
    cooldown_days: int = 2
    fee_rate: float = 0.0003
    slippage: float = 0.0005

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.symbols, tuple) or not self.symbols:
            raise ValueError("symbols must be a nonempty unique tuple")
        if any(not isinstance(s, str) or not SYMBOL.fullmatch(s) for s in self.symbols):
            raise ValueError("invalid configured symbol")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("configured symbols must be unique")
        for name in (
            "start_cash",
            "max_notional",
            "max_position_value",
            "max_gross_exposure",
            "max_daily_loss",
        ):
            if finite(getattr(self, name), name, minimum=0) == 0:
                raise ValueError(f"{name} must be positive")
        finite(self.min_notional, "min_notional", minimum=0)
        if self.min_notional > self.max_notional:
            raise ValueError("min_notional exceeds max_notional")
        for name in ("fee_rate", "slippage", "max_price_deviation"):
            if finite(getattr(self, name), name, minimum=0) >= 1:
                raise ValueError(f"{name} must be below 1")
        integer(self.max_orders_per_day, "max_orders_per_day", 1)
        integer(self.cooldown_days, "cooldown_days")


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    day: int = 0
    day_pnl: float = 0.0
    orders_today: int = 0
    last_trade_day: dict[str, int] = field(default_factory=dict)
    equity: float = 0.0
    equity_history: list[float] = field(default_factory=list)
    realized_pnl: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    day_start_equity: float = 0.0
    last_prices: dict[str, float] = field(default_factory=dict)
    cost_basis: dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        if any(
            not isinstance(getattr(self, name), dict)
            for name in ("positions", "cost_basis", "last_trade_day", "last_prices")
        ) or not isinstance(self.equity_history, list):
            raise ValueError("invalid portfolio collection")
        finite(self.cash, "cash", minimum=0)
        for name in (
            "equity",
            "day_pnl",
            "realized_pnl",
            "day_start_equity",
            "peak_equity",
            "max_drawdown",
        ):
            finite(getattr(self, name), name)
        integer(self.day, "day")
        integer(self.orders_today, "orders_today")
        for symbol, qty in self.positions.items():
            if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
                raise ValueError("invalid holding symbol")
            integer(qty, "holding quantity")
        for value in self.cost_basis.values():
            finite(value, "cost basis", minimum=0)
        for value in self.last_trade_day.values():
            integer(value, "last trade day")
        for value in self.equity_history:
            finite(value, "equity history")
        validate_prices(self.last_prices)

    def position_value(self, prices: dict[str, float] | None = None) -> float:
        self.validate()
        quotes = dict(self.last_prices)
        if prices is not None:
            validate_prices(prices)
            quotes.update(prices)
        values = []
        for symbol, qty in self.positions.items():
            if qty:
                if symbol not in quotes:
                    raise ValueError(f"missing valuation for {symbol}")
                values.append(finite(qty * quotes[symbol], "position value", minimum=0))
        return finite(sum(values), "gross exposure", minimum=0)

    def new_day(self) -> None:
        self.validate()
        self.day += 1
        self.orders_today = 0
        self.day_pnl = 0.0
        self.day_start_equity = self.equity

    def revalue(self, prices: dict[str, float]) -> None:
        value = self.position_value(prices)
        equity = finite(self.cash + value, "equity", minimum=0)
        pnl = finite(equity - self.day_start_equity, "day pnl")
        self.last_prices.update(prices)
        self.equity, self.day_pnl = equity, pnl

    def mark(self, prices: dict[str, float]) -> None:
        self.revalue(prices)
        self.equity_history.append(self.equity)
        self.peak_equity = max(self.peak_equity, self.equity)
        if self.peak_equity > 0:
            self.max_drawdown = max(
                self.max_drawdown, (self.peak_equity - self.equity) / self.peak_equity
            )


def validate_prices(prices: dict[str, float]) -> None:
    if not isinstance(prices, dict):
        raise ValueError("prices must be an object")
    for symbol, price in prices.items():
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
            raise ValueError("invalid quote symbol")
        if finite(price, "market price", minimum=0) == 0:
            raise ValueError("market price must be positive")


@dataclass(frozen=True)
class ExecutionQuote:
    fill: float
    notional: float
    fee: float


def execution_quote(
    proposal: Proposal, prices: dict[str, float], cfg: RiskConfig
) -> ExecutionQuote:
    proposal.validate()
    cfg.validate()
    validate_prices(prices)
    if proposal.symbol not in prices:
        raise ValueError("proposal has no current market price")
    market = prices[proposal.symbol]
    fill = finite(
        market * (1 + cfg.slippage if proposal.side == "BUY" else 1 - cfg.slippage),
        "fill",
        minimum=0,
    )
    notional = finite(proposal.qty * fill, "execution notional", minimum=0)
    fee = finite(notional * cfg.fee_rate, "execution fee", minimum=0)
    return ExecutionQuote(fill, notional, fee)


def state_token(p: Proposal, pf: Portfolio, prices: dict[str, float], cfg: RiskConfig) -> str:
    blob = canonical(
        {"proposal": asdict(p), "portfolio": asdict(pf), "prices": prices, "config": asdict(cfg)}
    )
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(frozen=True)
class Decision:
    proposal: Proposal
    approved: bool
    checks: list[tuple[str, bool | None, str]] = field(default_factory=list)
    state_hash: str | None = None

    def reject_reasons(self) -> list[str]:
        return [f"{name}（{detail}）" for name, ok, detail in self.checks if ok is False]


CHECK_NAMES = (
    "标的白名单",
    "方向合法",
    "数量与输入合法",
    "单笔金额下限",
    "单笔金额上限",
    "报价偏离市价",
    "标的持仓上限",
    "总敞口上限",
    "现金或持仓充足",
    "当日订单数上限",
    "冷却期",
    "熔断状态",
    "标的有效",
)


class RiskGate:
    def __init__(self, cfg: RiskConfig):
        cfg.validate()
        self.cfg = cfg

    def evaluate(self, p: Proposal, pf: Portfolio, prices: dict[str, float]) -> Decision:
        try:
            p.validate()
            pf.validate()
            quote = execution_quote(p, prices, self.cfg)
            gross = pf.position_value(prices)
            held = pf.positions.get(p.symbol, 0)
            if p.side == "SELL" and held and p.symbol not in pf.cost_basis:
                raise ValueError("holding has no cost basis")
            market = prices[p.symbol]
            after_qty = held + p.qty if p.side == "BUY" else held - p.qty
            after_value = finite(after_qty * market, "post-trade position")
            gross_after = finite(gross - held * market + after_value, "post-trade exposure")
            cost = finite(quote.notional + quote.fee, "cash requirement")
            token = state_token(p, pf, prices, self.cfg)
        except (ValueError, TypeError, AttributeError, OverflowError):
            checks = [
                (
                    name,
                    False if index == 2 else None,
                    "invalid input or unavailable valuation"
                    if index == 2
                    else "not evaluated because input validation failed",
                )
                for index, name in enumerate(CHECK_NAMES)
            ]
            return Decision(p, False, checks)

        cfg = self.cfg
        reduce_only = p.side == "SELL" and 0 < p.qty <= held
        exempt = "reduce-only exemption" if reduce_only else "opening-order constraint"
        last = pf.last_trade_day.get(p.symbol, -MAX_QTY)
        checks = [
            (CHECK_NAMES[0], p.symbol in cfg.symbols, p.symbol),
            (CHECK_NAMES[1], p.side in ("BUY", "SELL"), p.side),
            (CHECK_NAMES[2], True, f"{p.qty} integer units; finite values"),
            (CHECK_NAMES[3], reduce_only or quote.notional >= cfg.min_notional, exempt),
            (
                CHECK_NAMES[4],
                quote.notional <= cfg.max_notional,
                f"execution notional {quote.notional:.4f} <= {cfg.max_notional:.4f}",
            ),
            (
                CHECK_NAMES[5],
                abs(p.price - market) / market <= cfg.max_price_deviation,
                "reference quote must be within the two-sided deviation bound",
            ),
            (CHECK_NAMES[6], reduce_only or abs(after_value) <= cfg.max_position_value, exempt),
            (CHECK_NAMES[7], reduce_only or gross_after <= cfg.max_gross_exposure, exempt),
            (
                CHECK_NAMES[8],
                p.qty <= held if p.side == "SELL" else cost <= pf.cash,
                "uses actual fill plus fee",
            ),
            (CHECK_NAMES[9], reduce_only or pf.orders_today < cfg.max_orders_per_day, exempt),
            (CHECK_NAMES[10], reduce_only or pf.day - last >= cfg.cooldown_days, exempt),
            (
                CHECK_NAMES[11],
                reduce_only or pf.day_pnl > -cfg.max_daily_loss,
                "熔断仅允许减仓; no short selling",
            ),
            (CHECK_NAMES[12], p.symbol in prices, p.symbol),
        ]
        return Decision(p, all(ok for _, ok, _ in checks), checks, token)


class Broker:
    """In-process simulated executor, not an authorization or real trading API."""

    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def execute(self, d: Decision, pf: Portfolio, prices: dict[str, float]) -> float:
        if not isinstance(d, Decision) or not d.approved or not d.state_hash:
            raise ValueError("execution requires an approved, gate-issued decision")
        current = RiskGate(self.cfg).evaluate(d.proposal, pf, prices)
        if not current.approved or current.state_hash != d.state_hash:
            raise ValueError("decision is stale or no longer passes current rules")
        p = d.proposal
        quote = execution_quote(p, prices, self.cfg)
        candidate = copy.deepcopy(pf)
        if p.side == "BUY":
            candidate.cash -= quote.notional + quote.fee
            candidate.positions[p.symbol] = candidate.positions.get(p.symbol, 0) + p.qty
            candidate.cost_basis[p.symbol] = (
                candidate.cost_basis.get(p.symbol, 0.0) + quote.notional + quote.fee
            )
        else:
            held = candidate.positions[p.symbol]
            avg_cost = candidate.cost_basis[p.symbol] / held
            candidate.realized_pnl += quote.notional - quote.fee - avg_cost * p.qty
            candidate.cost_basis[p.symbol] = max(
                candidate.cost_basis[p.symbol] - avg_cost * p.qty, 0.0
            )
            candidate.cash += quote.notional - quote.fee
            candidate.positions[p.symbol] -= p.qty
            if not candidate.positions[p.symbol]:
                del candidate.positions[p.symbol]
                del candidate.cost_basis[p.symbol]
        candidate.orders_today += 1
        candidate.last_trade_day[p.symbol] = candidate.day
        candidate.revalue(prices)
        candidate.validate()
        pf.__dict__.update(candidate.__dict__)
        return quote.fill


class Market:
    BASE = {"AAPL": 190.0, "MSFT": 420.0, "NVDA": 880.0, "SPY": 540.0}
    VOL = {"AAPL": 0.016, "MSFT": 0.014, "NVDA": 0.030, "SPY": 0.009}

    def __init__(self, symbols: tuple[str, ...], seed: int = 42):
        self.symbols = list(symbols)
        self.rng = random.Random(seed)
        self.price = {s: self.BASE.get(s, 100.0) for s in self.symbols}
        self.history = {s: [self.price[s]] for s in self.symbols}

    def step(self) -> dict[str, float]:
        for symbol in self.symbols:
            change = self.rng.gauss(0.0004, self.VOL.get(symbol, 0.02))
            self.price[symbol] = max(1.0, self.price[symbol] * (1 + change))
            self.history[symbol].append(self.price[symbol])
        return dict(self.price)

    def ma(self, symbol: str, window: int = 10) -> float:
        values = self.history[symbol][-window:]
        return sum(values) / len(values)


class MomentumAgent:
    name = "momentum"

    def __init__(self, market: Market, target_notional: float = 15_000.0):
        self.market, self.target_notional = market, target_notional

    def propose(self, prices: dict[str, float], portfolio: Portfolio) -> list[Proposal]:
        proposals = []
        for symbol in self.market.symbols:
            price, average = prices[symbol], self.market.ma(symbol)
            held = portfolio.positions.get(symbol, 0)
            if price > average * 1.012 and not held:
                qty = int(self.target_notional / price)
                if qty:
                    proposals.append(
                        Proposal(
                            symbol,
                            "BUY",
                            qty,
                            price,
                            "synthetic momentum above moving average",
                            self.name,
                        )
                    )
            elif price < average * 0.988 and held:
                proposals.append(
                    Proposal(
                        symbol,
                        "SELL",
                        held,
                        price,
                        "synthetic momentum below moving average",
                        self.name,
                    )
                )
        return proposals


class ChaoticAgent:
    name = "chaotic"

    def __init__(self, market: Market, seed: int = 7):
        self.market, self.rng = market, random.Random(seed)

    def propose(self, prices: dict[str, float], portfolio: Portfolio) -> list[Proposal]:
        proposals = []
        for _ in range(self.rng.randint(1, 3)):
            symbol = self.rng.choice(self.market.symbols + ["TSLA", "DOGE"])
            proposals.append(
                Proposal(
                    symbol,
                    self.rng.choice(["BUY", "SELL"]),
                    self.rng.choice([0, -5, 10, 80, 500, 2000]),
                    prices.get(symbol, 100.0) * self.rng.choice([0.5, 1.0, 1.0, 1.03, 1.25]),
                    "synthetic boundary challenge",
                    self.name,
                )
            )
        return proposals
