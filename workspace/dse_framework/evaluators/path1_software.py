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

Additionally exposes dump_hex_data() for Path 3 (Gate-Level Simulation).
This function extracts trained model weights and test vectors from the HD model
and serialises them to HEX files for the VCS Testbench.

The caller (bo_engine.py) normalises these raw values via normalizer.py before
passing them to the Ax client.
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

# Ensure the workspace/HDnn-PIM-Opt directory is on sys.path so we can import sim/
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
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
    evaluator_logger=None,
) -> Dict[str, float]:
    """
    Run the full Path 1 software simulation for a single parameter configuration.

    Args:
        params:         BO parameter dict (hd_dim, reram_size, cnn_x_dim_1, etc.)
        data_args:      Dataset config (dataset name, batch sizes, etc.)
        training_args:  Training hyperparameters (epochs, lr, devices, etc.)
        hardware_args:  Hardware config flags (type="cimloop", cnn=True, etc.)
        cwd:            Absolute path to the HDnn-PIM-Opt working directory.
        logger_override: Optional logger for [Path1] result output; defaults to module logger.
        evaluator_logger: Optional logger for sim/Evaluator internals (e.g. image size).
                         If WARNING, suppresses verbose sim logs.

    Returns:
        Canonical metrics dict with raw (un-normalised) values.

    Raises:
        RuntimeError:   If the simulation fails or returns unexpected shapes.
    """
    _log = logger_override or logger
    _eval_log = evaluator_logger if evaluator_logger is not None else _log

    try:
        from sim.evaluator import Evaluator
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import sim.evaluator. Ensure HDnn-PIM-Opt is on sys.path.\n"
            f"Attempted path: {_HDNN_ROOT}\nOriginal error: {exc}"
        ) from exc

    # ── 中繼檢查：確保 frequency 有傳入且不低於 200 MHz ─────────────────────
    _FREQ_MIN_HZ = int(2e8)  # 200 MHz
    freq = int(params.get("frequency", 0))
    if freq < _FREQ_MIN_HZ:
        _log.warning(
            f"[Path1] frequency={freq} Hz ({freq/1e6:.0f} MHz) < {_FREQ_MIN_HZ/1e6:.0f} MHz; "
            f"clamping to {_FREQ_MIN_HZ} Hz for timeloop/cimloop."
        )
        params = dict(params)
        params["frequency"] = _FREQ_MIN_HZ
    _log.info(f"[Path1] Passing params to Evaluator (frequency={params.get('frequency')} Hz = {params.get('frequency', 0)/1e6:.0f} MHz)")

    evaluator = Evaluator(data_args, training_args, hardware_args, cwd, _eval_log)

    # The Evaluator.evaluate() API expects a list (one item per GPU worker)
    results = evaluator.evaluate([params], _eval_log)

    if not results:
        raise RuntimeError("Evaluator returned empty results list.")

    result = results[0]
    # result format: {"accuracy": (value, sem), "power": (value, sem),
    #                 "performance": (value, sem), "area": (value, sem)}
    # Note: sim/metrics/cimloop uses _normalize(x) = x/BASE (BASE=3000) for power,
    #       performance, area. We must denormalize to get raw units (uJ, us, mm²).
    _BASE = 3000.0

    accuracy: float = result["accuracy"][0]
    energy_uj: float = result["power"][0] * _BASE
    timing_us: float = result["performance"][0] * _BASE
    area_mm2: float = result["area"][0] * _BASE

    _log.info(
        f"[Path1] accuracy={accuracy:.4f}, energy={energy_uj:.3f}uJ, "
        f"timing={timing_us:.3f}us, area={area_mm2:.4f}mm^2"
    )

    # Cache hd_model for Path 2 RRAM Cimloop (same as dump_hex_data)
    hd_model = None
    try:
        accuracy_eval = evaluator.metric_managers[0].accuracy_evaluator
        hd_factory = accuracy_eval.hd_factory
        hd_model = hd_factory.create_neurosim()
    except (AttributeError, IndexError, TypeError) as e:
        _log.debug("Path1: could not cache hd_model for Path 2: %s", e)

    return {
        "accuracy": accuracy,
        "energy_uj": energy_uj,
        "timing_us": timing_us,
        "area_mm2": area_mm2,
        "hd_model": hd_model,
    }


# ── Path 3 Hex Data Dumping ───────────────────────────────────────────────────

def _tensor_to_hex_lines(tensor: torch.Tensor, quantize_bits: int) -> list[str]:
    """
    Quantize a float tensor to `quantize_bits`-bit unsigned integers and
    return one hex string per row (for $readmemh compatibility).

    The tensor is flattened to 2D: (num_vectors, vector_length).
    Each element is clamped to [0, 2^bits - 1] and formatted as a hex integer
    with enough digits to represent the bit width (e.g. 8-bit → 2 hex chars).
    """
    max_val = (1 << quantize_bits) - 1
    hex_digits = (quantize_bits + 3) // 4

    flat = tensor.float()
    t_min, t_max = flat.min(), flat.max()
    if t_max > t_min:
        flat = (flat - t_min) / (t_max - t_min) * max_val
    else:
        flat = torch.zeros_like(flat)
    flat = flat.clamp(0, max_val).long()

    if flat.dim() == 1:
        flat = flat.unsqueeze(0)

    lines: list[str] = []
    for row in flat:
        parts = [f"{v.item():0{hex_digits}x}" for v in row]
        lines.append("".join(parts))
    return lines


def dump_hex_data(
    evaluator,
    test_loader,
    num_vectors: int = 50,
    quantize_bits: int = 8,
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """
    Extract inputs, golden labels, and HDnn weight hypervectors from the trained
    model and serialise them to HEX format for the VCS Testbench.

    Args:
        evaluator:      The `sim.evaluator.Evaluator` instance (after evaluate() call).
        test_loader:    PyTorch DataLoader for the test dataset.
        num_vectors:    Number of test samples to dump (default 50).
        quantize_bits:  Fixed-point bit width for quantization (default 8).
        output_dir:     If provided, also write three files:
                          <output_dir>/inputs.hex
                          <output_dir>/labels.hex
                          <output_dir>/weights.hex
                        If None, files are NOT written to disk.

    Returns:
        A dict with keys "inputs", "labels", "weights", each containing
        the file content as a plain-text string (newline-separated hex lines).
        This dict can be embedded directly in the Path 3 JSON payload.

    Raises:
        RuntimeError: If the evaluator has not been called yet (no hd_factory).
    """
    try:
        accuracy_eval = evaluator.metric_managers[0].accuracy_evaluator
        hd_factory = accuracy_eval.hd_factory
    except AttributeError as exc:
        raise RuntimeError(
            "dump_hex_data requires evaluate() to have been called first. "
            f"Original error: {exc}"
        ) from exc

    hd_model = hd_factory.create_neurosim()
    device = next(hd_model.parameters()).device

    # ── 1. Collect `num_vectors` test samples ───────────────────────────────
    inputs_list: list[torch.Tensor] = []
    labels_list: list[int] = []
    collected = 0
    for batch_x, batch_y in test_loader:
        for x, y in zip(batch_x, batch_y):
            inputs_list.append(x.flatten())
            labels_list.append(int(y.item()))
            collected += 1
            if collected >= num_vectors:
                break
        if collected >= num_vectors:
            break

    if not inputs_list:
        raise RuntimeError("test_loader is empty — cannot dump hex data.")

    inputs_tensor = torch.stack(inputs_list)          # (num_vectors, input_dim)
    labels_tensor = torch.tensor(labels_list).long()  # (num_vectors,)

    # ── 2. Quantize and serialise inputs ────────────────────────────────────
    input_lines = _tensor_to_hex_lines(inputs_tensor, quantize_bits)

    # ── 3. Serialise labels (1 hex byte per label) ──────────────────────────
    label_lines = [f"{v:02x}" for v in labels_list]

    # ── 4. Extract and serialise class hypervectors (weights) ───────────────
    with torch.no_grad():
        class_hvs = hd_model.hd_inference.class_hvs  # (num_classes, hd_dim)
    weight_lines = _tensor_to_hex_lines(class_hvs.cpu(), quantize_bits)

    inputs_text = "\n".join(input_lines) + "\n"
    labels_text = "\n".join(label_lines) + "\n"
    weights_text = "\n".join(weight_lines) + "\n"

    logger.info(
        f"[dump_hex_data] Dumped {len(input_lines)} input vectors, "
        f"{len(label_lines)} labels, {len(weight_lines)} class hypervectors "
        f"({quantize_bits}-bit quantization)."
    )

    # ── 5. Optionally write to disk ─────────────────────────────────────────
    if output_dir is not None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "inputs.hex").write_text(inputs_text, encoding="utf-8")
        (out_path / "labels.hex").write_text(labels_text, encoding="utf-8")
        (out_path / "weights.hex").write_text(weights_text, encoding="utf-8")
        logger.info(f"[dump_hex_data] Files written to {out_path}")

    return {
        "inputs": inputs_text,
        "labels": labels_text,
        "weights": weights_text,
    }
