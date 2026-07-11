#!/usr/bin/env python3
"""少妇战法 v1.0 验收参数寻优（v3.7.1）

用 5 轮 hill-climb 在 100 股 × 240 天 + Walk-forward 上跑
V10VerifyScorer，按 passed_count + 0.1*sharpe 适应度爬山，
最佳参数集写回 param_registry:shaofu_v1。

用法：
  python -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100
  python -m scripts.optimize_for_v10_verify --smoke   # 1 round × 5 stocks
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# 让 `python -m scripts.optimize_for_v10_verify` 能跑（项目根目录加 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.database import get_all_stock_codes  # noqa: E402
from modules.loop_engine import LoopConfig  # noqa: E402
from modules.verify.registry_writer import (  # noqa: E402
    write_optimization_to_registry,
)
from modules.verify.scorer import V10VerifyScorer, V10ScoreResult, LOOP_CONFIG_FIELDS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LoopConfig 字段的 (min, max, step) 元组（用于爬山边界）
PARAM_SPACE = {
    "j_threshold":         (3,    20,   1),
    "stop_loss_pct":      (-0.10, -0.01, 0.01),
    "vol_shrink_threshold": (0.5,  1.0,  0.1),
    "bbi_break_days":      (1,     5,    1),
    "min_holding_days":    (2,     7,    1),
    "lu_half":             (0,     1,    1),   # bool 当 int 用
    "position_pct":        (0.10,  0.50, 0.05),
}


def _clip(name: str, value: float) -> int | float | bool:
    lo, hi, step = PARAM_SPACE[name]
    v = max(lo, min(hi, value))
    v = round((v - lo) / step) * step + lo
    v = max(lo, min(hi, v))
    if name in ("lu_half",):
        return bool(int(v))
    return v


def _mutate(base: dict, rng: random.Random, n_mutations: int = 2) -> dict:
    """随机挑选 n_mutations 个字段微扰"""
    new = dict(base)
    keys = list(PARAM_SPACE.keys())
    picked = rng.sample(keys, k=min(n_mutations, len(keys)))
    for k in picked:
        lo, hi, step = PARAM_SPACE[k]
        delta = rng.choice([-2, -1, 1, 2]) * step
        new[k] = _clip(k, new.get(k, lo) + delta)
    return new


def _load_pool(stocks_arg: int | None) -> list[str]:
    """加载股票池：默认从 stock_basic 取前 N 只"""
    limit = stocks_arg or 100
    return get_all_stock_codes(limit=limit)


def run_hillclimb(
    scorer: V10VerifyScorer,
    initial: dict,
    rounds: int,
    rng: random.Random,
) -> tuple[dict, V10ScoreResult, list[dict]]:
    """返回 (best_params, best_score, history)"""
    current = dict(initial)
    current_result = scorer.score(current)
    history: list[dict] = [{
        "round": 0,
        "kind": "baseline",
        "params": current,
        "fit": current_result.fit,
        "passed_count": current_result.passed_count,
    }]
    logger.info(
        "基线 fit=%.3f passed=%d/%d",
        current_result.fit,
        current_result.passed_count,
        current_result.total_count,
    )

    best = current
    best_result = current_result
    no_improve = 0

    for r in range(1, rounds + 1):
        candidate = _mutate(current, rng)
        candidate_result = scorer.score(candidate)
        history.append({
            "round": r,
            "kind": "candidate",
            "params": candidate,
            "fit": candidate_result.fit,
            "passed_count": candidate_result.passed_count,
            "error": candidate_result.error,
        })

        if candidate_result.fit > current_result.fit:
            current = candidate
            current_result = candidate_result
            no_improve = 0
            status = "keep"
        else:
            no_improve += 1
            status = "revert"

        if candidate_result.fit > best_result.fit:
            best = candidate
            best_result = candidate_result

        logger.info(
            "round %d: %s fit=%.3f passed=%d/%d (best so far fit=%.3f passed=%d/%d)",
            r, status, candidate_result.fit, candidate_result.passed_count,
            candidate_result.total_count, best_result.fit, best_result.passed_count,
            best_result.total_count,
        )

        if no_improve >= 3:
            logger.info("收敛于 round %d", r)
            break

    return best, best_result, history


def main() -> int:
    parser = argparse.ArgumentParser(description="v1.0 验收参数寻优")
    parser.add_argument("--rounds", type=int, default=5, help="爬山轮数（默认 5）")
    parser.add_argument("--stocks", type=int, default=100, help="股票池大小（默认 100）")
    parser.add_argument("--days", type=int, default=240, help="回测天数（默认 240）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--smoke", action="store_true", help="冒烟模式：1 轮 × 5 股")
    parser.add_argument("--extras", type=int, default=0, help="额外补充轮数")
    args = parser.parse_args()

    if args.smoke:
        args.rounds = 1
        args.stocks = 5

    rng = random.Random(args.seed)

    pool = _load_pool(args.stocks)
    if not pool:
        logger.error("无法加载股票池（数据库可能未初始化）")
        return 1
    logger.info("股票池: %d 只", len(pool))

    scorer = V10VerifyScorer(
        stock_pool=pool,
        days=args.days,
        walk_forward=True,
        wf_train_days=120,
        wf_test_days=60,
    )

    baseline_params = {
        f: getattr(LoopConfig(), f)
        for f in LOOP_CONFIG_FIELDS
    }
    baseline_params["lu_half"] = bool(baseline_params["lu_half"])

    total_rounds = args.rounds + args.extras
    t0 = time.time()
    best_params, best_result, history = run_hillclimb(
        scorer=scorer,
        initial=baseline_params,
        rounds=total_rounds,
        rng=rng,
    )
    elapsed = time.time() - t0

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_dir = Path("optimization_drafts")
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"v10_verify_{run_id}.json"
    draft_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "elapsed_sec": elapsed,
                "rounds": total_rounds,
                "stocks": len(pool),
                "baseline_params": baseline_params,
                "best_params": best_params,
                "best_fit": best_result.fit,
                "best_passed_count": best_result.passed_count,
                "best_total_count": best_result.total_count,
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("中间产物：%s (%.1f s)", draft_path, elapsed)

    write_optimization_to_registry(
        optimization_results={"best_params": best_params},
        strategy_name="shaofu_v1",
    )
    logger.info(
        "已写回 param_registry:shaofu_v1 → fit=%.3f passed=%d/%d",
        best_result.fit,
        best_result.passed_count,
        best_result.total_count,
    )

    print(f"PASSED: {best_result.passed_count}/{best_result.total_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
