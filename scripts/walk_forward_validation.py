#!/usr/bin/env python3
"""
Walk-Forward 验证脚本 — 验证多因子优化参数的样本外表现

使用方法:
  python scripts/walk_forward_validation.py --stocks 50 --days 500
  python scripts/walk_forward_validation.py --quick  # 快速模式
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.datasource import DataSource, get_datasource
from modules.indicators.core import DailyData
from modules.loop_engine import LoopConfig
from modules.market_regime import MarketRegimeClassifier
from modules.dynamic_config import DynamicConfigAdapter
from modules.position_manager import PositionManager
from modules.industry_filter import IndustryFilter
from modules.backtest_six_step import backtest_shaofu_portfolio_integrated

# Import from optimization script
sys.path.insert(0, str(Path(__file__).parent))
from optimization_multifactor import load_klines_batch


def run_walk_forward(
    all_klines: dict[str, list[DailyData]],
    train_days: int = 250,
    test_days: int = 50,
    step_days: int = 50,
    params: dict | None = None,
    verbose: bool = True,
) -> dict:
    """
    Walk-Forward 验证

    Args:
        all_klines: 所有股票的 K 线数据 {ts_code: klines}
        train_days: 训练窗口天数
        test_days: 测试窗口天数
        step_days: 滚动步长
        params: 优化后的参数（如果为 None，使用默认参数）
        verbose: 是否打印详细信息

    Returns:
        Walk-Forward 结果字典
    """
    # 默认参数
    if params is None:
        params = {
            "j_threshold": 10,
            "stop_loss_pct": -0.03,
            "vol_shrink": 0.6,
            "risk_per_trade": 0.01,
            "max_positions": 3,
            "regime_multipliers": {"BULL": 1.0, "SIDEWAYS": 0.8, "BEAR": 0.5},
            "max_per_industry": 1,
            "max_industry_pct": 0.2,
        }

    # 获取所有交易日
    all_dates = set()
    for klines in all_klines.values():
        for k in klines:
            all_dates.add(k.trade_date)
    all_dates = sorted(list(all_dates))

    if len(all_dates) < train_days + test_days:
        raise ValueError(f"数据不足: {len(all_dates)} 天 < {train_days + test_days} 天")

    # 切分窗口
    windows = []
    for oos_end_idx in range(train_days + test_days, len(all_dates) + 1, step_days):
        oos_start_idx = oos_end_idx - test_days
        is_start_idx = oos_start_idx - train_days

        if is_start_idx < 0:
            break

        is_dates = all_dates[is_start_idx:oos_start_idx]
        oos_dates = all_dates[oos_start_idx:oos_end_idx]

        windows.append({
            "window_idx": len(windows),
            "is_dates": is_dates,
            "oos_dates": oos_dates,
            "is_start": is_dates[0],
            "is_end": is_dates[-1],
            "oos_start": oos_dates[0],
            "oos_end": oos_dates[-1],
        })

    if verbose:
        print(f"Walk-Forward 窗口数: {len(windows)}")
        print(f"训练窗口: {train_days} 天, 测试窗口: {test_days} 天")

    # 对每个窗口运行回测
    window_results = []
    oos_trades = []

    for w in windows:
        if verbose:
            print(f"\n窗口 {w['window_idx'] + 1}/{len(windows)}:")
            print(f"  训练: {w['is_start']} ~ {w['is_end']} ({len(w['is_dates'])} 天)")
            print(f"  测试: {w['oos_start']} ~ {w['oos_end']} ({len(w['oos_dates'])} 天)")

        # 过滤 K 线数据到训练窗口
        train_klines = {}
        for ts_code, klines in all_klines.items():
            filtered = [k for k in klines if k.trade_date in w['is_dates']]
            if len(filtered) >= 60:  # 至少 60 天数据
                train_klines[ts_code] = filtered

        if len(train_klines) < 5:
            if verbose:
                print(f"  跳过: 只有 {len(train_klines)} 只股票有足够数据")
            continue

        # 训练阶段：在训练窗口上运行回测
        try:
            train_result = _run_backtest(
                train_klines,
                params,
                days=len(w['is_dates']),
            )
        except Exception as e:
            if verbose:
                print(f"  训练失败: {e}")
            continue

        # 测试阶段：在测试窗口上运行回测
        test_klines = {}
        for ts_code, klines in all_klines.items():
            filtered = [k for k in klines if k.trade_date in w['oos_dates']]
            if len(filtered) >= 20:  # 至少 20 天数据
                test_klines[ts_code] = filtered

        if len(test_klines) < 5:
            if verbose:
                print(f"  跳过: 只有 {len(test_klines)} 只股票有足够数据")
            continue

        try:
            test_result = _run_backtest(
                test_klines,
                params,
                days=len(w['oos_dates']),
            )
        except Exception as e:
            if verbose:
                print(f"  测试失败: {e}")
            continue

        # 记录结果
        is_metrics = train_result.get("result")
        oos_metrics = test_result.get("result")

        # ShaofuBacktestResult 对象有属性，不是字典
        def get_metric(obj, name, default=0):
            if obj is None:
                return default
            if hasattr(obj, name):
                return getattr(obj, name)
            if isinstance(obj, dict):
                return obj.get(name, default)
            return default

        window_results.append({
            "window_idx": w['window_idx'],
            "is_start": w['is_start'],
            "is_end": w['is_end'],
            "oos_start": w['oos_start'],
            "oos_end": w['oos_end'],
            "is_win_rate": get_metric(is_metrics, 'win_rate'),
            "is_total_return": get_metric(is_metrics, 'total_return'),
            "is_sharpe": get_metric(is_metrics, 'sharpe_ratio'),
            "is_max_drawdown": get_metric(is_metrics, 'max_drawdown'),
            "is_trades": get_metric(is_metrics, 'trade_count'),
            "oos_win_rate": get_metric(oos_metrics, 'win_rate'),
            "oos_total_return": get_metric(oos_metrics, 'total_return'),
            "oos_sharpe": get_metric(oos_metrics, 'sharpe_ratio'),
            "oos_max_drawdown": get_metric(oos_metrics, 'max_drawdown'),
            "oos_trades": get_metric(oos_metrics, 'trade_count'),
        })

        # 收集 OOS 交易用于整体分析
        trade_details = test_result.get("trade_details", [])
        for td in trade_details:
            oos_trades.append(td)

        if verbose:
            print(f"  训练: 胜率={get_metric(is_metrics, 'win_rate'):.1%}, "
                  f"收益={get_metric(is_metrics, 'total_return'):+.2%}, "
                  f"夏普={get_metric(is_metrics, 'sharpe_ratio'):.2f}")
            print(f"  测试: 胜率={get_metric(oos_metrics, 'win_rate'):.1%}, "
                  f"收益={get_metric(oos_metrics, 'total_return'):+.2%}, "
                  f"夏普={get_metric(oos_metrics, 'sharpe_ratio'):.2f}")

    # 计算总体 OOS 指标
    if window_results:
        avg_is_wr = sum(w['is_win_rate'] for w in window_results) / len(window_results)
        avg_oos_wr = sum(w['oos_win_rate'] for w in window_results) / len(window_results)
        avg_is_ret = sum(w['is_total_return'] for w in window_results) / len(window_results)
        avg_oos_ret = sum(w['oos_total_return'] for w in window_results) / len(window_results)
        avg_is_sharpe = sum(w['is_sharpe'] for w in window_results) / len(window_results)
        avg_oos_sharpe = sum(w['oos_sharpe'] for w in window_results) / len(window_results)

        # 过拟合比率
        overfit_ratio = avg_is_ret / avg_oos_ret if avg_oos_ret > 0 else float('inf')

        return {
            "windows": window_results,
            "avg_is_win_rate": avg_is_wr,
            "avg_oos_win_rate": avg_oos_wr,
            "avg_is_return": avg_is_ret,
            "avg_oos_return": avg_oos_ret,
            "avg_is_sharpe": avg_is_sharpe,
            "avg_oos_sharpe": avg_oos_sharpe,
            "overfit_ratio": overfit_ratio,
            "total_oos_trades": len(oos_trades),
            "params": params,
        }
    else:
        return {
            "windows": [],
            "error": "没有有效的窗口",
        }


def _run_backtest(
    all_klines: dict[str, list[DailyData]],
    params: dict,
    days: int = 250,
) -> dict:
    """运行组合回测"""
    ts_codes = list(all_klines.keys())

    # 构建配置
    base_config = LoopConfig(
        j_threshold=params.get("j_threshold", 10),
        stop_loss_pct=params.get("stop_loss_pct", -0.03),
        vol_shrink_threshold=params.get("vol_shrink", 0.6),
    )

    # 市场状态分类器
    classifier = MarketRegimeClassifier()

    # 仓位管理器
    regime_multipliers = params.get("regime_multipliers", {"BULL": 1.0, "SIDEWAYS": 0.8, "BEAR": 0.5})
    pm = PositionManager(
        initial_capital=1_000_000,
        risk_per_trade=params.get("risk_per_trade", 0.01),
        max_positions=params.get("max_positions", 3),
        regime_multipliers=regime_multipliers,
    )

    # 行业过滤器
    industry_filter = IndustryFilter(
        max_per_industry=params.get("max_per_industry", 1),
        max_industry_pct=params.get("max_industry_pct", 0.2),
    )

    # 运行回测
    result = backtest_shaofu_portfolio_integrated(
        ts_codes=ts_codes,
        days=days,
        base_config=base_config,
        regime_classifier=classifier,
        position_manager=pm,
        industry_filter=industry_filter,
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="Walk-Forward 验证")
    parser.add_argument("--stocks", type=int, default=50, help="股票数量")
    parser.add_argument("--days", type=int, default=500, help="回测天数")
    parser.add_argument("--train", type=int, default=250, help="训练窗口天数")
    parser.add_argument("--test", type=int, default=50, help="测试窗口天数")
    parser.add_argument("--step", type=int, default=50, help="滚动步长")
    parser.add_argument("--quick", action="store_true", help="快速模式")
    args = parser.parse_args()

    if args.quick:
        args.stocks = 20
        args.days = 300
        args.train = 150
        args.test = 30
        args.step = 30

    print("=" * 70)
    print("Walk-Forward 验证")
    print("=" * 70)
    print(f"  股票数: {args.stocks}")
    print(f"  回测天数: {args.days}")
    print(f"  训练窗口: {args.train} 天")
    print(f"  测试窗口: {args.test} 天")
    print(f"  滚动步长: {args.step} 天")

    # 加载数据
    print("\n加载 K 线数据...")

    # 获取股票列表（直接从数据库）
    import sqlite3
    db_path = Path("data/stock_data.db")
    if not db_path.exists():
        print("错误: 数据库不存在")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ts_code, COUNT(*) as cnt
        FROM daily_kline
        GROUP BY ts_code
        ORDER BY cnt DESC
        LIMIT ?
    """, (args.stocks,))
    ts_codes = [row[0] for row in cursor.fetchall()]
    conn.close()

    # 使用优化脚本的批量加载函数
    all_klines = load_klines_batch(ts_codes, args.days)
    print(f"成功加载 {len(all_klines)} 只股票")

    # 运行 Walk-Forward
    print("\n开始 Walk-Forward 验证...")
    result = run_walk_forward(
        all_klines,
        train_days=args.train,
        test_days=args.test,
        step_days=args.step,
    )

    # 输出结果
    print("\n" + "=" * 70)
    print("Walk-Forward 验证结果")
    print("=" * 70)

    if "error" in result:
        print(f"错误: {result['error']}")
        return

    print(f"有效窗口数: {len(result['windows'])}")
    print(f"总 OOS 交易数: {result['total_oos_trades']}")

    print("\n样本内（训练）平均表现:")
    print(f"  胜率: {result['avg_is_win_rate']:.1%}")
    print(f"  收益: {result['avg_is_return']:+.2%}")
    print(f"  夏普: {result['avg_is_sharpe']:.2f}")

    print("\n样本外（测试）平均表现:")
    print(f"  胜率: {result['avg_oos_win_rate']:.1%}")
    print(f"  收益: {result['avg_oos_return']:+.2%}")
    print(f"  夏普: {result['avg_oos_sharpe']:.2f}")

    print(f"\n过拟合比率: {result['overfit_ratio']:.2f}")
    if result['overfit_ratio'] < 1.5:
        print("  ✅ 过拟合风险低（< 1.5）")
    elif result['overfit_ratio'] < 2.0:
        print("  ⚠️ 过拟合风险中等（1.5 ~ 2.0）")
    else:
        print("  ❌ 过拟合风险高（> 2.0）")

    # 保存结果
    output_path = Path("reports/walk_forward_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n结果保存: {output_path}")


if __name__ == "__main__":
    main()
