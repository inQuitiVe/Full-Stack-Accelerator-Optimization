# Full-Stack Accelerator Optimization Framework: Architecture & Implementation Plan
**Focus:** Multi-fidelity Design Space Exploration (DSE) for HDnn-PIM Architecture
**Last Updated:** Phase 2 (Baseline Exploration Flow) In Progress

## 1. Project Overview & Exploration Strategy [STATUS: DEFINED]
This project aims to build an automated, closed-loop Design Space Exploration (DSE) framework to optimize a parameterized Processing-in-Memory (PIM) accelerator for Hyperdimensional Neural Networks (HDnn).

### 1.1 Core Algorithm: Bayesian Optimization (BO)
* **Rationale:** The hardware design space is high-dimensional, and physical hardware evaluations (synthesis/simulation) are highly expensive. BO is chosen for its sample-efficient nature, effectively balancing **exploration** (searching new configurations) and **exploitation** (refining known good configurations).
* **Current Development Phase:** The decision logic (BO "brain") is intentionally decoupled from the evaluation pipeline ("muscle"). Currently, the framework acts as a robust executor, accepting manually or randomly generated YAML configurations. This ensures the backend automation and remote EDA execution flows are 100% validated before integrating the intelligent search algorithm.

---

## 2. Parameter Space Classification & Mapping [STATUS: DONE]
To maintain the "Zero-Touch RTL" principle and ensure hardware/software consistency, parameters are strictly categorized. All tunable parameters are centrally defined in a `config.yaml` file, ensuring human-readability and version control friendliness.

### 2.1 Software Parameter Categorization (Path 1 Inputs)
Software parameters (`SW params`) are divided into two categories to clarify what impacts the hardware generation versus what only impacts the algorithmic training/dataflow.

* **Category 1: Hardware-Related (Alters RTL Geometry & Memory)**
  * `hd_dim`, `inner_dim`: Dictates datapath width, counter sizes, and SRAM dimensions.
  * `reram_size`: Dictates the RRAM array dimensions and address widths.
  * `cell_bit`: Influences the precision and analog-to-digital interface in CIM.
  * `cnn_x_dim_1/2`, `cnn_y_dim_1/2`, `encoder_x_dim/y_dim`: Spatial mapping dimensions that dictate the physical parallelization (number of Processing Elements, Inputs/Outputs).
  * `num_classes`: Dictates the sizing of the search/associative memory and label buses.

* **Category 2: Training & Dataflow-Related (No RTL Impact)**
  * `dataset_name`, `num_tests`: Evaluation dataset configuration.
  * `hd_epochs`, `hd_lr`, `cnn_epochs`, `cnn_lr`: Training hyperparameters.
  * `noise`, `temperature`, `frequency`: Environmental simulation conditions for Path 1 analytical models.

### 2.2 SystemVerilog Parameter Injection & Translation Layer
A dedicated Python translation script (`yaml_to_svh.py`) parses the YAML and generates a SystemVerilog macro header (`config_macros.svh`). 

* **Category A: Fixed Parameters (Do Not Touch)**
  * *Examples:* `` `USE_DW ``, `` `USE_CW ``, `` `READ_FEAT_PATTERNET `` ~ `` `HD_PRED ``, `` `INST_WIDTH ``, `` `JTAG_LEN ``.
* **Category B: Tunable Parameters (Direct Injection via YAML)**
  * *Examples:* `` `INPUTS_NUM ``, `` `OUTPUTS_NUM ``, `` `HV_SEG_WIDTH ``, `` `PRE_FETCH_SIZE ``, `` `INST_FIFO_DEPTH ``.
* **Category C: Derived Parameters (Handled by Python Logic)**
  * The script applies strict mathematical relationships to ensure valid RTL generation:

| Software Parameter | Hardware Parameter (`SystemVerilog Macro`) | Mathematical Conversion / Logic |
| :--- | :--- | :--- |
| `reram_size` | `RRAM_ROW_ADDR_WIDTH` | $\lceil \log_2(reram\_size) \rceil$ |
| `num_classes` | `CLASS_LABEL_WIDTH` | $\lceil \log_2(\text{num\_classes}) \rceil$ |
| `hd_dim` / Spatial Dims | `HV_SEG_WIDTH` | Derivation based on PE array sizing |
| *Derived Internally* | `WEIGHT_BUS_WIDTH` | $\text{WEIGHT\_MEM\_DATA\_WIDTH} \times \text{NUM\_RF\_BANK}$ |

---

## 3. Multi-Fidelity Evaluation Pipeline [STATUS: DEFINED]


To overcome the evaluation bottleneck, the framework employs a three-tiered pipeline. This structure progressively evaluates designs from low to high fidelity, utilizing **Early Stopping (Gatekeeping)** mechanisms to discard sub-optimal configurations early and save compute time.

### 3.1 Path 1: Fast Software Simulation (1-min scale)
* **Purpose:** High-level algorithmic and analytical hardware estimation to rapidly prune the design space.
* **Engine:** Python wrapper (`Path1Evaluator`) around `HDnn-PIM-Opt/sim` decoupled via kwargs injection.
* **Evaluation Metrics (Standardized):**
  * **Accuracy:** Golden model accuracy.
  * **Energy:** $(\text{Timeloop uJ} + \text{CimLoop uJ}) \times 10^6 \rightarrow \text{pJ}$
  * **Time:** $\max(\text{Timeloop Clock}, \text{CimLoop Clock}) \times 10^3 \rightarrow \text{ns}$
  * **Area:** $(\text{Timeloop mm}^2 + \text{CimLoop mm}^2) \times 10^6 \rightarrow \text{um}^2$
* **Gatekeeping (Gate 1):** If the estimated accuracy falls below an acceptable threshold or area exceeds constraints, the configuration is immediately discarded.

### 3.2 Path 2: Hardware Synthesis (10-min scale)
* **Purpose:** Medium-fidelity evaluation to obtain accurate post-synthesis area and timing metrics.
* **Engine:** Synopsys Design Compiler (DC Synth).
* **Evaluation Metrics:**
  * **Area:** $\sum \text{Component Area}$ ($\text{um}^2$, considering optimization and resource sharing).
  * **Timing:** $\text{Clock Period}$ ($\text{ns}$, accurate critical path delay).
  * **Power:** Unit Power (Static/Leakage power is accurate; Dynamic serves as a relative trend).
* **Gatekeeping (Gate 2):** If the synthesized netlist fails to meet the target Clock Period (Timing Violation, Slack < 0), the design is discarded.

### 3.3 Path 3: Gate-Level Simulation & Power Analysis (30-min+ scale)
* **Purpose:** High-fidelity evaluation acting as the absolute ground truth for dynamic power consumption and cycle-accurate performance.
* **Engine:** Synopsys VCS + PrimeTime PX (PtPX).
* **Workflow:** VCS runs the synthesized netlist against configuration-aware testbenches to generate accurate switching activity files (SAIF/FSDB). These activity files are then fed into PtPX (or DC) to calculate exact dynamic power.
* **Evaluation Metrics:**
  * **Time:** $\text{Period} \times N_{\text{Exec Cycles}}$
  * **Energy:** $\text{Unit Power} \times \text{Time}$

---

## 4. Automation & Remote Execution Infrastructure [STATUS: IN PROGRESS]
[Image of client-server network architecture diagram]

Due to strict EDA tool licensing constraints, local execution of Path 2/3 is not possible. The framework implements a localized TCP/IP Client-Server architecture.

### 4.1 Detailed Implementation Strategy
* **Local Host (Exploration Client):**
  * Runs the BO algorithm in Python.
  * Serializes the `{SW params, HW spec}` configuration into a JSON payload.
  * Opens a socket connection, sends the JSON, and waits for a response (blocking with timeout).
* **Remote Host (Licensed EDA Server):**
  * Runs a persistent Python socket server listening on a specific port.
  * **Execution Flow:**
    1. Receives JSON config and writes it to a temporary `config.yaml`.
    2. Executes `python yaml_to_svh.py` to generate `config_macros.svh`.
    3. Uses `subprocess.run(["make", "synth"])` to headlessly trigger Design Compiler.
    4. Triggers the Regex Log Parser (see Section 5) to extract PPA.
    5. Packages extracted metrics into a JSON response and sends it back to the Client.
* **Error Handling:** If `subprocess` returns a non-zero exit code (e.g., DC crashes due to unroutable RTL), the server catches the exception and returns a JSON payload with `"status": "error"` and a massive penalty score to the BO algorithm.

---

## 5. EDA Log Parsing Strategy [STATUS: IN PROGRESS]
To automate data extraction from massive Synopsys text reports, the framework uses custom Python regex-based parsers (`parse_dc.py`, `parse_vcs.py`).

### 5.1 Design Compiler (DC) Parsing Logic
The script reads output `.rpt` files generated by the Makefile:

* **1. Parsing Area (`report_area.rpt`):**
  * Look for the line indicating total combinatorial and non-combinatorial area.
  * *Regex:* `r"Total cell area:\s+([0-9.]+)"`
  * *Python:* `match.group(1)` yields the exact float value.
* **2. Parsing Timing (`report_timing.rpt`):**
  * Look for the final slack margin.
  * *Regex (Slack):* `r"slack\s+\((MET|VIOLATED)\)\s+([-\.0-9]+)"`
  * *Logic:* If group 1 is "VIOLATED", Gate 2 logic immediately flags the design as failed.
* **3. Parsing Power (`report_power.rpt`):**
  * *Regex (Dynamic):* `r"Total Dynamic Power\s+=\s+([0-9.]+)\s+(\w+)"` (Group 2 captures units like `mW` or `uW` for auto-scaling).
  * *Regex (Leakage):* `r"Cell Leakage Power\s+=\s+([0-9.]+)\s+(\w+)"`

---

## 6. Pre-Implementation To-Do List [STATUS: PENDING]

### Phase 2: Automation Baseline (Immediate Focus)
- [ ] **Task 1: The Translation Script.** Write `yaml_to_svh.py` implementing the exact math defined in Section 2.2.
- [ ] **Task 2: Socket Server.** Write `server.py` and `client.py` using standard Python `socket` and `json` libraries. Implement a basic handshake.
- [ ] **Task 3: Makefiles.** Standardize the `Makefile` for DC and VCS so they can be executed headlessly without GUI (`-no_gui` flag).
- [ ] **Task 4: Regex Parsers.** Write `parse_dc.py` and test it against a historically successful `.rpt` file to ensure the regex patterns are robust.

### Phase 3 & 4: Verification & Exploration
- [ ] Establish the VCS to PtPX SAIF handoff pipeline.
- [ ] Integrate Bayesian Optimization (e.g., using `Ax` or `BoTorch` libraries).
- [ ] Define hard boundary constraints (Min/Max values) for every parameter to prevent BO from generating illegal configurations.
- [ ] **Cross-Path Calibration:** Implement a feedback loop where physical hardware metrics from Path 2 and Path 3 are used to calibrate the analytical models in Path 1, minimizing Correlation Mismatch.