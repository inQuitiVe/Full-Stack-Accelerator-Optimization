"""
path1_software.py — Path 1 Software Simulation Evaluator.

Wraps the existing `sim/` module (CiMLoop + Timeloop) and standardises its
output into the canonical metrics format used by the BO engine.

Canonical output (raw, before normalisation):
  {
    "accuracy":     float,  # 0.0 ~ 1.0
    "energy_uj":    float,  # uJ  (asic_energy + rram_energy)
    "timing_us":    float,  # us  (asic_delay + rram_delay, sequential)
    "area_mm2":     float,  # mm^2 (asic_area + rram_area)
  }

The caller (bo_engine.py) normalises these raw values via normalizer.py before
passing them to the Ax client.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Ensure the workspace/HDnn-PIM-Opt directory is on sys.path so we can import sim/
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "workspace")
)
_HDNN_ROOT = os.path.join(_WORKSPACE_ROOT, "HDnn-PIM-Opt")
if _HDNN_ROOT not in sys.path:
    sys.path.insert(0, _HDNN_ROOT)


def evaluate_path1(
    params: Dict[str, Any],
    data_args: Dict[str, Any],
    training_args: Dict[str, Any],
    hardware_args: Dict[str, Any],
    cwd: str,
    logger_override=None,
) -> Dict[str, float]:
    """
    Run the full Path 1 software simulation for a single parameter configuration.

    Args:
        params:         BO parameter dict (hd_dim, reram_size, cnn_x_dim_1, etc.)
        data_args:      Dataset config (dataset name, batch sizes, etc.)
        training_args:  Training hyperparameters (epochs, lr, devices, etc.)
        hardware_args:  Hardware config flags (type="cimloop", cnn=True, etc.)
        cwd:            Absolute path to the HDnn-PIM-Opt working directory.
        logger_override: Optional logger to use; defaults to module logger.

    Returns:
        Canonical metrics dict with raw (un-normalised) values.

    Raises:
        RuntimeError:   If the simulation fails or returns unexpected shapes.
    """
    _log = logger_override or logger

    try:
        from sim.evaluator import Evaluator
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import sim.evaluator. Ensure HDnn-PIM-Opt is on sys.path.\n"
            f"Attempted path: {_HDNN_ROOT}\nOriginal error: {exc}"
        ) from exc

    evaluator = Evaluator(data_args, training_args, hardware_args, cwd, _log)

    # The Evaluator.evaluate() API expects a list (one item per GPU worker)
    results = evaluator.evaluate([params], _log)

    if not results:
        raise RuntimeError("Evaluator returned empty results list.")

    result = results[0]
    # result format: {"accuracy": (value, sem), "power": (value, sem),
    #                 "performance": (value, sem), "area": (value, sem)}
    # Note: "power" in the sim code stores energy (uJ); we rename it here for clarity.

    accuracy: float = result["accuracy"][0]
    energy_uj: float = result["power"][0]        # sim uses "power" key for energy (uJ)
    timing_us: float = result["performance"][0]  # us
    area_mm2: float = result["area"][0]          # mm^2

    _log.info(
        f"[Path1] accuracy={accuracy:.4f}, energy={energy_uj:.3f}uJ, "
        f"timing={timing_us:.3f}us, area={area_mm2:.4f}mm^2"
    )

    return {
        "accuracy": accuracy,
        "energy_uj": energy_uj,
        "timing_us": timing_us,
        "area_mm2": area_mm2,
    }
