"""
run_10_supplemental.py — 獨立執行 10 個補充實驗（Group G），不影響主實驗輸出。

設計：僅執行 DP 23–32（Group G）的 10 個實驗，包含 DP 12 重試與 frequency 掃描。
輸出至 dse_10_supplemental_*.json，與主實驗 dse_22_* / dse_32_* 完全分離。

Usage (from workspace/ directory):
  python3 run_10_supplemental.py                           # Path 1 only
  python3 run_10_supplemental.py --path2                   # Path 1 + Path 2
  python3 run_10_supplemental.py --path2 --path3           # Path 1 + Path 2 + Path 3
  python3 run_10_supplemental.py --path2 --path3 --eda-host 132.239.17.21

Output: dse_10_supplemental_p1.json / dse_10_supplemental_p1p2.json / dse_10_supplemental_p1p2p3.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

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
logger = logging.getLogger("run_10_supplemental")

for _name in ("ax", "ax.service", "ax.core", "sim"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# ── 10 個補充實驗（Group G：DP 12 retry + frequency sweep）────────────────────
SUPPLEMENTAL_EXPERIMENTS: List[Dict[str, Any]] = [
    # G1: DP 12 retry — inner_dim=2048 @ 100 MHz
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    # G2–G6: inner_dim=2048 @ 80/110/120/125/150 MHz
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(2e8),
     "top_module": "hd_top"},
    # G7–G8: base arch @ 80/175 MHz
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(2e8),
     "top_module": "hd_top"},
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(2e8),
     "top_module": "hd_top"},
    # G9: inner_dim=4096 @ 125 MHz
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 4096, "frequency": int(2e8),
     "top_module": "hd_top"},
    # G10: small arch @ 175 MHz
    {"group": "G", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(2e8),
     "top_module": "hd_top"},
]


def _default_output_path(use_path2: bool, use_path3: bool) -> str:
    """輸出檔名與主實驗分離，永不覆寫 dse_22_* / dse_32_*。"""
    if use_path3:
        return "dse_10_supplemental_p1p2p3.json"
    if use_path2:
        return "dse_10_supplemental_p1p2.json"
    return "dse_10_supplemental_p1.json"


def main():
    parser = argparse.ArgumentParser(
        description="10-point supplemental experiment (Group G) — 獨立執行，不影響主實驗輸出",
    )
    parser.add_argument("--path2", action="store_true", help="Enable Path 2 (EDA synthesis)")
    parser.add_argument("--path3", action="store_true", help="Enable Path 3 (gate-level sim)")
    parser.add_argument("--eda-host", type=str, default="EDA_SERVER_IP", help="EDA Server host")
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
        help="Output JSON path (default: dse_10_supplemental_*.json)",
    )
    args = parser.parse_args()

    if args.path3 and not args.path2:
        logger.warning("--path3 requires --path2. Path 3 will not run.")

    output_file = args.output or _default_output_path(args.path2, args.path3 and args.path2)

    logger.info("=" * 60)
    logger.info("10-Point Supplemental Experiment (Group G)")
    logger.info("  Path 2: %s", "ENABLED" if args.path2 else "DISABLED")
    logger.info("  Path 3: %s", "ENABLED" if args.path3 and args.path2 else "DISABLED")
    logger.info("  synth_mode=%s, top_module=%s", args.synth_mode, args.top_module)
    logger.info("  output: %s (獨立於主實驗 dse_22/dse_32)", output_file)
    if args.path2:
        logger.info("  EDA Server: %s:%s", args.eda_host, args.eda_port)
    logger.info("=" * 60)

    run_start = datetime.now(timezone.utc).isoformat()
    t_start = time.monotonic()

    from run_15_experiments import run_experiments

    results = run_experiments(
        use_path2=args.path2,
        use_path3=args.path3 and args.path2,
        eda_host=args.eda_host,
        eda_port=args.eda_port,
        synth_mode=args.synth_mode,
        top_module=args.top_module,
        accuracy_threshold=args.accuracy_threshold,
        experiments=SUPPLEMENTAL_EXPERIMENTS,
    )

    wall_clock_s = round(time.monotonic() - t_start, 2)
    run_end = datetime.now(timezone.utc).isoformat()

    if len(results) != 10:
        logger.error(
            "INCOMPLETE: expected 10 results, got %d. Script may have been interrupted.",
            len(results),
        )
        sys.exit(1)

    status_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    logger.info("=" * 60)
    logger.info("Summary: 10/10 supplemental experiments completed")
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
                    "total_data_points": 10,
                    "run_type": "supplemental_group_g",
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
