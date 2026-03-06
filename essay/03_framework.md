# 3. 提出的全端設計空間探索框架 (Proposed Full-Stack DSE Framework)

為了解決高維度參數耦合與硬體評估過於耗時的問題，我們提出了一套基於多目標貝葉斯最佳化 (Multi-Objective BO) 的全自動化全端協同設計框架。本框架具備去耦合架構 (Decoupled Architecture)、多層次保真度 (Multi-Fidelity) 評估，以及首創的快速黑盒子合成機制 (Fast Black-Box Synthesis)。

## 3.1 系統架構：Thin-Client 黑盒子 API 模型
由於商用 EDA 工具 (如 Synopsys Design Compiler, VCS) 通常受到嚴格的授權 (License) 與內網環境限制，難以直接與現代基於 Python/Docker 的機器學習與 BO 框架綁定。為此，我們設計了 **Thin-Client (瘦客戶端) 系統架構**：

* **Client 端 (BO Engine)**：運行於 Docker 容器內，負責執行貝葉斯最佳化演算法 (使用 Meta Ax 框架)、PyTorch 軟體神經網路訓練，以及架構級的效能模擬 (Cimloop/Timeloop)。Client 端扮演 DSE 的「大腦」。
* **EDA Server 端 (硬體評估中心)**：運行於具有 EDA 授權的遠端 Linux 伺服器上。Server 端暴露了一個基於 TCP Socket 的非同步 API。當 Client 產生一組新的參數組合時，會將其打包為 JSON 格式發送給 Server。Server 負責將參數動態轉換為 SystemVerilog 標頭檔 (`config_macros.svh`) 與 TCL 腳本，並驅動 Design Compiler 進行合成。最終，Server 僅將解析後的數值化 PPA 指標回傳給 Client。

這種 Decoupled API 模式不僅解決了授權問題，更使得架構具備極高的擴充性，未來可輕鬆替換後端的 EDA 工具或叢集。

## 3.2 多層次保真度評估與提早停止機制 (Multi-Fidelity Evaluation and Gatekeeping)
為避免在無效的設計上浪費昂貴的合成時間，我們將單次評估 (Evaluation) 拆分為三個具備「提早停止 (Early Stopping/Gatekeeping)」機制的層次 (Paths)：

1. **Path 1: 軟體模擬 (Software Simulation - Fast)**
   - 流程：Client 端利用 PyTorch 訓練 HDnn 模型，並取得軟體準確率 (Accuracy)。同時，利用分析模型 (Analytical Models，如 Cimloop) 進行初步的 RRAM 能量與延遲估算。
   - **Gate 1 (準確率門檻)**：若此參數組合訓練出的模型準確率低於使用者定義的底線 (如 79%)，BO 引擎會立即將此 Trial 標記為失敗 (Failed)，終止評估，**完全跳過後續的硬體合成**。

2. **Path 2: 硬體合成與混合拼接 (Hardware Synthesis and Stitching - Medium)**
   - 流程：通過 Gate 1 的參數將被送往 EDA Server 進行邏輯合成。由於 PIM 加速器中的 RRAM 類比陣列部分沒有標準的 RTL，我們採用「混合拼接 (Stitching)」策略：
     - `總面積 (Area) = 數位邏輯面積 (來自 EDA) + RRAM 面積 (來自 Cimloop)`
     - `總延遲 (Delay) = 數位邏輯時脈週期 (來自 EDA) + RRAM 讀寫延遲 (來自 Cimloop)`
   - **Gate 2 (時序門檻)**：若合成出的電路發生嚴重的時序違例 (Timing Violation, Slack < 0)，表示此架構在給定的頻率下無法實作，該 Trial 將被判定為失敗，BO 模型會記錄此硬性限制。

3. **Path 3: 閘級模擬與功耗驗證 (Gate-Level Simulation & Power Verification - High Fidelity)**
   - Path 3 僅在「通過 Gate 2 且使用者啟用 Path 3」時被觸發。Client 端只需在送往 EDA Server 的 JSON 請求中加入 `run_path3=True` 旗標，Server 便會在 Path 2 合成完成且無時序違例時，自動進一步執行閘級模擬與功耗分析。
   - 為了避免從 PyTorch 傳輸大量 `.hex` 測試資料到 EDA 主機，我們改採 **LFSR-based Testbench**：在硬體專案 `fsl-hd/verilog/tb/` 中，提供 `tb_core_timing.sv` 與 `tb_hd_top_timing.sv` 兩個測試平台，分別對應 `core` 以及 `hd_top` 兩種頂層。這些 Testbench 會以 LFSR 自行產生輸入序列，並在有限狀態機 (FSM) 內部精確記錄「ENC_PRELOAD → oFIFO result」之間的 **計算週期數 (`COMPUTE CYCLES`)**，同時產生 SAIF 活動檔供 PrimeTime PX 使用。
   - PrimeTime PX 讀取 SAIF 檔與合成後網表，回傳閘級動態功耗與漏電功耗；設計框架則將 Path 2 的時脈週期 (clock period) 與 Path 3 的執行週期數 (execution cycles) 相乘，得到更高保真度的 ASIC 延遲估計，再與 Cimloop 的 RRAM 延遲與能量加總，形成最終的多目標指標。RRAM 區塊在實驗中依然沒有真實 RTL，因此其 PPA 仍以 Cimloop 為唯一來源。

## 3.3 核心創新：快速黑盒子合成機制 (Fast Black-Box Synthesis Mode)
即使用了 Gatekeeping 機制，留下來需要進行邏輯合成的參數組合依然非常龐大。我們進一步分析 HDnn-PIM 的硬體特性發現：在 DSE 過程中，**被改變的參數僅影響 HD 核心邏輯** (如 Hypervector 寬度、Encoder 單元數等)。而佔據極大面積的 CNN 特徵提取器 (PatterNet)、固定的 SRAM Buffer 與系統介面，在整個搜尋過程中是完全靜態的。

為此，我們提出了 **「快速合成模式 (Fast Mode)」**：
* 在產生 TCL 腳本時，我們使用**白名單 (Whitelist) 機制**，僅將隨參數變動的 SystemVerilog 檔案 (如 `hd_enc.sv`, `hd_search.sv`) 加入 `analyze` 清單。
* 刻意**不引入**靜態且龐大的 PatterNet 模組。Design Compiler 在 `elaborate` 與 `link` 階段會找不到這些模組，進而將其視為**黑盒子 (Black Box)**。
* **效益與影響**：在這種由下而上 (Bottom-up) 的黑盒子合成下，EDA 工具會將未定義模組的面積與功耗視為 0，並迅速完成剩餘邏輯的合成。這使得**單次合成時間從接近 1 小時驟降至數分鐘內**。由於 PatterNet 等靜態模組的 PPA 在整個 DSE 中可視為常數，將常數移除並**不影響 BO 觀察參數變動的「相對趨勢」**。BO 依然能準確無誤地朝向真正的 Pareto 最佳解收斂。

進一步地，我們將 **「合成模式 (synth_mode)」** 與 **「頂層模組 (top_module)」** 做到完全解耦：

* `synth_mode ∈ {slow, fast}`：控制是否將 PatterNet 等靜態模組納入 DC 合成中。`slow` 會重新合成全系統；`fast` 則維持黑盒子模式，只針對 HD 核心邏輯進行增量合成。
* `top_module ∈ {core, hd_top}`：控制 DC Elaborate 以及 Path 3 Testbench 的觀測範圍。`core` 代表從 SoC 封裝視角觀察 (含 `chip_interface` / FIFO 等介面邏輯)；`hd_top` 則只聚焦在超維度核心本身。

透過這兩個正交的維度，本框架可以支援 2D 的實驗組合：例如在前期 DSE 用 `synth_mode=fast, top_module=hd_top` 快速掃描 HD 核心的趨勢，最後再以 `synth_mode=slow, top_module=core` 對少數 Pareto 候選進行高保真度的全系統驗證。

## 3.4 EDA 綜合策略的多維度探索 (Synthesis Optimization Exploration)
傳統硬體 DSE 往往將 EDA 工具視為固定且被動的編譯器，忽視了綜合腳本對最終電路效能的影響。本框架打破了這個限制，將 **Design Compiler 的綜合策略 (Synthesis Flags) 直接納入 BO 的搜尋空間**。

我們將以下參數交由 BO 動態決策：
1. **`synth_profile` (綜合輪廓)**：提供高層級的策略預設。
   - `balanced_default`：標準的 `compile_ultra`、時脈閘控與 `set_max_area 0`。
   - `timing_aggressive`：`set_max_area 0` + 重定時 (`-retime`) 與高時序優化腳本，犧牲面積換取極限速度。
   - `power_aggressive`：時脈閘控 + 漏電/動態優化 + `compile_ultra -gate_clock`，追求極致功耗優化。
   - `area_aggressive`：`set_max_area 0 -ignore_tns` + 面積導向腳本，追求極致微縮（可能違反時序）。
   - `exact_map`：保留 RTL 階層，確保精準對應。
2. **`syn_map_effort` 與 `syn_opt_effort`**：控制對映 (Mapping) 與優化 (Optimization) 階段的努力度等級 (`low`/`medium`/`high`)。

透過將「硬體架構參數」與「EDA 綜合參數」聯合優化，BO 可以在遇到架構層面的時序瓶頸時，主動切換至 `timing_aggressive` 的 EDA 策略來彌補，從而發掘出單獨調整架構或單獨調整腳本都無法達到的隱藏 Pareto 最佳點。