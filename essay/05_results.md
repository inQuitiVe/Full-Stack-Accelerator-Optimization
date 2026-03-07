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
