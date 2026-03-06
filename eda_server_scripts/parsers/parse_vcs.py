"""
parse_vcs.py — VCS Gate-Level Simulation report parser (Path 3).

Extracts:
  execution_cycles  : int    (cycle-accurate count from VCS simulation log)
  total_sim_time_ps : int    (optional)
  clock_period_ns   : float  (optional)
  equivalent_latency_us : float (optional)

Power analysis (PtPX) is removed; Path 3 uses DC report_power for power metrics.

Expected files in `reports_dir/`:
  vcs_simulation.log   — VCS stdout captured by Makefile (contains $display output)

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

    In addition to the primary cycle count, we also parse:
      - "Total sim time      = 3013234000"
      - "Clock period        = 4.0 ns"
      - "Equivalent latency  = 3013.168 us"
    when present in the log, so that Path 3 can report both cycle-based
    and wall-clock based metrics.
    Returns:
        {
          "execution_cycles":      int,
          "total_sim_time_ps":     int   | None,
          "clock_period_ns":       float | None,
          "equivalent_latency_us": float | None,
        }
    """
    # ── Cycle Count ──────────────────────────────────────────────────────────
    # Ordered by priority: LFSR TB format first, then legacy formats.
    cycle_patterns = [
        # Primary: new LFSR-based testbenches (tb_core_timing.sv / tb_hd_top_timing.sv)
        re.compile(r"COMPUTE CYCLES\s*:\s*([0-9]+)", re.IGNORECASE),
        # Legacy fallbacks
        # Accept both ':' and '=' as separators, e.g.
        #   "Total cycles: 12345"
        #   "Total cycles        = 12345"
        re.compile(r"Total cycles\s*[:=]\s*([0-9]+)", re.IGNORECASE),
        re.compile(r"Execution cycles\s*[:=]\s*([0-9]+)", re.IGNORECASE),
        re.compile(r"SIM_CYCLES\s*[:=]\s*([0-9]+)", re.IGNORECASE),
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
            "or a legacy line like 'Total cycles = <N>'.\n"
            "Check that tb_core_timing.sv / tb_hd_top_timing.sv outputs this line via $display."
        )

    # ── Optional wall-clock style metrics ─────────────────────────────────────
    # Example lines:
    #   Total sim time      = 3013234000
    #   Clock period        = 4.0 ns
    #   Equivalent latency  = 3013.168 us
    total_time_re = re.compile(r"Total sim time\s*=\s*([0-9]+)", re.IGNORECASE)
    clk_period_re = re.compile(
        r"Clock period\s*=\s*([0-9]*\.?[0-9]+)\s*ns", re.IGNORECASE
    )
    equiv_lat_re = re.compile(
        r"Equivalent latency\s*=\s*([0-9]*\.?[0-9]+)\s*us", re.IGNORECASE
    )

    total_time_ps = None
    clock_period_ns = None
    equivalent_latency_us = None

    m_time = total_time_re.search(log_text)
    if m_time:
        try:
            total_time_ps = int(m_time.group(1))
        except ValueError:
            total_time_ps = None

    m_clk = clk_period_re.search(log_text)
    if m_clk:
        try:
            clock_period_ns = float(m_clk.group(1))
        except ValueError:
            clock_period_ns = None

    m_lat = equiv_lat_re.search(log_text)
    if m_lat:
        try:
            equivalent_latency_us = float(m_lat.group(1))
        except ValueError:
            equivalent_latency_us = None

    return {
        "execution_cycles": cycles,
        "total_sim_time_ps": total_time_ps,
        "clock_period_ns": clock_period_ns,
        "equivalent_latency_us": equivalent_latency_us,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def parse_vcs_reports(reports_dir: str) -> Dict[str, Any]:
    """
    Parse VCS simulation log. Power analysis (PtPX) is removed; Path 3 uses
    DC report_power for power metrics.

    Returns:
        {
          "execution_cycles":      int,
          "total_sim_time_ps":     int   | None,
          "clock_period_ns":       float | None,
          "equivalent_latency_us": float | None,
        }

    Raises:
        FileNotFoundError: if vcs_simulation.log is missing.
        ValueError:        if cycle count cannot be extracted.
    """
    reports_path = Path(reports_dir)
    vcs_log = reports_path / "vcs_simulation.log"

    if not vcs_log.exists():
        raise FileNotFoundError(
            "Expected report not found: %s\n"
            "Ensure 'make sim' completed successfully." % vcs_log
        )

    sim_metrics = _parse_vcs_log(vcs_log.read_text(encoding="utf-8", errors="replace"))

    return {
        "execution_cycles":       sim_metrics["execution_cycles"],
        "total_sim_time_ps":      sim_metrics.get("total_sim_time_ps"),
        "clock_period_ns":        sim_metrics.get("clock_period_ns"),
        "equivalent_latency_us":  sim_metrics.get("equivalent_latency_us"),
    }
