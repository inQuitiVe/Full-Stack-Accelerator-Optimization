"""
path2_hardware.py — Path 2 Hardware Synthesis Evaluator (Client-Side Stitching).

Responsibilities:
  1. Send params JSON to the remote EDA Server via eda_client.evaluate_remote().
  2. Locally re-run Cimloop (RRAM-only portion) to obtain RRAM energy/delay/area,
     since the RRAM does not have real RTL and Cimloop remains its ground truth.
  3. Stitch the ASIC data (from EDA) with RRAM data (from Cimloop):
       total_timing_us = asic_clock_period_ns * (1e-3) + rram_delay_us
       total_energy_uj = (asic_dynamic_mw * total_timing_us) + rram_energy_uj
       total_area_mm2  = asic_area_um2 * (1e-6) + rram_area_mm2
  4. Return the canonical metrics dict. If EDA fails, return {"status": "failed"}.

Path 3 Extension:
  If `path3=True` is passed, the function additionally queries a VCS/PtPX result
  from the server (using the stored Path 2 job metrics as fallback if Path 3 fails).
  In Path 3 mode, cycle count replaces the clock-period-based timing estimate.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Ensure workspace is importable for Cimloop calls
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "workspace")
)
_HDNN_ROOT = os.path.join(_WORKSPACE_ROOT, "HDnn-PIM-Opt")
if _HDNN_ROOT not in sys.path:
    sys.path.insert(0, _HDNN_ROOT)

from dse_framework.network.eda_client import evaluate_remote, EDAClientError


# ── RRAM-only Cimloop evaluation ──────────────────────────────────────────────

def _evaluate_rram_cimloop(
    params: Dict[str, Any],
    data_args: Dict[str, Any],
    training_args: Dict[str, Any],
    hardware_args: Dict[str, Any],
    cwd: str,
    hd_model=None,
) -> Dict[str, float]:
    """
    Run Cimloop for the RRAM portion only, returning (rram_energy_uj,
    rram_delay_us, rram_area_mm2).

    If `hd_model` is provided (cached from Path 1), re-use it to avoid
    re-running the full training pass.
    """
    try:
        from cimloop.workspace import cimloop_ppa
        from sim.datasets import load_dataloader
    except ImportError as exc:
        raise RuntimeError(f"Cannot import Cimloop dependencies: {exc}") from exc

    reram_size: int = int(params["reram_size"])
    frequency: int = int(params.get("frequency", int(1e8)))

    # Load a single test sample as the activity input for Cimloop
    dataset_name: str = data_args["dataset"]
    _, _, test_loader = load_dataloader(dataset_name, cwd, data_args, True)
    sample = next(iter(test_loader))[0][0][None, :]

    if hd_model is None:
        raise RuntimeError(
            "hd_model must be provided to _evaluate_rram_cimloop. "
            "Pass the cached model from Path 1 evaluation."
        )

    device = training_args.get("devices", ["cpu"])[0]
    sample = sample.to(device)

    reram_energy, reram_delay, reram_area, _ = cimloop_ppa(
        "HD",
        hd_model.hd_inference,
        hd_model.feature_encode(sample),
        reram_size,
        frequency,
        5,  # cell_bit (fixed)
    )

    return {
        "rram_energy_uj": float(reram_energy),
        "rram_delay_us": float(reram_delay),
        "rram_area_mm2": float(reram_area),
    }


# ── Data Stitching ────────────────────────────────────────────────────────────

def _stitch_metrics(
    asic_metrics: Dict[str, float],
    rram_metrics: Dict[str, float],
    execution_cycles: Optional[int] = None,
) -> Dict[str, float]:
    """
    Combine ASIC (from EDA) and RRAM (from Cimloop) metrics.

    If `execution_cycles` is provided (Path 3), compute timing as:
        total_timing_us = (clock_period_ns * execution_cycles) * 1e-3
    Otherwise (Path 2), compute timing as:
        total_timing_us = clock_period_ns * 1e-3 + rram_delay_us
        (ASIC and RRAM treated as sequential)

    Energy formula (once real hardware data is available):
        dynamic_energy_uj  = asic_dynamic_power_mw * total_timing_us
        leakage_energy_uj  = asic_leakage_power_mw * total_timing_us
        total_energy_uj    = dynamic_energy_uj + leakage_energy_uj + rram_energy_uj
    """
    clock_period_ns: float = asic_metrics["clock_period_ns"]
    dynamic_power_mw: float = asic_metrics["dynamic_power_mw"]
    leakage_power_mw: float = asic_metrics["leakage_power_mw"]
    asic_area_um2: float = asic_metrics["area_um2"]

    rram_energy_uj: float = rram_metrics["rram_energy_uj"]
    rram_delay_us: float = rram_metrics["rram_delay_us"]
    rram_area_mm2: float = rram_metrics["rram_area_mm2"]

    # Timing
    if execution_cycles is not None:
        # Path 3: cycle-accurate timing
        asic_timing_us = (clock_period_ns * execution_cycles) * 1e-3
    else:
        # Path 2: single-cycle period as proxy for ASIC portion
        asic_timing_us = clock_period_ns * 1e-3

    total_timing_us: float = asic_timing_us + rram_delay_us

    # Energy  (Power × Time)
    asic_energy_uj: float = (dynamic_power_mw + leakage_power_mw) * total_timing_us
    total_energy_uj: float = asic_energy_uj + rram_energy_uj

    # Area (convert ASIC um^2 → mm^2)
    asic_area_mm2: float = asic_area_um2 * 1e-6
    total_area_mm2: float = asic_area_mm2 + rram_area_mm2

    return {
        "timing_us": total_timing_us,
        "energy_uj": total_energy_uj,
        "area_mm2": total_area_mm2,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_path2(
    params: Dict[str, Any],
    job_id: int,
    accuracy: float,
    data_args: Dict[str, Any],
    training_args: Dict[str, Any],
    hardware_args: Dict[str, Any],
    cwd: str,
    hd_model=None,
    eda_host: str = "EDA_SERVER_IP",
    eda_port: int = 5000,
) -> Dict[str, Any]:
    """
    Full Path 2 evaluation: EDA synthesis + Cimloop RRAM stitching.

    Args:
        params:         BO parameter dict.
        job_id:         Ax trial index (used as EDA job_id for tracking).
        accuracy:       Accuracy value carried over from Path 1 (software model).
        data_args:      Dataset configuration.
        training_args:  Training configuration.
        hardware_args:  Hardware configuration flags.
        cwd:            HDnn-PIM-Opt working directory.
        hd_model:       Cached HD model from Path 1 (required for RRAM Cimloop).
        eda_host:       EDA Server hostname or IP.
        eda_port:       EDA Server TCP port.

    Returns:
        {"status": "success", "metrics": {accuracy, energy_uj, timing_us, area_mm2}}
        OR
        {"status": "failed"}    — caller should call ax_client.mark_trial_failed()
    """
    # Step 1: Submit to EDA Server and wait for synthesis result
    try:
        eda_result = evaluate_remote(
            params, job_id, host=eda_host, port=eda_port
        )
    except EDAClientError as exc:
        logger.error(f"[Job {job_id}] EDA Client network error: {exc}")
        return {"status": "failed"}

    if eda_result.get("status") != "success":
        logger.warning(
            f"[Job {job_id}] EDA returned non-success status: "
            f"{eda_result.get('status')} — {eda_result.get('reason', '')}"
        )
        return {"status": "failed"}

    asic_metrics: Dict[str, float] = eda_result["metrics"]
    logger.info(f"[Job {job_id}] ASIC metrics received: {asic_metrics}")

    # Step 2: Re-run Cimloop locally for RRAM data
    try:
        rram_metrics = _evaluate_rram_cimloop(
            params, data_args, training_args, hardware_args, cwd, hd_model
        )
    except Exception as exc:
        logger.error(f"[Job {job_id}] Cimloop RRAM evaluation failed: {exc}")
        return {"status": "failed"}

    logger.info(f"[Job {job_id}] RRAM metrics (Cimloop): {rram_metrics}")

    # Step 3: Stitch ASIC + RRAM data
    combined = _stitch_metrics(asic_metrics, rram_metrics)

    return {
        "status": "success",
        "metrics": {
            "accuracy": accuracy,   # carried from Path 1 (PyTorch model)
            "energy_uj": combined["energy_uj"],
            "timing_us": combined["timing_us"],
            "area_mm2": combined["area_mm2"],
        },
    }


def evaluate_path3(
    params: Dict[str, Any],
    job_id: int,
    accuracy: float,
    path2_asic_metrics: Dict[str, float],
    data_args: Dict[str, Any],
    training_args: Dict[str, Any],
    hardware_args: Dict[str, Any],
    cwd: str,
    hd_model=None,
    eda_host: str = "EDA_SERVER_IP",
    eda_port: int = 5000,
) -> Dict[str, Any]:
    """
    Path 3 evaluation: query VCS cycle count from EDA Server, then stitch with
    Path 2 ASIC power data (already obtained) and Cimloop RRAM data.

    `path2_asic_metrics` must be the `metrics` dict returned by the EDA Server
    during Path 2 (contains area_um2, clock_period_ns, dynamic_power_mw,
    leakage_power_mw).
    """
    path3_job_id = job_id + 1_000_000  # Distinguish Path 3 jobs from Path 2

    try:
        vcs_result = evaluate_remote(
            params, path3_job_id, host=eda_host, port=eda_port
        )
    except EDAClientError as exc:
        logger.error(f"[Job {job_id}] Path 3 EDA Client error: {exc}")
        return {"status": "failed"}

    if vcs_result.get("status") != "success":
        logger.warning(
            f"[Job {job_id}] Path 3 EDA returned: {vcs_result.get('status')}"
        )
        return {"status": "failed"}

    execution_cycles: int = vcs_result["metrics"]["execution_cycles"]
    path3_dynamic_power_mw: float = vcs_result["metrics"]["dynamic_power_mw"]
    path3_leakage_power_mw: float = vcs_result["metrics"].get("leakage_power_mw", 0.0)

    # Use cycle-accurate power from PtPX; keep area from Path 2 (unchanged)
    upgraded_asic = {
        **path2_asic_metrics,
        "dynamic_power_mw": path3_dynamic_power_mw,
        "leakage_power_mw": path3_leakage_power_mw,
    }

    try:
        rram_metrics = _evaluate_rram_cimloop(
            params, data_args, training_args, hardware_args, cwd, hd_model
        )
    except Exception as exc:
        logger.error(f"[Job {job_id}] Path 3 Cimloop RRAM failed: {exc}")
        return {"status": "failed"}

    combined = _stitch_metrics(upgraded_asic, rram_metrics, execution_cycles=execution_cycles)

    return {
        "status": "success",
        "metrics": {
            "accuracy": accuracy,
            "energy_uj": combined["energy_uj"],
            "timing_us": combined["timing_us"],
            "area_mm2": combined["area_mm2"],
        },
    }
