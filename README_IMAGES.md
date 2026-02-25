# README Diagrams (Mermaid)

This file contains all Mermaid diagrams referenced from [README.md](README.md). Render this file in a Markdown viewer that supports Mermaid (e.g. GitHub, VS Code) to see the figures.

---

## 1. System Architecture (Thin-Client Model)

*Referred from README §2.*

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

## 2. Multi-Fidelity Evaluation Pipeline

*Referred from README §3.*

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

---

## 3. Phase 3 Testbench Architecture and Data Flow

*Referred from README §3.3.*

```mermaid
flowchart TD
    subgraph Client ["Client (Docker)"]
        P1[Path 1: PyTorch Model] -->|Dump| H1(inputs.hex)
        P1 -->|Dump| H2(labels.hex)
        P1 -->|Dump| H3(weights.hex)
        
        SW_Params[YAML: num_tests, frequency] --> JSON[JSON Payload]
        H1 -.->|Base64 or Text| JSON
        H2 -.-> JSON
        H3 -.-> JSON
    end

    subgraph Server ["EDA Server (VCS + PtPX)"]
        JSON -->|Extract| S_Data[data/ Directory]
        JSON -->|Generate| S_Macro[`tb_macros.svh`]
        
        S_Macro -->|TB_CLK_PERIOD_NS<br/>TB_NUM_VECTORS| TB[`tb_top.sv`]
        S_Data -->| $readmemh | TB
        
        Netlist[`synth_netlist.v`] --> TB
        
        TB -->|Run Simulation| VCS[Synopsys VCS]
        
        VCS -->|1. Print| Log[`vcs.log`]
        VCS -->|2. Dump| SAIF[`activity.saif`]
        
        Log -->|Parse| Cycles[Execution Cycles & HW Accuracy]
        SAIF --> PtPX[PrimeTime PX] --> Power[Exact Dynamic Power]
    end
    
    style TB fill:#d4edda,stroke:#333,stroke-width:2px
    style Netlist fill:#cce5ff,stroke:#333,stroke-width:2px
```

---

## 4. EDA Server Protocol (Polling Sequence)

*Referred from README §4.*

```mermaid
sequenceDiagram
    participant BO as BO Engine (Client)
    participant Client as EDA Client
    participant Server as EDA Server
    participant DC as Design Compiler

    BO->>Client: evaluate_remote(params)
    Client->>Server: POST action submit params
    Server-->>Client: status accepted job_id 101
    
    Note over Server,DC: Worker thread pops job 101<br/>Generates config_macros.svh
    Server->>DC: subprocess.run make synth
    
    loop Every 15 seconds
        Client->>Server: GET action status job_id 101
        Server-->>Client: status running
    end
    
    DC-->>Server: Generates .rpt files
    Server->>Server: parse_dc.py extracts Area, Timing, Power
    
    Client->>Server: GET action status job_id 101
    Server-->>Client: status success metrics
    Client-->>BO: Return ASIC PPA metrics
```

---

## 5. Synthesis Profile to TCL Injection (Config Flow)

*Referred from README §5.2.*

```mermaid
flowchart LR
    subgraph Client ["Client (BO Engine)"]
        A[config.yaml] -->|Generate| B(JSON Payload)
        B -.->|Includes synth_profile| C
    end

    subgraph Server ["EDA Server"]
        C[eda_server.py] --> D[json_to_svh.py]
        
        D -->|1. Write Macros| E[`config_macros.svh`]
        
        D -->|2. Inject Strategy| F[`synth.tcl`]
        
        F --> F1["insert_clock_gating"]
        F --> F2["compile_ultra -retime -timing_high_effort_script"]
        F --> F3["set_dp_smartgen_options -strategy ..."]
        
        E --> G[Design Compiler]
        F --> G
    end
```
