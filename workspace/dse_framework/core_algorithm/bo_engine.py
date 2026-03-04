"""
bo_engine.py — Multi-fidelity Bayesian Optimization Engine.

Orchestrates the full DSE loop:
  1. Ax/BoTorch generates the next parameter configuration to evaluate.
  2. Path 1 (software) is evaluated locally.
     - Gate 1: accuracy below threshold → log_trial_failure(), skip.
  3. (Optional) Path 2 (hardware synthesis) evaluated via EDA Server.
     - Gate 2 (handled server-side, result status = "timing_violated") →
       log_trial_failure().
  4. Raw metrics are normalised via DynamicNormalizer and reported to Ax.
  5. Hypervolume is tracked after every iteration.

Key design decisions (from architecture discussions):
  - kron parameter: REMOVED. No branch logic for Kronecker encoders.
  - cnn flag: treated as a fixed environment constant (set in config, not BO).
  - Failed trials: use ax_client.log_trial_failure(), never inject penalty values.
  - Normalisation: DynamicNormalizer with running max as the base.
  - Objective: maximise Hypervolume (multi-objective qNEHVI).
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from typing import Any, Dict, List, Optional, Tuple

import torch
from ax.modelbridge import Models
from ax.modelbridge.generation_strategy import GenerationStep, GenerationStrategy
from ax.modelbridge.modelbridge_utils import observed_hypervolume
from ax.service.ax_client import AxClient, ObjectiveProperties
from omegaconf import DictConfig
from tqdm import tqdm

from .normalizer import DynamicNormalizer

logger = logging.getLogger(__name__)

# Logger for sim/Evaluator — set to WARNING to suppress "image size", "num_classes", etc.
_sim_logger = logging.getLogger("dse_framework.sim")
_sim_logger.setLevel(logging.WARNING)


def _format_trial_params(param: Dict[str, Any], params_prop: List[Dict[str, Any]]) -> str:
    """Format trial params: show only choice (tunable) params in compact form."""
    choice_names = {p["name"] for p in params_prop if p.get("type") == "choice"}
    parts = [f"{k}={v}" for k, v in sorted(param.items()) if k in choice_names]
    return ", ".join(parts) if parts else str(param)

# ── Metric name mapping ───────────────────────────────────────────────────────
# The Ax experiment uses these normalised metric names.
AX_ACCURACY = "accuracy"
AX_ENERGY = "energy_uj_norm"
AX_TIMING = "timing_us_norm"
AX_AREA = "area_mm2_norm"


# ── Ax experiment setup ───────────────────────────────────────────────────────

def _build_ax_client(
    params_prop: List[Dict[str, Any]],
    num_sobol_trials: int,
    acqf_name: str,
) -> AxClient:
    """
    Construct an AxClient with a SOBOL → BOTORCH_MODULAR GenerationStrategy.
    Objectives are set to maximise Hypervolume across all four metrics.
    """
    from ax.modelbridge.registry import Models as _Models

    try:
        from dse_framework.flow.acqfManagerFactory import acqf_factory
        botorch_acqf_class = acqf_factory(acqf_name)
        model_kwargs = {
            "torch_device": "cpu",
            "botorch_acqf_class": botorch_acqf_class,
        }
    except Exception:
        # Fall back to default qNEHVI if custom factory or module is unavailable
        model_kwargs = {"torch_device": "cpu"}

    cli = AxClient(
        verbose_logging=False,
        generation_strategy=GenerationStrategy(
            [
                GenerationStep(_Models.SOBOL, num_trials=num_sobol_trials),
                GenerationStep(
                    _Models.BOTORCH_MODULAR,
                    num_trials=-1,
                    model_kwargs=model_kwargs,
                ),
            ]
        )
    )

    # Suppress Ax ChoiceParameter warnings: explicitly set is_ordered
    # (sort_values is not accepted by parameter_from_json; filter the warning instead)
    for p in params_prop:
        if p.get("type") == "choice":
            p.setdefault("is_ordered", p.get("value_type") == "int")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*sort_values.*", module="ax.core.parameter")
        # All objectives with their Ax ObjectiveProperties
        cli.create_experiment(
            parameters=params_prop,
            objectives={
                AX_ACCURACY: ObjectiveProperties(minimize=False, threshold=0.0),
                AX_ENERGY:   ObjectiveProperties(minimize=True,  threshold=1.0),
                AX_TIMING:   ObjectiveProperties(minimize=True,  threshold=1.0),
                AX_AREA:     ObjectiveProperties(minimize=True,  threshold=1.0),
            },
        )
    return cli


# ── Metric conversion helpers ─────────────────────────────────────────────────

def _raw_to_ax_dict(normed: Dict[str, float]) -> Dict[str, Tuple[float, float]]:
    """Convert a normalised metrics dict to Ax's (mean, sem) tuple format."""
    return {
        AX_ACCURACY: (normed.get("accuracy", 0.0), 0.0),
        AX_ENERGY:   (normed.get("energy_uj", 1.0),  0.0),
        AX_TIMING:   (normed.get("timing_us", 1.0),  0.0),
        AX_AREA:     (normed.get("area_mm2", 1.0),   0.0),
    }


# ── Gate checks ───────────────────────────────────────────────────────────────

def _passes_gate1(accuracy: float, constraints: Dict[str, float]) -> bool:
    """Gate 1: accuracy must meet the minimum threshold."""
    return accuracy >= constraints.get("accuracy", 0.0)


# ── Main BO loop ──────────────────────────────────────────────────────────────

def run_bo(
    args: DictConfig,
    data_args: Dict[str, Any],
    training_args: Dict[str, Any],
    hardware_args: Dict[str, Any],
    cwd: str,
    use_path2: bool = False,
    use_path3: bool = False,
    top_module: str = "core",
    eda_host: str = "EDA_SERVER_IP",
    eda_port: int = 5000,
) -> Dict[str, List]:
    """
    Execute the full multi-fidelity BO loop.

    Args:
        args:           Hydra DictConfig (contains optimization, params_prop sections).
        data_args:      Dataset config dict.
        training_args:  Training config dict.
        hardware_args:  Hardware flags dict (cnn, noise, temperature, etc.).
        cwd:            HDnn-PIM-Opt working directory (for Evaluator).
        use_path2:      If True, runs Path 2 EDA synthesis for configs passing Gate 1.
        use_path3:      If True, runs Path 3 gate-level simulation (VCS + PtPX) after
                        Path 2 succeeds. No hex data transfer required — the testbench
                        uses LFSR-generated patterns. Requires use_path2=True.
        top_module:     Synthesis and simulation scope: 'core' (full wrapper) or
                        'hd_top' (HD core only). Controls TCL elaboration and VCS TB.
        eda_host:       EDA Server IP/hostname (used only when use_path2=True).
        eda_port:       EDA Server port.

    Returns:
        A history dict with lists of observed values:
        {"accuracy", "energy_uj", "timing_us", "area_mm2", "hv", "param"}
    """
    from sim.flow.utils import process_params_prop, set_seed
    from dse_framework.evaluators.path1_software import evaluate_path1
    from dse_framework.evaluators.path2_hardware import evaluate_path2, evaluate_path3

    set_seed(args["seed"])

    opt_cfg = args["optimization"]
    constraints: Dict[str, float] = opt_cfg.get("constraints", {})
    num_sobol: int = int(opt_cfg["num_trials"])
    num_epochs: int = int(opt_cfg["num_epochs"])
    acqf_name: str = opt_cfg["acqf"]

    # Build normalizer with design-space upper bounds as initial base
    normalizer = DynamicNormalizer(
        upper_bound_constraints={
            "energy_uj": 5000.0,   # Initial fallback base (uJ)
            "timing_us": 500.0,    # Initial fallback base (us)
            "area_mm2": 5.0,       # Initial fallback base (mm^2)
        }
    )

    params_prop = process_params_prop(args["params_prop"])
    cli = _build_ax_client(params_prop, num_sobol, acqf_name)

    history: Dict[str, List] = {
        "accuracy": [], "energy_uj": [], "timing_us": [],
        "area_mm2": [], "hv": [], "param": [],
    }

    for iteration in tqdm(range(num_epochs), desc="BO Iterations"):
        # ── Generate next candidate ──────────────────────────────────────────
        if iteration < num_sobol:
            model = Models.SOBOL(
                experiment=cli.experiment,
                data=cli.experiment.fetch_data(),
            )
        else:
            model = Models.BOTORCH_MODULAR(
                experiment=cli.experiment,
                data=cli.experiment.fetch_data(),
                torch_device=torch.device("cpu"),
            )

        gen_run = model.gen(1)
        param = gen_run.arms[0].parameters
        _, trial_idx = cli.attach_trial(param)
        logger.info(f"[Trial {trial_idx}] {_format_trial_params(param, params_prop)}")

        # ── Path 1: Software Simulation ──────────────────────────────────────
        try:
            p1_result = evaluate_path1(
                param, data_args, training_args, hardware_args, cwd,
                logger_override=logger,
                evaluator_logger=_sim_logger,
            )
        except Exception as exc:
            logger.error(f"[Trial {trial_idx}] Path 1 failed: {exc}")
            cli.log_trial_failure(trial_idx)
            continue

        accuracy = p1_result["accuracy"]

        # Gate 1 check
        if not _passes_gate1(accuracy, constraints):
            logger.info(
                f"[Trial {trial_idx}] GATE 1 FAILED: accuracy={accuracy:.4f} "
                f"< threshold={constraints.get('accuracy', 0.0):.4f}"
            )
            cli.log_trial_failure(trial_idx)
            continue

        # ── Path 2 (optional): Hardware Synthesis ────────────────────────────
        if use_path2:
            p2_result = evaluate_path2(
                param, trial_idx, accuracy,
                data_args, training_args, hardware_args, cwd,
                hd_model=p1_result.get("hd_model"),
                top_module=top_module,
                eda_host=eda_host, eda_port=eda_port,
            )
            if p2_result["status"] != "success":
                logger.warning(f"[Trial {trial_idx}] GATE 2 FAILED: Path 2 returned {p2_result['status']}.")
                cli.log_trial_failure(trial_idx)
                continue
            raw_metrics = p2_result["metrics"]

            # ── Path 3 (optional): Gate-Level Simulation ─────────────────────
            # Gate 2 has already passed (Path 2 succeeded). Run VCS + PtPX to
            # get cycle-accurate timing and precise dynamic power.
            if use_path3:
                p3_result = evaluate_path3(
                    param, trial_idx, accuracy,
                    path2_asic_metrics=p2_result.get("_asic_metrics", {}),
                    data_args=data_args,
                    training_args=training_args,
                    hardware_args=hardware_args,
                    cwd=cwd,
                    hd_model=p1_result.get("hd_model"),
                    top_module=top_module,
                    eda_host=eda_host,
                    eda_port=eda_port,
                )
                if p3_result.get("status") == "success":
                    raw_metrics = p3_result["metrics"]
                    logger.info(f"[Trial {trial_idx}] Path 3 success — upgraded to VCS+PtPX metrics.")
                else:
                    logger.warning(
                        f"[Trial {trial_idx}] Path 3 failed — keeping Path 2 metrics as fallback."
                    )
        else:
            raw_metrics = p1_result  # Use Path 1 metrics directly

        # ── Normalise & report to Ax ─────────────────────────────────────────
        normalizer.update(raw_metrics)
        normed = normalizer.normalize(raw_metrics)
        ax_data = _raw_to_ax_dict(normed)
        cli.complete_trial(trial_idx, raw_data=ax_data)

        # ── Track history ────────────────────────────────────────────────────
        history["accuracy"].append(raw_metrics["accuracy"])
        history["energy_uj"].append(raw_metrics["energy_uj"])
        history["timing_us"].append(raw_metrics["timing_us"])
        history["area_mm2"].append(raw_metrics["area_mm2"])
        history["param"].append(param)

        # ── Hypervolume ──────────────────────────────────────────────────────
        try:
            hv_model = Models.BOTORCH_MODULAR(
                experiment=cli.experiment,
                data=cli.experiment.fetch_data(),
            )
            hv = observed_hypervolume(hv_model)
        except Exception:
            hv = 0.0
        history["hv"].append(hv)

        logger.info(
            f"[Iter {iteration}] acc={raw_metrics['accuracy']:.4f}, "
            f"energy={raw_metrics['energy_uj']:.2f}uJ, "
            f"timing={raw_metrics['timing_us']:.2f}us, "
            f"area={raw_metrics['area_mm2']:.4f}mm^2, HV={hv:.4f}"
        )

    return history
