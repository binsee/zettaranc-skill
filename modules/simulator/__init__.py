#!/usr/bin/env python3
"""
少女/少妇模拟器 v0.1

把「择时 → 选股 → 等信号 → 仓位 → 买入 → 卖出」串成可回测的端到端闭环。
基于已有战法/指标/评分体系，不做新预测模型，只做规则执行与资金管理。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketRegime(Enum):
    """市场环境状态"""

    STRONG = "强势"  # 大盘趋势向上，可积极开仓
    NEUTRAL = "震荡"  # 无明确方向，控制仓位
    WEAK = "弱势"  # 趋势向下，空仓或轻仓


class SignalVerdict(Enum):
    """单票信号评审结果"""

    PASS = "通过"
    NO_SIGNAL = "无信号"
    LOW_SCORE = "评分不足"
    HIGH_RISK = "风险过高"
    BAD_STAGE = "阶段不利"


@dataclass
class MarketContext:
    """每日市场环境快照"""

    date: str
    regime: MarketRegime
    index_trend: float  # 大盘指数趋势得分 0-100
    breadth: float  # 涨跌家数比，-1 ~ 1
    moneyflow_score: float  # 资金流向得分 0-100
    notes: list[str] = field(default_factory=list)


@dataclass
class SignalScore:
    """单只股票在某日的综合信号评分"""

    ts_code: str
    name: str
    date: str
    score: float  # 综合评分 0-100
    b1_score: float
    trend_score: float
    volume_score: float
    risk_score: float
    signals: list[str]  # 触发的战法/指标标签
    reasons: list[str]
    warnings: list[str]
    verdict: SignalVerdict = SignalVerdict.NO_SIGNAL


@dataclass
class Position:
    """持仓头寸"""

    ts_code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    risk_amount: float  # 单笔承担风险金额
    partial_exited: bool = False


@dataclass
class TradeRecord:
    """模拟成交记录"""

    ts_code: str
    name: str
    action: str  # BUY / SELL / PARTIAL_SELL
    date: str
    price: float
    shares: int
    pnl: float = 0  # 仅 SELL 时有效，金额盈亏
    pnl_pct: float = 0  # 仅 SELL 时有效，百分比盈亏
    reason: str = ""  # 成交原因
    fee: float = 0


@dataclass
class SimulationConfig:
    """模拟器配置"""

    initial_capital: float = 1_000_000.0
    start_date: str = ""  # 空表示从数据最早日期
    end_date: str = ""  # 空表示到数据最晚日期
    max_positions: int = 5  # 最大同时持仓
    risk_per_trade: float = 0.02  # 单笔风险占净值比例
    risk_per_trade_min: float = 0.01
    commission_rate: float = 0.0003  # 手续费（双向）
    slippage: float = 0.001  # 滑点（买入 +0.1%，卖出 -0.1%）
    position_score_threshold: float = 70.0  # 入选信号最低综合评分
    signal_min_count: int = 2  # 至少需要 N 个共振标签
    partial_take_profit_rr: float = 2.0  # 卤煮：达到 2R 减半
    trailing_ma_days: int = 20  # 移动止盈参考 MA
    allow_short: bool = False  # v0.1 仅做多
    market_neutral_max_positions: int = 2  # 弱势环境下最大持仓


@dataclass
class SimulationResult:
    """模拟回测结果"""

    config: SimulationConfig
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)  # 最终未平仓
    initial_capital: float = 0
    final_value: float = 0
    total_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    win_rate: float = 0
    profit_factor: float = 0
    total_trades: int = 0
    avg_holding_days: float = 0


__all__ = [
    "MarketRegime",
    "SignalVerdict",
    "MarketContext",
    "SignalScore",
    "Position",
    "TradeRecord",
    "SimulationConfig",
    "SimulationResult",
]
