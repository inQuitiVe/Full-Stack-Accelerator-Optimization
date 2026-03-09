# 3. 提出的全端設計空間探索框架 (Proposed Full-Stack DSE Framework)

本節詳述所提框架，以填補第 2 節指出的研究缺口：將軟體參數、硬體架構與 EDA 合成旗標整合至單一搜尋空間，並透過邏輯合成與閘級模擬取得具保真度的 PPA。**核心設計邏輯為可修改性**：優化器、評估階段、門檻與資料來源均可依需求修改，使流程能適應不同約束與目標。以下依序說明框架總覽、Path 1–Path 3 整體規劃、系統架構與關鍵模組、參數轉換對應關係，以及合成旗標設計。

---

## 3.0 框架總覽 (Framework Overview)

**設計動機**：商用 EDA 工具（如 Synopsys Design Compiler、VCS）受授權與內網限制，難以與 Python/Docker 型 BO 框架直接綁定；且單次邏輯合成與閘級模擬耗時可觀（約 30–60 分鐘與 10–30 分鐘）。為此，我們採用 **Thin-Client 解耦架構**：Client 將參數打包為 JSON 發送至遠端 EDA Server；Server 動態產生 RTL 巨集與合成腳本，驅動 DC 合成與 VCS 模擬，並僅回傳數值化 PPA 指標。此架構解決授權問題，並具備高擴充性。

**形式化定義**：設計空間 \(\mathcal{X}\) 涵蓋軟體參數（如 \(D\)、\(\text{inner\_dim}\)、out_channels）、硬體參數（reram_size、encoder_x/y_dim、frequency）與 EDA 合成旗標。單次評估 \(e(\mathbf{x})\) 依提早停止條件分階段執行：

- **Gate 1**：\(\text{Accuracy}(\mathbf{x}) \geq \tau\)；若不滿足，\(e(\mathbf{x})\) 終止，**完全跳過硬體合成**。
- **Gate 2**：\(\text{Slack}(\mathbf{x}) \geq 0\)；若時序違例，Path 3 不觸發。

相較於對每個候選設計都執行完整合成與閘級模擬的 **naive baseline**，本框架透過 Gate 1 與 Gate 2 提早淘汰不具競爭力的設計，可顯著減少昂貴評估次數，並以多層次保真度（軟體模擬 → 邏輯合成 → 閘級模擬）逐步提升評估準確度。

---

## 3.1 Path 1–Path 3 整體規劃 (Overall Multi-Fidelity Pipeline)

本小節對應**貢獻 2**：可修改的多層次保真度評估與提早停止機制。

### 3.1.1 Path 1：軟體模擬 (Fast)

Client 端以 PyTorch 訓練 HDnn 模型並取得 Accuracy，同時以 Cimloop 估算 RRAM 能量與延遲。

**Gate 1**：若 Accuracy 低於使用者定義門檻 \(\tau\)（如 0.79），該 Trial 標記為失敗，**完全跳過後續硬體合成**。門檻 \(\tau\) 可依資料集與約束修改。

### 3.1.2 Path 2：硬體合成與混合拼接 (Medium)

通過 Gate 1 的參數送往 EDA Server 進行邏輯合成。由於 RRAM 缺乏標準 RTL，我們採用混合拼接策略：

\[
A_{\text{total}} = A_{\text{ASIC}} + A_{\text{RRAM}}, \quad T_{\text{total}} = T_{\text{ASIC}} + T_{\text{RRAM}}, \quad E_{\text{total}} = P_{\text{ASIC}} \cdot T_{\text{total}} + E_{\text{RRAM}}
\]

**Gate 2**：若合成網表發生時序違例（Slack \(< 0\)），該 Trial 判定失敗，Path 3 不觸發。

### 3.1.3 Path 3：閘級模擬與功耗驗證 (High Fidelity)

Path 3 僅在「通過 Gate 2 且使用者啟用 Path 3」時觸發。Server 於合成完成且無違例後執行 VCS 閘級模擬與 PrimeTime PX 功耗分析。**Path 3 的核心優勢在於功耗預測準確度**：VCS 閘級模擬產生實際波形，PtPX 依此 toggle 行為進行動態功耗分析，相較於 Path 1 的軟體能量估算與 Path 2 合成報告的靜態功耗分析，Path 3 能捕捉真實電路切換活動，預測準確度顯著較高。

**LFSR-based Testbench 設計動機與驗證**：傳統做法需從 PyTorch 傳輸大量 `.hex` 測試資料至 EDA Server，造成網路負擔與授權環境限制。我們採用 **LFSR 自產生測試平台**，在 Server 端本地產生 pseudo-random 刺激，精確記錄 ENC_PRELOAD → oFIFO 的 **COMPUTE CYCLES**，並產生 SAIF 供 PtPX 使用。LFSR 產生的 toggle 模式涵蓋典型推論 workload 的電路切換行為；其代表性經由與 golden 測試向量比對驗證，確保週期計數與功耗分析具正確性。Testbench 支援 `inner_dim` 驅動的 `N_WEIGHT_WORDS` 與 10 classes（MNIST/CIFAR-10）。

**Path 3 指標拼接公式**：

\[
T_{\text{ASIC}} = \frac{T_{\text{clk}} \times N_{\text{cycles}}}{1000} \text{ (µs)}, \quad E_{\text{ASIC}} = (P_{\text{dyn}} + P_{\text{leak}}) \times T_{\text{ASIC}}
\]

**表 3-1：LFSR Testbench 指令序列摘要**

| 階段 | 指令 | 目的 |
| :--- | :--- | :--- |
| Pre-setup | STORE_BUF | 載入 encoding weights、class HVs |
| Per-inference | STORE_BUF | 載入 input features |
| Compute | ENC_PRELOAD → ENC_SEG → STORE_BUF (HAM) → HAM_SEG → PRED | 編碼 → 漢明搜尋 → 輸出預測 |

**黑盒子快速合成與 synth_mode**：DSE 參數僅影響 HD 核心邏輯（Encoder、Search 等），PatterNet、系統介面等大型模組在搜尋過程中完全靜態。我們以白名單機制僅將隨參數變動的檔加入 DC `analyze` 清單，將靜態模組視為 Black Box，縮短合成時間。**synth_mode × top_module 二維決策**：`synth_mode=fast, top_module=hd_top` 用於前期快速掃描；對少數 Pareto 候選再以 `synth_mode=slow, top_module=core` 進行高保真驗證。

---

## 3.2 系統架構與關鍵模組 (System Architecture and Key Modules)

本小節對應**貢獻 1**：可修改的全端軟硬體與 EDA 聯合流程。表 3-2 概括 Thin-Client 架構與關鍵模組職責。

**Client 端**：優化引擎（Ax/BoTorch）負責參數搜尋與多目標評估；Path 1 評估器以 PyTorch 訓練 HDnn 模型並以 Cimloop 估算 RRAM 能量與延遲；Path 2/3 評估器將參數打包為 JSON、提交至遠端 EDA Server，並接收回傳的 PPA 指標。EDA 客戶端採用 **polling-based 非同步協定**：提交任務後不維持長連線，改以約 15 秒間隔輪詢 Server 狀態，直至任務完成或逾時（硬性逾時 30 分鐘）；此設計可避免企業防火牆對長連線的限制，並降低 Client 與 Server 的耦合度。

**Server 端**：任務佇列以單一 worker 執行緒序列處理 EDA 任務，確保 Design Compiler 授權不衝突。收到任務後，**參數轉換模組**（以 JSON 為輸入、stdin 傳遞）依軟體參數推導 RTL 巨集（如 HV_LENGTH、WEIGHT_MEM_ADDR_WIDTH、HV_SEG_WIDTH 等），並執行參數合法性檢查（如 hd_dim 整除 encoder 維度、reram_size 為 2 的冪次）；通過後寫入 `config_macros.svh` 至硬體專案 include 目錄。同時依 `synth_mode`（slow/fast）選擇 TCL 模板，注入 `create_clock` 週期（由 frequency 推得）、TOP_MODULE（core 或 hd_top）、以及細粒度合成旗標區塊，產生 `synth_dse.tcl`；並寫入 `tb_macros.svh`（含 TB_CLK_PERIOD_NS）供 LFSR testbench 使用。**Path 2**：Server 呼叫 `make synth`，以 `synth_dse.tcl` 驅動 Design Compiler 進行邏輯合成，輸出寫入 `fsl-hd/reports/`（report_area.rpt、report_timing.rpt、report_power.rpt）。**Path 3**：若 payload 含 `run_path3=True` 且 Gate 2 通過（slack ≥ 0），Server **跳過第二次 DC 呼叫**，直接重用同設計點的 netlist 與報告，改呼叫 `make sim`；Makefile 依 `TOP_MODULE` 選擇 tb_core_timing.sv 或 tb_hd_top_timing.sv，以 VCS 編譯並執行閘級模擬，testbench 以 LFSR 自產生刺激、輸出 `COMPUTE CYCLES` 至 vcs_simulation.log。**報告解析器**：parse_dc 以 regex 從 report_area、report_timing、report_power 萃取 area_um2、timing_slack_ns、clock_period_ns、dynamic_power_mw、leakage_power_mw；parse_vcs 從 vcs_simulation.log 萃取 execution_cycles（匹配 `COMPUTE CYCLES : <N>`）。Path 3 時合併兩者，以週期數與 DC 時脈週期計算精確執行時間，並可依 SAIF/VCD 活動檔升級功耗（PtPX）。最終僅回傳精簡 JSON 予 Client，**不傳輸 .rpt、.fsdb 等大型檔案**，以適應受限的網路環境。詳細通訊協定與檔案路徑見**附錄 A**。

---

## 3.3 參數轉換對應關係 (Parameter-to-RTL Conversion Mapping)

BO 搜尋空間由**搜尋空間定義檔**指定；**參數轉換模組**負責將軟體參數轉換為 RTL 巨集與 DC TCL。本小節對應**貢獻 3**：EDA 細粒度旗標探索的參數化基礎。

### 3.3.1 參數分類

| 類別 | 參數 | 影響範圍 |
| :--- | :--- | :--- |
| **HW (RTL 幾何)** | hd_dim, inner_dim, reram_size | HV_LENGTH, WEIGHT_MEM_ADDR_WIDTH, RRAM_ROW_ADDR_WIDTH |
| **HW (空間對映)** | cnn_x/y_dim_1/2, encoder_x/y_dim, out_channels_1/2 | CNN/Encoder PE 佈局、HV_SEG_WIDTH |
| **SW (無 RTL)** | dataset, hd_epochs, cnn_epochs, cnn | 僅 PyTorch 訓練 |
| **SW (時脈)** | frequency | DC create_clock、TB 時脈產生器 |
| **Synth (EDA)** | synth_mode, top_module, 細粒度旗標 | 合成策略區塊 |

### 3.3.2 軟體參數 → RTL 巨集轉換摘要

**表 3-3：關鍵轉換公式**

| 軟體參數 | RTL 巨集 | 轉換公式 |
| :--- | :--- | :--- |
| reram_size | RRAM_ROW_ADDR_WIDTH | \(\lceil \log_2(\text{reram\_size}) \rceil\)（reram_size 須為 2 的冪次） |
| hd_dim | HV_LENGTH | 直接對應（上限 8191） |
| inner_dim | WEIGHT_MEM_ADDR_WIDTH | \(\lceil \log_2(\text{inner\_dim} / 32) \rceil\) |
| encoder_x × encoder_y, hd_dim | HV_SEG_WIDTH | hd_dim ÷ (encoder_x × encoder_y)，須整除且 ≥ 20 |
| frequency | create_clock, TB_CLK_PERIOD_NS | \(T_{\text{clk}} = 10^9 / f\) (ns) |

**參數合法性約束**：轉換模組在產生 RTL 前執行事前驗證，包括：`hd_dim % (encoder_x_dim * encoder_y_dim) == 0`、`reram_size` 為 2 的冪次、`inner_dim >= 32`、`HV_SEG_WIDTH >= 20`、`256 % HV_SEG_WIDTH == 0`、`TRAINING_DATA_NUM * HV_SEG_WIDTH <= 512`。違反任一約束時，該設計點於轉換階段即被拒絕。完整轉換表見**附錄 B**。

---

## 3.4 合成旗標設計 (Synthesis Flags Design)

傳統 DSE 將 EDA 工具視為固定編譯器。本框架將 **Design Compiler 的細粒度合成旗標直接納入 BO 搜尋空間**（**貢獻 3**），將過去整包式策略拆解為多個獨立布林/選擇參數，大幅擴展探索空間。

### 3.4.1 努力度旗標

| 參數 | 允許值 | DC 效果 |
| :--- | :--- | :--- |
| syn_map_effort | low, medium, high | compile_map_effort |
| syn_opt_effort | low, medium, high | compile_opt_effort |

### 3.4.2 細粒度策略旗標摘要

**表 3-4：代表性合成旗標與 DC 對應**

| 參數 | DC 效果（啟用時） |
| :--- | :--- |
| enable_clock_gating | set_clock_gating_style + insert_clock_gating |
| enable_retime | compile_ultra -retime |
| compile_timing_high_effort | -timing_high_effort_script |
| compile_area_high_effort | -area_high_effort_script |
| enable_leakage_optimization | set_leakage_optimization true |
| enable_dynamic_optimization | set_dynamic_optimization true |
| dp_smartgen_strategy | none \| timing \| area → set_dp_smartgen_options |

完整 13+ 項旗標列表見**附錄 C**。

### 3.4.3 synth_mode × top_module 決策矩陣

| | top_module=core | top_module=hd_top |
| :--- | :--- | :--- |
| synth_mode=slow | 完整 RTL + PatterNet | HD 核心 |
| synth_mode=fast | PatterNet Black Box | HD 核心 |

透過硬體架構與 EDA 策略聯合優化，探索流程可在遭遇時序瓶頸時主動啟用 enable_retime 等策略彌補，發掘單一領域優化無法觸及的 Pareto 點。**可擴展性**：新增參數時，僅需在搜尋空間定義檔中宣告、並在參數轉換模組中實作對應的巨集或 TCL 注入邏輯；合成旗標的增減同樣遵循此模式，使框架能適應不同 EDA 工具與優化目標。

---

## 3.5 評估環境與搜尋空間 (Evaluation Environment and Search Space)

### 3.5.1 評估環境與工具 (Evaluation Environment and Tools)

**表 3-5：實驗環境配置**

| 層級 | 工具 / 環境 | 用途 |
| :--- | :--- | :--- |
| 軟體與 ML | Python 3, PyTorch | HDnn 模型訓練與推論 |
| 架構模擬 | Cimloop, Timeloop | RRAM 能量與延遲估算 |
| EDA 合成 | Synopsys Design Compiler | RTL 邏輯合成 |
| 閘級模擬 | VCS | 週期精確模擬 (LFSR testbench) |
| 功耗分析 | DC report_power | 動態與漏電功耗 |

**合成模式**：全實驗採用 `synth_mode=fast`、`top_module=hd_top`，以黑盒子快速合成等技巧縮短單次評估時間。資料集為 MNIST（10 classes）。

### 3.5.2 搜尋空間定義 (Search Space Definition)

設計空間涵蓋軟體、硬體與 EDA 三層抽象，關鍵參數如下。

**表 3-6：Full-Stack DSE 搜尋空間**

| 領域 | 參數 | 型別 | 數值範圍 / 選項 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **Software** | hd_dim | Choice | {2048, 4096} | 超維度 \(D\) |
| **Software** | inner_dim | Choice | {1024, 2048, 4096} | Encoder 內部維度 |
| **Hardware** | reram_size | Choice | {128, 256} | RRAM 陣列大小 |
| **Hardware** | out_channels_1/2 | Choice | {4,8,16} / {8,16,32} | CNN 輸出通道數 |
| **Hardware** | kernel_size_1/2 | Choice | {3, 5, 7} | 卷積核大小 |
| **Hardware** | frequency | Integer | 80–300 MHz | 目標時脈頻率 |
| **EDA** | syn_map_effort | Choice | {low, medium, high} | DC 映射努力度 |
| **EDA** | syn_opt_effort | Choice | {low, medium, high} | DC 優化努力度 |
| **EDA** | enable_clock_gating | Choice | {false, true} | 時脈閘控 |
| **EDA** | enable_retime | Choice | {false, true} | 暫存器重定時 |
| **EDA** | max_area_ignore_tns | Choice | {false, true} | 面積優先（可能違反 timing） |
| **EDA** | compile_timing_high_effort | Choice | {false, true} | 高時序優化 |
| **EDA** | dp_smartgen_strategy | Choice | {none, timing, area} | DP Smartgen 策略 |

---

## 附錄 A：通訊協定與檔案路徑 (Appendix A: Protocol and File Paths)

**Socket 協定**：TCP，預設 PORT=5000。訊息以 newline 結尾的 JSON 傳輸。Client 發送 `{"action": "submit", "job_id": <int>, "params": {...}, "run_path3": true|false}`；Server 回覆 `{"job_id": <int>, "status": "accepted"}`。Client 以 `{"action": "status", "job_id": <int>}` 輪詢；Server 回覆 `{"job_id": <int>, "status": "queued"|"running"|"success"|"error"|"timeout"|"timing_violated", "metrics": {...}, "reason": "..."}`。

**Server 端關鍵檔案**：任務佇列主程式、參數轉換腳本、DC 慢速/快速合成模板、動態產生的 synth_dse.tcl、Makefile、DC/VCS 報告解析器。

**參數轉換輸出**：RTL 巨集檔（config_macros.svh）、Testbench 常數檔（tb_macros.svh）、注入 clock/TOP_MODULE/合成旗標後的 synth_dse.tcl。

**Client 端關鍵檔案**：Path 1 軟體評估器、Path 2/3 硬體評估器、EDA 客戶端、搜尋空間定義檔（cimloop.yaml）。

**LFSR Testbench 完整指令序列**：

| 階段 | 指令 | 資料 | 目的 |
| :--- | :--- | :--- | :--- |
| Pre-setup | STORE_BUF | Encoding weights | inp_buf[1..N_WEIGHT_WORDS] |
| Pre-setup | STORE_BUF | Class HVs | data_buf[0..N_CLASS_WORDS-1] |
| Per-inference | STORE_BUF | Input features | inp_buf[0..N_FEAT_WORDS-1] |
| Compute | ENC_PRELOAD | — | inp_buf → encoder RF |
| Compute | ENC_SEG | — | Encode → HV segments |
| Compute | STORE_BUF | HAM config | inp_buf[0] 或 inp_buf[64] |
| Compute | HAM_SEG | — | Hamming distance search |
| Compute | PRED | — | 輸出預測至 oFIFO |

---

## 附錄 B：完整參數轉換表 (Appendix B: Full Parameter Mapping)

| 軟體參數 | RTL 巨集 | 轉換公式 / 說明 |
| :--- | :--- | :--- |
| reram_size | RRAM_ROW_ADDR_WIDTH | \( W = \lceil \log_2(\text{reram\_size}) \rceil \)；reram_size 須為 2 的冪次 |
| hd_dim | HV_LENGTH | 直接對應；上限 8191（HAMMING_DIST_WIDTH=13） |
| inner_dim | INNER_DIM, WEIGHT_MEM_ADDR_WIDTH | \( N_{\text{RF}} = \text{inner\_dim} / 32 \)，\( W = \lceil \log_2(N_{\text{RF}}) \rceil \) |
| cnn_x_dim_1 × cnn_y_dim_1 | CNN1_INPUTS_NUM | 乘積 |
| cnn_x_dim_2 × cnn_y_dim_2 | CNN2_INPUTS_NUM | 乘積 |
| encoder_x_dim × encoder_y_dim | ENC_INPUTS_NUM | 乘積 |
| hd_dim / ENC_INPUTS_NUM | HV_SEG_WIDTH | 整除；須滿足 HV_SEG_WIDTH ≥ 20、WEIGHT_BUS_WIDTH mod HV_SEG_WIDTH = 0 |
| frequency | DC TCL create_clock -period | \( T_{\text{clk}} = 10^9 / f \) (ns) |
| frequency | TB_CLK_PERIOD_NS (tb_macros.svh) | 同上，供 LFSR testbench 時脈產生器使用 |
| top_module | TCL TOP_MODULE_PLACEHOLDER | core 或 hd_top；決定 elaborate 根模組與 Path 3 使用的 testbench |

---

## 附錄 C：完整合成旗標列表 (Appendix C: Full Synthesis Flags)

| 參數 | 類型 | DC 效果（啟用時） |
| :--- | :--- | :--- |
| enable_clock_gating | bool | set_clock_gating_style -sequential_cell latch + insert_clock_gating |
| max_area_ignore_tns | bool | set_max_area 0 -ignore_tns（否則 set_max_area 0） |
| enable_retime | bool | compile_ultra -retime |
| compile_timing_high_effort | bool | compile_ultra -timing_high_effort_script |
| compile_area_high_effort | bool | compile_ultra -area_high_effort_script |
| compile_ultra_gate_clock | bool | compile_ultra -gate_clock |
| compile_exact_map | bool | compile_ultra -exact_map |
| compile_no_autoungroup | bool | compile_ultra -no_autoungroup |
| compile_clock_gating_through_hierarchy | bool | set compile_clock_gating_through_hierarchy true |
| enable_leakage_optimization | bool | set_leakage_optimization true |
| enable_dynamic_optimization | bool | set_dynamic_optimization true |
| enable_enhanced_resource_sharing | bool | set compile_enhanced_resource_sharing true |
| dp_smartgen_strategy | choice | none \| timing \| area → set_dp_smartgen_options -optimization_strategy <value> |
