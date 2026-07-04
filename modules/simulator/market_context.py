#!/usr/bin/env python3
"""
市场环境判断模块。

基于大盘指数（sh000001 / sz399006）和全市场涨跌家数比，
把每个交易日归类为 STRONG / NEUTRAL / WEAK，用于控制仓位上限。
"""

from __future__ import annotations

from ..datasource import DataSource, get_datasource
from ..indicators import DailyData, calculate_zg_white, calculate_dg_yellow, calculate_ma
from . import MarketContext, MarketRegime


_DEFAULT_INDEX_CODE = "000001.SH"


def _trend_score(klines: list[DailyData]) -> float:
    """基于白线/黄线位置与斜率给出大盘趋势得分 0-100。"""
    if len(klines) < 60:
        return 50.0

    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    prev_white = calculate_zg_white(klines[:-1])
    prev_yellow = calculate_dg_yellow(klines[:-1])

    score = 50.0
    if white > yellow:
        score += 20
    else:
        score -= 20

    if white > prev_white:
        score += 10
    if yellow > prev_yellow:
        score += 10

    # 价格在黄线上方加分
    if klines[-1].close > yellow:
        score += 10

    return max(0.0, min(100.0, score))


def _breadth_approx(klines: list[DailyData]) -> float:
    """用指数涨跌幅度近似市场广度，-1 ~ 1。"""
    if len(klines) < 20:
        return 0.0

    up_days = sum(1 for k in klines[-20:] if k.close > k.open)
    down_days = 20 - up_days
    return (up_days - down_days) / 20.0


def _moneyflow_score(klines: list[DailyData]) -> float:
    """基于量价关系给出资金得分 0-100。"""
    if len(klines) < 20:
        return 50.0

    recent = klines[-20:]
    volume_trend = recent[-1].vol / (sum(k.vol for k in recent[:-1]) / max(1, len(recent) - 1))
    price_trend = recent[-1].close / recent[0].close - 1.0

    score = 50.0 + price_trend * 200  # 涨幅 5% → +10 分
    if volume_trend > 1.2:
        score += 10
    elif volume_trend < 0.8:
        score -= 10

    return max(0.0, min(100.0, score))


def get_market_context(
    trade_date: str,
    index_code: str = _DEFAULT_INDEX_CODE,
    datasource: DataSource | None = None,
) -> MarketContext:
    """
    获取指定交易日之前的市场环境上下文。

    Args:
        trade_date: 当前日期（YYYYMMDD 或 YYYY-MM-DD）
        index_code: 大盘指数代码
        datasource: 数据源，默认 Composite

    Returns:
        MarketContext
    """
    ds = datasource or get_datasource()
    raw_klines = ds.get_kline_dicts(index_code, days=120, end_date=trade_date.replace("-", ""))

    if not raw_klines:
        return MarketContext(
            date=trade_date,
            regime=MarketRegime.NEUTRAL,
            index_trend=50.0,
            breadth=0.0,
            moneyflow_score=50.0,
            notes=["无指数数据，默认震荡"],
        )

    klines: list[DailyData] = [DailyData(**k) for k in raw_klines]

    trend = _trend_score(klines)
    breadth = _breadth_approx(klines)
    mf = _moneyflow_score(klines)

    # 环境判定
    if trend >= 65 and breadth > 0.1 and mf >= 55:
        regime = MarketRegime.STRONG
    elif trend <= 40 or breadth < -0.15 or mf <= 40:
        regime = MarketRegime.WEAK
    else:
        regime = MarketRegime.NEUTRAL

    notes = [f"大盘趋势得分 {trend:.0f}", f"涨跌广度 {breadth:+.2f}", f"资金得分 {mf:.0f}"]

    return MarketContext(
        date=trade_date,
        regime=regime,
        index_trend=trend,
        breadth=breadth,
        moneyflow_score=mf,
        notes=notes,
    )


def max_positions_allowed(context: MarketContext, config_max: int, weak_max: int) -> int:
    """根据市场环境返回当日最大持仓数。"""
    if context.regime == MarketRegime.STRONG:
        return config_max
    if context.regime == MarketRegime.WEAK:
        return weak_max
    return max(config_max - 1, weak_max)
