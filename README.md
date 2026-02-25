# Full-Stack Accelerator Optimization Framework: Architecture & Implementation Plan
**Focus:** Multi-fidelity Design Space Exploration (DSE) for HDnn-PIM Architecture

## 1. Project Overview & Exploration Strategy
This project aims to build an automated, closed-loop Design Space Exploration (DSE) framework to optimize a parameterized Processing-in-Memory (PIM) accelerator for Hyperdimensional Neural Networks (HDnn).

### 1.1 Core Algorithm: Bayesian Optimization (BO)
* **Rationale:** The hardware design space is high-dimensional, and physical hardware evaluations (synthesis/simulation) are highly expensive. BO is chosen for its sample-efficient nature, effectively balancing **exploration** (searching new configurations) and **exploitation** (refining known good configurations).
* **Current Development Phase:** The decision logic (BO "brain") is intentionally decoupled from the evaluation pipeline ("muscle"). Currently, the framework acts as a robust executor, accepting manually or randomly generated YAML configurations. This ensures the backend automation and remote EDA execution flows are 100% validated before integrating the intelligent search algorithm.

---

## 2. Multi-Fidelity Evaluation Pipeline
To overcome the evaluation bottleneck, the framework employs a three-tiered pipeline. This structure progressively evaluates designs from low to high fidelity, utilizing **Early Stopping (Gatekeeping)** mechanisms to discard sub-optimal configurations early and save compute time.

### 2.1 Path 1: Fast Software Simulation (1-min scale)
* **Purpose:** High-level algorithmic and analytical hardware estimation to rapidly prune the design space.
* **Engine:** Python-based simulator adapted from the existing `HDnn-PIM-Opt/sim` repository. A standardized Python adapter (`Path1Evaluator`) wraps the existing simulator to decouple argument parsing and enable direct dictionary/kwargs injection.
* **Evaluation Metrics:**
  * **Accuracy:** Golden model accuracy.
  * **Energy:** $\text{Unit Cost} \times N_{\text{OPS}}$
  * **Time:** $\text{Clock Period} \times N_{\text{OPS}}$
  * **Area:** $\sum \text{Datapath Components}$
* **Gatekeeping (Gate 1):** If the estimated accuracy falls below an acceptable threshold or area exceeds constraints, the configuration is immediately discarded.

### 2.2 Path 2: Hardware Synthesis (10-min scale)
* **Purpose:** Medium-fidelity evaluation to obtain accurate post-synthesis area and timing metrics.
* **Engine:** Synopsys Design Compiler (DC Synth).
* **Evaluation Metrics:**
  * **Area:** $\sum \text{Component Area}$ (Accurate gate-level area considering optimization and resource sharing).
  * **Timing:** $\text{Clock Period}$ (Accurate critical path delay).
  * **Power:** Unit Power (Note: Provides accurate Static/Leakage power; Dynamic power is estimated based on default toggle rates and serves only as a relative trend).
* **Gatekeeping (Gate 2):** If the synthesized netlist fails to meet the target Clock Period (Timing Violation), the design is discarded, preventing unnecessary simulation.

### 2.3 Path 3: Gate-Level Simulation & Power Analysis (30-min+ scale)
* **Purpose:** High-fidelity evaluation acting as the absolute ground truth for dynamic power consumption and cycle-accurate performance.
* **Engine:** Synopsys VCS + PrimeTime PX (PtPX).
* **Workflow:** VCS runs the synthesized netlist against configuration-aware testbenches to generate accurate switching activity files (SAIF/FSDB). These activity files are then fed into PtPX (or DC) to calculate exact dynamic power.
* **Evaluation Metrics:**
  * **Time:** $\text{Period} \times N_{\text{Exec Cycles}}$
  * **Energy:** $\text{Unit Power} \times \text{Time}$

---

## 3. Configuration Management & Hardware Isolation
The framework adheres to a strict **"Zero-Touch RTL"** principle. The core SystemVerilog design is completely isolated from the exploration logic to prevent breaking verified hardware.

### 3.1 YAML-Driven Configuration
All tunable parameters are centrally defined in a `config.yaml` file, ensuring human-readability, reproducibility, and version control friendliness.

### 3.2 SystemVerilog Parameter Injection & Categorization
A dedicated Python translation script (`yaml_to_svh.py`) parses the YAML and generates a SystemVerilog macro header (`config_macros.svh`). Based on RTL analysis, parameters are strictly categorized to constrain the search space:

* **Category A: Fixed Parameters (Do Not Touch)**
  * *Purpose:* Infrastructure, EDA flags, and ISA definitions.
  * *Examples:* `` `USE_DW ``, `` `USE_CW ``, `` `READ_FEAT_PATTERNET `` ~ `` `HD_PRED ``, `` `INST_WIDTH ``, `` `JTAG_LEN ``.
* **Category B: Tunable Parameters (Exploration Space via YAML)**
  * *Compute & Datapath:* `` `INPUTS_NUM ``, `` `OUTPUTS_NUM ``, `` `HV_SEG_WIDTH ``, `` `MAX_CLASS_NUM ``, `` `SP_TRAINING_WIDTH ``.
  * *Memory Sizing:* `` `PRE_FETCH_SIZE ``, `` `NUM_RF_BANK ``, `` `INP_BUF_ADDR_WIDTH ``, `` `DATA_BUF_ADDR_WIDTH ``, `` `RRAM_ROW_ADDR_WIDTH ``.
  * *FIFO Depths:* `` `CDC_INST_FIFO_DEPTH ``, `` `CDC_IO_FIFO_DEPTH ``, `` `INST_FIFO_DEPTH ``, `` `IO_FIFO_DEPTH ``.
* **Category C: Derived Parameters (Handled by Python Translation Layer)**
  * *Purpose:* Parameters that depend on mathematical relationships. The Python script calculates these automatically to ensure valid RTL generation.
  * *Examples:* `` `CLASS_LABEL_WIDTH `` (calculated as `$clog2(MAX_CLASS_NUM)`), `` `WEIGHT_BUS_WIDTH `` (calculated as `WEIGHT_MEM_DATA_WIDTH * NUM_RF_BANK`).

---

## 4. Automation & Remote Execution Infrastructure

Due to strict EDA tool licensing constraints, local execution of Path 2/3 is not possible. The framework implements a localized Client-Server architecture.

* **Local Host (Exploration Node):**
  * Runs the BO algorithm and evaluation pipeline logic.
  * Generates YAML configurations.
  * Acts as a Socket Client, sending configuration payloads to the remote host.
* **Remote Host (Licensed EDA Node):**
  * Runs a Socket Server (Tcl/Python).
  * Listens for incoming configurations.
  * Translates YAML to `.svh` (or receives it directly).
  * Triggers Makefile execution for Design Compiler and VCS.
* **Automated Telemetry Extraction:**
  * Custom Python regex-based parsers (`parse_dc.py`, `parse_vcs.py`) automatically extract critical metrics (Area, Critical Path Slack, Leakage/Dynamic Power, Cycle Counts) from massive unstructured EDA logs.
  * Parsed results are condensed into structured JSON dictionaries and returned via socket to the Local Host.

---

## 5. Pre-Implementation Research & Pending Action Items
Before writing the core automation scripts, the following research and planning tasks must be completed to ensure a smooth and bug-free integration phase. This acts as our immediate To-Do list:

### 5.1 Path 1: Software Simulator (`HDnn-PIM-Opt`) Profiling
- [ ] **Input Parameter Mapping:** Identify the exact Python variables/arguments in the `sim` folder that correspond to our Tunable Hardware Parameters (e.g., mapping YAML's `hv_seg_width` to the script's internal variable).
- [ ] **Output Metric Standardization:** Determine how the current simulator outputs Accuracy, Area, Power, and Timing. Plan the modifications needed to make it return a standard Python dictionary instead of `print()` statements.
- [ ] **Headless Execution:** Ensure the `sim` code can run entirely in the background. Identify and comment out any GUI triggers, `matplotlib` plotting, or interactive prompts.

### 5.2 Path 2/3: EDA Automation & Log Parsing Strategy
- [ ] **EDA Script Standardization:** Draft the exact `Makefile` or Tcl scripts needed to run Design Compiler and VCS strictly from the command line (batch mode, no GUI).
- [ ] **Log File Identification (Crucial):** Run a manual DC and VCS flow *once*. Identify exactly which `.rpt` or `.log` files contain the Critical Path Slack, Total Area, and Power numbers so we know where to point our regex parsers.
- [ ] **Power Analysis Flow Pipeline:** Research and map out the exact command sequence to take the VCS simulation output (SAIF/FSDB file) and feed it into PrimeTime PX (PtPX) or DC to get the accurate dynamic power.

### 5.3 Infrastructure: Translation Layer & Remote Communication
- [ ] **Derived Parameter Math (`yaml_to_svh.py`):** Document the exact mathematical formulas needed for all Category C parameters (e.g., how to implement `$clog2` correctly in Python).
- [ ] **Socket Payload Schema:** Define the exact JSON structure that will be sent from the Local Client to the Remote Server (e.g., `{ "job_id": 123, "config_yaml": "..." }`), and the expected format for the return payload.
- [ ] **Timeout & Error Handling:** Plan how the local script should react if the remote EDA tool hangs, crashes, or fails due to license unavailability.

### 5.4 Algorithm Preparation: Bounding the Design Space
- [ ] **Define Parameter Constraints:** For every parameter in Category B, explicitly define the absolute Minimum, Maximum, and valid Step Size (e.g., must be a power of 2, or must be an even number). This is essential to prevent the future Bayesian Optimization algorithm from generating mathematically impossible hardware geometries.