"""
run_merged_experiments.py — 整合 run_15、run_10、run_5 三個實驗為一個大實驗，並剔除跨腳本重複。

設計：
  - 合併 run_15_experiments (32 點)、run_10_supplemental (10 點)、run_5_aggressive_freq (5 點)
  - 僅做「跨腳本」去重：run_15 全部保留，run_10/run_5 中 params 已存在於 run_15 者跳過
  - 預期：run_10 的 10 個與 run_15 Group G 重疊 → 0 新增；run_5 的 200 MHz 重疊 → 4 新增
  - 總計：32 + 0 + 4 = 36 個實驗

Usage (from workspace/ directory):
  python3 run_merged_experiments.py                           # Path 1 only
  python3 run_merged_experiments.py --path2                   # Path 1 + Path 2
  python3 run_merged_experiments.py --path2 --path3           # Path 1 + Path 2 + Path 3

Output: dse_merged_p1.json / dse_merged_p1p2.json / dse_merged_p1p2p3.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# Bootstrap paths
_WORKSPACE = os.path.dirname(os.path.abspath(__file__))
_HDNN_ROOT = os.path.join(_WORKSPACE, "HDnn-PIM-Opt")
for _p in [_WORKSPACE, _HDNN_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_merged_experiments")

for _name in ("ax", "ax.service", "ax.core", "sim"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# Import experiment lists and run logic from run_15
from run_15_experiments import (
    EXPERIMENTS as RUN15_EXPERIMENTS,
    _merge_params,
    run_experiments,
)
from run_10_supplemental import SUPPLEMENTAL_EXPERIMENTS
from run_5_aggressive_freq import AGGRESSIVE_FREQ_EXPERIMENTS


def _params_signature(exp: Dict[str, Any], synth_mode: str = "fast", top_module: str = "hd_top") -> Tuple[Tuple[Any, ...], ...]:
    """產生 params 簽名，用於跨腳本去重。排除 group、hd_model。"""
    merged = _merge_params(exp, synth_mode, top_module)
    keys = sorted(k for k in merged.keys() if k not in ("group", "hd_model"))
    return tuple((k, merged[k]) for k in keys)


def get_merged_experiments(
    synth_mode: str = "fast",
    top_module: str = "hd_top",
) -> List[Dict[str, Any]]:
    """
    合併三個實驗來源，僅做「跨腳本」去重：
    - run_15 的 32 個全部保留（不更動內部結構）
    - run_10 的 10 個：若 params 已存在於 run_15 則跳過
    - run_5 的 5 個：若 params 已存在於 run_15+run_10 則跳過

    預期：run_10 全部與 run_15 Group G 重疊 → 0 個新增
          run_5 的 200 MHz 與 run_15 重疊 → 4 個新增（225/250/275/300 MHz）
    總計：32 + 0 + 4 = 36
    """
    result: List[Dict[str, Any]] = list(RUN15_EXPERIMENTS)
    seen_sigs: set = {_params_signature(e, synth_mode, top_module) for e in result}

    r10_added = 0
    for exp in SUPPLEMENTAL_EXPERIMENTS:
        sig = _params_signature(exp, synth_mode, top_module)
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            result.append(exp)
            r10_added += 1

    r5_added = 0
    for exp in AGGRESSIVE_FREQ_EXPERIMENTS:
        sig = _params_signature(exp, synth_mode, top_module)
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            result.append(exp)
            r5_added += 1

    dropped = (len(SUPPLEMENTAL_EXPERIMENTS) - r10_added) + (len(AGGRESSIVE_FREQ_EXPERIMENTS) - r5_added)
    if dropped > 0:
        logger.info(
            "Cross-script dedup: %d duplicate(s) removed (run_10: %d, run_5: %d), %d experiments total",
            dropped, len(SUPPLEMENTAL_EXPERIMENTS) - r10_added, len(AGGRESSIVE_FREQ_EXPERIMENTS) - r5_added, len(result),
        )

    # 重新設計 grouping（依探索主軸）
    result = _reassign_groups(result)
    return result


# ── Grouping 設計（論文用，依 controlled variable 與實驗目的）────────────────
#
# | Group    | 數量 | 說明（論文用） |
# |----------|------|----------------|
# | EDA      | 5    | EDA 策略對 PPA 的影響（固定 base arch） |
# | ARCH     | 5    | 架構規模梯度（hd_dim, reram, oc1, oc2） |
# | INNER    | 13   | inner_dim 梯度與擴展（1024 / 2048 / 4096） |
# | FREQ     | 4    | 頻率掃描（225–300 MHz） |
# | ARCH_EXT | 9    | 架構擴展：緊湊（oc=4/8）+ 大架構壓力測試（250–300 MHz） |


def _reassign_groups(experiments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    依 DP 順序重新指派 group，便於論文撰寫。
    """
    result = []
    for i, exp in enumerate(experiments):
        dp = i + 1
        if 1 <= dp <= 5:
            new_group = "EDA"
        elif 6 <= dp <= 10:
            new_group = "ARCH"
        elif 11 <= dp <= 13 or 23 <= dp <= 32:
            new_group = "INNER"     # inner_dim 梯度與擴展（合併）
        elif 14 <= dp <= 16 or 21 <= dp <= 22 or 17 <= dp <= 20:
            new_group = "ARCH_EXT"  # 緊湊架構 + 大架構壓力測試（合併）
        elif 33 <= dp <= 36:
            new_group = "FREQ"
        else:
            new_group = exp.get("group", "?")
        out = dict(exp)
        out["group"] = new_group
        result.append(out)
    return result


def _default_output_path(use_path2: bool, use_path3: bool) -> str:
    if use_path3:
        return "dse_merged_p1p2p3.json"
    if use_path2:
        return "dse_merged_p1p2.json"
    return "dse_merged_p1.json"


def main():
    parser = argparse.ArgumentParser(
        description="整合 run_15 + run_10 + run_5 為一個大實驗，剔除重複 case",
    )
    parser.add_argument("--path2", action="store_true", help="Enable Path 2 (EDA synthesis)")
    parser.add_argument("--path3", action="store_true", help="Enable Path 3 (gate-level sim)")
    parser.add_argument("--eda-host", type=str, default="132.239.17.21", help="EDA Server host")
    parser.add_argument("--eda-port", type=int, default=5000, help="EDA Server port")
    parser.add_argument(
        "--synth-mode",
        type=str,
        default="fast",
        choices=["fast", "slow"],
        help="fast=PatterNet blackbox, slow=full synthesis",
    )
    parser.add_argument(
        "--top-module",
        type=str,
        default="hd_top",
        choices=["core", "hd_top"],
        help="Synthesis/simulation scope",
    )
    parser.add_argument(
        "--accuracy-threshold",
        type=float,
        default=0.5,
        help="Gate 1 minimum accuracy (default 0.5)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: dse_merged_*.json)",
    )
    args = parser.parse_args()

    if args.path3 and not args.path2:
        logger.warning("--path3 requires --path2. Path 3 will not run.")

    output_file = args.output or _default_output_path(args.path2, args.path3 and args.path2)

    experiments = get_merged_experiments(args.synth_mode, args.top_module)
    n_total = len(experiments)

    logger.info("=" * 60)
    logger.info("Merged Experiment (run_15 + run_10 + run_5, deduplicated)")
    logger.info("  Total experiments: %d", n_total)
    from collections import Counter
    grp = Counter(e.get("group", "?") for e in experiments)
    logger.info("  Groups: %s", dict(sorted(grp.items())))
    logger.info("  Path 2: %s", "ENABLED" if args.path2 else "DISABLED")
    logger.info("  Path 3: %s", "ENABLED" if args.path3 and args.path2 else "DISABLED")
    logger.info("  synth_mode=%s, top_module=%s", args.synth_mode, args.top_module)
    logger.info("  output: %s", output_file)
    if args.path2:
        logger.info("  EDA Server: %s:%s", args.eda_host, args.eda_port)
    logger.info("=" * 60)

    run_start = datetime.now(timezone.utc).isoformat()
    t_start = time.monotonic()

    results = run_experiments(
        use_path2=args.path2,
        use_path3=args.path3 and args.path2,
        eda_host=args.eda_host,
        eda_port=args.eda_port,
        synth_mode=args.synth_mode,
        top_module=args.top_module,
        accuracy_threshold=args.accuracy_threshold,
        experiments=experiments,
    )

    wall_clock_s = round(time.monotonic() - t_start, 2)
    run_end = datetime.now(timezone.utc).isoformat()

    if len(results) != n_total:
        logger.error(
            "INCOMPLETE: expected %d results, got %d. Script may have been interrupted.",
            n_total,
            len(results),
        )
        sys.exit(1)

    status_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    logger.info("=" * 60)
    logger.info("Summary: %d/%d experiments completed", len(results), n_total)
    for status, count in sorted(status_counts.items()):
        logger.info("  %s: %d", status, count)
    logger.info("  Wall clock: %.1fs", wall_clock_s)
    logger.info("=" * 60)

    out_path = os.path.join(os.getcwd(), output_file)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "path2_enabled": args.path2,
                    "path3_enabled": args.path3 and args.path2,
                    "synth_mode": args.synth_mode,
                    "top_module": args.top_module,
                    "total_data_points": n_total,
                    "run_type": "merged_run15_run10_run5_deduplicated",
                    "run_start_iso": run_start,
                    "run_end_iso": run_end,
                    "wall_clock_seconds": wall_clock_s,
                },
                "results": results,
            },
            f,
            indent=2,
        )
    logger.info("Results saved to: %s", out_path)


if __name__ == "__main__":
    main()
