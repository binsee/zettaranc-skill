#!/usr/bin/env python3
"""
仓位管理模块。

基于单笔风险（risk_per_trade）和止损幅度计算买入股数。
公式：shares = (equity * risk_pct) / (entry_price - stop_loss)
确保不超过可用现金和最大持仓限制。
"""

from __future__ import annotations

import math

from . import Position, SimulationConfig


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss: float,
    cash: float,
    config: SimulationConfig,
) -> tuple[int, float]:
    """
    计算应买入股数与承担的风险金额。

    Args:
        equity: 当前账户净值
        entry_price: 计划买入价
        stop_loss: 止损价
        cash: 可用现金
        config: 模拟配置

    Returns:
        (shares, risk_amount)
    """
    if entry_price <= 0 or stop_loss <= 0 or entry_price <= stop_loss:
        return 0, 0.0

    risk_pct = max(config.risk_per_trade_min, min(config.risk_per_trade, 0.10))
    risk_amount = equity * risk_pct

    risk_per_share = entry_price - stop_loss
    shares = int(math.floor(risk_amount / risk_per_share))

    # A股最小交易单位 100 股
    shares = (shares // 100) * 100
    if shares < 100:
        return 0, 0.0

    # 不超过可用现金（含手续费预留）
    max_cost = cash / (1 + config.commission_rate)
    max_shares = int(math.floor(max_cost / entry_price / 100)) * 100
    shares = min(shares, max_shares)

    if shares < 100:
        return 0, 0.0

    actual_risk = shares * risk_per_share
    return shares, actual_risk


def build_position(
    ts_code: str,
    name: str,
    entry_date: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    cash: float,
    equity: float,
    config: SimulationConfig,
) -> Position | None:
    """
    构建一个持仓头寸。

    Args:
        ...

    Returns:
        Position or None（若资金不足或止损无效）
    """
    shares, risk_amount = calculate_position_size(equity, entry_price, stop_loss, cash, config)
    if shares <= 0:
        return None

    return Position(
        ts_code=ts_code,
        name=name,
        entry_date=entry_date,
        entry_price=entry_price,
        shares=shares,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_amount=risk_amount,
    )
