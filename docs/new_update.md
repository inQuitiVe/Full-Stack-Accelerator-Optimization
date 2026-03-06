# Full-Stack DSE – Server & EDA Updates Summary

This document summarizes the server-side and EDA-flow changes for the Full-Stack Accelerator Optimization framework. It supersedes the earlier daily note `2026-02-27-修改與優化總結.md` and is meant to be a stable reference for how the remote EDA host is structured and how it interacts with the thin client.

---

## 1. Python Compatibility & Robustness on the EDA Server

The EDA host runs an older Python environment (Python 3.6.x in some deployments). All server scripts under `eda_server_scripts/` have been hardened to support this:

- **Dropped unsupported `__future__` imports**: Removed `from __future__ import annotations` from `eda_server.py`, `json_to_svh.py`, `parse_dc.py`, and `parse_vcs.py`.
- **Subprocess API compatibility**: Replaced `capture_output=True` / `text=True` with
  `stdout=subprocess.PIPE`, `stderr=subprocess.PIPE`, and `universal_newlines=True` in all subprocess calls.
- **Type hinting made 3.6-friendly**: Replaced newer forms such as `dict[str, int]` or `int | str` with `Dict[str, Union[int, str]]` and imported types from `typing`.
- **Encoding declaration**: Added `# -*- coding: utf-8 -*-` at the top of Python scripts to avoid encoding issues on mixed locales.
- **Explicit `python3` in subprocesses**: `eda_server.py` now explicitly calls `python3 json_to_svh.py` to avoid accidentally invoking a Python 2 binary on legacy hosts.

---

## 2. EDA Server Architecture & Stability Improvements

The EDA server acts as a black-box API that accepts JSON, runs DC / VCS / PtPX locally, and returns distilled metrics. Several robustness changes have been implemented:

- **Duplicate `job_id` handling**: The job registry allows re‑submitting the same `job_id` if the previous job is already in a terminal state (`success`, `error`, `timeout`, `timing_violated`). This enables safe retries from the client.
- **Absolute-path resolution**: `WORK_DIR`, `FSL_HD_DIR` and `REPORTS_DIR` in `eda_server.py` are all resolved via `.resolve()`. This removes sensitivity to the working directory from which the server is launched.
- **Stricter timeouts**: All long-running EDA subprocesses (`make synth`, `make sim`, `make power`) use a hard wall‑clock timeout (default 30 minutes). On timeout, the process is killed and the job is marked `timeout` in the registry.
- **Clear status transitions**: The worker thread sets job status to `queued` → `running` → `{success,error,timeout,timing_violated}`, and the polling client (`eda_client.py`) only ever sees these well-defined states.

---

## 3. DC Synthesis Flow Refactor (Templates, Makefile, and Paths)

To ensure that the automated DC flow reproduces the original golden flow and remains maintainable, the synthesis scripts have been fully refactored:

### 3.1 Directory Layout on the EDA Host

The expected layout on the EDA host is:

```text
~/workspace/
├── fsl-hd/                 # Original HDL project (RTL, libs, reports, tb, etc.)
│   ├── verilog/hdl/        # Main RTL sources
│   ├── verilog/include/    # param.vh, config_macros.svh
│   ├── verilog/tb/         # Timing testbenches (tb_core_timing.sv, tb_hd_top_timing.sv)
│   └── reports/            # DC / VCS / PtPX reports and netlists
└── full-stack-opt/         # This repository's server scripts
    ├── eda_server_scripts/
    │   ├── eda_server.py
    │   ├── json_to_svh.py
    │   ├── parsers/
    │   └── dc/
    │       ├── synth_template_slow.tcl
    │       ├── synth_template_fast.tcl
    │       ├── synth_dse.tcl        # auto-generated per job
    │       └── ptpx.tcl
    └── Makefile                     # wraps dc_shell, vcs, pt_shell
```

### 3.2 DC Templates and Synthesis Modes

There are now **two** DC templates, selected by the `synth_mode` flag:

- `synth_template_slow.tcl` — **Slow mode** (full-system synthesis)
  - Reads all relevant RTL, including PatterNet, chip interface, SRAM/RF wrappers.
  - Matches the original `compile_dc.tcl` environment: `search_path`, `target_library`, `link_library`, etc.
  - Uses a whitelist of RTL files to avoid pulling in legacy or test-only modules.

- `synth_template_fast.tcl` — **Fast mode** (black-box synthesis)
  - Uses a **whitelist** that only contains the HD core and its immediate wrapper:
    `core.sv`, `hd_top.sv`, `hd_enc.sv`, `hd_search.sv`, `hd_train.sv`, `sub_module.sv`.
  - PatterNet, chip interface, and large memories are intentionally omitted so they are treated as DC black boxes during `elaborate`/`link`.
  - Greatly reduces compile time while preserving the PPA trend for the tunable HD core.

Both templates declare:

```tcl
set top_module TOP_MODULE_PLACEHOLDER
...
elaborate $top_module
current_design $top_module
link
```

The placeholder is replaced at runtime by `json_to_svh.py` according to the `top_module` parameter (`core` or `hd_top`), enabling a clean separation between **synthesis mode** and **observation scope**.

### 3.3 Makefile (EDA Orchestration)

The `eda_server_scripts/Makefile` (executed from `full-stack-opt/`) now supports:

- **Runtime variables**:
  - `SYNTH_MODE ?= slow` — selects slow/fast DC template (handled in `json_to_svh.py`).
  - `TOP_MODULE ?= core` — selects elaboration and testbench scope: `core` or `hd_top`.
- **Testbench selection**:

```makefile
TB_DIR  := $(FSL_HD)/verilog/tb
ifeq ($(TOP_MODULE),hd_top)
  TB_FILE := $(TB_DIR)/tb_hd_top_timing.sv
  SIM_TOP := tb_hd_top_timing
else
  TB_FILE := $(TB_DIR)/tb_core_timing.sv
  SIM_TOP := tb_core_timing
endif
```

- **Targets**:
  - `synth` — runs DC with `synth_dse.tcl` (generated by `json_to_svh.py`).
  - `sim` — compiles gate-level netlist + timing testbench using VCS and runs simulation, producing `vcs_simulation.log` and an SAIF file.
  - `power` — runs `pt_shell -f dc/ptpx.tcl` to get dynamic + leakage power from SAIF.

`eda_server.py` injects `SYNTH_MODE=<fast|slow>` and `TOP_MODULE=<core|hd_top>` into these `make` calls, ensuring that Path 2 and Path 3 honor both dimensions.

---

## 4. Parsers: DC & VCS/PTPX

### 4.1 `parse_dc.py`

Enhancements include:

- **Area parsing fallback**: If `"Total cell area"` is not found, the parser now falls back to summing `"Combinational area"`, `"Noncombinational area"`, and `"Macro/Black Box area"` to derive a total area value.
- **Clock period fix**: `report_timing.rpt` contains multiple `clock (rise edge)` lines. The code now uses `re.findall()` and takes the **maximum** of the matched periods to avoid incorrectly returning `0.0 ns`.
- **Improved error messages**: When parsing fails, the offending portion of the report (first ~1500 characters) is included in the error message to simplify debugging on the server.

### 4.2 `parse_vcs.py`

Path 3 has been redesigned to rely on LFSR-based testbenches that print a well-defined summary line and produce SAIF files. Accordingly:

- The parser extracts execution cycles using the primary regex:

```text
COMPUTE CYCLES      : <num>
```

implemented as `COMPUTE CYCLES\s*:\s*([0-9]+)`.

- Legacy patterns (e.g. `"Total cycles: <N>"`, `"SIM_CYCLES: <N>"`) are retained as fallbacks for older testbenches.
- The public API `parse_vcs_reports()` now returns:

```python
{
    "execution_cycles": int,
    "dynamic_power_mw": float,
    "leakage_power_mw": float,
}
```

Hardware accuracy is **not** extracted in the LFSR-based flow; functional correctness remains the responsibility of Path 1 (PyTorch).

---

## 5. Synthesis Flags DSE (json_to_svh.py + cimloop.yaml)

The BO search space now includes a dedicated EDA-synthesis subspace. These flags are defined in `workspace/conf/params_prop/cimloop.yaml` and implemented in `eda_server_scripts/json_to_svh.py`:

### 5.1 High-Level Profiles (`synth_profile`)

The `synth_profile` choice parameter selects a multi-line TCL block injected at `SYNTH_PROFILE_PLACEHOLDER`:

- `balanced_default` — clock gating + `set_max_area 0` + `compile_ultra`.
- `timing_aggressive` — `set_max_area 0` + `compile_ultra -retime -timing_high_effort_script` (no clock gating).
- `power_aggressive` — clock gating + `set_leakage_optimization` + `set_dynamic_optimization` + `compile_ultra -gate_clock`.
- `area_aggressive` — `set_max_area 0 -ignore_tns` + `compile_ultra -area_high_effort_script` (may violate timing).
- `exact_map` — `compile_ultra -exact_map -no_autoungroup` to preserve hierarchy.

If an invalid value is received (e.g. the `"1024"` bug caused by `process_params_prop`), the code logs a warning and falls back to `balanced_default` instead of raising an exception.

### 5.2 Low-Level Effort Flags

Additional scalar flags are combined with `synth_profile` to refine DC behavior:

- `syn_map_effort ∈ {low, medium, high}`  
  → `set_app_var compile_map_effort <value>`
- `syn_opt_effort ∈ {low, medium, high}`  
  → `set_app_var compile_opt_effort <value>`
- `enable_gate_clock ∈ {"false","true"}`  
  → when `"true"`, emits

```tcl
set_clock_gating_style -sequential_cell latch
insert_clock_gating
```

- `enable_retime ∈ {"false","true"}`  
  → when `"true"`, injects `-retime` into the first `compile_ultra` command that does **not** already have it.

These options are emitted by `_build_synth_dse_options_block()` and `_apply_retime_if_requested()`.

---

## 6. Software → RTL Macro Mapping (json_to_svh.py)

`json_to_svh.py` is the single source of truth for translating BO parameters into SystemVerilog macros (`config_macros.svh`) and for patching `synth_dse.tcl`. Key mappings include:

- `reram_size` → `` `RRAM_ROW_ADDR_WIDTH `` via `ceil(log2(reram_size))`.
- `hd_dim` → `` `HV_LENGTH `` (direct).
- `inner_dim` → `` `INNER_DIM `` (direct).
- `cnn_x_dim_1 * cnn_y_dim_1` → `` `CNN1_INPUTS_NUM ``.
- `cnn_x_dim_2 * cnn_y_dim_2` → `` `CNN2_INPUTS_NUM ``.
- `encoder_x_dim * encoder_y_dim` → `` `ENC_INPUTS_NUM ``.
- `HV_SEG_WIDTH` is derived as:

```text
HV_SEG_WIDTH = hd_dim / (encoder_x_dim * encoder_y_dim)
```

with structural constraints:

- Must divide `WEIGHT_BUS_WIDTH` exactly.
- Must be at least `HAMMING_DIST_WIDTH + CLASS_LABEL_WIDTH` (to pack label + distance).
- Must satisfy `TRAINING_DATA_NUM * HV_SEG_WIDTH ≤ SP_TRAINING_WIDTH`.

Violations of these constraints cause `json_to_svh.py` to raise a clear `ValueError`, ensuring that illegal design points are rejected early before RTL is generated.

---

## 7. Path 2 & Path 3 Stitching Semantics

The client-side evaluators (`path2_hardware.py`) now implement:

- **Path 2 (ASIC + RRAM stitching)**:
  - Receives ASIC metrics from the EDA server (area, clock period, power) and combines them with Cimloop’s RRAM metrics.
  - Total timing and energy are computed as:

    - `total_timing_us = asic_timing_us + rram_delay_us`
    - `total_energy_uJ = asic_energy_uJ + rram_energy_uJ`

- **Path 3 (LFSR GLS + PtPX)**:
  - Upgrades ASIC timing from `clock_period`-only to `clock_period × execution_cycles`.
  - Replaces DC power with PtPX power based on SAIF activity from the LFSR testbenches.
  - RRAM timing/energy are still sourced from Cimloop and simply added.

This preserves the earlier “additive” semantics (ASIC + RRAM) while providing a higher-fidelity view of the ASIC portion in Path 3.

---

## 8. Relation to README and Thesis

The high-level description in `README.md` and `essay/full_thesis_zh.md` has been updated to match this implementation:

- Path 3 is explicitly described as an **LFSR-based gate-level timing and power verification path**, triggered via `run_path3` and parameterized by `top_module`.
+- The separation between `synth_mode ∈ {slow, fast}` and `top_module ∈ {core, hd_top}` is highlighted as a 2D design/verification knob.
- The EDA synthesis flags (`synth_profile`, `syn_map_effort`, `syn_opt_effort`, `enable_retime`, `enable_gate_clock`) and their search spaces are documented consistently across `cimloop.yaml`, `json_to_svh.py`, `README.md`, and the thesis.

This file should be treated as the canonical, up-to-date description of the remote EDA flow and its interaction with the thin client.

