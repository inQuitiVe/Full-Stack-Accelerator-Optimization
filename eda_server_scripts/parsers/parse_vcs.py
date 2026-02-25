"""
parse_vcs.py — VCS Gate-Level Simulation & PrimeTime PX report parser (Path 3).

Extracts:
  execution_cycles  : int    (cycle-accurate count from VCS simulation log)
  dynamic_power_mw  : float  (mW, from PtPX power report using SAIF activity)

Expected files in `reports_dir/`:
  vcs_simulation.log       — VCS stdout/stderr, contains cycle count
  ptpx_power.rpt           — PrimeTime PX power report
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from .parse_dc import _scale_power


# ── VCS Simulation Log Parser ─────────────────────────────────────────────────

def _parse_vcs_cycles(log_text: str) -> int:
    """
    Extract cycle count from VCS simulation log.

    Expected log pattern (customise to your testbench's $display format):
      [PASS] Simulation finished. Total cycles: 12345
      OR:
      SIM_CYCLES: 12345
    """
    patterns = [
        re.compile(r"Total cycles:\s+([0-9]+)", re.IGNORECASE),
        re.compile(r"SIM_CYCLES:\s*([0-9]+)", re.IGNORECASE),
        re.compile(r"Execution cycles:\s+([0-9]+)", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(log_text)
        if match:
            return int(match.group(1))

    raise ValueError(
        "Could not find cycle count in VCS simulation log. "
        "Ensure testbench prints 'Total cycles: <N>' or 'SIM_CYCLES: <N>'."
    )


# ── PrimeTime PX Power Report Parser ─────────────────────────────────────────

def _parse_ptpx_power(report_text: str) -> Dict[str, float]:
    """
    Extract dynamic power from PrimeTime PX report.

    PtPX report format is similar to DC power reports:
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
        raise ValueError("Could not find 'Total Dynamic Power' in PtPX report.")

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
    Parse VCS + PtPX reports to obtain cycle-accurate execution count and
    gate-level dynamic power.

    Returns:
        {
          "execution_cycles":  int,
          "dynamic_power_mw":  float,
          "leakage_power_mw":  float,
        }
    """
    reports_path = Path(reports_dir)
    vcs_log = reports_path / "vcs_simulation.log"
    ptpx_rpt = reports_path / "ptpx_power.rpt"

    for f in [vcs_log, ptpx_rpt]:
        if not f.exists():
            raise FileNotFoundError(f"Expected VCS/PtPX report not found: {f}")

    cycles = _parse_vcs_cycles(vcs_log.read_text(encoding="utf-8", errors="replace"))
    power_metrics = _parse_ptpx_power(ptpx_rpt.read_text(encoding="utf-8", errors="replace"))

    return {"execution_cycles": cycles, **power_metrics}
