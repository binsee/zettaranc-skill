#!/usr/bin/env python3
"""
信号过滤模块。

对 screener 评分结果进行二次过滤：
- 综合评分 >= threshold
- 至少触发 N 个共振标签（如 B1 + 沙漏完美 + 量比攻击日 + 牛绳金叉）
- 风险不过高（非冲刺波/派发）
- 输出 SignalScore 列表，按分数降序
"""

from __future__ import annotations

from ..screener import StockScore, analyze_stock, get_all_stocks
from ..datasource import DataSource, get_datasource
from ..indicators import DailyData, calculate_sandglass_score
from ..indicators.volume_patterns import detect_volume_ratio_strategy
from ..indicators.price_patterns import detect_bull_rope
from . import SignalScore, SignalVerdict


_REQUIRED_SIGNALS = ("B1", "沙漏完美", "量比攻击", "牛绳金叉")


def _extract_signals(score: StockScore, klines: list[DailyData]) -> list[str]:
    """从 StockScore 和原始 K 线中提取共振标签。"""
    signals: list[str] = []
    reasons = " ".join(score.reasons)
    warnings = " ".join(score.warnings)

    if score.b1_score >= 60 or "B1" in reasons:
        signals.append("B1")

    # 沙漏完美
    try:
        sg = calculate_sandglass_score(klines)
        if sg.get("is_perfect"):
            signals.append("沙漏完美")
        elif sg.get("score", 0) >= 70:
            signals.append("沙漏良好")
    except Exception:
        pass

    # 量比战法
    try:
        vr = detect_volume_ratio_strategy(klines)
        scene = vr.get("scene", "")
        if scene in ("攻击日", "超级攻击", "单向拉升"):
            signals.append("量比攻击")
        elif scene in ("出货日", "弱势日"):
            signals.append("量比恶劣")
    except Exception:
        pass

    # 牛绳
    try:
        br = detect_bull_rope(klines)
        if br.get("signal") == "牵牛":
            signals.append("牛绳金叉")
        elif br.get("signal") == "牛绳断":
            signals.append("牛绳断")
    except Exception:
        pass

    # 三波 / 麒麟会阶段（从 reason/warning 推断）
    if "建仓波" in reasons:
        signals.append("建仓波")
    if "吸筹" in reasons:
        signals.append("吸筹")
    if "冲刺波" in warnings or "派发" in warnings:
        signals.append("高风险阶段")

    return signals


def evaluate_stock(
    ts_code: str,
    trade_date: str,
    klines: list[DailyData] | None = None,
    datasource: DataSource | None = None,
) -> SignalScore:
    """
    评估单只股票在某交易日的信号质量。

    Args:
        ts_code: 股票代码
        trade_date: 当前日期
        klines: 可选，外部传入 K 线
        datasource: 数据源

    Returns:
        SignalScore
    """
    ds = datasource or get_datasource()
    if klines is None:
        from ..screener.data import get_recent_klines

        klines = get_recent_klines(ts_code, 150, datasource=ds)

    if not klines or len(klines) < 60:
        return SignalScore(
            ts_code=ts_code,
            name=ts_code,
            date=trade_date,
            score=0,
            b1_score=0,
            trend_score=0,
            volume_score=0,
            risk_score=0,
            signals=[],
            reasons=[],
            warnings=["数据不足"],
            verdict=SignalVerdict.NO_SIGNAL,
        )

    score = analyze_stock(ts_code, klines=klines, datasource=ds)
    signals = _extract_signals(score, klines)

    verdict = SignalVerdict.PASS
    if score.score < 60:
        verdict = SignalVerdict.LOW_SCORE
    elif "高风险阶段" in signals:
        verdict = SignalVerdict.HIGH_RISK
    elif "牛绳断" in signals or "量比恶劣" in signals:
        verdict = SignalVerdict.BAD_STAGE
    elif "B1" not in signals:
        verdict = SignalVerdict.NO_SIGNAL

    return SignalScore(
        ts_code=ts_code,
        name=score.name or ts_code,
        date=trade_date,
        score=score.score,
        b1_score=score.b1_score,
        trend_score=score.trend_score,
        volume_score=score.volume_score,
        risk_score=score.risk_score,
        signals=signals,
        reasons=score.reasons,
        warnings=score.warnings,
        verdict=verdict,
    )


def filter_signals(
    scores: list[SignalScore],
    score_threshold: float = 70.0,
    min_signal_count: int = 2,
) -> list[SignalScore]:
    """
    过滤并排序候选信号。

    过滤条件：
    - verdict == PASS
    - score >= score_threshold
    - 有效共振标签数 >= min_signal_count
    """

    def _effective_signals(s: SignalScore) -> int:
        positive = {"B1", "沙漏完美", "沙漏良好", "量比攻击", "牛绳金叉", "建仓波", "吸筹"}
        return len(positive.intersection(s.signals))

    filtered = [
        s
        for s in scores
        if s.verdict == SignalVerdict.PASS and s.score >= score_threshold and _effective_signals(s) >= min_signal_count
    ]
    filtered.sort(key=lambda x: (x.score, _effective_signals(x)), reverse=True)
    return filtered
