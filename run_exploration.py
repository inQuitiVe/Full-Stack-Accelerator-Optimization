"""
run_exploration.py — Entry point for the Full-Stack DSE Framework.

Usage:
  python run_exploration.py                     # Path 1 only (software simulation)
  python run_exploration.py --path2             # Path 1 + Path 2 (EDA synthesis)
  python run_exploration.py --path2 --eda-host 192.168.1.100 --eda-port 5000

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

# Add workspace paths to sys.path
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE = os.path.join(_REPO_ROOT, "workspace")
_HDNN_ROOT = os.path.join(_WORKSPACE, "HDnn-PIM-Opt")
for _p in [_WORKSPACE, _HDNN_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _parse_args():
    parser = argparse.ArgumentParser(description="HDnn-PIM DSE Framework")
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
    return parser.parse_args()


@hydra.main(version_base=None, config_path="workspace/conf", config_name="config")
def main(cfg: DictConfig) -> None:
    args = _parse_args()
    cwd = hydra.utils.get_original_cwd()

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
        cwd=os.path.join(cwd, "workspace", "HDnn-PIM-Opt"),
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
