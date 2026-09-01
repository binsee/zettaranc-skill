"""CLI screen 子命令实现。"""

from __future__ import annotations

from ._helpers import json_output
from .strategy_alias import STRATEGY_ALIAS


def cmd_screen(args) -> None:
    """筛选股票（调 screener.screen_stocks）

    Rust 路径：screen_stocks 暂未封装为 PyO3 binding（v4.0.1），所以 Rust 优先
    计算的单项评分函数（`compute_atr_py` 等）暂未在 CLI 暴露；当 `screen_stocks_py`
    PyO3 binding 落地后（v4.1+），这里可直接 bridge。
    当前行为：保持 Python `screen_stocks` 路径不动（无需回退检查）。
    """
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(args.strategy, args.strategy)

    # 预留 Rust hook：未来 v4.1+ 可在此处
    # `from modules.backtest._rust_bridge import compute_func`
    # `rust_screen = compute_func("screen_stocks_py")`
    # 若 rust_screen 不为 None 即可走 Rust。

    results = screen_stocks(
        criteria=criteria,
        max_stocks=args.limit if args.limit > 0 else 0,
        use_parallel=not args.no_parallel,
    )

    # 输出前 limit 只（limit=0 时输出全部 500 上限内的命中）
    output_limit = args.limit if args.limit > 0 else len(results)

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "criteria": criteria,
            "count": len(results[:output_limit]),
            "stocks": [
                {
                    "ts_code": r.ts_code,
                    "name": r.name,
                    "score": r.score,
                    "rating": r.rating,
                    "reasons": getattr(r, "reasons", []) or [],
                    "warnings": getattr(r, "warnings", []) or [],
                }
                for r in results[:output_limit]
            ],
        }
        json_output(json_result)
        return

    # ── 人类可读输出（保持原样） ──
    print(f"\n{'=' * 60}")
    print(f"股票筛选 (criteria={criteria}, 上限={args.limit or '全市场'})")
    print(f"{'=' * 60}")
    print(f"\n扫描完成，命中: {len(results)} 只\n")

    for r in results[:output_limit]:
        print(f"  {r.ts_code:<12} {r.name:<8} score={r.score:.1f}  {r.rating}")
        reasons = getattr(r, "reasons", []) or []
        warnings = getattr(r, "warnings", []) or []
        if reasons:
            print(f"    reasons: {','.join(reasons[:3])}")
        if warnings:
            print(f"    warnings: {','.join(warnings[:3])}")
