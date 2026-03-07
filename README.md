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
* **Stitching Logic:** Since the RRAM portion lacks RTL, Path 2 stitches ASIC data (from the EDA server) with RRAM data (re-run locally via Cimloop):

| Metric | Formula |
| :--- | :--- |
| Total Timing | \( T_{\text{total}} = T_{\text{ASIC}} + T_{\text{RRAM}} \) |
| Total Energy | \( E_{\text{total}} = P_{\text{ASIC}} \times T_{\text{total}} + E_{\text{RRAM}} \) |
| ASIC Timing | \( T_{\text{ASIC}} = T_{\text{clk}} \times N_{\text{cycles}} \) (Path 3 cycles × Path 2 clock period) |

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
  Testbenches support `inner_dim`-driven `N_WEIGHT_WORDS` and 10 classes (MNIST/CIFAR-10); see [docs/hardware_modification_report.md](docs/hardware_modification_report.md) for RTL handoff.
* **Final Metrics Stitching:**

| Metric | Formula |
| :--- | :--- |
| ASIC Timing (µs) | \( T_{\text{ASIC}} = \frac{\text{clock\_period\_ns} \times \text{execution\_cycles}}{1000} \) |
| ASIC Energy | \( E_{\text{ASIC}} = (P_{\text{dyn}} + P_{\text{leak}}) \times T_{\text{ASIC}} \) |
| Total Energy | \( E_{\text{total}} = E_{\text{ASIC}} + E_{\text{RRAM}} \) (Cimloop) |

* **LFSR Testbench Instruction Sequence (tb_core_timing / tb_hd_top_timing):**

| Phase | Instruction | Data | Purpose |
| :--- | :--- | :--- | :--- |
| Pre-setup | STORE_BUF | Encoding weights | inp_buf[1..N_WEIGHT_WORDS] |
| Pre-setup | STORE_BUF | Class HVs | data_buf[0..N_CLASS_WORDS-1] |
| Per-inference | STORE_BUF | Input features | inp_buf[0..N_FEAT_WORDS-1] |
| Compute | ENC_PRELOAD | — | inp_buf → encoder RF |
| Compute | ENC_SEG | — | Encode features → HV segments |
| Compute | STORE_BUF | HAM config | inp_buf[0] or inp_buf[64] |
| Compute | HAM_SEG | — | Hamming distance search |
| Compute | PRED | — | Output prediction to oFIFO |

* **Testbench Macro Mapping:**
  - `frequency` → `TB_CLK_PERIOD_NS` (full clock period for TB clock generator).
  - `inner_dim` → `N_WEIGHT_WORDS` via `WEIGHT_MEM_ADDR_WIDTH` (see Section 5.4).
  - No hex file paths; all stimuli generated on-chip by LFSRs.

---

## 4. EDA Server Protocol (Black-Box API)

To navigate restrictive corporate firewalls, large `.rpt` files are never transferred. The EDA Server "locally extracts" metrics and returns a tiny JSON payload.

**Diagram:** [EDA Server Protocol (Polling Sequence)](README_IMAGES.md#4-eda-server-protocol-polling-sequence) — see [README_IMAGES.md](README_IMAGES.md).

---

## 5. Parameter Space Classification & Mapping

Tunable parameters are centrally defined in `workspace/conf/params_prop/cimloop.yaml`.

### 5.1 Software Parameter Categorization

| Category | Parameters | Impact |
| :--- | :--- | :--- |
| **HW (RTL Geometry)** | `hd_dim`, `inner_dim`, `reram_size` | `config_macros.svh` → HV_LENGTH, WEIGHT_MEM_ADDR_WIDTH, RRAM_ROW_ADDR_WIDTH |
| **HW (Spatial)** | `cnn_x_dim_1/2`, `cnn_y_dim_1/2`, `encoder_x_dim/y_dim`, `out_channels_1/2` | CNN/Encoder PE layout, HV_SEG_WIDTH |
| **SW (No RTL)** | `dataset`, `hd_epochs`, `cnn_epochs`, `cnn` | PyTorch training only |
| **SW (Clock)** | `frequency` | DC `create_clock`, TB `TB_CLK_PERIOD_NS` |
| **Synth (EDA)** | Granular flags (Section 5.2) | `synth_dse.tcl` strategy block |

**Parameter Impact Summary:**

| Affects | Parameters |
| :--- | :--- |
| Synthesis (RTL + DC) | All HW params, `frequency`, `top_module`, `synth_mode`, granular synth flags |
| Testbench (VCS) | `frequency`, `top_module`, all HW params (via `config_macros.svh`) |
| Path 1 (Software) | `hd_dim`, `inner_dim`, `dataset`, `hd_epochs`, `cnn_epochs`, `cnn` |

### 5.2 Synthesis Flags DSE (Config & TCL Mapping)

By exposing granular synthesis flags to the BO engine, we can explore the Pareto front between RTL architecture and EDA optimization strategies. These flags are defined in `workspace/conf/params_prop/cimloop.yaml` and injected into `synth_dse.tcl` by `eda_server_scripts/json_to_svh.py`.

#### 5.2.1 Effort Flags

| YAML Parameter | Allowed Values | DC Effect |
| :--- | :--- | :--- |
| `syn_map_effort` | `low`, `medium`, `high` | `set_app_var compile_map_effort <value>` |
| `syn_opt_effort` | `low`, `medium`, `high` | `set_app_var compile_opt_effort <value>` |

#### 5.2.2 Granular Strategy Flags

Each flag is independent; TCL commands are composed in `_build_synth_strategy_block()` inside `json_to_svh.py`:

| YAML Parameter | DC Effect when `"true"` |
| :--- | :--- |
| `enable_clock_gating` | `set_clock_gating_style` + `insert_clock_gating` |
| `max_area_ignore_tns` | `set_max_area 0 -ignore_tns` (else `set_max_area 0`) |
| `enable_retime` | `-retime` in `compile_ultra` |
| `compile_timing_high_effort` | `-timing_high_effort_script` |
| `compile_area_high_effort` | `-area_high_effort_script` |
| `compile_ultra_gate_clock` | `-gate_clock` |
| `compile_exact_map` | `-exact_map` |
| `compile_no_autoungroup` | `-no_autoungroup` |
| `compile_clock_gating_through_hierarchy` | `set compile_clock_gating_through_hierarchy true` |
| `enable_leakage_optimization` | `set_leakage_optimization true` |
| `enable_dynamic_optimization` | `set_dynamic_optimization true` |
| `enable_enhanced_resource_sharing` | `set compile_enhanced_resource_sharing true` |
| `dp_smartgen_strategy` | `none` \| `timing` \| `area` → `set_dp_smartgen_options -optimization_strategy <value>` |

**Synth Mode × Top Module Matrix:**

| | `top_module=core` | `top_module=hd_top` |
| :--- | :--- | :--- |
| `synth_mode=slow` | Full RTL + PatterNet; tb_core_timing | HD core only; tb_hd_top_timing |
| `synth_mode=fast` | PatterNet black-box; tb_core_timing | HD core only; tb_hd_top_timing |

See [docs/synth_decision_diagram.md](docs/synth_decision_diagram.md) for the full decision diagram.

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
| `reram_size` | `` `RRAM_ROW_ADDR_WIDTH `` | \( W = \lceil \log_2(\text{reram\_size}) \rceil \) |
| `hd_dim` | `` `HV_LENGTH `` | Direct; **max 8191** (HAMMING_DIST_WIDTH=13 ⇒ \( 2^{13}-1 \)) |
| `inner_dim` | `` `INNER_DIM `` / `` `WEIGHT_MEM_ADDR_WIDTH `` | See Eq. (1)–(2) below |
| `cnn_x_dim_1` × `cnn_y_dim_1` | `` `CNN1_INPUTS_NUM `` | Product |
| `cnn_x_dim_2` × `cnn_y_dim_2` | `` `CNN2_INPUTS_NUM `` | Product |
| `encoder_x_dim` × `encoder_y_dim` | `` `ENC_INPUTS_NUM `` | Product |
| `hd_dim` / (`encoder_x_dim` × `encoder_y_dim`) | `` `HV_SEG_WIDTH `` | Integer division; constraints: \( \text{HV\_SEG\_WIDTH} \geq 20 \), \( \text{WEIGHT\_BUS\_WIDTH} \bmod \text{HV\_SEG\_WIDTH} = 0 \), \( \text{TRAINING\_DATA\_NUM} \times \text{HV\_SEG\_WIDTH} \leq 512 \) |
| `frequency` | DC TCL `create_clock -period` | \( T_{\text{clk}} = 10^9 / f \) (ns) |

#### 5.4.1 inner_dim → WEIGHT_MEM_ADDR_WIDTH Derivation

Encoder weight RF rows are determined by the inner dimension:

\[
N_{\text{RF}} = \frac{\text{inner\_dim}}{\text{OUTPUTS\_NUM}}, \quad \text{OUTPUTS\_NUM} = 32
\]

\[
\text{WEIGHT\_MEM\_ADDR\_WIDTH} = \lceil \log_2(N_{\text{RF}}) \rceil
\]

| `inner_dim` | \( N_{\text{RF}} \) | `WEIGHT_MEM_ADDR_WIDTH` |
| :--- | :--- | :--- |
| 1024 | 32 | 5 |
| 2048 | 64 | 6 |
| 4096 | 128 | 7 |

Testbench weight word count:

\[
N_{\text{WEIGHT\_WORDS}} = 2^{\text{WEIGHT\_MEM\_ADDR\_WIDTH}} \times \frac{\text{WEIGHT\_BUS\_WIDTH}}{\text{HV\_SEG\_WIDTH}}
\]

#### 5.4.2 HAM_SEG Config Word Format (Testbench → RTL)

| Testbench | Config Address | Format | num_class-1 | num_feat_seg-1 |
| :--- | :--- | :--- | :--- | :--- |
| tb_core_timing | inp_buf[0] | 64-bit | bits [19:13] (7 bits) | bits [12:9] (4 bits) |
| tb_hd_top_timing | inp_buf[64] | 16-bit | bits [15:12] (4 bits) | bits [11:8] (4 bits) |

Both formats support 10 classes (MNIST/CIFAR-10). See [docs/hardware_modification_report.md](docs/hardware_modification_report.md) for RTL handoff.

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
│   ├── synth_decision_diagram.md      # SYNTH_MODE × TOP_MODULE decision diagram (Mermaid)
│   └── hardware_modification_report.md  # RTL changes for inner_dim param & 10-class inference
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
- [x] Granular synthesis flags (replacing `synth_profile`); `hd_dim` upper bound enforced at 8191.
- [x] `inner_dim` → `WEIGHT_MEM_ADDR_WIDTH`; testbenches support 10-class inference; hardware modification report for RTL handoff.
- [ ] Define hard boundary constraints for all BO parameters (min/max bounds).
- [ ] **Cross-Path Calibration:** Use Path 2/3 physical data to calibrate Path 1 analytical models.
