"""
少女/少妇模拟器单元测试
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from modules.indicators import DailyData
from modules.simulator import (
    MarketRegime,
    Position,
    SimulationConfig,
    SimulationResult,
    TradeRecord,
)
from modules.simulator.execution_engine import execute_buy, execute_sell
from modules.simulator.exit_manager import check_exit
from modules.simulator.market_context import MarketContext, max_positions_allowed
from modules.simulator.position_sizer import build_position, calculate_position_size
from modules.simulator.signal_filter import SignalScore, SignalVerdict, filter_signals
from modules.simulator.simulator import _build_result, _portfolio_value, _run_single_day


def _make_klines(n=60, ts_code="600519.SH", start_price=100.0, trend=0.01):
    """生成测试 K 线（DailyData 对象）"""
    klines = []
    dt = datetime(2026, 1, 1)
    price = start_price
    for i in range(n):
        date_str = dt.strftime("%Y%m%d")
        prev = price
        price *= 1 + trend
        klines.append(
            DailyData(
                ts_code=ts_code,
                trade_date=date_str,
                open=prev,
                high=price * 1.02,
                low=prev * 0.98,
                close=price,
                vol=10000 + i * 100,
                amount=price * (10000 + i * 100),
                pct_chg=trend * 100,
                prev_close=prev,
            )
        )
        dt += timedelta(days=1)
    return klines


class TestPositionSizer:
    def test_basic_size(self):
        shares, risk = calculate_position_size(
            equity=1000000,
            entry_price=100,
            stop_loss=95,
            cash=1000000,
            config=SimulationConfig(risk_per_trade=0.02),
        )
        assert shares >= 100
        assert shares % 100 == 0
        assert risk > 0

    def test_cash_limit(self):
        shares, _ = calculate_position_size(
            equity=1000000,
            entry_price=10000,
            stop_loss=9500,
            cash=100000,
            config=SimulationConfig(risk_per_trade=0.02),
        )
        # 现金只够买 10 股，但 A 股最小 100 股
        assert shares == 0

    def test_invalid_stop_loss(self):
        shares, risk = calculate_position_size(
            equity=1000000,
            entry_price=100,
            stop_loss=100,
            cash=1000000,
            config=SimulationConfig(),
        )
        assert shares == 0
        assert risk == 0

    def test_build_position(self):
        pos = build_position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            stop_loss=95,
            take_profit=110,
            cash=1000000,
            equity=1000000,
            config=SimulationConfig(),
        )
        assert pos is not None
        assert pos.shares >= 100
        assert pos.shares % 100 == 0
        assert pos.stop_loss == 95


class TestExecutionEngine:
    def test_buy_slippage_and_fee(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        kline = DailyData(
            ts_code="600519.SH",
            trade_date="20260101",
            open=100,
            high=102,
            low=99,
            close=101,
            vol=10000,
            amount=1010000,
            pct_chg=1.0,
            prev_close=100,
        )
        trade = execute_buy(pos, kline, SimulationConfig(slippage=0.001, commission_rate=0.0003))
        assert trade.action == "BUY"
        assert trade.price > 100  # 滑点加价
        assert trade.fee > 0

    def test_sell_pnl(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        kline = DailyData(
            ts_code="600519.SH",
            trade_date="20260105",
            open=110,
            high=112,
            low=109,
            close=110,
            vol=10000,
            amount=1100000,
            pct_chg=10.0,
            prev_close=100,
        )
        trade = execute_sell(pos, kline, SimulationConfig(), "止盈")
        assert trade.action == "SELL"
        assert trade.pnl > 0
        assert trade.pnl_pct > 0


class TestExitManager:
    def test_stop_loss(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        klines = _make_klines(n=10, start_price=100, trend=-0.02)
        action, shares = check_exit(pos, klines, SimulationConfig())
        assert action == "STOP_LOSS"
        assert shares == 1000

    def test_hold_when_above_stop(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=90,
            take_profit=120,
            risk_amount=5000,
        )
        klines = _make_klines(n=25, start_price=100, trend=0.005)
        action, shares = check_exit(pos, klines, SimulationConfig(partial_take_profit_rr=10))
        assert action == "HOLD"
        assert shares == 0


class TestMarketContext:
    def test_max_positions_strong(self):
        ctx = MarketContext(
            date="20260101", regime=MarketRegime.STRONG, index_trend=80, breadth=0.3, moneyflow_score=70
        )
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 5

    def test_max_positions_weak(self):
        ctx = MarketContext(date="20260101", regime=MarketRegime.WEAK, index_trend=30, breadth=-0.3, moneyflow_score=30)
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 1

    def test_max_positions_neutral(self):
        ctx = MarketContext(date="20260101", regime=MarketRegime.NEUTRAL, index_trend=50, breadth=0, moneyflow_score=50)
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 4


class TestSignalFilter:
    def test_filter_requires_pass_verdict(self):
        good = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )
        bad = SignalScore(
            ts_code="000001.SZ",
            name="平安",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.HIGH_RISK,
        )
        result = filter_signals([good, bad], score_threshold=70, min_signal_count=2)
        assert len(result) == 1
        assert result[0].ts_code == "600519.SH"

    def test_filter_requires_min_signals(self):
        s = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )
        result = filter_signals([s], score_threshold=70, min_signal_count=2)
        assert len(result) == 0


class TestSimulatorCore:
    def test_portfolio_value(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=90,
            take_profit=120,
            risk_amount=5000,
        )
        klines = _make_klines(n=10, start_price=100, trend=0.01)
        state = MagicMock()
        state.cash = 500000
        state.positions = [pos]
        value = _portfolio_value(state, klines[-1].trade_date, {"600519.SH": klines})
        assert value > state.cash

    def test_build_result_empty(self):
        config = SimulationConfig()
        state = MagicMock()
        state.equity = config.initial_capital
        state.trades = []
        state.equity_curve = [{"date": "20260101", "equity": config.initial_capital}]
        state.positions = []
        result = _build_result(state, config)
        assert result.total_return == 0
        assert result.max_drawdown == 0

    def test_build_result_with_trades(self):
        config = SimulationConfig()
        state = MagicMock()
        state.equity = config.initial_capital * 1.1
        state.trades = [
            TradeRecord(ts_code="600519.SH", name="茅台", action="BUY", date="20260101", price=100, shares=100),
            TradeRecord(
                ts_code="600519.SH",
                name="茅台",
                action="SELL",
                date="20260105",
                price=110,
                shares=100,
                pnl=1000,
                pnl_pct=0.1,
            ),
        ]
        state.equity_curve = [
            {"date": "20260101", "equity": config.initial_capital},
            {"date": "20260105", "equity": config.initial_capital * 1.1},
        ]
        state.positions = []
        result = _build_result(state, config)
        assert result.total_return > 0
        assert result.total_trades == 1
        assert result.win_rate == 1.0


class TestRunSingleDay:
    @patch("modules.simulator.simulator.execute_buy")
    @patch("modules.simulator.simulator.execute_sell")
    @patch("modules.simulator.simulator.get_market_context")
    @patch("modules.simulator.simulator.build_position")
    def test_opens_position_when_signal_pass(self, mock_build, mock_ctx, mock_sell, mock_buy):
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(max_positions=1)
        state = _SimulatorState(cash=1000000, equity=1000000)

        ctx = MarketContext(
            date="20260110", regime=MarketRegime.STRONG, index_trend=70, breadth=0.1, moneyflow_score=60
        )
        mock_ctx.return_value = ctx

        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260110",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        mock_build.return_value = pos
        mock_buy.return_value = TradeRecord(
            ts_code="600519.SH", name="茅台", action="BUY", date="20260110", price=100, shares=1000
        )

        klines = _make_klines(n=70, start_price=100, trend=0.005)
        klines_map = {"600519.SH": klines}

        sig = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260110",
            score=85,
            b1_score=80,
            trend_score=80,
            volume_score=75,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )

        _run_single_day("20260110", state, [sig], klines_map, ctx, config)
        assert len(state.positions) == 1
        assert state.cash < 1000000
        mock_buy.assert_called_once()

    @patch("modules.simulator.simulator.execute_sell")
    @patch("modules.simulator.simulator.check_exit")
    @patch("modules.simulator.simulator.get_market_context")
    def test_exits_position_on_stop_loss(self, mock_ctx, mock_exit, mock_sell):
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig()
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        state = _SimulatorState(cash=0, equity=100000, positions=[pos])

        ctx = MarketContext(
            date="20260105", regime=MarketRegime.STRONG, index_trend=70, breadth=0.1, moneyflow_score=60
        )
        mock_ctx.return_value = ctx
        mock_exit.return_value = ("STOP_LOSS", 1000)
        mock_sell.return_value = TradeRecord(
            ts_code="600519.SH", name="茅台", action="SELL", date="20260105", price=94, shares=1000, pnl=-6000
        )

        klines = _make_klines(n=10, start_price=100, trend=-0.02)
        _run_single_day("20260105", state, [], {"600519.SH": klines}, ctx, config)
        assert len(state.positions) == 0
        mock_sell.assert_called_once()


class TestIntegration:
    @patch("modules.simulator.simulator.get_datasource")
    @patch("modules.simulator.simulator.get_all_stocks")
    @patch("modules.simulator.simulator.get_recent_klines")
    @patch("modules.simulator.simulator.get_market_context")
    def test_run_simulation_empty_pool(self, mock_ctx, mock_klines, mock_stocks, mock_ds):
        from modules.simulator.simulator import run_simulation

        mock_ds.return_value = MagicMock()
        mock_stocks.return_value = []
        mock_ctx.return_value = MarketContext(
            date="20260101", regime=MarketRegime.NEUTRAL, index_trend=50, breadth=0, moneyflow_score=50
        )

        result = run_simulation(ts_codes=[], days=30)
        assert isinstance(result, SimulationResult)
        assert result.total_trades == 0
        assert result.initial_capital == SimulationConfig().initial_capital
