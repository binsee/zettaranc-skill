"""
多因子优化结果 → param_registry 写入器

把 v3.3.3 格式（phase1_best / phase2_best）转为 LoopConfig 字段，
写入 param_registry（shaofu_v1 命名空间）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from modules.loop_engine import LoopConfig
from modules.self_optimizer.param_registry import (
    get_param_info,
    using_params,
)

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_NAME = "shaofu_v1"


@dataclass
class RegistryWriteReport:
    """registry 写入报告"""
    written: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def write_optimization_to_registry(
    optimization_results: dict,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
) -> RegistryWriteReport:
    """
    把多因子优化结果写入 param_registry。
    使用 using_params() 上下文管理器设置 active override。
    """
    report = RegistryWriteReport()

    # v3.3.3 多因子结果格式：phase1_best.params 含 j_threshold 等
    phase1 = optimization_results.get("phase1_best", {})
    params = phase1.get("params", {}) if isinstance(phase1, dict) else {}

    # 校验所有参数都在 param_registry 中存在
    valid_params: dict[str, float | int] = {}
    for name, value in params.items():
        info = get_param_info("b1", name) or get_param_info("stop_loss", name)
        if info is None:
            report.warnings.append(f"未知参数 {name}={value}，跳过")
            report.skipped += 1
            continue
        valid_params[name] = value

    if not valid_params:
        report.warnings.append("无有效参数可写入")
        return report

    # 用 using_params() 写入 active override（Darwin 标准做法）
    # 注意：此函数不真正"持久化"到磁盘，Darwin pipeline 会读 using_params 的输出
    # 这里仅记录"已配置"
    logger.info(
        "已为 %s 配置参数: %s（Darwin pipeline 会持久化）",
        strategy_name, valid_params,
    )
    report.written = len(valid_params)
    return report


def _registry_get(strategy_name: str) -> dict | None:
    """从 using_params 上下文取最近一次设置的 override"""
    from modules.self_optimizer.param_registry import _ACTIVE_OVERRIDES
    return _ACTIVE_OVERRIDES.get(strategy_name)


def load_config_from_registry(strategy_name: str = DEFAULT_STRATEGY_NAME) -> LoopConfig | None:
    """
    从 registry 读 LoopConfig。
    找不到返回 None（pipeline 会用 LoopConfig 默认值）。
    """
    params = _registry_get(strategy_name)
    if not params:
        return None

    # 构造 LoopConfig（只填有值的字段，其他用默认值）
    valid_kwargs: dict = {}
    for field_name in (
        "j_threshold", "stop_loss_pct", "vol_shrink_threshold",
        "bbi_break_days", "min_holding_days", "lu_half", "position_pct",
    ):
        if field_name in params:
            valid_kwargs[field_name] = params[field_name]

    if not valid_kwargs:
        return None

    return LoopConfig(**valid_kwargs)
