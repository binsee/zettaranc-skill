#!/usr/bin/env python3
"""
Walk-Forward 验证脚本 v2 — 基于交易日期分割

使用方法:
  python scripts/walk_forward_validation_v2.py --stocks 50 --days 500
  python scripts/walk_forward_validation_v2.py --quick
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from modules.indicators.core import DailyData
from modules.loop_engine import LoopConfig
from modules.market_regime import MarketRegimeClassifier
from modules.position_manager import PositionManager
from modules.industry_filter import IndustryFilter
from modules.backtest_six_step import backtest_shaofu_portfolio_integrated
from optimization_multifactor import load_klines_batch


def run_walk_forward_v2(
    all_klines: dict[str, list[DailyData]],
    train_days: int = 250,
    test_days: int = 50,
    step_days: int = 50,
    params: dict | None = None,
    verbose: bool = True,
) -> dict:
    """
    Walk-Forward 验证 v2 — 基于交易日期分割

    策略：
    1. 运行一次完整回测（使用所有数据）
    2. 收集所有交易及其日期
    3. 按窗口分割交易到 IS 和 OOS
    4. 计算各窗口的指标

    Args:
        all_klines: 所有股票的 K 线数据
        train_days: 训练窗口天数
        test_days: 测试窗口天数
        step_days: 滚动步长
        params: 优化后的参数
        verbose: 是否打印详细信息

    Returns:
        Walk-Forward 结果字典
    """
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

    if verbose:
        print(f"总数据: {len(all_dates)} 天 ({all_dates[0]} ~ {all_dates[-1]})")

    # 运行完整回测
    if verbose:
        print("\n运行完整回测...")

    ts_codes = list(all_klines.keys())
    base_config = LoopConfig(
        j_threshold=params.get("j_threshold", 10),
        stop_loss_pct=params.get("stop_loss_pct", -0.03),
        vol_shrink_threshold=params.get("vol_shrink", 0.6),
    )

    classifier = MarketRegimeClassifier()
    regime_multipliers = params.get("regime_multipliers", {"BULL": 1.0, "SIDEWAYS": 0.8, "BEAR": 0.5})
    pm = PositionManager(
        initial_capital=1_000_000,
        risk_per_trade=params.get("risk_per_trade", 0.01),
        max_positions=params.get("max_positions", 3),
        regime_multipliers=regime_multipliers,
    )
    industry_filter = IndustryFilter(
        max_per_industry=params.get("max_per_industry", 1),
        max_industry_pct=params.get("max_industry_pct", 0.2),
    )

    result = backtest_shaofu_portfolio_integrated(
        ts_codes=ts_codes,
        days=len(all_dates),
        base_config=base_config,
        regime_classifier=classifier,
        position_manager=pm,
        industry_filter=industry_filter,
    )

    # 提取交易信息
    trades = result.get("trade_details", [])
    if verbose:
        print(f"总交易数: {len(trades)}")

    if not trades:
        return {"error": "没有交易"}

    # 按日期分割交易
    windows = []
    for oos_end_idx in range(train_days + test_days, len(all_dates) + 1, step_days):
        oos_start_idx = oos_end_idx - test_days
        is_start_idx = oos_start_idx - train_days

        if is_start_idx < 0:
            break

        is_dates = set(all_dates[is_start_idx:oos_start_idx])
        oos_dates = set(all_dates[oos_start_idx:oos_end_idx])

        # 分割交易
        is_trades = [t for t in trades if t.get("entry_date") in is_dates]
        oos_trades = [t for t in trades if t.get("entry_date") in oos_dates]

        # 计算指标
        def calc_metrics(trade_list):
            if not trade_list:
                return {"win_rate": 0, "total_return": 0, "sharpe": 0, "trades": 0}

            wins = sum(1 for t in trade_list if t.get("pnl_pct", 0) > 0)
            win_rate = wins / len(trade_list)
            total_return = sum(t.get("pnl_pct", 0) for t in trade_list)
            avg_return = total_return / len(trade_list)

            # 简化的夏普计算
            if len(trade_list) > 1:
                returns = [t.get("pnl_pct", 0) for t in trade_list]
                mean_ret = sum(returns) / len(returns)
                var_ret = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
                std_ret = var_ret ** 0.5
                sharpe = (mean_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0
            else:
                sharpe = 0

            return {
                "win_rate": win_rate,
                "total_return": total_return,
                "sharpe": sharpe,
                "trades": len(trade_list),
            }

        is_metrics = calc_metrics(is_trades)
        oos_metrics = calc_metrics(oos_trades)

        windows.append({
            "window_idx": len(windows),
            "is_start": all_dates[is_start_idx],
            "is_end": all_dates[oos_start_idx - 1],
            "oos_start": all_dates[oos_start_idx],
            "oos_end": all_dates[oos_end_idx - 1],
            "is_metrics": is_metrics,
            "oos_metrics": oos_metrics,
        })

        if verbose:
            print(f"\n窗口 {len(windows)}/{(len(all_dates) - train_days) // step_days}:")
            print(f"  IS: {all_dates[is_start_idx]} ~ {all_dates[oos_start_idx - 1]}")
            print(f"    交易: {is_metrics['trades']}, 胜率: {is_metrics['win_rate']:.1%}, "
                  f"收益: {is_metrics['total_return']:+.2f}%, 夏普: {is_metrics['sharpe']:.2f}")
            print(f"  OOS: {all_dates[oos_start_idx]} ~ {all_dates[oos_end_idx - 1]}")
            print(f"    交易: {oos_metrics['trades']}, 胜率: {oos_metrics['win_rate']:.1%}, "
                  f"收益: {oos_metrics['total_return']:+.2f}%, 夏普: {oos_metrics['sharpe']:.2f}")

    # 计算总体指标
    if not windows:
        return {"error": "没有有效窗口"}

    avg_is_wr = sum(w['is_metrics']['win_rate'] for w in windows) / len(windows)
    avg_oos_wr = sum(w['oos_metrics']['win_rate'] for w in windows) / len(windows)
    avg_is_ret = sum(w['is_metrics']['total_return'] for w in windows) / len(windows)
    avg_oos_ret = sum(w['oos_metrics']['total_return'] for w in windows) / len(windows)
    avg_is_sharpe = sum(w['is_metrics']['sharpe'] for w in windows) / len(windows)
    avg_oos_sharpe = sum(w['oos_metrics']['sharpe'] for w in windows) / len(windows)
    total_is_trades = sum(w['is_metrics']['trades'] for w in windows)
    total_oos_trades = sum(w['oos_metrics']['trades'] for w in windows)

    # 过拟合比率
    overfit_ratio = avg_is_ret / avg_oos_ret if avg_oos_ret > 0 else float('inf') if avg_is_ret > 0 else 1.0

    return {
        "windows": windows,
        "avg_is_win_rate": avg_is_wr,
        "avg_oos_win_rate": avg_oos_wr,
        "avg_is_return": avg_is_ret,
        "avg_oos_return": avg_oos_ret,
        "avg_is_sharpe": avg_is_sharpe,
        "avg_oos_sharpe": avg_oos_sharpe,
        "total_is_trades": total_is_trades,
        "total_oos_trades": total_oos_trades,
        "overfit_ratio": overfit_ratio,
        "params": params,
    }


def main():
    parser = argparse.ArgumentParser(description="Walk-Forward 验证 v2")
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
    print("Walk-Forward 验证 v2 — 基于交易日期分割")
    print("=" * 70)
    print(f"  股票数: {args.stocks}")
    print(f"  回测天数: {args.days}")
    print(f"  训练窗口: {args.train} 天")
    print(f"  测试窗口: {args.test} 天")
    print(f"  滚动步长: {args.step} 天")

    # 加载数据
    print("\n加载 K 线数据...")
    import sqlite3
    db_path = Path("data/stock_data.db")
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

    all_klines = load_klines_batch(ts_codes, args.days)
    print(f"成功加载 {len(all_klines)} 只股票")

    # 运行 Walk-Forward
    print("\n开始 Walk-Forward 验证...")
    result = run_walk_forward_v2(
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
    print(f"IS 总交易数: {result['total_is_trades']}")
    print(f"OOS 总交易数: {result['total_oos_trades']}")

    print("\n样本内（训练）平均表现:")
    print(f"  胜率: {result['avg_is_win_rate']:.1%}")
    print(f"  收益: {result['avg_is_return']:+.2f}%")
    print(f"  夏普: {result['avg_is_sharpe']:.2f}")

    print("\n样本外（测试）平均表现:")
    print(f"  胜率: {result['avg_oos_win_rate']:.1%}")
    print(f"  收益: {result['avg_oos_return']:+.2f}%")
    print(f"  夏普: {result['avg_oos_sharpe']:.2f}")

    print(f"\n过拟合比率: {result['overfit_ratio']:.2f}")
    if result['overfit_ratio'] < 1.5:
        print("  ✅ 过拟合风险低（< 1.5）")
    elif result['overfit_ratio'] < 2.0:
        print("  ⚠️ 过拟合风险中等（1.5 ~ 2.0）")
    else:
        print("  ❌ 过拟合风险高（> 2.0）")

    # 保存结果
    output_path = Path("reports/walk_forward_v2_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n结果保存: {output_path}")


if __name__ == "__main__":
    main()
