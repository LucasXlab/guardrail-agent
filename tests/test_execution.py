import copy
import math
from dataclasses import asdict, replace

import pytest

from guardrail_agent import (
    Broker,
    Decision,
    Portfolio,
    Proposal,
    RiskConfig,
    RiskGate,
    execution_quote,
)


def setup(cash=100_000.0, **overrides):
    cfg = RiskConfig(**overrides)
    pf = Portfolio(cash=cash, equity=cash)
    prices = {"AAPL": 100.0}
    return cfg, pf, prices


def proposal(**values):
    return replace(Proposal("AAPL", "BUY", 10, 100.0, "synthetic", "test"), **values)


@pytest.mark.parametrize(
    "cash,qty,reference", [(2000, 100, 10), (100000, 300, 50), (1000.3, 10, 100)]
)
def test_actual_fill_budget_regressions(cash, qty, reference):
    cfg, pf, prices = setup(cash)
    before = asdict(pf)
    decision = RiskGate(cfg).evaluate(proposal(qty=qty, price=reference), pf, prices)
    assert not decision.approved
    with pytest.raises(ValueError):
        Broker(cfg).execute(decision, pf, prices)
    assert asdict(pf) == before


def test_exact_cash_boundary_and_shared_quote():
    cfg, _, prices = setup()
    p = proposal()
    quote = execution_quote(p, prices, cfg)
    pf = Portfolio(quote.notional + quote.fee, equity=quote.notional + quote.fee)
    d = RiskGate(cfg).evaluate(p, pf, prices)
    assert d.approved
    assert Broker(cfg).execute(d, pf, prices) == quote.fill
    assert pf.cash == 0


@pytest.mark.parametrize(
    "values",
    [
        {"qty": True},
        {"qty": 10.5},
        {"qty": "10"},
        {"qty": None},
        {"qty": 0},
        {"qty": -1},
        {"qty": 10**1000},
        {"price": math.nan},
        {"price": math.inf},
        {"price": 0},
        {"price": "100"},
        {"side": "HOLD"},
        {"symbol": "../escape"},
        {"source": "\x1b[31m"},
    ],
)
def test_invalid_inputs_reject_without_state_change(values):
    cfg, pf, prices = setup()
    before = asdict(pf)
    d = RiskGate(cfg).evaluate(proposal(**values), pf, prices)
    assert not d.approved
    assert len(d.checks) == 13
    assert sum(ok is False for _, ok, _ in d.checks) == 1
    assert any(ok is None for _, ok, _ in d.checks)
    assert asdict(pf) == before


@pytest.mark.parametrize(
    "values",
    [
        {"fee_rate": -1},
        {"slippage": 1},
        {"max_price_deviation": math.nan},
        {"max_notional": 0},
        {"min_notional": 30000},
        {"max_orders_per_day": True},
        {"cooldown_days": -1},
        {"symbols": ("AAPL", "AAPL")},
        {"symbols": ()},
    ],
)
def test_invalid_config_fails(values):
    with pytest.raises(ValueError):
        RiskConfig(**values)


def test_rejected_forged_and_replayed_decisions_are_nonmutating():
    cfg, pf, prices = setup()
    broker, gate = Broker(cfg), RiskGate(cfg)
    manual = Decision(proposal(), True, [])
    before = asdict(pf)
    with pytest.raises(ValueError):
        broker.execute(manual, pf, prices)
    assert asdict(pf) == before
    d = gate.evaluate(proposal(), pf, prices)
    broker.execute(d, pf, prices)
    after = asdict(pf)
    with pytest.raises(ValueError):
        broker.execute(d, pf, prices)
    assert asdict(pf) == after


@pytest.mark.parametrize("change", ["price", "cash", "day", "config"])
def test_stale_decision_is_rejected(change):
    cfg, pf, prices = setup()
    d = RiskGate(cfg).evaluate(proposal(), pf, prices)
    if change == "price":
        prices["AAPL"] = 100.1
    elif change == "cash":
        pf.cash -= 1
    elif change == "day":
        pf.day += 1
    else:
        cfg = replace(cfg, fee_rate=0.001)
    before = asdict(pf)
    with pytest.raises(ValueError):
        Broker(cfg).execute(d, pf, prices)
    assert asdict(pf) == before


def test_reduce_only_bypasses_opening_constraints_but_never_short_sells():
    cfg, pf, prices = setup()
    pf.positions["AAPL"], pf.cost_basis["AAPL"] = 100, 10000
    pf.last_prices.update(prices)
    pf.day, pf.last_trade_day["AAPL"] = 5, 5
    pf.orders_today, pf.day_pnl = cfg.max_orders_per_day, -9000
    p = proposal(side="SELL", qty=5)
    d = RiskGate(cfg).evaluate(p, pf, prices)
    assert d.approved
    Broker(cfg).execute(d, pf, prices)
    assert pf.positions["AAPL"] == 95
    assert not RiskGate(cfg).evaluate(replace(p, qty=96), pf, prices).approved


def test_unknown_valuation_and_nonfinite_quotes_fail_without_mutation():
    _, pf, _ = setup()
    pf.positions["AAPL"] = 100
    before = copy.deepcopy(asdict(pf))
    for prices in ({}, {"AAPL": math.nan}, {"AAPL": 0}):
        with pytest.raises(ValueError):
            pf.revalue(prices)
        assert asdict(pf) == before
    pf.last_prices["AAPL"] = 100
    assert pf.position_value({}) == 10000


def test_current_prices_override_last_and_missing_basis_cannot_sell():
    cfg, pf, prices = setup()
    pf.positions["AAPL"], pf.last_prices["AAPL"] = 20, 90
    assert pf.position_value(prices) == 2000
    assert not RiskGate(cfg).evaluate(proposal(side="SELL"), pf, prices).approved


def test_loss_and_profit_remain_real_floating_accounting():
    cfg, pf, prices = setup()
    broker, gate = Broker(cfg), RiskGate(cfg)
    pf.new_day()
    broker.execute(gate.evaluate(proposal(qty=100), pf, prices), pf, prices)
    original_basis = pf.cost_basis["AAPL"]
    prices["AAPL"] = 110
    sell = proposal(side="SELL", qty=40, price=110)
    broker.execute(gate.evaluate(sell, pf, prices), pf, prices)
    assert pf.cost_basis["AAPL"] == pytest.approx(original_basis * 0.6)
    assert pf.realized_pnl > 0
    assert pf.cash >= 0


def test_oversized_numeric_input_cannot_overflow_out_of_gate():
    cfg, pf, prices = setup()
    prices["AAPL"] = 1e308
    assert not RiskGate(cfg).evaluate(proposal(qty=MAX_AMOUNT, price=1e308), pf, prices).approved


MAX_AMOUNT = 1_000_000_000
