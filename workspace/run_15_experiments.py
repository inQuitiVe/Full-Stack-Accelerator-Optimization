"""
run_15_experiments.py — 22-point differentiated experiment for Path 2/Path 3 validation.

Design: 22 fixed parameter configurations across 6 groups to maximize result
differentiation and highlight the importance of Path 2 (EDA synthesis) and Path 3
(gate-level simulation). Frequency tuned per actual DSE results to reduce Gate 2 failures.
Group F compares core vs hd_top synthesis time on same small arch.

Usage (from workspace/ directory):
  python3 run_15_experiments.py                           # Path 1 only
  python3 run_15_experiments.py --path2                   # Path 1 + Path 2
  python3 run_15_experiments.py --path2 --path3           # Path 1 + Path 2 + Path 3
  python3 run_15_experiments.py --path2 --path3 --eda-host 132.239.17.21 --eda-port 5000
  python3 run_15_experiments.py --path2 --synth-mode slow # Use slow (full) synthesis

Output: dse_22_p1.json / dse_22_p1p2.json / dse_22_p1p2p3.json with all metrics per data point.
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

# Bootstrap paths (same as run_exploration.py)
_WORKSPACE = os.path.dirname(os.path.abspath(__file__))
_HDNN_ROOT = os.path.join(_WORKSPACE, "HDnn-PIM-Opt")
for _p in [_WORKSPACE, _HDNN_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_15_experiments")

# Suppress noisy loggers
for _name in ("ax", "ax.service", "ax.core", "sim"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# ── Default params (merged with each experiment) ───────────────────────────────
DEFAULT_PARAMS = {
    "frequency": int(1e8),
    "stride_1": 2,
    "stride_2": 1,
    "padding_1": 0,
    "padding_2": 0,
    "dilation_1": 1,
    "dilation_2": 1,
    "cnn_x_dim_1": 16,
    "cnn_y_dim_1": 16,
    "cnn_x_dim_2": 8,
    "cnn_y_dim_2": 8,
    "encoder_x_dim": 8,
    "encoder_y_dim": 8,
    "syn_map_effort": "medium",
    "syn_opt_effort": "medium",
    "enable_clock_gating": "false",
    "max_area_ignore_tns": "false",
    "enable_retime": "false",
    "compile_timing_high_effort": "false",
    "compile_area_high_effort": "false",
    "compile_ultra_gate_clock": "false",
    "compile_exact_map": "false",
    "compile_no_autoungroup": "false",
    "compile_clock_gating_through_hierarchy": "false",
    "enable_leakage_optimization": "false",
    "enable_dynamic_optimization": "false",
    "enable_enhanced_resource_sharing": "false",
    "dp_smartgen_strategy": "none",
}

# ── 20 Experiment Configurations ─────────────────────────────────────────────
# Group A (DP 1–5): EDA strategy impact — fixed arch, varying EDA flags, all 100 MHz
# Group B (DP 6–10): Architecture gradient — varying SW/HW params, all 100 MHz
# Group C (DP 11–13): inner_dim gradient — Path 3 cycle count differentiation, all 100 MHz
# Group D (DP 14–16): Frequency sweep on small arch — 125/150/150 MHz
# Group E (DP 17–20): Gate 2 pressure — large arch, low vs high EDA, 125/100 MHz
# Group F (DP 21–22): core vs hd_top — same small arch, compare p2/p3 elapsed time
#
# frequency (Hz): 1e8=100MHz, 1.25e8=125MHz, 1.5e8=150MHz
# Tuned per actual DSE results to reduce Gate 2 failures (200 MHz → fail for mid/large arch).
# Do NOT enable compile_timing_high_effort and compile_area_high_effort together (DC conflict).
# reram_size unified to 128 where applicable.

EXPERIMENTS: List[Dict[str, Any]] = [
    # ── Group A: EDA strategy impact (all 100 MHz) ───────────────────────────
    {"group": "A", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "syn_map_effort": "low", "syn_opt_effort": "low"},
    {"group": "A", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "syn_map_effort": "high", "syn_opt_effort": "high", "enable_retime": "true",
     "compile_timing_high_effort": "true"},
    {"group": "A", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "enable_clock_gating": "true", "enable_leakage_optimization": "true",
     "enable_dynamic_optimization": "true", "compile_ultra_gate_clock": "true"},
    # DP4: Area aggressive — may trigger gate2_failed (timing_violated) by design
    {"group": "A", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "max_area_ignore_tns": "true", "compile_area_high_effort": "true",
     "dp_smartgen_strategy": "area"},
    # DP5: Max effort timing (omit compile_area_high_effort to avoid DC conflict)
    {"group": "A", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "syn_map_effort": "high", "syn_opt_effort": "high", "enable_retime": "true",
     "compile_timing_high_effort": "true", "enable_clock_gating": "true",
     "enable_leakage_optimization": "true", "enable_dynamic_optimization": "true",
     "dp_smartgen_strategy": "timing"},
    # ── Group B: Architecture gradient (all 100 MHz) ──────────────────────────
    {"group": "B", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8)},
    {"group": "B", "hd_dim": 2048, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 5, "inner_dim": 1024, "frequency": int(1e8)},
    {"group": "B", "hd_dim": 4096, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8)},
    {"group": "B", "hd_dim": 4096, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1e8)},
    {"group": "B", "hd_dim": 4096, "reram_size": 128, "out_channels_1": 16, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1e8)},
    # ── Group C: inner_dim gradient (all 100 MHz) ──────────────────────────────
    {"group": "C", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8)},
    {"group": "C", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 2048, "frequency": int(1e8)},
    {"group": "C", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 8, "kernel_size_1": 5,
     "out_channels_2": 16, "kernel_size_2": 3, "inner_dim": 4096, "frequency": int(1e8)},
    # ── Group D: Frequency sweep on small arch (125/150/150 MHz) ──────────────
    {"group": "D", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1.25e8)},
    {"group": "D", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1.5e8)},
    {"group": "D", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1.5e8),
     "syn_map_effort": "high", "syn_opt_effort": "high", "enable_retime": "true"},
    # ── Group E: Gate 2 pressure (large arch, 125/100 MHz) ────────────────────
    {"group": "E", "hd_dim": 4096, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1.25e8),
     "syn_map_effort": "low", "syn_opt_effort": "low", "enable_retime": "false",
     "compile_timing_high_effort": "false"},
    {"group": "E", "hd_dim": 4096, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1.25e8),
     "syn_map_effort": "high", "syn_opt_effort": "high", "enable_retime": "true",
     "compile_timing_high_effort": "true"},
    {"group": "E", "hd_dim": 4096, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1e8),
     "syn_map_effort": "low", "syn_opt_effort": "low", "enable_retime": "false",
     "compile_timing_high_effort": "false"},
    {"group": "E", "hd_dim": 4096, "reram_size": 256, "out_channels_1": 16, "kernel_size_1": 7,
     "out_channels_2": 32, "kernel_size_2": 7, "inner_dim": 1024, "frequency": int(1e8),
     "syn_map_effort": "high", "syn_opt_effort": "high", "enable_retime": "true",
     "compile_timing_high_effort": "true"},
    # ── Group F: same small arch (both hd_top for consistency) ─────────────────
    {"group": "F", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "top_module": "hd_top"},
    {"group": "F", "hd_dim": 2048, "reram_size": 128, "out_channels_1": 4, "kernel_size_1": 3,
     "out_channels_2": 8, "kernel_size_2": 3, "inner_dim": 1024, "frequency": int(1e8),
     "top_module": "hd_top"},
]


def _merge_params(exp: Dict[str, Any], synth_mode: str, top_module: str) -> Dict[str, Any]:
    """Merge experiment overrides with defaults; inject synth_mode and top_module."""
    base = {**DEFAULT_PARAMS, **{k: v for k, v in exp.items() if k != "group"}}
    base["synth_mode"] = synth_mode
    base["top_module"] = exp.get("top_module", top_module)
    return base


def run_experiments(
    use_path2: bool = False,
    use_path3: bool = False,
    eda_host: str = "EDA_SERVER_IP",
    eda_port: int = 5000,
    synth_mode: str = "fast",
    top_module: str = "hd_top",
    accuracy_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Run all 22 experiments and collect results.

    Returns:
        List of result dicts, one per data point. Each dict contains:
        - dp: data point index (1–22)
        - group: A|B|C|D|E|F
        - status: gate1_failed | gate2_failed | path3_failed | success
        - accuracy, energy_uj, timing_us, area_mm2 (final stitched)
        - p1_elapsed_s, p2_elapsed_s, p3_elapsed_s (wall-clock seconds per path)
        - p2_* (Path 2 raw ASIC metrics when available)
        - p3_* (Path 3 raw metrics when available)
    """
    from omegaconf import OmegaConf

    config_path = os.path.join(_WORKSPACE, "conf", "config.yaml")
    cfg = OmegaConf.load(config_path)
    data_args = OmegaConf.to_container(cfg["data"], resolve=True)
    training_args = OmegaConf.to_container(cfg["training"], resolve=True)
    hardware_args = OmegaConf.to_container(cfg["hardware"], resolve=True)

    hardware_args["synth_mode"] = synth_mode

    from dse_framework.evaluators.path1_software import evaluate_path1
    from dse_framework.evaluators.path2_hardware import evaluate_path2, evaluate_path3

    _sim_logger = logging.getLogger("dse_framework.sim")
    _sim_logger.setLevel(logging.WARNING)

    results: List[Dict[str, Any]] = []

    for i, exp in enumerate(EXPERIMENTS):
        dp = i + 1
        group = exp.get("group", "?")
        params = _merge_params(exp, synth_mode, top_module)
        top_mod = params["top_module"]
        hardware_args["top_module"] = top_mod

        logger.info("=" * 60)
        logger.info(
            f"[DP {dp}] Group {group} — hd_dim={params['hd_dim']}, "
            f"reram={params['reram_size']}, inner_dim={params['inner_dim']}, "
            f"freq={params.get('frequency', 1e8)/1e6:.0f}MHz, top={top_mod}"
        )

        record: Dict[str, Any] = {
            "dp": dp,
            "group": group,
            "params": {k: v for k, v in params.items() if k != "hd_model"},
            "status": None,
            "accuracy": None,
            "energy_uj": None,
            "timing_us": None,
            "area_mm2": None,
            "p2_area_um2": None,
            "p2_clock_period_ns": None,
            "p2_timing_slack_ns": None,
            "p2_dynamic_power_mw": None,
            "p3_execution_cycles": None,
            "p3_dynamic_power_mw": None,
            "p1_elapsed_s": None,
            "p2_elapsed_s": None,
            "p3_elapsed_s": None,
        }

        # ── Path 1: Software simulation ─────────────────────────────────────
        t0 = time.monotonic()
        try:
            p1 = evaluate_path1(
                params,
                data_args,
                training_args,
                hardware_args,
                _HDNN_ROOT,
                logger_override=logger,
                evaluator_logger=_sim_logger,
            )
        except Exception as exc:
            record["p1_elapsed_s"] = round(time.monotonic() - t0, 2)
            logger.error(f"[DP {dp}] Path 1 failed: {exc}")
            record["status"] = "path1_error"
            record["error"] = str(exc)
            results.append(record)
            continue
        record["p1_elapsed_s"] = round(time.monotonic() - t0, 2)

        accuracy = p1["accuracy"]
        record["accuracy"] = accuracy

        if accuracy < accuracy_threshold:
            logger.info(
                f"[DP {dp}] GATE 1 FAILED: accuracy={accuracy:.4f} < {accuracy_threshold}"
            )
            record["status"] = "gate1_failed"
            record["energy_uj"] = p1.get("energy_uj")
            record["timing_us"] = p1.get("timing_us")
            record["area_mm2"] = p1.get("area_mm2")
            results.append(record)
            continue

        if not use_path2:
            record["status"] = "path1_only"
            record["energy_uj"] = p1["energy_uj"]
            record["timing_us"] = p1["timing_us"]
            record["area_mm2"] = p1["area_mm2"]
            results.append(record)
            continue

        # ── Path 2: Hardware synthesis ──────────────────────────────────────
        t0 = time.monotonic()
        try:
            p2 = evaluate_path2(
                params,
                dp,
                accuracy,
                data_args,
                training_args,
                hardware_args,
                _HDNN_ROOT,
                hd_model=p1.get("hd_model"),
                top_module=params["top_module"],
                eda_host=eda_host,
                eda_port=eda_port,
            )
        except Exception as exc:
            record["p2_elapsed_s"] = round(time.monotonic() - t0, 2)
            logger.error(f"[DP {dp}] Path 2 failed: {exc}")
            record["status"] = "path2_error"
            record["error"] = str(exc)
            results.append(record)
            continue
        record["p2_elapsed_s"] = round(time.monotonic() - t0, 2)

        if p2["status"] != "success":
            logger.warning(f"[DP {dp}] GATE 2 FAILED: {p2.get('status', 'unknown')}")
            record["status"] = "gate2_failed"
            results.append(record)
            continue

        asic = p2.get("_asic_metrics", {})
        record["p2_area_um2"] = asic.get("area_um2")
        record["p2_clock_period_ns"] = asic.get("clock_period_ns")
        record["p2_timing_slack_ns"] = asic.get("timing_slack_ns")
        record["p2_dynamic_power_mw"] = asic.get("dynamic_power_mw")
        record["accuracy"] = p2["metrics"]["accuracy"]
        record["energy_uj"] = p2["metrics"]["energy_uj"]
        record["timing_us"] = p2["metrics"]["timing_us"]
        record["area_mm2"] = p2["metrics"]["area_mm2"]

        if not use_path3:
            record["status"] = "path2_only"
            results.append(record)
            continue

        # ── Path 3: Gate-level simulation ────────────────────────────────────
        t0 = time.monotonic()
        try:
            p3 = evaluate_path3(
                params,
                dp,
                accuracy,
                asic,
                data_args,
                training_args,
                hardware_args,
                _HDNN_ROOT,
                hd_model=p1.get("hd_model"),
                top_module=params["top_module"],
                eda_host=eda_host,
                eda_port=eda_port,
            )
        except Exception as exc:
            record["p3_elapsed_s"] = round(time.monotonic() - t0, 2)
            logger.warning(f"[DP {dp}] Path 3 failed (keeping Path 2): {exc}")
            record["status"] = "path3_failed"
            record["error"] = str(exc)
            results.append(record)
            continue
        record["p3_elapsed_s"] = round(time.monotonic() - t0, 2)

        if p3.get("status") != "success":
            record["status"] = "path3_failed"
            results.append(record)
            continue

        vcs = p3.get("_vcs_metrics", {})
        record["p3_execution_cycles"] = vcs.get("execution_cycles")
        record["p3_dynamic_power_mw"] = vcs.get("dynamic_power_mw")
        record["accuracy"] = p3["metrics"]["accuracy"]
        record["energy_uj"] = p3["metrics"]["energy_uj"]
        record["timing_us"] = p3["metrics"]["timing_us"]
        record["area_mm2"] = p3["metrics"]["area_mm2"]
        record["status"] = "success"

        logger.info(
            f"[DP {dp}] SUCCESS — acc={record['accuracy']:.4f}, "
            f"energy={record['energy_uj']:.2f}uJ, timing={record['timing_us']:.2f}us, "
            f"area={record['area_mm2']:.4f}mm², p3_cycles={record['p3_execution_cycles']}"
        )
        results.append(record)

    return results


def _parse_args():
    parser = argparse.ArgumentParser(
        description="22-point differentiated experiment for Path 2/Path 3 validation",
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
        help="Output JSON file path (default: auto by mode, e.g. dse_22_p1p2p3.json)",
    )
    return parser.parse_args()


def _default_output_path(use_path2: bool, use_path3: bool) -> str:
    """Auto-generate output filename by mode to avoid overwriting different runs."""
    if use_path3:
        return "dse_22_p1p2p3.json"
    if use_path2:
        return "dse_22_p1p2.json"
    return "dse_22_p1.json"


def main():
    args = _parse_args()
    if args.path3 and not args.path2:
        logger.warning("--path3 requires --path2. Path 3 will not run.")

    output_file = args.output or _default_output_path(args.path2, args.path3 and args.path2)

    logger.info("=" * 60)
    logger.info("22-Point Differentiated Experiment")
    logger.info(f"  Path 2: {'ENABLED' if args.path2 else 'DISABLED'}")
    logger.info(f"  Path 3: {'ENABLED' if args.path3 and args.path2 else 'DISABLED'}")
    logger.info(f"  synth_mode={args.synth_mode}, top_module={args.top_module}")
    logger.info(f"  output: {output_file}")
    if args.path2:
        logger.info(f"  EDA Server: {args.eda_host}:{args.eda_port}")
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
    )

    wall_clock_s = round(time.monotonic() - t_start, 2)
    run_end = datetime.now(timezone.utc).isoformat()

    # Ensure exactly 22 data points
    if len(results) != 22:
        logger.error(
            f"INCOMPLETE: expected 22 results, got {len(results)}. "
            "Script may have been interrupted or an experiment crashed."
        )
        sys.exit(1)

    # Summary
    status_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    logger.info("=" * 60)
    logger.info("Summary: 22/22 experiments completed")
    for status, count in sorted(status_counts.items()):
        logger.info(f"  {status}: {count}")
    logger.info(f"  Wall clock: {wall_clock_s:.1f}s")
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
                    "total_data_points": 22,
                    "run_start_iso": run_start,
                    "run_end_iso": run_end,
                    "wall_clock_seconds": wall_clock_s,
                },
                "results": results,
            },
            f,
            indent=2,
        )
    logger.info(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
