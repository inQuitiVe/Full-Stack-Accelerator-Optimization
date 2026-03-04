"""
parse_vcs.py — VCS Gate-Level Simulation & PrimeTime PX report parser (Path 3).

Extracts:
  execution_cycles  : int    (cycle-accurate count from VCS simulation log)
  dynamic_power_mw  : float  (mW, from PtPX power report using SAIF activity)
  leakage_power_mw  : float  (mW)

Expected files in `reports_dir/`:
  vcs_simulation.log   — VCS stdout captured by Makefile (contains $display output)
  ptpx_power.rpt       — PrimeTime PX power report

Testbench $display conventions for LFSR-based testbenches:
  tb_core_timing.sv / tb_hd_top_timing.sv output:
    $display("  COMPUTE CYCLES      : %0d  (ENC_PRELOAD → oFIFO result)", N);

The primary regex pattern is:
    COMPUTE CYCLES\\s*:\\s*([0-9]+)

Legacy patterns ("Total cycles:", "SIM_CYCLES:") are retained as fallbacks for
backward compatibility with older testbenches.
"""

import re
from pathlib import Path
from typing import Any, Dict

from .parse_dc import _scale_power


# ── VCS Simulation Log Parser ─────────────────────────────────────────────────

def _parse_vcs_log(log_text: str) -> Dict[str, Any]:
    """
    Extract cycle count from the VCS simulation log.

    Primary pattern (LFSR testbenches: tb_core_timing.sv / tb_hd_top_timing.sv):
      "  COMPUTE CYCLES      : 12345  (ENC_PRELOAD → oFIFO result)"

    Legacy fallback patterns (backward compatibility with older testbenches):
      "Total cycles: 12345"
      "Execution cycles: 12345"
      "SIM_CYCLES: 12345"

    Returns:
        {"execution_cycles": int}
    """
    # ── Cycle Count ──────────────────────────────────────────────────────────
    # Ordered by priority: LFSR TB format first, then legacy formats.
    cycle_patterns = [
        # Primary: new LFSR-based testbenches (tb_core_timing.sv / tb_hd_top_timing.sv)
        re.compile(r"COMPUTE CYCLES\s*:\s*([0-9]+)", re.IGNORECASE),
        # Legacy fallbacks
        re.compile(r"Total cycles:\s*([0-9]+)", re.IGNORECASE),
        re.compile(r"Execution cycles:\s*([0-9]+)", re.IGNORECASE),
        re.compile(r"SIM_CYCLES:\s*([0-9]+)", re.IGNORECASE),
    ]
    cycles = None
    for pat in cycle_patterns:
        m = pat.search(log_text)
        if m:
            cycles = int(m.group(1))
            break

    if cycles is None:
        raise ValueError(
            "Could not find cycle count in VCS simulation log.\n"
            "Expected format from LFSR testbench: 'COMPUTE CYCLES      : <N>'\n"
            "Check that tb_core_timing.sv / tb_hd_top_timing.sv outputs this line via $display."
        )

    return {"execution_cycles": cycles}


# ── PrimeTime PX Power Report Parser ─────────────────────────────────────────

def _parse_ptpx_power(report_text: str) -> Dict[str, float]:
    """
    Extract dynamic and leakage power from PrimeTime PX report.
    Uses the same regex as parse_dc._parse_power (PtPX format is identical).

    Example lines:
      Total Dynamic Power    =    10.5423 mW
      Cell Leakage Power     =   324.1234 uW
    """
    dynamic_pattern = re.compile(
        r"Total Dynamic Power\s+=\s+([0-9.]+)\s+(\w+)", re.IGNORECASE
    )
    leakage_pattern = re.compile(
        r"Cell Leakage Power\s+=\s+([0-9.]+)\s+(\w+)", re.IGNORECASE
    )

    dynamic_match = dynamic_pattern.search(report_text)
    leakage_match = leakage_pattern.search(report_text)

    if not dynamic_match:
        raise ValueError(
            "Could not find 'Total Dynamic Power' in PtPX report.\n"
            "Check that pt_shell ran successfully and ptpx_power.rpt is valid."
        )

    dynamic_mw = _scale_power(float(dynamic_match.group(1)), dynamic_match.group(2))
    leakage_mw = (
        _scale_power(float(leakage_match.group(1)), leakage_match.group(2))
        if leakage_match
        else 0.0
    )

    return {
        "dynamic_power_mw": dynamic_mw,
        "leakage_power_mw": leakage_mw,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def parse_vcs_reports(reports_dir: str) -> Dict[str, Any]:
    """
    Parse VCS simulation log and PtPX power report to obtain cycle-accurate
    execution statistics and gate-level dynamic power.

    The LFSR-based testbenches (tb_core_timing.sv / tb_hd_top_timing.sv) output
    COMPUTE CYCLES for timing accuracy; they do NOT check functional correctness
    (hw_accuracy is not available from these testbenches). Functional accuracy
    is provided by Path 1 (PyTorch software model) and carried forward.

    Returns:
        {
          "execution_cycles":  int,    # cycle count from LFSR testbench
          "dynamic_power_mw":  float,  # mW (from PtPX with SAIF toggle activity)
          "leakage_power_mw":  float,  # mW
        }

    Raises:
        FileNotFoundError: if a required report file is missing.
        ValueError:        if a required field cannot be extracted.
    """
    reports_path = Path(reports_dir)
    vcs_log  = reports_path / "vcs_simulation.log"
    ptpx_rpt = reports_path / "ptpx_power.rpt"

    for f in [vcs_log, ptpx_rpt]:
        if not f.exists():
            raise FileNotFoundError(
                "Expected report not found: %s\n"
                "Ensure 'make sim' and 'make power' completed successfully." % f
            )

    sim_metrics   = _parse_vcs_log(vcs_log.read_text(encoding="utf-8", errors="replace"))
    power_metrics = _parse_ptpx_power(ptpx_rpt.read_text(encoding="utf-8", errors="replace"))

    return {
        "execution_cycles":  sim_metrics["execution_cycles"],
        **power_metrics,
    }
