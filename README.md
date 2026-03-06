# Full-Stack Accelerator Optimization Framework

**Focus:** Multi-fidelity Design Space Exploration (DSE) for HDnn-PIM Architecture
**Status:** Phase 2 (Baseline Exploration) + Path 3 (LFSR Gate-Level Verification) Implemented

All architecture and flow diagrams (Mermaid) are in **[README_IMAGES.md](README_IMAGES.md)**.  
Modification summaries and changelogs: **[docs/](docs/)** (e.g. [2026-02-27 修改與優化總結](docs/2026-02-27-修改與優化總結.md)).

---

## 1. Project Overview & Exploration Strategy

This project builds an automated, closed-loop Design Space Exploration (DSE) framework to optimize a parameterized Processing-in-Memory (PIM) accelerator for Hyperdimensional Neural Networks (HDnn).

### Core Algorithm: Bayesian Optimization (BO)
The hardware design space is high-dimensional, and physical hardware evaluations (synthesis/simulation) are highly expensive. BO is chosen for its sample-efficient nature, effectively balancing **exploration** and **exploitation**. 
- **Multi-Objective Target:** Maximize Hypervolume across four metrics (Accuracy, Energy, Timing, Area) to form the Pareto frontier.
- **Decoupled Execution:** The BO "brain" is decoupled from the hardware "muscle". The EDA Server acts as a Black-box API.

---

## 2. System Architecture (Thin-Client Model)

Due to strict EDA tool licensing constraints, local execution of hardware synthesis is not possible. The framework implements a **Black-Box API** pattern: the local Docker client only transmits parameter JSON, and the remote EDA server executes synthesis and returns distilled numerical metrics.

**Diagram:** [System Architecture (Thin-Client)](README_IMAGES.md#1-system-architecture-thin-client-model) — see [README_IMAGES.md](README_IMAGES.md).

---

## 3. Multi-Fidelity Evaluation Pipeline

To overcome the evaluation bottleneck, the framework employs a three-tiered pipeline with **Early Stopping (Gatekeeping)** mechanisms.

**Diagram:** [Multi-Fidelity Evaluation Pipeline](README_IMAGES.md#2-multi-fidelity-evaluation-pipeline) — see [README_IMAGES.md](README_IMAGES.md).

### 3.1 Path 1: Fast Software Simulation
* **Engine:** `path1_software.py` (PyTorch HD model + Cimloop RRAM estimator)
* **Gate 1:** If PyTorch accuracy is below the defined constraint, the trial is marked as failed (via Ax) and **no hardware work is launched**.

### 3.2 Path 2: Hardware Synthesis (Client-Side Stitching)
* **Engine:** `path2_hardware.py`
* **Stitching Logic:** Since the RRAM portion lacks RTL, Path 2 stitches ASIC data (from the EDA server) with RRAM data (re-run locally via Cimloop).
  * `Total Timing = ASIC Delay (EDA) + RRAM Delay (Cimloop)`
  * `Total Energy = ASIC Power (EDA) * Total Timing + RRAM Energy (Cimloop)`
* **Gate 2:** If the synthesized netlist violates timing constraints (`slack < 0`), the trial fails. Path 3 is only considered for designs that pass Gate 2.

### 3.3 Path 3: Gate-Level Simulation & Power Verification (LFSR-Based)
* **Engine:** `evaluate_path3()` in `path2_hardware.py`, which reuses Path 2 ASIC metrics and calls the EDA Server with `run_path3=True`.
* **Triggering:** The client does **not** send HEX data. Instead, it sets `run_path3=True` and passes a `top_module` flag (`core` or `hd_top`) inside the JSON payload. The server checks `run_path3` and, if timing is met, runs:
  - `make sim` — VCS gate-level simulation with SAIF dump.
  - `make power` — PrimeTime PX dynamic power analysis using the SAIF activity.
* **LFSR Testbenches (on the EDA server):**
  - `fsl-hd/verilog/tb/tb_core_timing.sv` — exercises the `core` top-level, including chip interface and FIFOs.
  - `fsl-hd/verilog/tb/tb_hd_top_timing.sv` — focuses on the `hd_top` core only.
  Both testbenches generate their own pseudo-random stimuli using LFSRs and print a line of the form  
  `COMPUTE CYCLES      : <num>  (ENC_PRELOAD → oFIFO result)`, from which the server parses the exact execution cycle count.
* **Final Metrics Stitching:**
  - ASIC timing is computed as `clock_period_ns * execution_cycles / 1e3` (us) using **Path 2** clock period and **Path 3** cycle count.
  - ASIC energy is obtained from PtPX dynamic + leakage power and multiplied by the total timing.
  - RRAM timing and energy continue to come exclusively from Cimloop (no RTL), and are added on top of the ASIC portion.
* **Testbench Macro Mapping (summary):**
  - `frequency` → `TB_CLK_PERIOD_NS` (full clock period for TB clock generator).
  - No testbench file paths are needed; all stimuli are generated on-chip by the testbenches.

---

## 4. EDA Server Protocol (Black-Box API)

To navigate restrictive corporate firewalls, large `.rpt` files are never transferred. The EDA Server "locally extracts" metrics and returns a tiny JSON payload.

**Diagram:** [EDA Server Protocol (Polling Sequence)](README_IMAGES.md#4-eda-server-protocol-polling-sequence) — see [README_IMAGES.md](README_IMAGES.md).

---

## 5. Parameter Space Classification & Mapping

Tunable parameters are centrally defined in `workspace/conf/params_prop/cimloop.yaml`.

### 5.1 Software Parameter Categorization
* **Category 1: Hardware-Related (Alters RTL Geometry & Memory)**
  * `hd_dim`, `inner_dim`, `reram_size`
  * Spatial mapping: `cnn_x_dim_1/2`, `encoder_x_dim/y_dim`, etc.
* **Category 2: Training & Dataflow-Related (No RTL Impact)**
  * `dataset`, `frequency`, `hd_epochs`, `cnn_epochs`
  * `cnn` (Fixed flag: true = CNN+HD, false = HD only)
* **Category 3: Synthesis Strategy (EDA Impact)**
  * `synth_profile`: Groups DC synthesis flags to explore the trade-off between strict timing and low power/area.

### 5.2 Synthesis Flags DSE (Config & TCL Mapping)

By exposing synthesis flags to the BO engine, we can explore the Pareto front between RTL architecture and EDA optimization strategies. These flags are defined in `workspace/conf/params_prop/cimloop.yaml` and injected into `synth_dse.tcl` by `eda_server_scripts/json_to_svh.py`.

#### 5.2.1 High-Level Synthesis Profiles (`synth_profile`)

The `synth_profile` parameter selects a multi-line TCL strategy block that is injected at `SYNTH_PROFILE_PLACEHOLDER` in the DC template:

| `synth_profile` (YAML) | DC TCL Commands Generated | Strategy Goal |
| :--- | :--- | :--- |
| `balanced_default` | `insert_clock_gating` + `set_max_area 0` + `compile_ultra` | Standard compilation; secondary area reduction. |
| `timing_aggressive` | `set_max_area 0` + `compile_ultra -retime -timing_high_effort_script` | Meet strict clock periods (no clock gating). |
| `power_aggressive` | Clock gating + `set_leakage_optimization` + `set_dynamic_optimization` + `compile_ultra -gate_clock` | Minimize power (Power Compiler recommended). |
| `area_aggressive` | `set_max_area 0 -ignore_tns` + `compile_ultra -area_high_effort_script` | Minimize area; may violate timing. |
| `exact_map` | `compile_ultra -exact_map -no_autoungroup` | Preserves RTL hierarchy; minimal optimization. |

Invalid values (e.g., a mis-mapped integer like `"1024"`) are automatically mapped back to `balanced_default` with a warning on the server, preventing BO bugs from crashing the flow.

#### 5.2.2 Low-Level Effort Flags (`syn_map_effort`, `syn_opt_effort`, `enable_retime`, `enable_gate_clock`)

In addition to `synth_profile`, several scalar flags are tuned by BO and translated into DC `set_app_var` commands or compile options:

| YAML Parameter | Allowed Values | DC Effect |
| :--- | :--- | :--- |
| `syn_map_effort` | `low`, `medium`, `high` | `set_app_var compile_map_effort <value>` |
| `syn_opt_effort` | `low`, `medium`, `high` | `set_app_var compile_opt_effort <value>` |
| `enable_gate_clock` | `"false"`, `"true"` | When `"true"`, emits `set_clock_gating_style -sequential_cell latch` + `insert_clock_gating`. |
| `enable_retime` | `"false"`, `"true"` | When `"true"`, injects `-retime` into the first `compile_ultra` command that does not already specify it. |

These flags are fully implemented in `_build_synth_dse_options_block()` and `_apply_retime_if_requested()` inside `json_to_svh.py`.

**Synth Decision Diagram:** See [docs/synth_decision_diagram.md](docs/synth_decision_diagram.md) for the `SYNTH_MODE` (slow/fast) × `TOP_MODULE` (core/hd_top) decision matrix.

### 5.3 Output Format (`dse_results.json`)

Each run writes `dse_results.json` with final stitched metrics plus Path 2/3 raw data:

| Key | Description |
| :--- | :--- |
| `accuracy`, `energy_uj`, `timing_us`, `area_mm2`, `hv` | Final objectives (used for Pareto / Hypervolume) |
| `param` | List of BO parameter dicts per trial |
| `p2_area_um2`, `p2_timing_slack_ns`, `p2_clock_period_ns`, `p2_dynamic_power_mw` | Path 2 ASIC metrics (EDA synthesis) |
| `p3_execution_cycles`, `p3_dynamic_power_mw` | Path 3 VCS/PtPX metrics (gate-level simulation) |

### 5.4 Software-to-RTL Mapping Table
Implemented in `eda_server_scripts/json_to_svh.py`.

| Software Parameter | Hardware Macro (`config_macros.svh`) | Mathematical Conversion |
| :--- | :--- | :--- |
| `reram_size` | `` `RRAM_ROW_ADDR_WIDTH `` | `ceil(log2(reram_size))` |
| `hd_dim` | `` `HV_LENGTH `` | Direct; **max 8191** (HAMMING_DIST_WIDTH=13 ⇒ 2^13−1) |
| `inner_dim` | `` `INNER_DIM `` | Direct |
| `cnn_x_dim_1` × `cnn_y_dim_1` | `` `CNN1_INPUTS_NUM `` | Product |
| `cnn_x_dim_2` × `cnn_y_dim_2` | `` `CNN2_INPUTS_NUM `` | Product |
| `encoder_x_dim` × `encoder_y_dim` | `` `ENC_INPUTS_NUM `` | Product |
| `hd_dim` / (`encoder_x_dim` × `encoder_y_dim`) | `` `HV_SEG_WIDTH `` | Integer division; `hd_dim ≤ 8191` (2^13−1); must be ≥ `HAMMING_DIST_WIDTH + CLASS_LABEL_WIDTH`, divide `WEIGHT_BUS_WIDTH`, and satisfy `TRAINING_DATA_NUM * HV_SEG_WIDTH ≤ SP_TRAINING_WIDTH`. |
| `frequency` | DC TCL `create_clock -period` | `1e9 / frequency` (ns) |

---

## 6. Directory Structure

```text
Full-Stack-Accelerator-Optimization/
│
├── workspace/                         # Local execution environment
│   ├── run_exploration.py             # Main entry point (CLI args for Path 2/3)
│   ├── dse_framework/                 # [Core] DSE Control Center
│   │   ├── evaluators/                # Evaluator Wrappers (Path 1 & 2)
│   │   ├── network/                   # Socket Client (Polling Protocol)
│   │   └── core_algorithm/            # BO Engine & Dynamic Normalizer
│   │
│   ├── HDnn-PIM-Opt/                  # Pure software evaluator (Path 1 / Cimloop)
│   ├── conf/                          # Hydra configurations (YAML)
│   │   └── params_prop/               # cimloop.yaml (search space definition)
│   └── outputs/                      # Hydra output dirs (dse_results.json, run_exploration.log)
│
├── docs/                              # Documentation
│   └── synth_decision_diagram.md     # SYNTH_MODE × TOP_MODULE decision diagram (Mermaid)
└── eda_server_scripts/                # Scripts deployed onto the remote EDA server (often as full-stack-opt/ alongside fsl-hd/)
    ├── eda_server.py                  # Socket Server (Queue + Timeout, run_path3 flag, SYNTH_MODE/TOP_MODULE forwarding)
    ├── json_to_svh.py                 # Macro & TCL generation (clock, TOP_MODULE, synthesis flags, TB macros)
    └── parsers/                       # DC and VCS/PTPX regex parsers (including COMPUTE CYCLES extraction)
```

---

## 7. Implementation To-Do / Status

### Phase 2: Automation Baseline [✅ COMPLETED]
- [x] Parameter Mapping Table & `json_to_svh.py`.
- [x] `eda_server.py` with Task Queue and strict 30-min timeouts.
- [x] Regex parsers for DC reports (`parse_dc.py`).
- [x] Polling client (`eda_client.py`).
- [x] Client-side data stitching (`path2_hardware.py`).
- [x] Ax/BoTorch Engine refactoring (`bo_engine.py` + dynamic normalization).

### Phase 3 & 4: Verification & Full BO Integration
- [x] Implement `synth_profile` logic in `json_to_svh.py` to generate TCL strategy blocks (with defensive fallback to `balanced_default`).
- [x] Establish VCS → PtPX SAIF handoff pipeline (`Makefile sim/power` + `parse_vcs.py` with `COMPUTE CYCLES` regex).
- [x] Create LFSR-based timing testbenches (`tb_core_timing.sv` / `tb_hd_top_timing.sv`) driven by `TB_CLK_PERIOD_NS` and selected via `TOP_MODULE`.
- [x] Replace hex-data-based Path 3 with a `run_path3` flag and on-server LFSR stimulus generation (no PyTorch HEX transfer).
- [x] Persist Path 2/3 raw metrics in `dse_results.json` (p2_area_um2, p2_timing_slack_ns, p3_execution_cycles, etc.).
- [x] `synth_profile` extended with `area_aggressive`; `hd_dim` upper bound enforced at 8191.
- [ ] Define hard boundary constraints for all BO parameters (min/max bounds).
- [ ] **Cross-Path Calibration:** Use Path 2/3 physical data to calibrate Path 1 analytical models.
