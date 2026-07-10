"""
v1.0 验收统一管线

调用现有 backtest_shaofu_portfolio / metrics / param_registry，
不修改任何现有模块的内部逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StockResult:
    """单股回测结果"""
    ts_code: str
    name: str
    trades: int
    win_rate: float
    return_pct: float
    sharpe: float
    max_drawdown: float
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class AggregateMetrics:
    """组合级聚合指标"""
    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class GateResult:
    """单项硬指标判定结果"""
    name: str
    value: float
    threshold: float
    passed: bool
    message: str = ""


@dataclass
class VerifyResult:
    """v1.0 验收聚合结果"""
    per_stock: list[StockResult] = field(default_factory=list)
    aggregate: AggregateMetrics = field(default_factory=AggregateMetrics)
    gates: dict[str, GateResult] = field(default_factory=dict)
    config_used: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: object | None = None,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """v1.0 验收流水线骨架（Task 2-4 补完内部逻辑）"""
    logger.info(
        "verify_v10_pipeline 启动: stocks=%d, days=%d, wf=%s",
        len(ts_codes),
        days,
        walk_forward,
    )
    if not ts_codes:
        return VerifyResult(meta={"empty_input": True})
    # TODO Task 2-4: 实现数据加载 + 回测 + 指标计算 + gates 判定
    return VerifyResult(meta={"stub": True})
