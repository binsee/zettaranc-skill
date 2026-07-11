"""v1.0 验收适配的达尔文可调评分器

封装 verify_v10_pipeline 作为 fitness，方便 V2 hill-climb 寻优。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class V10ScoreResult:
    """单次评分的结果"""
    passed_count: int = 0
    total_count: int = 5
    sharpe: float = 0.0
    fit: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class V10VerifyScorer:
    """达尔文友好的 v1.0 验收适配器

    接口形态与 modules.self_optimizer.BacktestScorer 对齐：
      - 构造时接收 stock_pool / days / wf 等配置
      - score(params) 返回 V10ScoreResult（fit 为爬山适应度）
    """

    def __init__(
        self,
        stock_pool: list[str],
        days: int = 250,
        walk_forward: bool = True,
        wf_train_days: int = 120,
        wf_test_days: int = 60,
    ):
        self.stock_pool = stock_pool
        self.days = days
        self.walk_forward = walk_forward
        self.wf_train_days = wf_train_days
        self.wf_test_days = wf_test_days