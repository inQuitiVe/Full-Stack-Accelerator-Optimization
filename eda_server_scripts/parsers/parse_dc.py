"""
parse_dc.py — Design Compiler report parser.

Reads the standard DC text report files and extracts PPA metrics using
regex patterns. All raw values are auto-scaled to canonical units before
being returned.

Canonical output units:
  area_um2            : float  (um^2)
  timing_slack_ns     : float  (ns, positive = met, negative = violated)
  clock_period_ns     : float  (ns, the constrained clock period)
  dynamic_power_mw    : float  (mW)
  leakage_power_mw    : float  (mW)

Expected report files in `reports_dir/`:
  report_area.rpt
  report_timing.rpt
  report_power.rpt
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

# ── Unit scaling helpers ──────────────────────────────────────────────────────

_POWER_SCALE: Dict[str, float] = {
    "pw": 1e-9,   # picowatts → mW
    "nw": 1e-6,   # nanowatts → mW
    "uw": 1e-3,   # microwatts → mW
    "mw": 1.0,    # milliwatts (already mW)
    "w":  1e3,    # watts → mW
}


def _scale_power(value: float, unit: str) -> float:
    """Convert a power value from the reported unit to mW."""
    key = unit.lower().rstrip("s")  # normalise plural, e.g. "mWs" → "mw"
    factor = _POWER_SCALE.get(key)
    if factor is None:
        raise ValueError(f"Unknown power unit: {unit!r}")
    return value * factor


# ── Individual report parsers ─────────────────────────────────────────────────

def _parse_area(report_text: str) -> float:
    """
    Extract total cell area in um^2.
    DC reports area in library units (typically um^2 for modern PDKs).

    Example line:
      Total cell area:             15234.567890
    """
    pattern = re.compile(r"Total cell area:\s+([0-9.]+)")
    match = pattern.search(report_text)
    if not match:
        raise ValueError("Could not find 'Total cell area' in area report.")
    return float(match.group(1))


def _parse_timing(report_text: str) -> Dict[str, float]:
    """
    Extract timing slack and clock period.

    Example lines:
      slack (MET)                          0.23
      slack (VIOLATED)                    -1.05

    Clock period from constraint line:
      clock clk (rise edge)                5.0000    5.0000
      OR from:
      clock period: 5.000000ns
    """
    # Slack
    slack_pattern = re.compile(
        r"slack\s+\((MET|VIOLATED)\)\s+([-0-9.]+)", re.IGNORECASE
    )
    slack_match = slack_pattern.search(report_text)
    if not slack_match:
        raise ValueError("Could not find timing slack in timing report.")
    status = slack_match.group(1).upper()
    slack_ns = float(slack_match.group(2))
    if status == "VIOLATED":
        slack_ns = -abs(slack_ns)

    # Clock period — try to extract from the "clock ... (rise edge)" line
    period_ns: float = 0.0
    period_pattern = re.compile(
        r"clock\s+\S+\s+\(rise edge\)\s+([0-9.]+)\s+([0-9.]+)"
    )
    period_match = period_pattern.search(report_text)
    if period_match:
        period_ns = float(period_match.group(1))

    return {"timing_slack_ns": slack_ns, "clock_period_ns": period_ns}


def _parse_power(report_text: str) -> Dict[str, float]:
    """
    Extract dynamic and leakage power with automatic unit conversion to mW.

    Example lines:
      Total Dynamic Power    =     8.2345 mW
      Cell Leakage Power     =   312.4567 uW
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
        raise ValueError("Could not find 'Total Dynamic Power' in power report.")
    if not leakage_match:
        raise ValueError("Could not find 'Cell Leakage Power' in power report.")

    dynamic_mw = _scale_power(float(dynamic_match.group(1)), dynamic_match.group(2))
    leakage_mw = _scale_power(float(leakage_match.group(1)), leakage_match.group(2))

    return {
        "dynamic_power_mw": dynamic_mw,
        "leakage_power_mw": leakage_mw,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def parse_dc_reports(reports_dir: str) -> Dict[str, Any]:
    """
    Parse all three DC report files in `reports_dir` and return a unified
    metrics dictionary in canonical units.

    Returns:
        {
          "area_um2":          float,
          "timing_slack_ns":   float,   # negative = violated
          "clock_period_ns":   float,
          "dynamic_power_mw":  float,
          "leakage_power_mw":  float,
        }

    Raises:
        FileNotFoundError  if a required report file is missing.
        ValueError         if a required field cannot be extracted from the report.
    """
    reports_path = Path(reports_dir)

    area_rpt = reports_path / "report_area.rpt"
    timing_rpt = reports_path / "report_timing.rpt"
    power_rpt = reports_path / "report_power.rpt"

    for rpt in [area_rpt, timing_rpt, power_rpt]:
        if not rpt.exists():
            raise FileNotFoundError(f"Expected DC report not found: {rpt}")

    area_um2 = _parse_area(area_rpt.read_text(encoding="utf-8", errors="replace"))
    timing_metrics = _parse_timing(timing_rpt.read_text(encoding="utf-8", errors="replace"))
    power_metrics = _parse_power(power_rpt.read_text(encoding="utf-8", errors="replace"))

    return {
        "area_um2": area_um2,
        **timing_metrics,
        **power_metrics,
    }
