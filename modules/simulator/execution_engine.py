#!/usr/bin/env python3
"""
成交模拟模块。

- 买入：下一交易日开盘价 + 滑点
- 卖出：下一交易日收盘价 - 滑点
- 手续费：按配置比例双向收取
"""

from __future__ import annotations

from ..indicators import DailyData
from . import Position, SimulationConfig, TradeRecord


def _apply_slippage_buy(price: float, slippage: float) -> float:
    """买入滑点：提高成交价"""
    return price * (1 + slippage)


def _apply_slippage_sell(price: float, slippage: float) -> float:
    """卖出滑点：降低成交价"""
    return price * (1 - slippage)


def _fee(amount: float, rate: float) -> float:
    return max(amount * rate, 0.01)


def execute_buy(
    position: Position,
    kline: DailyData,
    config: SimulationConfig,
) -> TradeRecord:
    """
    模拟买入成交。

    Args:
        position: 待买入头寸
        kline: 买入日 K 线
        config: 配置

    Returns:
        TradeRecord
    """
    fill_price = _apply_slippage_buy(kline.open, config.slippage)
    amount = fill_price * position.shares
    fee = _fee(amount, config.commission_rate)

    return TradeRecord(
        ts_code=position.ts_code,
        name=position.name,
        action="BUY",
        date=kline.trade_date,
        price=round(fill_price, 3),
        shares=position.shares,
        reason=f"B1信号入场，止损{position.stop_loss:.2f}",
        fee=fee,
    )


def execute_sell(
    position: Position,
    kline: DailyData,
    config: SimulationConfig,
    reason: str,
) -> TradeRecord:
    """
    模拟卖出成交。

    Args:
        position: 持仓
        kline: 卖出日 K 线
        config: 配置
        reason: 卖出原因

    Returns:
        TradeRecord
    """
    fill_price = _apply_slippage_sell(kline.close, config.slippage)
    amount = fill_price * position.shares
    fee = _fee(amount, config.commission_rate)

    cost = position.entry_price * position.shares
    pnl = amount - cost - fee - position.entry_price * position.shares * config.commission_rate
    pnl_pct = (
        (fill_price - position.entry_price) / position.entry_price - 2 * config.slippage - 2 * config.commission_rate
    )

    return TradeRecord(
        ts_code=position.ts_code,
        name=position.name,
        action="SELL",
        date=kline.trade_date,
        price=round(fill_price, 3),
        shares=position.shares,
        pnl=round(pnl, 2),
        pnl_pct=round(pnl_pct, 4),
        reason=reason,
        fee=fee,
    )


def execute_partial_sell(
    position: Position,
    kline: DailyData,
    config: SimulationConfig,
    sell_shares: int,
    reason: str,
) -> TradeRecord:
    """
    模拟部分卖出（卤煮减半）。

    Args:
        position: 持仓
        kline: 卖出日 K 线
        config: 配置
        sell_shares: 卖出股数
        reason: 卖出原因

    Returns:
        TradeRecord
    """
    fill_price = _apply_slippage_sell(kline.close, config.slippage)
    amount = fill_price * sell_shares
    fee = _fee(amount, config.commission_rate)

    cost_basis = position.entry_price * sell_shares
    pnl = amount - cost_basis - fee
    pnl_pct = (fill_price - position.entry_price) / position.entry_price

    return TradeRecord(
        ts_code=position.ts_code,
        name=position.name,
        action="PARTIAL_SELL",
        date=kline.trade_date,
        price=round(fill_price, 3),
        shares=sell_shares,
        pnl=round(pnl, 2),
        pnl_pct=round(pnl_pct, 4),
        reason=reason,
        fee=fee,
    )
