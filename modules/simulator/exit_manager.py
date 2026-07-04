#!/usr/bin/env python3
"""
退出管理模块。

负责每日检查持仓是否需要退出：
- 止损：收盘价跌破入场日最低价（或 N 型结构前低）
- 止盈（卤煮）：达到固定 R/R 后减半
- 移动止盈：收盘价跌破 20MA 或白线死叉黄线
"""

from __future__ import annotations

from ..indicators import DailyData, calculate_zg_white, calculate_dg_yellow, calculate_ma
from . import Position, SimulationConfig


def _stop_loss_hit(position: Position, kline: DailyData) -> bool:
    """收盘价跌破止损位"""
    return kline.close < position.stop_loss


def _take_profit_hit(position: Position, kline: DailyData, rr: float) -> bool:
    """达到固定盈亏比（如 2R）"""
    risk = position.entry_price - position.stop_loss
    if risk <= 0:
        return False
    target = position.entry_price + risk * rr
    return kline.close >= target


def _trailing_stop_hit(klines: list[DailyData], position: Position, ma_days: int = 20) -> bool:
    """收盘价跌破 20MA 或白线死叉黄线"""
    if len(klines) < ma_days + 5:
        return False

    ma_value = calculate_ma([k.close for k in klines], ma_days)
    if klines[-1].close < ma_value:
        return True

    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    prev_white = calculate_zg_white(klines[:-1])
    prev_yellow = calculate_dg_yellow(klines[:-1])

    # 白线在黄线之上 → 死叉
    if prev_white >= prev_yellow and white < yellow:
        return True

    return False


def check_exit(
    position: Position,
    klines: list[DailyData],
    config: SimulationConfig,
) -> tuple[str, int]:
    """
    检查持仓当日退出状态。

    Args:
        position: 持仓
        klines: 截至当前日期的 K 线（含当前日）
        config: 配置

    Returns:
        (action, shares_to_sell)
        action: "HOLD" / "STOP_LOSS" / "TAKE_PROFIT_PARTIAL" / "TRAILING_EXIT"
        shares_to_sell: 卖出股数（HOLD 时为 0，部分卖出时为半数）
    """
    if not klines:
        return "HOLD", 0

    current = klines[-1]

    # 1. 止损最高优先级
    if _stop_loss_hit(position, current):
        return "STOP_LOSS", position.shares

    # 2. 卤煮：达到固定 R/R 且尚未减半
    if not position.partial_exited and _take_profit_hit(position, current, config.partial_take_profit_rr):
        half = (position.shares // 2 // 100) * 100
        if half < 100:
            half = position.shares
        return "TAKE_PROFIT_PARTIAL", half

    # 3. 移动止盈：跌破 20MA 或白线死叉
    if _trailing_stop_hit(klines, position, config.trailing_ma_days):
        return "TRAILING_EXIT", position.shares

    return "HOLD", 0
