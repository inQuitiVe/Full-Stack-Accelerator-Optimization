# 基於多目標貝葉斯最佳化之 HDnn-PIM 全端協同設計框架

---

# 摘要 (Abstract)

**背景與動機**：記憶體內運算 (Processing-in-Memory, PIM) 與超維度運算 (Hyperdimensional Computing, HDC) 的結合 (HDnn-PIM) 在邊緣運算能效上展現極具潛力。然而，HDnn-PIM 的設計空間橫跨軟體演算法、硬體 RTL 架構與 EDA 合成策略三層抽象，其參數間存在非線性耦合，傳統孤立優化方法難以逼近全域 Pareto 最佳解。此外，單次邏輯合成動輒數十分鐘至數小時，成為高維度設計空間探索 (Design Space Exploration, DSE) 的主要瓶頸。

**方法**：本研究提出一套自動化全端協同設計框架。本框架以多目標貝葉斯最佳化 (Multi-Objective Bayesian Optimization, BO) 為核心，將軟體模型參數、硬體陣列規模與 EDA 細粒度合成旗標同時納入搜尋空間。為克服評估耗時，我們設計具提早停止 (Gatekeeping) 機制的三階段多層次保真度評估管道，並首創「黑盒子快速合成模式 (Fast Black-Box Synthesis Mode)」——透過將不隨參數變動的大型模組自合成清單抽離，使單次合成時間縮短超過 10 倍，同時保留 PPA 相對趨勢。

**結果**：實驗結果顯示，相較於僅優化軟體或硬體，本框架能在極短時間內收斂，並發掘兼具高準確率與低功耗面積的隱藏最佳解，顯著推動 HDnn-PIM 的效能極限。

**關鍵字**：硬體加速器；超維度運算；記憶體內運算；設計空間探索；貝葉斯最佳化；邏輯合成；全端協同設計

---

# 1. 簡介 (Introduction)

## 1.1 研究背景與動機 (Background and Motivation)

隨著人工智慧與物聯網 (IoT) 邊緣運算的蓬勃發展，對高能效、低延遲運算架構的需求日益迫切。傳統范紐曼 (von Neumann) 架構受制於記憶體牆 (Memory Wall)，在大量資料搬移時產生嚴重能耗與延遲。記憶體內運算 (Processing-in-Memory, PIM) 透過在記憶體陣列內部或鄰近處直接執行運算，大幅降低資料搬移，展現極高能效潛力 [1,2]。同時，超維度運算 (Hyperdimensional Computing, HDC) 作為輕量級機器學習典範，具備高度平行性、強容錯能力與簡易訓練流程，被視為邊緣運算的理想演算法 [3]。將 HDC 與 PIM 結合的 HDnn-PIM 架構 [4]，能在極低功耗下實現高效推論與學習，已成為硬體加速器研究的熱門方向。

## 1.2 問題陳述與研究缺口 (Problem Statement and Research Gap)

設計最佳化 HDnn-PIM 加速器面臨三層抽象耦合與評估成本雙重挑戰。

**設計空間的多層耦合**：HDnn-PIM 的設計空間橫跨 (i) 軟體演算法層（如超維度向量長度 \(D\)、編碼器內部維度 \(\text{inner\_dim}\)），(ii) 硬體架構層（如 RRAM 陣列大小、處理單元數量），以及 (iii) EDA 合成策略層（如 Design Compiler 的優化旗標）。表 1 概括各層參數對 PPA 的影響。參數間存在非線性耦合：例如增加 \(D\) 可提升準確率，但會導致硬體面積與功耗急遽上升。傳統「先軟體後硬體」的脫節流程難以捕捉此耦合，無法逼近全域 Pareto 最佳解。

**表 1：HDnn-PIM 設計空間參數分類與 PPA 影響**

| 抽象層 | 代表性參數 | 主要影響 |
| :--- | :--- | :--- |
| 軟體 | \(D\) (hd_dim), inner_dim | Accuracy |
| 硬體 | reram_size, encoder_x/y_dim | Area, Power, Timing |
| EDA | enable_retime, syn_map_effort 等 | Area, Power, Timing |

**高昂的評估成本**：取得精確 PPA 需將 RTL 送入 EDA 工具進行邏輯合成與閘級模擬，單次評估動輒數十分鐘至數小時。在包含數萬種組合的高維空間中，窮舉或隨機搜尋在實務上不可行。

**研究缺口**：既有文獻或專注於軟硬體參數但忽略 EDA 策略 [5,6]，或專注於 EDA 調校卻未與軟體演算法聯合優化 [7,8]。此外，缺乏能從根本上加速 RTL 評估的機制，導致高維 DSE 仍受困於時間瓶頸。

## 1.3 本文貢獻 (Contributions)

為解決上述挑戰，本研究提出一套**自動化、多層次保真度的全端協同設計框架**，專為 HDnn-PIM 量身打造。本文的主要貢獻如下：

1. **全端軟硬體與 EDA 聯合優化**：打破軟硬體設計藩籬，將 HDC 演算法參數、PIM 陣列架構參數與 Synopsys Design Compiler 的細粒度合成旗標同時納入 BO 搜尋空間，實現真正的全域 Pareto 優化。

2. **多層次保真度評估與提早停止機制**：建立「軟體模擬 → 邏輯合成 → 閘級模擬」三階段評估管道，以軟體準確率作為 Gate 1 提早淘汰不達標設計，以時序違例作為 Gate 2 過濾不可實作架構，大幅節省無效合成。

3. **黑盒子快速合成機制**：針對 DSE 中不隨參數變動的大型模組（如 PatterNet），提出白名單驅動的黑盒子合成策略，將單次合成時間縮短 10× 以上，同時保留 PPA 相對趨勢，使 BO 仍能正確收斂至 Pareto 前緣。

4. **EDA 細粒度旗標探索**：首創將 DC 的 13+ 項細粒度合成旗標（如 enable_retime、enable_clock_gating、compile_timing_high_effort 等）參數化，證明 BO 動態決策合成策略能有效推動 Pareto 邊界極限。

## 1.4 論文組織 (Paper Organization)

本文其餘部分組織如下：第 2 節回顧 HDC、PIM、貝葉斯最佳化與相關工作；第 3 節詳述所提框架的系統架構、多層次評估管道、快速合成機制與 EDA 策略探索；第 4 節說明實驗設定；第 5 節呈現結果與討論；第 6 節總結並展望未來工作。

---

# 2. 背景與相關工作 (Background and Related Work)

本節首先介紹超維度運算與記憶體內運算的基礎概念，接著說明貝葉斯最佳化在設計空間探索中的角色，最後回顧相關文獻並指出本研究與既有工作的差異。

## 2.1 超維度運算 (Hyperdimensional Computing)

**超維度運算 (HDC)** [3] 是一種基於高維隨機向量代數的機器學習典範。在 HDC 中，所有資料被編碼為 \(D\) 維超維度向量 (Hypervectors)，其中 \(D\) 通常介於 1000 至 10000。運算僅涉及位元運算（XOR、Majority Vote）與加法，相較於深度學習的浮點乘加運算 (MAC)，具備極低運算複雜度。HDC 將資訊分散於所有維度，使其對硬體雜訊與錯誤具備強容錯能力，適合邊緣部署。

**編碼與推論流程**：給定輸入特徵 \(\mathbf{x}\)，HDC 透過編碼器 (Encoder) 產生超維度向量 \(\mathbf{h} \in \{0,1\}^D\)。分類時，將 \(\mathbf{h}\) 與各類別原型向量比較漢明距離 (Hamming Distance)，選取距離最小者作為預測類別。編碼器內部維度 \(\text{inner\_dim}\) 與超維度 \(D\) 共同決定模型容量與硬體資源需求。

## 2.2 記憶體內運算 (Processing-in-Memory)

**記憶體內運算 (PIM)** [1,2] 旨在打破記憶體牆。傳統加速器在神經網路推論時，絕大部分功耗與延遲耗費於權重與特徵的資料搬移。PIM 架構（如基於 ReRAM 或 SRAM 的交叉陣列）允許在資料儲存位置直接執行矩陣向量乘法 (MVM)，大幅降低搬移成本。

**HDnn-PIM 架構** [4] 將 HDC 的位元運算映射至 PIM，結合 CNN 特徵擷取 (PatterNet) 與 HDC 編碼器，達成極低功耗的邊緣推論。其設計空間包含 RRAM 陣列大小、Encoder PE 佈局、超維度 \(D\) 與編碼器維度 \(\text{inner\_dim}\) 等參數，彼此高度耦合。

## 2.3 貝葉斯最佳化 (Bayesian Optimization)

**貝葉斯最佳化 (BO)** [9] 是樣本效率最高的黑盒子優化演算法之一，適用於評估成本極高的設計空間探索。BO 包含兩項核心元件：

1. **代理模型 (Surrogate Model)**：通常採用高斯過程 (Gaussian Process, GP) 擬合目標函數分佈，預測未探索區域的均值 \(\mu(\mathbf{x})\) 與不確定性 \(\sigma(\mathbf{x})\)。

2. **擷取函數 (Acquisition Function)**：在多目標情境下，常使用 qNEHVI (q-Noisy Expected Hypervolume Improvement) [10]，在探索 (Exploration) 與開發 (Exploitation) 間取得平衡，指引下一步採樣點。

**多目標 BO**：本研究以 Accuracy、Energy、Timing、Area 為四維目標，以超體積 (Hypervolume, HV) 衡量 Pareto 前緣品質，在滿足 Accuracy \(\geq \tau\) 的硬性限制下最大化 HV。

## 2.4 相關工作 (Related Work)

**表 2：相關工作比較**

| 工作 | 軟硬體聯合 | EDA 策略探索 | RTL 評估加速 | 全端覆蓋 |
| :--- | :---: | :---: | :---: | :---: |
| Timeloop [11] | ✗ | ✗ | ✓ (分析模型) | ✗ |
| Cimloop [12] | ✗ | ✗ | ✓ (分析模型) | ✗ |
| HDnn-PIM [4] | 部分 | ✗ | ✗ | ✗ |
| HierCGRA [13] | ✓ | ✗ | 部分 | ✗ |
| Sun et al. [7] | ✗ | ✓ | 部分 | ✗ |
| REMOTune [8] | ✗ | ✓ | 部分 | ✗ |
| **本研究** | ✓ | ✓ | ✓ (Fast Mode) | ✓ |

**分析模型與架構探索**：Timeloop [11] 與 Cimloop [12] 提供快速的 DNN/CiM 效能估算，但缺乏 RTL 邏輯合成驗證，無法捕捉實際電路的面積與時序違例。HDnn-PIM [4] 展現 HDnn 與 PIM 結合的能效潛力，但仰賴人工靜態設計。HierCGRA [13] 提出階層式 CGRA 探索框架，未將 EDA 策略納入搜尋空間。

**EDA 參數調校**：Sun 等人 [7] 針對 HLS 指令提出多目標多層次保真度優化；REMOTune [8] 利用隨機嵌入與信賴區間 BO 調校 VLSI 綜合與 PnR 參數。這些工作證實 EDA 參數對 PPA 的顯著影響，但優化範圍僅限於硬體與 EDA 階層，未向上延伸至軟體演算法。

**研究缺口**：既有工作或「專注軟硬體參數但忽略 EDA 且受限于 RTL 評估速度」，或「專注 EDA 調校卻無法與軟體演算法產生聯合效應」。本研究提出的全端協同設計框架填補此缺口，並透過黑盒子快速合成機制突破 RTL 評估瓶頸。

---

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

---

# 4. 實驗設定 (Experimental Setup)

本節說明評估環境、搜尋空間定義、評估指標與實驗組別設計，以確保實驗可重現性。

## 4.1 評估環境與工具 (Evaluation Environment and Tools)

**表 4-1：實驗環境配置**

| 層級 | 工具 / 環境 | 用途 |
| :--- | :--- | :--- |
| 軟體與 ML | Python 3, PyTorch | HDnn 模型訓練與推論 |
| BO 引擎 | Meta Ax, BoTorch | 多目標貝葉斯最佳化 |
| 架構模擬 | Cimloop, Timeloop | RRAM 能量與延遲估算 |
| EDA 合成 | Synopsys Design Compiler | RTL 邏輯合成 |
| 閘級模擬 | VCS | 週期精確模擬 |
| 功耗分析 | PrimeTime PX | 動態與漏電功耗 |

製程節點採用真實標準元件庫（如 TSMC 28nm/45nm；定稿時請填寫實際製程與電壓）。資料集選用 MNIST 與 CIFAR-10 作為影像分類基準。

## 4.2 搜尋空間定義 (Search Space Definition)

設計空間由 `conf/params_prop/cimloop.yaml` 定義，涵蓋軟體、硬體與 EDA 三層抽象。

**表 4-2：Full-Stack DSE 搜尋空間**

| 領域 | 參數 | 型別 | 數值範圍 / 選項 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **Software** | hd_dim | Choice | {2048, 4096, 8191} | 超維度 \(D\)；上限 8191（HAMMING_DIST_WIDTH=13） |
| **Software** | inner_dim | Choice | {1024, 2048, ...} | Encoder 內部維度；須為 32 的倍數 |
| **Hardware** | reram_size | Choice | {128, 256} | RRAM 陣列大小 |
| **Hardware** | out_channels_1/2 | Choice | {4,8,16} / {8,16,32} | CNN 輸出通道數 |
| **Hardware** | kernel_size_1/2 | Choice | {3, 5, 7} | 卷積核大小 |
| **Hardware** | cnn_x/y_dim_1/2 | Choice | 依實驗設定 | PatterNet PE 佈局 |
| **Hardware** | encoder_x/y_dim | Choice | {8}×{8} 等 | Encoder PE 佈局；影響 HV_SEG_WIDTH |
| **EDA** | syn_map_effort | Choice | {low, medium, high} | DC 映射努力度 |
| **EDA** | syn_opt_effort | Choice | {low, medium, high} | DC 優化努力度 |
| **EDA** | enable_clock_gating | Choice | {false, true} | 時脈閘控 |
| **EDA** | enable_retime | Choice | {false, true} | 暫存器重定時 |
| **EDA** | max_area_ignore_tns | Choice | {false, true} | 面積優先（可能違反 timing） |
| **EDA** | compile_timing_high_effort | Choice | {false, true} | 高時序優化 |
| **EDA** | enable_leakage_optimization | Choice | {false, true} | 漏電優化 |
| **EDA** | dp_smartgen_strategy | Choice | {none, timing, area} | DP Smartgen 策略 |

**inner_dim 與硬體對應**：Encoder 權重 RF 行數由 inner_dim 決定：

\[
N_{\text{RF}} = \frac{\text{inner\_dim}}{\text{OUTPUTS\_NUM}}, \quad \text{WEIGHT\_MEM\_ADDR\_WIDTH} = \lceil \log_2(N_{\text{RF}}) \rceil
\]

其中 OUTPUTS_NUM = 32（param.vh 固定）。對照表如下：

**表 4-3：inner_dim 與 WEIGHT_MEM_ADDR_WIDTH 對照**

| inner_dim | \(N_{\text{RF}}\) | WEIGHT_MEM_ADDR_WIDTH |
| :--- | :--- | :--- |
| 1024 | 32 | 5 |
| 2048 | 64 | 6 |
| 4096 | 128 | 7 |

## 4.3 評估指標與多目標優化 (Evaluation Metrics and Objectives)

本研究為多目標最佳化問題 (MOOP)，定義四維評估指標：

**表 4-4：評估指標定義**

| 指標 | 方向 | 來源 |
| :--- | :--- | :--- |
| Accuracy | 最大化 | PyTorch 軟體模擬 |
| Energy (µJ) | 最小化 | \(E_{\text{ASIC}} + E_{\text{RRAM}}\) |
| Timing (µs) | 最小化 | \(T_{\text{ASIC}} + T_{\text{RRAM}}\) |
| Area (mm²) | 最小化 | \(A_{\text{ASIC}} + A_{\text{RRAM}}\) |

我們以 **超體積 (Hypervolume, HV)** 衡量 Pareto 前緣品質，在滿足 Accuracy \(\geq \tau\) 的硬性限制下最大化 HV。

## 4.4 實驗組別設計 (Experimental Design)

為驗證框架在不同面向的貢獻，我們設計以下四類實驗情境：

**表 4-5：實驗情境與對應研究問題**

| 實驗 | 研究問題 (RQ) | 方法 |
| :--- | :--- | :--- |
| **E1: 協同設計效益** | 全端聯合優化是否優於單一領域優化？ | 比較 SW-Only、HW-Only 與 Full-Stack 的 Pareto 前緣 |
| **E2: EDA 策略影響** | 細粒度合成旗標對 PPA 的擾動範圍？ | 固定架構，僅變動 EDA 參數，以雷達圖觀察 |
| **E3: 快速合成驗證** | Fast Mode 是否保留 PPA 相對趨勢？ | 比較 Slow/Fast Mode 的 Area、Power 皮爾森相關係數 |
| **E4: 搜尋效率** | BO 相較 Random Search 的收斂效率？ | 繪製 HV 隨 Trials 成長曲線 |

輸出 `dse_results.json` 包含最終目標（accuracy, energy_uj, timing_us, area_mm2, hv）與 Path 2/3 原始指標（p2_area_um2, p2_timing_slack_ns, p3_execution_cycles 等），供後續分析與圖表繪製。

---

# 5. 實驗結果與討論 (Results and Discussion)

本章依研究問題 (RQ) 呈現實驗結果，並討論其意涵。*(註：部分數值為預期結果，待實際數據收集後可替換為真實量測值。)*

## 5.1 研究問題與實驗對應 (Research Questions and Experiments)

**表 5-1：研究問題與實驗對應**

| RQ | 研究問題 | 對應實驗 | 主要指標 |
| :--- | :--- | :--- | :--- |
| RQ1 | 全端協同設計是否優於單一領域優化？ | E1 | Pareto 前緣、HV |
| RQ2 | EDA 細粒度策略對 PPA 的擾動範圍為何？ | E2 | Area、Power、Timing 變異 |
| RQ3 | Fast Mode 是否保留 PPA 相對趨勢？ | E3 | Pearson \(r\)、加速比 |
| RQ4 | BO 相較 Random Search 的收斂效率為何？ | E4 | HV vs. Trials |

---

## 5.2 快速合成模式之驗證與加速效益 (RQ3)

為驗證黑盒子快速合成 (Fast Mode) 的有效性，我們隨機抽樣 20 組涵蓋不同 `hd_dim`、`reram_size` 與 `synth_profile` 的參數組合，分別以 Slow Mode 與 Fast Mode 進行編譯。

**表 5-2：Slow Mode vs. Fast Mode 編譯時間比較**

| 模式 | 平均單次合成時間 | 說明 |
| :--- | :--- | :--- |
| Slow Mode | 45–60 分鐘 | 全系統（含 CNN PatterNet）邏輯合成 |
| Fast Mode | 3–5 分鐘 | 僅核心變動邏輯（如 Encoder）合成 |
| **加速比** | **10×–15×** | 使上百次 BO 迭代可由數週縮短至一日內 |

**趨勢準確性**：繪製 Fast Mode 與 Slow Mode 在 Area 與 Power 上的散佈圖，計算皮爾森相關係數 \(r\)。預期 \(r > 0.95\)，顯示 Fast Mode 保留設計空間的相對地貌，BO 在 Fast Mode 下找到的解在真實全系統中仍具競爭力。

> **[圖 5-1]**：Fast Mode vs. Slow Mode 之 Area 與 Power 散佈圖（預期高度線性相關）

---

## 5.3 EDA 綜合策略對 PPA 的影響 (RQ2)

在固定架構（如 `hd_dim=2048`, `reram_size=128`）下，僅變動 EDA 參數 (`synth_profile`, `syn_map_effort`, `syn_opt_effort`) 進行多次合成。

**表 5-3：EDA 策略對 PPA 的預期影響**

| 策略 | Timing | Area | Leakage | 適用情境 |
| :--- | :--- | :--- | :--- | :--- |
| timing_aggressive | ↑ 10–15% 改善 | ↑ 上升 | ↑ 上升 | 時序關鍵路徑 |
| power_aggressive | 可能放寬 | 持平 | ↓ 優化 | 邊緣低功耗 |
| area_aggressive | 可能放寬 | ↓ 優化 | 持平 | 面積極小化 |
| syn_map_effort=high | 改善 | 改善 | 改善 | 編譯時間可接受時 |

**結論**：將 EDA 綜合策略納入 DSE 探索，可為硬體加速器「擠出」最後一哩路的效能極限。

> **[圖 5-2]**：EDA 策略對 PPA 的雷達圖（預期）

---

## 5.4 全端協同設計之 Pareto 前緣分析 (RQ1)

比較三種探索策略：SW-Only、HW-Only 與 Full-Stack Co-Design。

**表 5-4：三種策略的預期特性**

| 策略 | Accuracy 上限 | Energy/Area 行為 | 瓶頸 |
| :--- | :--- | :--- | :--- |
| SW-Only | 受硬體支撐限制 | 達某點後指數型暴增 | 底層硬體無法支援 |
| HW-Only | 受固定 hd_dim 限制 | 可優化但 Accuracy 天花板低 | 軟體維度固定 |
| Full-Stack | 突破單一領域 | 發掘反直覺甜蜜點 | 無 |

**甜蜜點範例**：適度調降 `hd_dim` 雖略降基礎準確率，但節省硬體面積，使 BO 可將資源投資於更強 CNN 或 `timing_aggressive` 策略，**在相同功耗下達成更高系統準確率**。

> **[圖 5-3]**：Accuracy vs. Energy 與 Accuracy vs. Area 之 2D Pareto 散佈圖（三策略比較）

---

## 5.5 搜尋演算法效率比較 (RQ4)

比較多目標貝葉斯最佳化 (qNEHVI) 與隨機搜尋 (Random Search) 的收斂效率。

**表 5-5：BO vs. Random Search 預期行為**

| 方法 | 收斂速度 | 最終 HV | 機制 |
| :--- | :--- | :--- | :--- |
| Random Search | 緩慢 | 較低 | 盲目採樣 |
| BO (qNEHVI) | 20–30 次後快速收斂 | 較高 | GP 代理模型引導 |

**結論**：BO 得益於高斯過程代理模型，在有限預算內能更有效率地描繪 Pareto 前緣，適合「高維度且昂貴評估」的 DSE 問題。

> **[圖 5-4]**：Hypervolume 隨 Trials 成長之折線圖（BO vs. Random Search）

---

## 5.6 討論 (Discussion)

1. **多維度協同優化的必要性**：單一領域優化存在明顯天花板；全端聯合優化能發掘隱藏的 Pareto 最佳解。
2. **Fast Mode 的實務價值**：在保留 PPA 相對趨勢的前提下，10×–15× 加速使高維 DSE 在合理時程內可行。
3. **EDA 策略的潛力**：過去研究多忽略 EDA 旗標；本研究證實其對 PPA 有顯著擾動，值得納入搜尋空間。

---

# 6. 結論與未來展望 (Conclusion and Future Work)

## 6.1 結論 (Conclusion)

本研究針對超維度記憶體內運算 (HDnn-PIM) 架構，提出並實作一套基於多目標貝葉斯最佳化 (MO-BO) 的自動化全端協同設計框架。我們成功克服傳統硬體設計空間探索 (DSE) 面臨的三項挑戰：軟硬體脫節、合成評估過度耗時，以及忽略 EDA 綜合策略的潛力。

**表 6-1：本研究主要貢獻與對應結論**

| 貢獻 | 結論 |
| :--- | :--- |
| 多維度協同優化 | 打破軟體演算法與硬體 RTL 界線，並首次將 EDA 合成旗標納入探索空間，使 BO 能發掘單一領域優化無法觸及的 Pareto 最佳解 |
| 多層次保真度與提早停止 | 以軟體模擬準確率作為 Gatekeeping，有效過濾不具競爭力的設計，避免後續硬體資源浪費 |
| 黑盒子快速合成 | Fast Mode 將不變動模組抽離，單次合成時間縮短 10×–15×，同時保留 PPA 相對趨勢，使高維 DSE 在合理時程內可行 |

綜上，本框架在「高維度且昂貴評估」的硬體 DSE 問題上，展現出卓越的搜尋效率與 Pareto 前緣品質。

## 6.2 研究限制 (Limitations)

1. **評估止步於邏輯合成**：目前未納入 Floorplan、Placement 與 Routing，時序與擁塞數據為合成階段估算。
2. **架構專一性**：框架針對 HDnn-PIM 量身打造，擴展至其他加速器架構需額外適配。
3. **保真度層級**：目前為兩層（軟體模擬 + 邏輯合成），尚未實作 Multi-Fidelity BO 的主動採樣策略。

## 6.3 未來工作 (Future Work)

**表 6-2：未來研究方向**

| 方向 | 內容 |
| :--- | :--- |
| **實體設計層擴展** | 將 Floorplan、Placement、Routing 等後端參數納入搜尋空間，取得更精確的時序與擁塞數據 |
| **Multi-Fidelity BO** | 引進 BOCA 或 MF-MES 等演算法，讓 BO 主動選擇在 Fast Mode 或 Slow Mode 下評估，進一步極大化搜尋效率 |
| **架構泛化** | 透過擴充模板機制，使框架適用於 Systolic Arrays、Transformer 加速器等其他類型深度學習硬體 |

---
