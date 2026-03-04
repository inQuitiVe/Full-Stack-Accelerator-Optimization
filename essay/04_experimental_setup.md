# 4. 實驗設定 (Experimental Setup)

為驗證本框架的有效性，我們設計了一系列的實驗來評估全端協同設計、貝葉斯最佳化效率，以及 EDA 綜合策略對最終結果的影響。

## 4.1 評估環境與工具 (Evaluation Environment and Tools)
本框架橫跨軟硬體與多個運算節點，具體實驗環境如下：
* **軟體與機器學習層**：在 Client 端使用 Python 3 與 PyTorch 進行 HDnn 模型的訓練與推論。貝葉斯最佳化 (BO) 引擎採用 Meta 開源的 `Ax` (Adaptive Experimentation Platform) 與 `BoTorch`。
* **架構模擬層**：利用 `Cimloop` 與 `Timeloop` 進行硬體效能 (如 RRAM 陣列) 的初步分析與估算。
* **EDA 合成層**：在遠端伺服器 (Server) 使用 Synopsys Design Compiler (DC) 進行 RTL 邏輯合成 (Logic Synthesis)。製程節點採用真實的標準元件庫 (Standard Cell Library，例如 TSMC 28nm/45nm 等，*註：請於定稿時填寫實際使用的製程與電壓*)。

資料集部分，為驗證 HDC 演算法的表現，我們選用標準的影像分類資料集 (如 MNIST, CIFAR-10) 作為測試基準 (Benchmarks)。

## 4.2 搜尋空間定義 (Search Space Definition)
我們的設計空間 (Design Space) 涵蓋了三個不同的抽象層次。表一列出了本實驗所定義的搜尋參數與其對應的數值範圍 (或離散選項)：

**表一：Full-Stack DSE 搜尋空間 (Search Space)**  
（以下為本論文實驗中實際啟用的離散 search space 設定）

| 領域 (Domain) | 參數名稱 (Parameter) | 型別 (Type) | 數值範圍或選項 (Values / Bounds) | 說明 (Description) |
| :--- | :--- | :--- | :--- | :--- |
| **Software** | `hd_dim` | Choice (int) | {2048, 4096} | 超維度向量長度，影響模型容量與硬體資源需求 |
| **Software** | `inner_dim` | Choice (int) | {1024} | HD Encoder 內部轉換維度（本實驗固定） |
| **Hardware** | `reram_size` | Choice (int) | {128, 256} | RRAM 陣列大小，影響 PIM 計算能力與面積 |
| **Hardware** | `out_channels_1` | Choice (int) | {4, 8, 16} | CNN 第一層輸出通道數 |
| **Hardware** | `kernel_size_1` | Choice (int) | {3, 5, 7} | CNN 第一層卷積核大小 |
| **Hardware** | `out_channels_2` | Choice (int) | {8, 16, 32} | CNN 第二層輸出通道數 |
| **Hardware** | `kernel_size_2` | Choice (int) | {3, 5, 7} | CNN 第二層卷積核大小 |
| **Hardware** | `cnn_x_dim_1` / `cnn_y_dim_1` | Choice (int) | {16} / {16} | PatterNet CNN Layer 1 PE array 佈局 |
| **Hardware** | `cnn_x_dim_2` / `cnn_y_dim_2` | Choice (int) | {8} / {8} | PatterNet CNN Layer 2 PE array 佈局 |
| **Hardware** | `encoder_x_dim` / `encoder_y_dim` | Choice (int) | {8} / {8} | Encoder PE 佈局，亦影響 `HV_SEG_WIDTH`（確保 `HV_SEG_WIDTH = hd_dim / (8×8) ∈ {32, 64} ≥ 20）` |
| **EDA** | `synth_profile` | Choice (str) | {`balanced_default`, `timing_aggressive`, `power_aggressive`, `exact_map`} | DC 合成策略預設腳本 |
| **EDA** | `syn_map_effort` | Choice (str) | {`low`, `medium`, `high`} | DC 映射階段優化努力度 |
| **EDA** | `syn_opt_effort` | Choice (str) | {`low`, `medium`, `high`} | DC 整體優化階段努力度 |
| **EDA** | `enable_retime` | Choice (str) | {`false`, `true`} | 是否開啟額外的暫存器重定時 (retiming) |
| **EDA** | `enable_gate_clock` | Choice (str) | {`false`, `true`} | 是否啟用 gate-level clock gating 探索 |

## 4.3 評估指標與多目標優化 (Evaluation Metrics and Objective)
本研究為一個典型的多目標最佳化問題 (Multi-Objective Optimization Problem, MOOP)。我們定義了四個維度的評估指標：
1. **Accuracy (準確率)**：愈高愈好，由 PyTorch 軟體模擬取得。
2. **Energy (能量消耗, uJ)**：愈低愈好，由 (DC 動態/漏電功耗 $\times$ 執行時間) + RRAM 能量所構成。
3. **Delay / Timing (執行延遲, us)**：愈低愈好，由 (DC 合成出之時脈週期 $\times$ 執行週期數) 構成。
4. **Area (晶片面積, mm²)**：愈低愈好，由 DC 報告之數位邏輯面積 + RRAM 面積構成。

在貝葉斯最佳化中，我們使用 **超體積 (Hypervolume, HV)** 作為衡量 Pareto 前緣 (Pareto Front) 品質的單一指標。我們將尋求在特定硬性限制 (Constraints，例如 Accuracy $\geq 0.79$) 下，最大化這四個指標所形成的超體積。

## 4.4 實驗組別設計 (Baseline Configurations)
為了驗證本框架在不同面向的貢獻，我們設計了以下四大實驗情境 (Scenarios)：

1. **協同設計效益分析 (Impact of Full-Stack Co-Design)**：
   - **Software-Only**：固定硬體與 EDA 參數，僅搜尋軟體參數 (`hd_dim` 等)。
   - **Hardware-Only**：固定軟體參數，僅搜尋硬體陣列大小。
   - **Ours (Full-Stack)**：開啟表一中所有的搜尋空間，觀察 Pareto 邊界是否能被推向更佳的位置。
2. **EDA 合成策略影響力 (Impact of Synthesis Strategies)**：
   在固定軟硬體架構參數的前提下，由 BO 切換不同的 `synth_profile` 與 `effort`，並以雷達圖觀察其對 Area、Timing、Power 的擾動範圍。
3. **快速合成模式加速評估 (Fast Mode Acceleration Evaluation)**：
   - 比較「傳統全系統合成 (Slow Mode)」與我們提出的「黑盒子快速合成 (Fast Mode)」在累積運算時間 (Wall-clock Time) 上的差異。
   - 透過散佈圖 (Scatter Plot) 與皮爾森相關係數 (Pearson Correlation) 驗證 Fast Mode 取出的面積與功耗數值，是否與真實的 Slow Mode 保持高度的相對趨勢。
4. **搜尋演算法效率比較 (Search Algorithm Efficiency)**：
   比較本框架所使用的 qNEHVI (BO) 演算法與隨機搜尋 (Random Search) / 傳統進化演算法 (如 NSGA-II) 在收斂超體積 (Hypervolume) 所需的試驗次數 (Trials) 與時間效率。