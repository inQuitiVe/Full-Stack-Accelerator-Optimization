# 4. 實驗設定與結果 (Experimental Setup and Results)

本章說明評估指標與**差異化實驗組別設計**，並依實驗組別呈現 33 點 DSE 結果。評估環境與搜尋空間定義見**第 3 節 3.5**。本研究採用**固定參數配置**（非 BO 隨機採樣）進行系統性探索，共 **33 個有效實驗點**（合併自 22+10+5 點，已去重並剔除 gate1_failed）。資料來源：`workspace/dse_merged_p1p2p3.json`。

---

## 4.1 評估指標 (Evaluation Metrics)

***表 4-1：四維評估指標**

| 指標 | 方向 | 說明 |
| :--- | :--- | :--- |
| Accuracy | 最大化 | 軟體模擬分類準確率 |
| Energy (µJ) | 最小化 | \(E_{\text{ASIC}} + E_{\text{RRAM}}\) |
| Timing (µs) | 最小化 | \(T_{\text{ASIC}} + T_{\text{RRAM}}\) |
| Area (mm²) | 最小化 | \(A_{\text{ASIC}} + A_{\text{RRAM}}\) |

**三階段管道與資料來源**：Path 1（軟體模擬）一律執行；Gate 1 通過後執行 Path 2（邏輯合成）；Gate 2 通過後可選執行 Path 3（閘級模擬）。後階段可覆蓋前階段對應指標。

**表 4-1a：四維指標之階段貢獻**

| 指標 | Path 1 | Path 2 | Path 3 |
| :--- | :--- | :--- | :--- |
| Accuracy | 提供（唯一來源） | — | — |
| Area | 估算 | 提供（邏輯合成） | 沿用 |
| Timing | 估算 | 提供（單週期近似） | **覆蓋**（clock_period × execution_cycles） |
| Energy | 估算 | 提供（DC 功耗 × 時間） | **覆蓋**（PtPX 功耗 × 週期精確時間） |

**中間參數**：Path 2 產出 `p2_area_um2`、`p2_clock_period_ns`、`p2_timing_slack_ns`（Gate 2 判據）、`p2_dynamic_power_mw`、`p2_leakage_power_mw`。Path 3 產出 `p3_execution_cycles`，並以 PtPX 功耗覆蓋 Path 2 的 dynamic/leakage power；Area 與 clock_period 沿用 Path 2。

---

## 4.2 差異化實驗組別設計 (Differentiated Experiment Groups)

為系統性驗證框架在不同面向的貢獻，我們將 33 個有效實驗點整理為 **三大組**：**A**（EDA 策略）、**BC**（架構與 inner_dim）、**DEGH**（頻率掃描與高頻極限）。

### 4.2.1 Group A：EDA 策略影響 (5 點)

**目的**：固定架構，僅變動 EDA 旗標，觀察 PPA 擾動範圍。

| DP | syn_map/opt | enable_retime | compile_timing_high | 其他 EDA |
| :--- | :--- | :--- | :--- | :--- |
| A1 | low / low | false | false | 預設 |
| A2 | high / high | true | true | — |
| A3 | medium / medium | false | false | clock_gating, leakage, dynamic, ultra_gate |
| A4 | medium / medium | false | false | max_area_ignore_tns, area_high_effort, dp=area |
| A5 | high / high | true | true | clock_gating, leakage, dynamic, dp=timing |

**固定參數**：hd_dim=2048, reram=128, oc1=8, oc2=16, inner_dim=1024, **frequency=100 MHz**

### 4.2.2 Group BC：架構規模與 inner_dim (7 點)

**目的**：掃描不同 hd_dim、reram、CNN 規模與 inner_dim，觀察 PPA 隨架構變化及 Path 3 週期數。

**BC-B：架構規模梯度 (5 點)** — B6–B10

**BC-C：inner_dim 梯度 (2 點)** — C11 (1024), C12 (4096)

**固定參數**：frequency=100 MHz

### 4.2.3 Group DEGH：頻率掃描與高頻極限 (21 點)

**目的**：涵蓋小架構、大架構、base arch、inner_dim=2048/4096 在不同頻率 (80–300 MHz) 下的 timing 與 PPA。

**DEGH-D**：小架構頻率掃描 (3 點) — 125/150 MHz  
**DEGH-E**：大架構 Gate 2 壓力 (4 點) — 100/125 MHz  
**DEGH-G**：補充頻率掃描 (9 點) — 80–175 MHz  
**DEGH-H**：激進頻率 (5 點) — 200–300 MHz

### 4.2.4 實驗組別總覽

**表 4-2：三大組與對應研究問題**

| 組別 | 實驗數 | 涵蓋 | 研究問題 |
| :--- | :--- | :--- | :--- |
| **A** | 5 | EDA 旗標 | RQ2：EDA 策略對 PPA 的擾動範圍 |
| **BC** | 7 | 架構規模 (B) + inner_dim (C) | RQ1：架構梯度與 Encoder 規模對 Energy/Area 的影響 |
| **DEGH** | 21 | 頻率掃描 (D,E,G) + 高頻極限 (H) | RQ3/RQ4：頻率與 timing、高頻極限 |
| **總計** | **33** | | |

---

## 4.3 研究問題與實驗對應 (Research Questions and Experiments)

**表 4-3：研究問題與實驗對應**

| RQ | 研究問題 | 對應組別 | 主要指標 |
| :--- | :--- | :--- | :--- |
| RQ1 | 架構規模與 inner_dim 對 Energy/Area 的影響為何？ | BC | Energy, Area, Accuracy |
| RQ2 | EDA 細粒度策略對 PPA 的擾動範圍為何？ | A | Area, Power, Timing, Accuracy |
| RQ3 | 頻率對 timing 與 PPA 的關係為何？ | DEGH | Timing, Energy, Accuracy |
| RQ4 | 高頻 (200–300 MHz) 下的 timing 極限為何？ | DEGH (H 子組) | p2_timing_slack_ns, Accuracy |

---

## 4.4 整體統計摘要 (Overall Statistics)

**表 4-4：33 點實驗之 PPA 統計**

| 指標 | 最小值 | 最大值 | 平均值 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| Accuracy | 0.573 | 0.961 | 0.89 | 最低：G27 (inner_dim=2048 @ 150 MHz) |
| Energy (µJ) | 103,367 | 882,466 | 547,000 | 最低：E18；最高：B6/A1 (small/base arch) |
| Timing (µs) | 2,509 | 9,634 | 6,200 | 最低：H33 (300 MHz)；最高：A1 (100 MHz) |
| Area (mm²) | 427.4 | 861.4 | 502 | 大架構 (B9, E) 約 861 |
| p3_execution_cycles | 753,382 | 963,462 | 820,000 | 依 inner_dim 與架構而異 |

---

## 4.5 Group A：EDA 策略對 PPA 的影響 (RQ2)

**表 4-5：Group A 五種 EDA 策略之 PPA 比較**

| DP | 策略簡述 | Accuracy | Energy (µJ) | Timing (µs) | Area (mm²) | p2_dynamic_power (mW) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| A1 | low/low, 預設 | 0.920 | 882,416 | 9,635 | 427.55 | 91.6 |
| A2 | high/high, retime, timing_high | 0.923 | 881,473 | 9,635 | 427.55 | 91.5 |
| A3 | clock_gating, leakage, dynamic, ultra_gate | **0.958** | **709,381** | **7,535** | 427.54 | 94.1 |
| A4 | area_aggressive, max_area_ignore_tns | 0.739 | 882,416 | 9,635 | 427.55 | 91.6 |
| A5 | timing_aggressive (high+retime+clock_gating+leakage) | 0.917 | 664,707 | 7,535 | 427.54 | 88.2 |

**觀察**：**A3**（clock_gating + leakage + dynamic + ultra_gate）達成最高 Accuracy (0.958) 與最低 Energy (709k µJ)。**A5** Energy 較 A1 降低約 25%，Timing 由 9.6 ms 降至 7.5 ms。**A4**（area_aggressive）Accuracy 明顯下降 (0.739)。

---

## 4.6 Group BC：架構規模與 inner_dim (RQ1)

**表 4-6：Group BC 架構規模與 PPA（BC-B 子組）**

| DP | 架構簡述 | hd_dim | reram | Accuracy | Energy (µJ) | Area (mm²) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| B6 | small (oc1=4, oc2=8) | 2048 | 128 | 0.914 | 882,416 | 427.55 |
| B7 | mid (oc1=16, oc2=32) | 2048 | 256 | 0.936 | 882,466 | 861.37 |
| B8 | hd=4096, small CNN | 4096 | 128 | 0.734 | 132,021 | 427.62 |
| B9 | hd=4096, large CNN | 4096 | 256 | 0.954 | 132,239 | 861.45 |
| B10 | hd=4096, mixed | 4096 | 128 | 0.938 | 132,021 | 427.62 |

**表 4-7：Group BC inner_dim 梯度（BC-C 子組）**

| DP | inner_dim | p3_execution_cycles | Accuracy | Energy (µJ) | Timing (µs) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| C11 | 1024 | 963,462 | 0.957 | 882,416 | 9,635 |
| C12 | 4096 | 754,440 | 0.962 | 644,942 | 7,544 |

**觀察**：**hd_dim=4096** 的 Energy 顯著低於 2048（約 132k vs 882k µJ）。**inner_dim** 增大使 Path 3 週期數由 963k 降至 754k，Energy 與 Timing 同步改善。

---

## 4.7 Group DEGH：頻率掃描與高頻極限 (RQ3, RQ4)

**表 4-8：Group DEGH 頻率與 PPA 關係（精選）**

| 子組 | 架構 | 頻率 (MHz) | Accuracy | Energy (µJ) | Timing (µs) | p2_timing_slack (ns) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| D | small | 125 | 0.878 | 690,130 | 6,028 | 3.03 |
| D | small | 150 | 0.922 | 690,420 | 5,026 | 2.50 |
| G | inner=2048 | 80 | **0.949** | 644,356 | 9,422 | 4.83 |
| G | inner=2048 | 100–150 | 0.57–0.94 | 644k | 5–7.5k | 2.5–3.8 |
| G | base | 175 | 0.931 | 689,660 | 4,302 | 1.84 |
| H | base | 200–300 | 0.77–0.95 | 689k | **2,509**–3,767 | 0–1.12 |

**觀察**：**80 MHz** Accuracy 最高 (0.949)，timing slack 最大 (4.83 ns)。**DEGH-H**（200–300 MHz）：base arch 在 275、300 MHz 時 timing slack 已為 0，仍通過 Gate 2；Timing 最低達 2,509 µs (300 MHz)。

---

## 4.8 Pareto 前緣分析 (Pareto Front)

**表 4-9：Pareto 候選（Accuracy ≥ 0.90 且 Energy 較低）**

| DP | 組別 | Accuracy | Energy (µJ) | Timing (µs) | Area (mm²) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| A3 | A | 0.958 | 709,381 | 7,535 | 427.54 |
| C12 | BC | 0.962 | 644,942 | 7,544 | 427.45 |
| G2 | DEGH | 0.949 | 644,356 | 9,422 | 427.45 |
| B9 | BC | 0.954 | 132,239 | 9,634 | 861.45 |
| E19 | DEGH | 0.957 | 103,343 | 6,027 | 861.45 |
| H33 | DEGH | 0.945 | 689,704 | 2,509 | 427.55 |

**甜蜜點**：**E19**（大架構 + 125 MHz + high EDA）Energy 最低 (103k µJ)、Accuracy 0.957。**H33**（base @ 300 MHz）Timing 最低 (2,509 µs)，Accuracy 0.945。

---

## 4.9 討論 (Discussion)

1. **EDA 策略的實務價值**：Group A 顯示 clock_gating、leakage、dynamic 與 timing_aggressive 可顯著改善 Energy 與 Timing，且不犧牲 Accuracy；area_aggressive 則需謹慎，可能導致 Accuracy 下降。

2. **架構規模與 Energy 的權衡**：hd_dim=4096 大幅降低 Energy（約 6–7×），但 Area 隨 CNN 規模擴張；大架構在 125 MHz 下可達成極低 Energy (103k µJ)。

3. **頻率與 Accuracy 的非單調關係**：80–110 MHz 區間 Accuracy 較高；120、150 MHz 出現異常低點，可能與 LFSR 隨機性或時序邊際有關，值得後續重複實驗驗證。

4. **高頻極限**：base arch 在 275–300 MHz 仍通過 Gate 2（slack=0），Timing 最低 2.5 ms，顯示架構具備一定高頻潛力。

5. **Pareto 多樣性**：不同組別貢獻不同維度的最優解——DEGH-E 在 Energy、DEGH-H 在 Timing、A/BC-C/DEGH-G 在 Accuracy-Energy 平衡，驗證全端 DSE 能發掘多樣化甜蜜點。

---

## 4.10 繪圖腳本與產出 (Figure Generation)

腳本 `essay/plot_results.py` 可自 `workspace/dse_merged_p1p2p3.json` 產生圖表，供重現實驗與後續分析使用。執行：`python essay/plot_results.py`（需安裝 matplotlib）。可指定 `--output-dir` 設定輸出目錄。
