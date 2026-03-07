# 3. 提出的全端設計空間探索框架 (Proposed Full-Stack DSE Framework)

本節詳述所提框架的系統架構、多層次保真度評估管道、黑盒子快速合成機制，以及 EDA 細粒度策略探索。圖 1（概念性）描繪整體流程；以下分小節說明各模組。

## 3.1 系統架構：Thin-Client 解耦模型 (System Architecture: Thin-Client Decoupled Model)

商用 EDA 工具（如 Synopsys Design Compiler、VCS）通常受授權與內網限制，難以與 Python/Docker 型 BO 框架直接綁定。為此，我們設計 **Thin-Client 解耦架構**：

**表 3-1：Thin-Client 架構角色分工**

| 端點 | 職責 | 關鍵元件 |
| :--- | :--- | :--- |
| **Client** | BO 演算法、軟體訓練、架構模擬 | Ax/BoTorch、PyTorch、Cimloop/Timeloop |
| **EDA Server** | 參數→RTL 轉換、合成、模擬、指標萃取 | json_to_svh.py、DC、VCS、PrimeTime PX |

Client 將參數打包為 JSON 發送至 Server；Server 動態產生 `config_macros.svh` 與 `synth_dse.tcl`，驅動 DC 合成，並僅回傳數值化 PPA 指標。此解耦模式解決授權問題，並具備高擴充性。

## 3.2 多層次保真度評估與提早停止 (Multi-Fidelity Evaluation and Gatekeeping)

為避免在無效設計上浪費昂貴合成時間，我們將單次評估拆分為三階段，並在每階段設置提早停止門檻。

### 3.2.1 Path 1：軟體模擬 (Fast)

Client 端以 PyTorch 訓練 HDnn 模型並取得 Accuracy，同時以 Cimloop 估算 RRAM 能量與延遲。

**Gate 1**：若 Accuracy 低於使用者定義門檻 \(\tau\)（如 0.79），該 Trial 標記為失敗，**完全跳過後續硬體合成**。

### 3.2.2 Path 2：硬體合成與混合拼接 (Medium)

通過 Gate 1 的參數送往 EDA Server 進行邏輯合成。由於 RRAM 缺乏標準 RTL，我們採用混合拼接策略：

\[
A_{\text{total}} = A_{\text{ASIC}} + A_{\text{RRAM}}, \quad T_{\text{total}} = T_{\text{ASIC}} + T_{\text{RRAM}}, \quad E_{\text{total}} = P_{\text{ASIC}} \cdot T_{\text{total}} + E_{\text{RRAM}}
\]

**Gate 2**：若合成網表發生時序違例（Slack \(< 0\)），該 Trial 判定失敗，Path 3 不觸發。

### 3.2.3 Path 3：閘級模擬與功耗驗證 (High Fidelity)

Path 3 僅在「通過 Gate 2 且使用者啟用 Path 3」時觸發。Client 在 JSON 中加入 `run_path3=True`，Server 於合成完成且無違例後執行 VCS 閘級模擬與 PrimeTime PX 功耗分析。

**LFSR-based Testbench**：為避免從 PyTorch 傳輸大量 `.hex` 測試資料，我們採用 LFSR 自產生測試平台 (`tb_core_timing.sv` / `tb_hd_top_timing.sv`)，精確記錄 ENC_PRELOAD → oFIFO 的 **COMPUTE CYCLES**，並產生 SAIF 供 PtPX 使用。Testbench 支援 `inner_dim` 驅動的 `N_WEIGHT_WORDS` 與 10 classes（MNIST/CIFAR-10）。

**Path 3 指標拼接公式**：

\[
T_{\text{ASIC}} = \frac{T_{\text{clk}} \times N_{\text{cycles}}}{1000} \text{ (µs)}, \quad E_{\text{ASIC}} = (P_{\text{dyn}} + P_{\text{leak}}) \times T_{\text{ASIC}}
\]

**表 3-2：LFSR Testbench 指令序列**

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

## 3.3 黑盒子快速合成機制 (Fast Black-Box Synthesis Mode)

即便有 Gatekeeping，通過的 Trial 仍眾多。我們分析 HDnn-PIM RTL 發現：**DSE 參數僅影響 HD 核心邏輯**（Encoder、Search 等），而 PatterNet、系統介面等大型模組在搜尋過程中完全靜態。

**快速合成模式 (Fast Mode)** 作法：

1. **白名單機制**：僅將隨參數變動的 SystemVerilog 檔（如 `hd_enc.sv`、`hd_search.sv`）加入 DC `analyze` 清單。
2. **黑盒子化**：刻意不引入 PatterNet 等靜態模組，DC 在 elaborate/link 階段將其視為 Black Box。
3. **效益**：單次合成時間由約 45–60 分鐘降至 3–5 分鐘（約 10×–15× 加速）。由於靜態模組 PPA 為常數，移除不影響 BO 觀察的相對趨勢。

**synth_mode × top_module 二維決策**：

| | top_module=core | top_module=hd_top |
| :--- | :--- | :--- |
| synth_mode=slow | 全系統合成；tb_core_timing | HD 核心；tb_hd_top_timing |
| synth_mode=fast | PatterNet 黑盒；tb_core_timing | HD 核心；tb_hd_top_timing |

前期 DSE 可採用 `synth_mode=fast, top_module=hd_top` 快速掃描；對少數 Pareto 候選再以 `synth_mode=slow, top_module=core` 進行高保真驗證。

## 3.4 EDA 細粒度策略探索 (Granular EDA Strategy Exploration)

傳統 DSE 將 EDA 工具視為固定編譯器。本框架將 **Design Compiler 的細粒度合成旗標直接納入 BO 搜尋空間**，將過去整包式策略拆解為多個獨立布林/選擇參數，大幅擴展探索空間。

**表 3-3：細粒度綜合旗標與 DC TCL 對應**

| YAML 參數 | DC 效果（啟用時） |
| :--- | :--- |
| enable_clock_gating | set_clock_gating_style + insert_clock_gating |
| max_area_ignore_tns | set_max_area 0 -ignore_tns |
| enable_retime | compile_ultra -retime |
| compile_timing_high_effort | -timing_high_effort_script |
| compile_area_high_effort | -area_high_effort_script |
| compile_ultra_gate_clock | -gate_clock |
| compile_exact_map | -exact_map |
| compile_no_autoungroup | -no_autoungroup |
| enable_leakage_optimization | set_leakage_optimization true |
| enable_dynamic_optimization | set_dynamic_optimization true |
| dp_smartgen_strategy | none \| timing \| area → set_dp_smartgen_options |

此外，`syn_map_effort` 與 `syn_opt_effort` 控制對映與優化努力度 (`low`/`medium`/`high`)。透過硬體架構與 EDA 策略聯合優化，BO 可在遭遇時序瓶頸時主動啟用 `enable_retime` 等策略彌補，發掘單一領域優化無法觸及的 Pareto 點。
