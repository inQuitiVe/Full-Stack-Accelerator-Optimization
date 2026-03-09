# -*- coding: utf-8 -*-
"""
json_to_svh.py — Server-side parameter translation script.

Reads a JSON parameter dictionary (from stdin or function call) and:
  1. Applies the software-to-RTL mathematical mapping defined in README Section 2.2.
  2. Writes `../fsl-hd/verilog/include/config_macros.svh` with `define macros.
  3. Patches `../fsl-hd/tcl/synth_dse.tcl` (from dc/synth_template_*.tcl) with the
     correct `create_clock` period derived from the `frequency` parameter.
  4. Injects TOP_MODULE_PLACEHOLDER with the top_module value ("core" or "hd_top").
  5. Injects Synthesis Optimization DSE options (syn_map_effort, syn_opt_effort)
     and the synthesis strategy TCL block from granular flags (enable_clock_gating,
     enable_retime, compile_* options, etc.).
  6. Writes `../fsl-hd/verilog/tb/tb_macros.svh` with Testbench constants for Path 3.
     (LFSR-based testbenches — no hex file paths needed; tb_macros only carries clock period)

Server deployment layout assumed:
  ~/workspace/
    ├── fsl-hd/                          ← existing hardware project
    │   ├── verilog/include/             ← config_macros.svh written here
    │   ├── tcl/                         ← synth_dse.tcl written here
    │   └── verilog/tb/                  ← tb_macros.svh written here
    └── full-stack-opt/                  ← this script lives here
        └── dc/synth_template_slow.tcl   ← TCL template (slow mode)
        └── dc/synth_template_fast.tcl   ← TCL template (fast mode)

Usage (called by eda_server.py via subprocess):
  echo '<json_params>' | python json_to_svh.py

The JSON is read from stdin. Exit code 0 = success, non-zero = failure.
"""

import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Union

# ── File paths (relative to this script's location on the EDA server) ──────
# This script lives in full-stack-opt/; hardware project is in the sibling fsl-hd/.
SCRIPT_DIR  = Path(__file__).parent            # ~/workspace/full-stack-opt/
FSL_HD_DIR  = SCRIPT_DIR.parent / "fsl-hd"    # ~/workspace/fsl-hd/

SVH_OUTPUT        = FSL_HD_DIR / "verilog" / "include" / "config_macros.svh"
# Slow template (synth_template_slow.tcl) — full PatterNet/SRAMs synthesized from RTL
# Fast template (synth_template_fast.tcl) — PatterNet/SRAMs treated as black boxes
TCL_TEMPLATE_SLOW = SCRIPT_DIR / "dc" / "synth_template_slow.tcl"
TCL_TEMPLATE_FAST = SCRIPT_DIR / "dc" / "synth_template_fast.tcl"
TCL_OUTPUT        = SCRIPT_DIR / "dc" / "synth_dse.tcl"
# tb_macros.svh lives alongside the LFSR testbenches in fsl-hd/verilog/tb/
TB_MACROS_OUTPUT  = FSL_HD_DIR / "verilog" / "tb" / "tb_macros.svh"


# ── Hardware / RTL invariants (mirrored from param.vh) ───────────────────────
#
# 這些常數必須與 RTL 中的 param.vh 保持一致；用來在 Python 端做「事前 sanity check」，
# 避免 DSE/BO 傳入的參數組合產生結構上不合法的 RTL（例如負的位寬、SIPO 長度不整除等）。

# Search / classification 固定架構
CLASS_LABEL_WIDTH: int = 7      # param.vh: CLASS_LABEL_WIDTH
HAMMING_DIST_WIDTH: int = 13    # param.vh: HAMMING_DIST_WIDTH

# Training path 固定架構
TRAINING_DATA_NUM: int = 8      # param.vh: TRAINING_DATA_NUM
SP_TRAINING_WIDTH: int = 512    # param.vh: SP_TRAINING_WIDTH

# Encoder weight bus 寬度（用於 SIPO: IDATA_WIDTH=HV_SEG_WIDTH, ODATA_WIDTH=WEIGHT_BUS_WIDTH）
WEIGHT_BUS_WIDTH: int = 256     # param.vh: WEIGHT_BUS_WIDTH

# 由上述常數導出的幾個安全條件
MIN_HV_SEG_WIDTH: int = CLASS_LABEL_WIDTH + HAMMING_DIST_WIDTH  # for {label,dist} packing
MAX_HD_DIM_FROM_HAMMING: int = (1 << HAMMING_DIST_WIDTH) - 1    # Hamming distance不溢位的上限


# ── Mathematical Mapping ─────────────────────────────────────────────────────

def _derive_macros(params: dict) -> Dict[str, Union[int, str]]:
    """
    Apply the mathematical relationships from README Section 2.2 to produce
    a flat dictionary of {MACRO_NAME: value} entries for the SVH file，並在此處
    做所有與 RTL 結構相關的「參數合理性檢查」。

    Parameter conventions (all integers unless noted):
      hd_dim           : Hypervector dimension (HV_LENGTH)
      inner_dim        : Inner dimension of the HD encoder
      reram_size       : Number of RRAM rows (must be power-of-2 friendly)
      cnn_x_dim_1/2    : CNN spatial PE columns (Layer 1/2)
      cnn_y_dim_1/2    : CNN spatial PE rows (Layer 1/2)
      out_channels_1/2 : CNN output channel count (Layer 1/2)
      encoder_x_dim    : Encoder PE columns
      encoder_y_dim    : Encoder PE rows
      frequency        : Operating frequency in Hz (e.g. 1e8 = 100 MHz)
    """
    hd_dim: int = int(params["hd_dim"])
    inner_dim: int = int(params["inner_dim"])
    reram_size: int = int(params["reram_size"])

    cnn_x_dim_1: int = int(params["cnn_x_dim_1"])
    cnn_y_dim_1: int = int(params["cnn_y_dim_1"])
    cnn_x_dim_2: int = int(params["cnn_x_dim_2"])
    cnn_y_dim_2: int = int(params["cnn_y_dim_2"])
    out_channels_1: int = int(params["out_channels_1"])
    out_channels_2: int = int(params["out_channels_2"])

    encoder_x_dim: int = int(params["encoder_x_dim"])
    encoder_y_dim: int = int(params["encoder_y_dim"])

    # ── Basic positivity / range checks ────────────────────────────────────
    if hd_dim <= 0:
        raise ValueError(f"hd_dim must be positive; got {hd_dim}.")
    if hd_dim > MAX_HD_DIM_FROM_HAMMING:
        raise ValueError(
            f"hd_dim ({hd_dim}) is too large for fixed HAMMING_DIST_WIDTH={HAMMING_DIST_WIDTH}. "
            f"Max supported (without distance overflow) is {MAX_HD_DIM_FROM_HAMMING}."
        )

    if inner_dim <= 0:
        raise ValueError(f"inner_dim must be positive; got {inner_dim}.")

    if reram_size <= 0:
        raise ValueError(f"reram_size must be positive; got {reram_size}.")
    # Hardware expects row address to be a clean log2; enforce power-of-two row count.
    if reram_size & (reram_size - 1) != 0:
        raise ValueError(
            f"reram_size ({reram_size}) must be a power of 2 so that row addressing "
            "matches the RTL layout."
        )

    if encoder_x_dim <= 0 or encoder_y_dim <= 0:
        raise ValueError(
            f"encoder_x_dim and encoder_y_dim must be positive; "
            f"got ({encoder_x_dim}, {encoder_y_dim})."
        )

    # RRAM address width: ceil(log2(reram_size))
    rram_row_addr_width: int = math.ceil(math.log2(reram_size))

    # Encoder PE count
    enc_inputs_num: int = encoder_x_dim * encoder_y_dim

    # Encoder weight RF: inner_dim = OUTPUTS_NUM (32) × RF_ROWS
    # WEIGHT_MEM_ADDR_WIDTH = ceil(log2(RF_ROWS))
    outputs_num: int = 32  # from param_opt.vh
    rf_rows: int = inner_dim // outputs_num
    if rf_rows <= 0:
        raise ValueError(f"inner_dim ({inner_dim}) must be >= OUTPUTS_NUM ({outputs_num}).")
    weight_mem_addr_width: int = max(1, math.ceil(math.log2(rf_rows)))

    # Hypervector segment width: hd_dim / (encoder_x_dim * encoder_y_dim)
    # Integer division — must divide evenly for valid RTL
    if hd_dim % enc_inputs_num != 0:
        raise ValueError(
            f"hd_dim ({hd_dim}) must be divisible by encoder_x_dim*encoder_y_dim "
            f"({enc_inputs_num}). Got remainder {hd_dim % enc_inputs_num}."
        )
    hv_seg_width: int = hd_dim // enc_inputs_num

    # ── Structural safety checks for HV_SEG_WIDTH ──────────────────────────
    # 1) Search path：必須能容納 {class_label, hamming_distance} 兩個欄位
    if hv_seg_width < MIN_HV_SEG_WIDTH:
        raise ValueError(
            f"Derived HV_SEG_WIDTH={hv_seg_width} is too small for "
            f"HAMMING_DIST_WIDTH={HAMMING_DIST_WIDTH} and CLASS_LABEL_WIDTH={CLASS_LABEL_WIDTH}; "
            f"need at least {MIN_HV_SEG_WIDTH} bits so that "
            "({class_label, distance}) fits in one segment."
        )

    # 2) Encoder weight SIPO：IDATA_WIDTH=HV_SEG_WIDTH 必須整除 WEIGHT_BUS_WIDTH
    if WEIGHT_BUS_WIDTH % hv_seg_width != 0:
        raise ValueError(
            f"Derived HV_SEG_WIDTH={hv_seg_width} does not divide WEIGHT_BUS_WIDTH="
            f"{WEIGHT_BUS_WIDTH}. SIPO(ins_sipo_weight) requires WEIGHT_BUS_WIDTH "
            "to be an integer multiple of HV_SEG_WIDTH."
        )

    # 3) Training path：TRAINING_DATA_NUM * HV_SEG_WIDTH <= SP_TRAINING_WIDTH
    if TRAINING_DATA_NUM * hv_seg_width > SP_TRAINING_WIDTH:
        raise ValueError(
            f"TRAINING_DATA_NUM * HV_SEG_WIDTH = {TRAINING_DATA_NUM * hv_seg_width} "
            f"exceeds SP_TRAINING_WIDTH={SP_TRAINING_WIDTH}. "
            "Increase SP_TRAINING_WIDTH or decrease hv_dim / encoder grid."
        )

    macros: Dict[str, Union[int, str]] = {
        # Hypervector geometry
        "HV_LENGTH": hd_dim,
        "INNER_DIM": inner_dim,
        "HV_SEG_WIDTH": hv_seg_width,

        # RRAM
        "RRAM_ROW_ADDR_WIDTH": rram_row_addr_width,

        # CNN Layer 1 spatial mapping
        "CNN1_INPUTS_NUM": cnn_x_dim_1 * cnn_y_dim_1,
        "CNN1_OUTPUTS_NUM": out_channels_1,

        # CNN Layer 2 spatial mapping
        "CNN2_INPUTS_NUM": cnn_x_dim_2 * cnn_y_dim_2,
        "CNN2_OUTPUTS_NUM": out_channels_2,

        # Encoder spatial mapping
        "ENC_INPUTS_NUM": enc_inputs_num,

        # Encoder weight RF address width (inner_dim / OUTPUTS_NUM rows)
        "WEIGHT_MEM_ADDR_WIDTH": weight_mem_addr_width,
    }
    return macros


def _write_svh(macros: Dict[str, Union[int, str]], output_path: Path) -> None:
    """Write the macro dictionary to a SystemVerilog header (.svh) file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "// AUTO-GENERATED by json_to_svh.py — DO NOT EDIT MANUALLY",
        "// Generated at runtime by the DSE framework.",
        "`ifndef CONFIG_MACROS_SVH",
        "`define CONFIG_MACROS_SVH",
        "",
    ]
    for name, value in macros.items():
        lines.append(f"`define {name} {value}")
    lines += ["", "`endif // CONFIG_MACROS_SVH", ""]
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ── Synthesis Strategy (Granular Flags) ───────────────────────────────────────
#
# Replaces the old synth_profile presets. Each flag is independent; TCL is built
# by composing enabled options. This expands the DSE exploration space.
#
# Flag → TCL mapping:
#   enable_clock_gating              → set_clock_gating_style + insert_clock_gating
#   max_area_ignore_tns              → set_max_area 0 -ignore_tns (else set_max_area 0)
#   enable_retime                    → -retime in compile_ultra
#   compile_timing_high_effort       → -timing_high_effort_script
#   compile_area_high_effort         → -area_high_effort_script
#   compile_ultra_gate_clock         → -gate_clock
#   compile_exact_map                → -exact_map
#   compile_no_autoungroup           → -no_autoungroup
#   compile_clock_gating_through_hierarchy → set compile_clock_gating_through_hierarchy true
#   enable_leakage_optimization      → set_leakage_optimization true
#   enable_dynamic_optimization      → set_dynamic_optimization true
#   enable_enhanced_resource_sharing → set compile_enhanced_resource_sharing true
#   dp_smartgen_strategy            → none | timing | area (set_dp_smartgen_options)

# Synthesis Optimization DSE: valid values for BO-tunable flags (conf/params_prop/cimloop.yaml)
_EFFORT_LEVELS = ("low", "medium", "high")
_ENABLE_TRUE = ("true", "1", "yes")


def _build_synth_dse_options_block(params: dict) -> str:
    """
    Build TCL block for SYNTH_DSE_OPTIONS_PLACEHOLDER from BO params.
    Injects set_app_var for syn_map_effort / syn_opt_effort only.
    (Clock gating moved to strategy block via enable_clock_gating.)
    """
    lines = ["# Synthesis Optimization DSE (syn_map_effort, syn_opt_effort)"]

    map_effort = str(params.get("syn_map_effort", "medium")).strip().lower()
    if map_effort not in _EFFORT_LEVELS:
        map_effort = "medium"
    lines.append("set_app_var compile_map_effort " + map_effort)

    opt_effort = str(params.get("syn_opt_effort", "medium")).strip().lower()
    if opt_effort not in _EFFORT_LEVELS:
        opt_effort = "medium"
    lines.append("set_app_var compile_opt_effort " + opt_effort)

    return "\n".join(lines)


def _is_true(params: dict, key: str, default: bool = False) -> bool:
    """Check if a param is truthy ('true', '1', 'yes')."""
    val = str(params.get(key, "false" if not default else "true")).strip().lower()
    return val in _ENABLE_TRUE


def _build_synth_strategy_block(params: dict) -> str:
    """
    Build TCL block for SYNTH_PROFILE_PLACEHOLDER from granular synthesis flags.
    Each flag is independent; TCL commands are composed in a sensible order.
    """
    lines = ["# Synthesis strategy (granular flags from DSE)"]

    # 1) Resource sharing (before compile)
    if _is_true(params, "enable_enhanced_resource_sharing"):
        lines.append("set compile_enhanced_resource_sharing true")

    # 2) DP Smartgen strategy
    dp_strat = str(params.get("dp_smartgen_strategy", "none")).strip().lower()
    if dp_strat in ("timing", "area"):
        lines.append(f"set_dp_smartgen_options -optimization_strategy {dp_strat}")

    # 3) Max area (secondary optimization target)
    if _is_true(params, "max_area_ignore_tns"):
        lines.append("set_max_area 0 -ignore_tns")
    else:
        lines.append("set_max_area 0")

    # 4) RTL-level clock gating
    if _is_true(params, "enable_clock_gating"):
        lines.append("set_clock_gating_style -sequential_cell latch")
        lines.append("insert_clock_gating")

    # 5) Power / hierarchy clock gating
    if _is_true(params, "compile_clock_gating_through_hierarchy"):
        lines.append("set compile_clock_gating_through_hierarchy true")
    if _is_true(params, "enable_leakage_optimization"):
        lines.append("set_leakage_optimization true")
    if _is_true(params, "enable_dynamic_optimization"):
        lines.append("set_dynamic_optimization true")

    # 6) compile_ultra with optional flags
    cu_flags: List[str] = []
    if _is_true(params, "enable_retime"):
        cu_flags.append("-retime")
    if _is_true(params, "compile_timing_high_effort"):
        cu_flags.append("-timing_high_effort_script")
    if _is_true(params, "compile_area_high_effort"):
        cu_flags.append("-area_high_effort_script")
    if _is_true(params, "compile_ultra_gate_clock"):
        cu_flags.append("-gate_clock")
    if _is_true(params, "compile_exact_map"):
        cu_flags.append("-exact_map")
    if _is_true(params, "compile_no_autoungroup"):
        cu_flags.append("-no_autoungroup")

    cu_cmd = "compile_ultra" + (" " + " ".join(cu_flags) if cu_flags else "")
    lines.append(cu_cmd)

    return "\n".join(lines)


def _inject_top_module(output_path: Path, top_module: str) -> None:
    """
    Replace TOP_MODULE_PLACEHOLDER in the TCL file with the actual top module name.

    Controls both the DC elaboration root and (indirectly) which VCS testbench the
    Makefile selects for Path 3:
      top_module="core"    → elaborate core;  Path 3 uses tb_core_timing.sv
      top_module="hd_top"  → elaborate hd_top; Path 3 uses tb_hd_top_timing.sv
    """
    placeholder = "TOP_MODULE_PLACEHOLDER"
    content = output_path.read_text(encoding="utf-8")
    if placeholder not in content:
        return
    tm = str(top_module).strip().lower()
    if tm not in ("core", "hd_top"):
        import warnings
        warnings.warn(
            "Unknown top_module %r, defaulting to 'core'. Valid: ('core', 'hd_top')" % tm
        )
        tm = "core"
    content = content.replace(placeholder, tm)
    output_path.write_text(content, encoding="utf-8")


def _inject_synth_dse_options(output_path: Path, params: dict) -> None:
    """Replace SYNTH_DSE_OPTIONS_PLACEHOLDER in the TCL file at output_path with the DSE options block."""
    placeholder = "# SYNTH_DSE_OPTIONS_PLACEHOLDER"
    content = output_path.read_text(encoding="utf-8")
    if placeholder not in content:
        return
    block = _build_synth_dse_options_block(params)
    content = content.replace(placeholder, block)
    output_path.write_text(content, encoding="utf-8")


def _inject_synth_strategy(output_path: Path, params: dict) -> None:
    """
    Replace the SYNTH_PROFILE_PLACEHOLDER token in the TCL file with the
    synthesis strategy block built from granular flags.
    """
    placeholder = "# SYNTH_PROFILE_PLACEHOLDER"
    content = output_path.read_text(encoding="utf-8")
    if placeholder not in content:
        return
    strategy_block = _build_synth_strategy_block(params)
    content = content.replace(placeholder, strategy_block)
    output_path.write_text(content, encoding="utf-8")


# ── Testbench Macro Generation ────────────────────────────────────────────────

def _write_tb_macros(params: dict, output_path: Path) -> None:
    """
    Generate `fsl-hd/verilog/tb/tb_macros.svh` with Testbench constants derived
    from the current BO parameter configuration.

    Path 3 uses LFSR-based testbenches (tb_core_timing.sv / tb_hd_top_timing.sv)
    that self-generate random stimuli, so NO hex file paths are needed here.

    Generated macros:
      TB_CLK_PERIOD_NS — full clock period in ns (drives the clock generator in the TB)
    """
    frequency_hz: float = float(params.get("frequency", 2e8))
    period_ns: float = round(1e9 / frequency_hz, 4)

    lines = [
        "// AUTO-GENERATED by json_to_svh.py — DO NOT EDIT MANUALLY",
        "// Used by LFSR-based testbenches (tb_core_timing.sv / tb_hd_top_timing.sv).",
        "// No hex data files are required — testbench generates its own LFSR stimuli.",
        "`ifndef TB_MACROS_SVH",
        "`define TB_MACROS_SVH",
        "",
        "`define TB_CLK_PERIOD_NS  " + str(period_ns),
        "",
        "`endif // TB_MACROS_SVH",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ── Clock TCL Patching ────────────────────────────────────────────────────────

def _patch_tcl_clock(frequency_hz: float, template_path: Path, output_path: Path) -> None:
    """
    Patch the DC synthesis TCL script to set the correct clock period.

    The template TCL file must contain a placeholder line of the form:
        create_clock -period CLOCK_PERIOD_PLACEHOLDER [get_ports clk]

    This function replaces CLOCK_PERIOD_PLACEHOLDER with the computed period in ns.
    """
    period_ns: float = round(1e9 / frequency_hz, 4)

    if not template_path.exists():
        raise FileNotFoundError(
            f"TCL template not found: {template_path}\n"
            "Create 'hardware/dc/synth_template.tcl' with placeholder "
            "'CLOCK_PERIOD_PLACEHOLDER' in the create_clock command."
        )

    tcl_content = template_path.read_text(encoding="utf-8")
    if "CLOCK_PERIOD_PLACEHOLDER" not in tcl_content:
        raise ValueError(
            "TCL template does not contain 'CLOCK_PERIOD_PLACEHOLDER'. "
            "Cannot inject clock period dynamically."
        )

    patched = tcl_content.replace("CLOCK_PERIOD_PLACEHOLDER", str(period_ns))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched, encoding="utf-8")


# ── Entry Point ───────────────────────────────────────────────────────────────

def translate(params: dict) -> None:
    """
    Main translation function: params dict → SVH macros + patched TCL + TB macros.

    Steps:
      1. Derive RTL macros from HW parameters → config_macros.svh
      2. Select template based on synth_mode (fast/slow) and patch clock period
      3. Inject TOP_MODULE_PLACEHOLDER with top_module value ("core" or "hd_top")
      4. Inject synthesis DSE options (syn_map_effort, syn_opt_effort, etc.)
      5. Inject synthesis strategy block (based on synth_profile)
      6. Apply -retime flag if enable_retime is 'true'
      7. Write tb_macros.svh for LFSR-based testbenches (clock period only)
    """
    macros = _derive_macros(params)
    _write_svh(macros, SVH_OUTPUT)

    frequency_hz: float = float(params.get("frequency", 2e8))
    synth_mode: str = str(params.get("synth_mode", "slow")).strip().lower()
    top_module: str = str(params.get("top_module", "core")).strip().lower()
    tcl_template = TCL_TEMPLATE_FAST if synth_mode == "fast" else TCL_TEMPLATE_SLOW

    _patch_tcl_clock(frequency_hz, tcl_template, TCL_OUTPUT)
    _inject_top_module(TCL_OUTPUT, top_module)
    _inject_synth_dse_options(TCL_OUTPUT, params)
    _inject_synth_strategy(TCL_OUTPUT, params)

    _write_tb_macros(params, TB_MACROS_OUTPUT)

    print(
        "[json_to_svh] Written %s (%d macros, clock=%.3f ns, "
        "synth_mode=%s, top_module=%s)" % (
            SVH_OUTPUT.name, len(macros), 1e9 / frequency_hz,
            synth_mode, top_module,
        )
    )


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No JSON input on stdin.", file=sys.stderr)
        sys.exit(1)
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        translate(params)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
