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
