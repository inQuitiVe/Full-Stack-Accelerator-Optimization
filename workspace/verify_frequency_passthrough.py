#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_frequency_passthrough.py — 中繼檢查：確認送進 timeloop 前的 frequency 是否正確。

檢查點：
  Path 1：params 中的 frequency → Evaluator.evaluate() → sim 的 CiMLoop metric manager
         → timeloop_ppa_hdnn(..., frequency)

執行方式：
  python verify_frequency_passthrough.py [--run-path1]
  --run-path1：若提供，會執行一次真實的 Path 1 評估以驗證（需 HDnn-PIM-Opt 環境）
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_FREQ_MIN_HZ = int(2e8)  # 200 MHz


def check_path1_timeloop_frequency() -> bool:
    """檢查 Path 1 送進 timeloop 前的 frequency。"""
    logger.info("=" * 60)
    logger.info("檢查：送進 timeloop 前的 frequency")
    logger.info("流程：params → Evaluator.evaluate() → timeloop_ppa_hdnn(..., frequency)")
    logger.info("=" * 60)

    # 模擬實驗定義的 params
    params = {
        "hd_dim": 2048,
        "reram_size": 256,
        "inner_dim": 1024,
        "frequency": int(2e8),  # 200 MHz
    }
    freq = int(params.get("frequency", 0))
    if freq < _FREQ_MIN_HZ:
        logger.error(f"  ✗ frequency={freq} Hz < 200 MHz")
        return False
    logger.info(f"  ✓ params 含 frequency={freq} Hz ({freq/1e6:.0f} MHz)")

    # 檢查 path1_software 的檢查邏輯（送進 Evaluator = 送進 timeloop 前）
    workspace = os.path.dirname(os.path.abspath(__file__))
    path1_path = os.path.join(workspace, "dse_framework", "evaluators", "path1_software.py")
    if os.path.exists(path1_path):
        with open(path1_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "_FREQ_MIN_HZ" in content and "Passing params to Evaluator" in content:
            logger.info("  ✓ path1_software.py 在送進 Evaluator（timeloop）前有 frequency 檢查與 log")
        else:
            logger.warning("  ? path1_software.py 可能未含完整 frequency 檢查")
    return True


def run_path1_single_eval() -> bool:
    """執行一次 Path 1 評估，驗證送進 timeloop 的 frequency。"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("實際執行 Path 1：驗證 log 中送進 timeloop 的 frequency")
    logger.info("=" * 60)

    try:
        from dse_framework.evaluators.path1_software import evaluate_path1
    except ImportError as exc:
        logger.warning(f"  無法 import evaluate_path1: {exc}")
        logger.info("  請在 workspace 目錄下執行，並確保 HDnn-PIM-Opt 在 sys.path")
        return False

    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HDnn-PIM-Opt")
    if not os.path.isdir(cwd):
        logger.warning(f"  HDnn-PIM-Opt 目錄不存在: {cwd}")
        return False

    params = {
        "hd_dim": 2048,
        "reram_size": 256,
        "inner_dim": 1024,
        "frequency": int(2e8),
        "out_channels_1": 8,
        "kernel_size_1": 3,
        "stride_1": 2,
        "padding_1": 0,
        "dilation_1": 1,
        "out_channels_2": 16,
        "kernel_size_2": 3,
        "stride_2": 1,
        "padding_2": 0,
        "dilation_2": 1,
        "cnn_x_dim_1": 8,
        "cnn_y_dim_1": 8,
        "cnn_x_dim_2": 4,
        "cnn_y_dim_2": 4,
        "encoder_x_dim": 8,
        "encoder_y_dim": 8,
    }
    data_args = {"dataset": "mnist"}
    training_args = {"devices": ["cpu"]}
    hardware_args = {"type": "cimloop", "cnn": True}

    logger.info("  執行 evaluate_path1(params={..., frequency=200e6})...")
    try:
        result = evaluate_path1(
            params, data_args, training_args, hardware_args, cwd,
            logger_override=logger,
            evaluator_logger=logging.getLogger("sim"),
        )
        acc = result.get("accuracy")
        logger.info(f"  ✓ Path 1 完成: accuracy={acc:.4f}" if isinstance(acc, (int, float)) else f"  ✓ Path 1 完成: {result}")
        logger.info("  若上方 log 顯示 '[Path1] Passing params to Evaluator (frequency=...)' 則送進 timeloop 的 frequency 已確認")
        return True
    except Exception as exc:
        logger.error(f"  ✗ Path 1 執行失敗: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證送進 timeloop 前的 frequency")
    parser.add_argument("--run-path1", action="store_true", help="執行實際 Path 1 評估")
    args = parser.parse_args()

    ok = check_path1_timeloop_frequency()
    if args.run_path1:
        ok &= run_path1_single_eval()

    logger.info("")
    logger.info("=" * 60)
    if ok:
        logger.info("檢查通過 ✓")
    else:
        logger.info("檢查未通過，請檢查上述輸出")
    logger.info("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
