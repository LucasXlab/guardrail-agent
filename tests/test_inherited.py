"""项目 04 · 护栏交易代理测试。

重点覆盖本次修复：
  1. day_pnl 必须包含持仓浮动盈亏 —— 修之前只扣手续费，熔断线永远碰不到
  2. 熔断语义：禁开仓、允许减仓
  3. 无行情标的的估值回退（不再按 0 计，凭空抹掉持仓）
  4. 已实现盈亏与成本基础结转
  5. 哈希链篡改检测
"""

import io
import pathlib
import unittest
from contextlib import redirect_stdout

import guardrail_agent as g


def mk_portfolio(cash=100_000.0):
    return g.Portfolio(cash=cash, equity=cash)


class TestRevalue(unittest.TestCase):
    """本次修复的核心。"""

    def test_float_loss_is_reflected_in_day_pnl(self):
        pf = mk_portfolio()
        pf.cash -= 10_000  # 买入 100 股 @100
        pf.positions["AAPL"] = 100
        pf.last_prices["AAPL"] = 100.0
        pf.equity = pf.cash + 100 * 100.0
        pf.new_day()  # 当日基准权益 = 100000

        pf.revalue({"AAPL": 80.0})  # 股价跌 20%

        self.assertAlmostEqual(pf.equity, 90_000 + 8_000, places=2)
        self.assertAlmostEqual(pf.day_pnl, -2_000, places=2)

    def test_float_gain_is_reflected(self):
        pf = mk_portfolio()
        pf.cash -= 10_000
        pf.positions["AAPL"] = 100
        pf.last_prices["AAPL"] = 100.0
        pf.equity = 100_000.0
        pf.new_day()

        pf.revalue({"AAPL": 130.0})

        self.assertAlmostEqual(pf.day_pnl, 3_000, places=2)

    def test_day_pnl_is_reachable_at_breaker_scale(self):
        """回归断言：修理前的口径下 day_pnl 只会是手续费量级（<100 元）。"""
        pf = mk_portfolio()
        pf.cash -= 50_000
        pf.positions["NVDA"] = 100
        pf.last_prices["NVDA"] = 500.0
        pf.equity = 100_000.0
        pf.new_day()

        pf.revalue({"NVDA": 400.0})  # 跌 20%

        self.assertLess(pf.day_pnl, -g.RiskConfig().max_daily_loss, "熔断阈值必须能被浮动亏损触及")


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.cfg = g.RiskConfig()
        self.gate = g.RiskGate(self.cfg)
        self.prices = {"AAPL": 100.0}

    def _portfolio_in_breaker(self):
        pf = mk_portfolio()
        pf.day = 5
        pf.day_pnl = -self.cfg.max_daily_loss - 1
        pf.positions["AAPL"] = 50
        pf.cost_basis["AAPL"] = 5000.0
        pf.last_prices.update(self.prices)
        return pf

    def test_breaker_rejects_buy(self):
        pf = self._portfolio_in_breaker()
        buy = g.Proposal("AAPL", "BUY", 10, 100.0, "测试", "t")
        d = self.gate.evaluate(buy, pf, self.prices)
        self.assertFalse(d.approved)
        self.assertTrue(any("熔断" in r for r in d.reject_reasons()))

    def test_breaker_still_allows_sell(self):
        """熔断只禁开仓，减仓通道必须保持畅通，否则就无法止损。"""
        pf = self._portfolio_in_breaker()
        sell = g.Proposal("AAPL", "SELL", 10, 100.0, "测试", "t")
        d = self.gate.evaluate(sell, pf, self.prices)
        self.assertTrue(d.approved, f"卖出被误拦：{d.reject_reasons()}")

    def test_all_checks_are_recorded(self):
        """无论通过与否都要留痕，方便审计追问"为什么没拦"。"""
        pf = mk_portfolio()
        buy = g.Proposal("AAPL", "BUY", 10, 100.0, "测试", "t")
        d = self.gate.evaluate(buy, pf, self.prices)
        self.assertEqual(len(d.checks), 13)


class TestPositionValuation(unittest.TestCase):
    def test_missing_quote_falls_back_to_last_price(self):
        """回归：以前无行情标的按 0 计，持仓会被凭空抹掉。"""
        pf = mk_portfolio()
        pf.positions["AAPL"] = 100
        pf.last_prices["AAPL"] = 150.0
        self.assertAlmostEqual(pf.position_value({}), 15_000.0)

    def test_explicit_quote_wins(self):
        pf = mk_portfolio()
        pf.positions["AAPL"] = 100
        pf.last_prices["AAPL"] = 150.0
        self.assertAlmostEqual(pf.position_value({"AAPL": 120.0}), 12_000.0)


class TestBroker(unittest.TestCase):
    def setUp(self):
        self.cfg = g.RiskConfig()
        self.broker = g.Broker(self.cfg)
        self.pf = mk_portfolio()
        self.pf.last_prices.update({"AAPL": 100.0})

    def _run(self, side, qty, price, mkt):
        proposal = g.Proposal("AAPL", side, qty, price, "", "t")
        d = g.RiskGate(self.cfg).evaluate(proposal, self.pf, {"AAPL": mkt})
        self.assertTrue(d.approved)
        return self.broker.execute(d, self.pf, {"AAPL": mkt})

    def test_realized_pnl_is_positive_on_profitable_sell(self):
        self._run("BUY", 100, 100.0, 100.0)
        self._run("SELL", 100, 110.0, 110.0)
        self.assertGreater(self.pf.realized_pnl, 0)
        self.assertNotIn("AAPL", self.pf.positions)
        self.assertNotIn("AAPL", self.pf.cost_basis)

    def test_realized_pnl_is_negative_on_loss_sell(self):
        self._run("BUY", 100, 100.0, 100.0)
        self._run("SELL", 100, 90.0, 90.0)
        self.assertLess(self.pf.realized_pnl, 0)

    def test_cost_basis_accumulates_on_partial_sell(self):
        self._run("BUY", 100, 100.0, 100.0)
        self._run("SELL", 40, 110.0, 110.0)
        self.assertEqual(self.pf.positions["AAPL"], 60)
        self.assertGreater(self.pf.cost_basis["AAPL"], 0)

    def test_fee_shows_up_in_day_pnl(self):
        self.pf.new_day()
        self._run("BUY", 100, 100.0, 100.0)
        self.assertLess(self.pf.day_pnl, 0)


class TestAuditChain(unittest.TestCase):
    def test_clean_chain_verifies(self):
        chain = g.AuditChain()
        for i in range(5):
            chain.add({"i": i})
        self.assertIsNone(chain.verify())

    def test_tampering_is_detected(self):
        chain = g.AuditChain()
        for i in range(5):
            chain.add({"i": i})
        chain.records[2]["payload"]["i"] = 999
        self.assertEqual(chain.verify(), 2)


class TestEndToEnd(unittest.TestCase):
    def test_momentum_run(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = g.main(["--days", "60", "--seed", "42"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("审计链", out)
        self.assertIn("完好", out)

    def test_chaotic_run_rejects_proposals(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = g.main(["--days", "60", "--seed", "3", "--agent", "chaotic"])
        self.assertEqual(rc, 0)
        self.assertIn("裁决驳回", buf.getvalue())

    def test_html_report_is_written(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = f"{d}/report.html"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = g.main(["--days", "30", "--seed", "1", "--html", path])
            self.assertEqual(rc, 0)
            html = pathlib.Path(path).read_text(encoding="utf-8")
            self.assertIn("<svg", html)
            self.assertIn("审计链", html)


if __name__ == "__main__":
    unittest.main()
