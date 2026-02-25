# Full-Stack Accelerator Optimization Framework

**Focus:** Multi-fidelity Design Space Exploration (DSE) for HDnn-PIM Architecture  
**Status:** Phase 2 (Baseline Exploration Flow) Implemented

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

```mermaid
flowchart TB
    subgraph Client ["Client (Local Docker Workspace)"]
        A[BO Engine<br/>Ax/BoTorch] --> B(Evaluators)
        B --> C[Path 1: Software Simulation<br/>Cimloop + Timeloop]
        B --> D[Path 2/3: Hardware<br/>EDA Client Socket]
    end

    subgraph Server ["EDA Server (Remote Host)"]
        E[EDA Socket Server<br/>Port 5000] --> F[Task Queue]
        F --> G[json_to_svh.py<br/>Macro & TCL Gen]
        G --> H[Design Compiler<br/>Synthesis]
        H --> I[Regex Parsers<br/>parse_dc.py]
    end

    D <-->|JSON over TCP<br/>Polling Mechanism| E
```

---

## 3. Multi-Fidelity Evaluation Pipeline

To overcome the evaluation bottleneck, the framework employs a three-tiered pipeline with **Early Stopping (Gatekeeping)** mechanisms.

```mermaid
flowchart TD
    Start([New Configuration from BO]) --> Path1[Path 1: Fast Software Simulation<br/>1-min scale]
    
    Path1 --> Gate1{Gate 1:<br/>Accuracy >= Threshold?}
    Gate1 -- No --> Fail1([mark_trial_failed])
    
    Gate1 -- Yes --> Path2[Path 2: Hardware Synthesis<br/>10-min scale]
    Path2 --> Gate2{Gate 2:<br/>Timing Slack >= 0?}
    Gate2 -- No --> Fail2([mark_trial_failed])
    
    Gate2 -- Yes --> Path3[Path 3: Gate-Level Simulation<br/>30-min scale]
    Path3 --> Done([Record Successful Trial])

    style Gate1 fill:#f9d0c4,stroke:#333,stroke-width:2px
    style Gate2 fill:#f9d0c4,stroke:#333,stroke-width:2px
```

### 3.1 Path 1: Fast Software Simulation
* **Engine:** `path1_software.py` (Calls Cimloop + Timeloop)
* **Gate 1:** If PyTorch accuracy is below the defined constraint, the trial is marked as failed without penalty injection.

### 3.2 Path 2: Hardware Synthesis (Client-Side Stitching)
* **Engine:** `path2_hardware.py`
* **Stitching Logic:** Since the RRAM portion lacks RTL, Path 2 stitches ASIC data (from the EDA server) with RRAM data (re-run locally via Cimloop).
  * `Total Timing = ASIC Delay (EDA) + RRAM Delay (Cimloop)`
  * `Total Energy = ASIC Power (EDA) * Total Timing + RRAM Energy (Cimloop)`
* **Gate 2:** If the synthesized netlist violates timing constraints (`slack < 0`), the trial fails.

---

## 4. EDA Server Protocol (Black-Box API)

To navigate restrictive corporate firewalls, large `.rpt` files are never transferred. The EDA Server "locally extracts" metrics and returns a tiny JSON payload.

```mermaid
sequenceDiagram
    participant BO as BO Engine (Client)
    participant Client as EDA Client
    participant Server as EDA Server
    participant DC as Design Compiler

    BO->>Client: evaluate_remote(params)
    Client->>Server: POST {"action": "submit", "params": {...}}
    Server-->>Client: {"status": "accepted", "job_id": 101}
    
    Note over Server,DC: Worker thread pops job 101<br/>Generates config_macros.svh
    Server->>DC: subprocess.run(["make", "synth"])
    
    loop Every 15 seconds
        Client->>Server: GET {"action": "status", "job_id": 101}
        Server-->>Client: {"status": "running"}
    end
    
    DC-->>Server: Generates .rpt files
    Server->>Server: parse_dc.py extracts Area, Timing, Power
    
    Client->>Server: GET {"action": "status", "job_id": 101}
    Server-->>Client: {"status": "success", "metrics": {...}}
    Client-->>BO: Return ASIC PPA metrics
```

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

### 5.2 Software-to-RTL Mapping Table
Implemented in `eda_server_scripts/json_to_svh.py`.

| Software Parameter | Hardware Macro (`config_macros.svh`) | Mathematical Conversion |
| :--- | :--- | :--- |
| `reram_size` | `` `RRAM_ROW_ADDR_WIDTH `` | `ceil(log2(reram_size))` |
| `hd_dim` | `` `HV_LENGTH `` | Direct |
| `inner_dim` | `` `INNER_DIM `` | Direct |
| `cnn_x_dim_1` × `cnn_y_dim_1` | `` `INPUTS_NUM `` (Layer 1) | Product |
| `encoder_x_dim` × `encoder_y_dim` | `` `ENC_INPUTS_NUM `` | Product |
| `hd_dim` / (`encoder_x_dim` × `encoder_y_dim`) | `` `HV_SEG_WIDTH `` | Integer Division |
| `frequency` | DC TCL `create_clock -period` | `1e9 / frequency` (ns) |

---

## 6. Directory Structure

```text
Full-Stack-Accelerator-Optimization/
│
├── run_exploration.py                 # Main entry point (CLI args for Path 2/3)
│
├── workspace/                         # Local execution environment
│   ├── dse_framework/                 # [Core] DSE Control Center
│   │   ├── evaluators/                # Evaluator Wrappers (Path 1 & 2)
│   │   ├── network/                   # Socket Client (Polling Protocol)
│   │   └── core_algorithm/            # BO Engine & Dynamic Normalizer
│   │
│   ├── HDnn-PIM-Opt/                  # Pure software evaluator (Path 1 / Cimloop)
│   └── conf/                          # Hydra configurations (YAML)
│
└── eda_server_scripts/                # Deploy on remote EDA Server
    ├── eda_server.py                  # Socket Server (Queue + Timeout)
    ├── json_to_svh.py                 # Macro & TCL generation
    └── parsers/                       # DC and VCS regex parsers
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

### Phase 3 & 4: Verification & Full BO Integration [⏳ PENDING]
- [ ] Establish VCS → PtPX SAIF handoff pipeline (`parse_vcs.py`).
- [ ] Define hard boundary constraints for all BO parameters (min/max bounds).
- [ ] **Cross-Path Calibration:** Use Path 2/3 physical data to calibrate Path 1 analytical models.
