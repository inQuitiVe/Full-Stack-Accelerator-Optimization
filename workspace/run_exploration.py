"""
run_exploration.py — Entry point for the Full-Stack DSE Framework.

Usage (from workspace/ directory):
  python3 run_exploration.py                           # Path 1 only (software simulation)
  python3 run_exploration.py --path2                   # Path 1 + Path 2 (EDA synthesis)
  python3 run_exploration.py --path2 --path3           # Path 1 + Path 2 + Path 3 (gate-level sim)
  python3 run_exploration.py --path2 --path3 --top-module hd_top  # Fast scope (hd_top only)
  python3 run_exploration.py --path2 --eda-host 132.239.17.21 --eda-port 5000

Usage (from repo root):
  python3 workspace/run_exploration.py
  python3 workspace/run_exploration.py --path2

Note: Use python3 (not ./run_exploration.py) to avoid CRLF line-ending issues
      when workspace is mounted from Windows into Docker.

Path 3 notes:
  - Path 3 runs LFSR-based gate-level simulation (VCS) + PtPX power analysis.
  - No hex data transfer required; the testbench generates its own LFSR patterns.
  - Path 3 is ONLY triggered if Path 2 timing is met (Gate 2 must pass).
  - --top-module selects the simulation scope: 'core' (full wrapper) or 'hd_top' (HD core only).

This script bootstraps the Hydra config system, then delegates to bo_engine.run_bo().
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import hydra
from omegaconf import DictConfig, OmegaConf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_exploration")

# Suppress Ax verbose logs before any Ax code runs
for _ax_name in ("ax", "ax.service", "ax.service.utils", "ax.service.utils.instantiation", "ax.core", "ax.core.experiment"):
    logging.getLogger(_ax_name).setLevel(logging.WARNING)

# This script lives inside workspace/; use its directory as the workspace root.
_WORKSPACE = os.path.dirname(os.path.abspath(__file__))
_HDNN_ROOT = os.path.join(_WORKSPACE, "HDnn-PIM-Opt")
for _p in [_WORKSPACE, _HDNN_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _parse_args():
    """
    Parse custom CLI flags and strip them from sys.argv so Hydra does not
    see unrecognised arguments.  Must be called before @hydra.main runs.
    """
    parser = argparse.ArgumentParser(description="HDnn-PIM DSE Framework", add_help=False)
    parser.add_argument(
        "--path2",
        action="store_true",
        help="Enable Path 2 hardware synthesis via EDA Server",
    )
    parser.add_argument(
        "--path3",
        action="store_true",
        help="Enable Path 3 gate-level simulation (VCS + PtPX) via EDA Server. Requires --path2.",
    )
    parser.add_argument(
        "--top-module",
        type=str,
        default="core",
        choices=["core", "hd_top"],
        help="Synthesis and simulation scope: 'core' (full wrapper) or 'hd_top' (HD core only). "
             "Applies to both Path 2 (TCL elaboration) and Path 3 (testbench selection).",
    )
    parser.add_argument(
        "--eda-host",
        type=str,
        default="EDA_SERVER_IP",
        help="EDA Server hostname or IP address",
    )
    parser.add_argument(
        "--eda-port",
        type=int,
        default=5000,
        help="EDA Server TCP port",
    )
    args, remaining = parser.parse_known_args()
    # Leave only the script name + Hydra-compatible args in sys.argv
    sys.argv = [sys.argv[0]] + remaining
    return args


# Parse and strip our custom flags before Hydra initialises.
_CLI_ARGS = _parse_args()


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    args = _CLI_ARGS

    logger.info("=" * 60)
    logger.info("Full-Stack Accelerator DSE Framework")
    logger.info(f"  Path 2 (EDA Synth):  {'ENABLED' if args.path2 else 'DISABLED'}")
    logger.info(f"  Path 3 (Gate-Level): {'ENABLED' if args.path3 else 'DISABLED'}")
    if args.path2 or args.path3:
        logger.info(f"  Top Module:   {args.top_module}")
        logger.info(f"  EDA Server:   {args.eda_host}:{args.eda_port}")
    if args.path3 and not args.path2:
        logger.warning("  WARNING: --path3 requires --path2. Path 3 will not run.")
    logger.info("=" * 60)

    # Suppress noisy third-party loggers; keep our framework at INFO for key messages
    logging.getLogger().setLevel(logging.WARNING)
    for _name in ("run_exploration", "dse_framework"):
        logging.getLogger(_name).setLevel(logging.INFO)

    from dse_framework.core_algorithm.bo_engine import run_bo

    history = run_bo(
        args=cfg,
        data_args=OmegaConf.to_container(cfg["data"], resolve=True),
        training_args=OmegaConf.to_container(cfg["training"], resolve=True),
        hardware_args=OmegaConf.to_container(cfg["hardware"], resolve=True),
        cwd=_HDNN_ROOT,
        use_path2=args.path2,
        use_path3=args.path3 and args.path2,  # Path 3 requires Path 2
        top_module=args.top_module,
        eda_host=args.eda_host,
        eda_port=args.eda_port,
    )

    # Dump results
    import json
    output_file = os.path.join(os.getcwd(), "dse_results.json")
    with open(output_file, "w") as f:
        json.dump(
            {
                k: v if not isinstance(v[0] if v else None, dict) else [str(x) for x in v]
                for k, v in history.items()
                if k != "param"
            },
            f,
            indent=2,
        )
    logger.info(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
