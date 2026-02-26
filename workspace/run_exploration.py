"""
run_exploration.py — Entry point for the Full-Stack DSE Framework.

Usage (from repo root):
  python workspace/run_exploration.py                     # Path 1 only (software simulation)
  python workspace/run_exploration.py --path2             # Path 1 + Path 2 (EDA synthesis)
  python workspace/run_exploration.py --path2 --eda-host 192.168.1.100 --eda-port 5000

Usage (from workspace/ directory):
  python run_exploration.py
  python run_exploration.py --path2

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
    logger.info(f"  Path 2 (EDA): {'ENABLED' if args.path2 else 'DISABLED'}")
    if args.path2:
        logger.info(f"  EDA Server:   {args.eda_host}:{args.eda_port}")
    logger.info("=" * 60)
    logger.info(OmegaConf.to_yaml(cfg))

    from dse_framework.core_algorithm.bo_engine import run_bo

    history = run_bo(
        args=cfg,
        data_args=OmegaConf.to_container(cfg["data"], resolve=True),
        training_args=OmegaConf.to_container(cfg["training"], resolve=True),
        hardware_args=OmegaConf.to_container(cfg["hardware"], resolve=True),
        cwd=_HDNN_ROOT,
        use_path2=args.path2,
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
