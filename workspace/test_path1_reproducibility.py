#!/usr/bin/env python3
"""
test_path1_reproducibility.py — 小實驗驗證 Path 1 每次執行結果相同。

對同一組參數執行 Path 1 共 N 次（透過 run_experiments），比較 accuracy、energy_uj、
timing_us、area_mm2 是否完全一致。若一致則通過；否則報告差異。

Usage (from workspace/):
  python test_path1_reproducibility.py
  python test_path1_reproducibility.py --runs 5

需求：與 run_15_experiments 相同（rich、torch、omegaconf 等）
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

_WORKSPACE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_WORKSPACE)
_HDNN_ROOT = os.path.join(_WORKSPACE, "HDnn-PIM-Opt")
for _p in [_WORKSPACE, _HDNN_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 單一組參數（小架構，較快）
TEST_EXPERIMENT = {
    "group": "T",
    "hd_dim": 2048,
    "reram_size": 128,
    "out_channels_1": 4,
    "kernel_size_1": 3,
    "out_channels_2": 8,
    "kernel_size_2": 3,
    "inner_dim": 1024,
    "frequency": int(2e8),
    "top_module": "hd_top",
}


def main():
    parser = argparse.ArgumentParser(description="驗證 Path 1 可重現性")
    parser.add_argument("--runs", type=int, default=3, help="重複執行次數")
    args = parser.parse_args()

    try:
        import rich  # noqa: F401
    except ImportError:
        print("錯誤：缺少 rich 模組。請執行: pip install rich")
        sys.exit(2)

    logging.basicConfig(level=logging.WARNING)
    for _n in ("ax", "ax.service", "ax.core", "sim", "run_15_experiments"):
        logging.getLogger(_n).setLevel(logging.WARNING)

    from run_15_experiments import run_experiments

    results: list[dict] = []
    experiments = [TEST_EXPERIMENT]

    print("=" * 60)
    print(f"Path 1 可重現性測試：同一組參數執行 {args.runs} 次")
    print("=" * 60)

    for i in range(args.runs):
        try:
            r_list = run_experiments(
                use_path2=False,
                use_path3=False,
                experiments=experiments,
            )
        except Exception as e:
            print(f"\n  Run {i + 1} 執行失敗: {e}")
            sys.exit(2)
        r = r_list[0]
        if r.get("status") == "path1_error":
            print(f"\n  Run {i + 1} Path 1 失敗: {r.get('error', 'unknown')}")
            sys.exit(2)
        m = {
            "accuracy": r["p1_accuracy"] or r["accuracy"],
            "energy_uj": r["p1_energy_uj"] or r["energy_uj"],
            "timing_us": r["p1_timing_us"] or r["timing_us"],
            "area_mm2": r["p1_area_mm2"] or r["area_mm2"],
        }
        results.append(m)
        print(f"  Run {i + 1}: acc={m['accuracy']:.6f} energy={m['energy_uj']:.6f} "
              f"timing={m['timing_us']:.6f} area={m['area_mm2']:.6f}")

    # 比較（浮點數用容差 1e-9）
    ref = results[0]
    keys = ["accuracy", "energy_uj", "timing_us", "area_mm2"]
    tol = 1e-9
    passed = True
    for k in keys:
        for i, r in enumerate(results[1:], start=2):
            a, b = ref[k], r[k]
            if a is None or b is None:
                if a != b:
                    print(f"\n  FAIL: {k} 不一致 — Run 1={a} vs Run {i}={b}")
                    passed = False
            elif abs(a - b) > tol:
                print(f"\n  FAIL: {k} 不一致 — Run 1={a} vs Run {i}={b}")
                passed = False

    print()
    if passed:
        print("  ✓ 通過：所有 runs 結果均相同")
    else:
        print("  ✗ 失敗：存在差異")
        sys.exit(1)


if __name__ == "__main__":
    main()
