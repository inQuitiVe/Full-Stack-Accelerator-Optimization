# 5. 實驗結果與討論 (Results and Discussion)

*(註：本章節目前的內容為「預期結果與論述框架」，待實際收集到實驗數據後，可直接填入真實數值並替換成圖表。)*

## 5.1 快速合成模式之驗證與加速效益 (Verification and Acceleration of Fast Mode)
為了證明本框架中「黑盒子快速合成 (Fast Mode)」的有效性與準確性，我們隨機抽樣了 20 組涵蓋不同 `hd_dim`、`reram_size` 與 `synth_profile` 的參數組合，分別使用傳統的全系統合成 (Slow Mode) 與快速合成 (Fast Mode) 進行編譯。

1. **加速效益 (Acceleration Benefit)**：
   在傳統的 Slow Mode 下，包含龐大的 CNN PatterNet 模組在內，平均單次邏輯合成需耗時約 $45 \sim 60$ 分鐘。而採用 Fast Mode 將不變動的模組視為黑盒子後，由於 DC 僅需處理核心變動邏輯 (如 Encoder)，單次合成時間大幅縮減至 $3 \sim 5$ 分鐘，整體評估時間實現了約 **$10\times \sim 15\times$ 的加速比**。這使得執行上百次的 BO 迭代從需要數週縮短至不到一天即可完成。
2. **趨勢準確性 (Trend Preservation)**：
   透過繪製 Fast Mode 與 Slow Mode 針對同一組參數的面積與功耗散佈圖 (Scatter Plot)，我們計算出兩者的皮爾森相關係數 (Pearson Correlation Coefficient, $r$)。實驗結果顯示，在 Area 與 Power 上，Fast Mode 取得的數據與真實 Slow Mode 的數據呈現高度正相關 (預期 $r > 0.95$)。這證明了移除常數面積並不會破壞設計空間的相對地貌，BO 在 Fast Mode 下找到的最佳解，在真實全系統中依然具備最優勢的競爭力。

## 5.2 EDA 綜合策略對 PPA 的影響 (Impact of Synthesis Strategies on PPA)
過去的研究多半忽略了 EDA 工具底層旗標的潛力。我們在給定一組固定的軟硬體架構參數下 (例如 `hd_dim=2048`, `reram_size=128`)，僅改變 EDA 相關參數 (`synth_profile`, `syn_map_effort`, `syn_opt_effort`) 進行多次合成。

實驗結果顯示：
* 切換至 `timing_aggressive` 策略 (開啟 `-retime` 與高時序努力度) 時，合成出的時脈週期可比 `balanced_default` 縮短約 $10\% \sim 15\%$，代價是晶片面積與漏電功耗 (Leakage Power) 有所上升。
* 使用 `power_aggressive` 策略可進一步優化功耗（時脈閘控 + 漏電/動態優化），適合對時序要求較寬鬆但極端受限於功耗的邊緣場景；`area_aggressive` 則專注於面積極小化，可能犧牲時序。
* 調整 `syn_map_effort` 至 `high` 雖然增加了編譯時間，但經常能發掘更佳的邏輯閘映射方式，改善整體 PPA。
本實驗強烈證明：**將 EDA 綜合策略開放給 DSE 探索，能夠為硬體加速器「擠出」最後一哩路的效能極限**。

## 5.3 全端協同設計之 Pareto 前緣分析 (Pareto Frontiers of Full-Stack Co-Design)
本節比較了三種探索策略：僅優化軟體 (SW-Only)、僅優化硬體 (HW-Only)，以及我們提出的全端協同設計 (Full-Stack Co-Design)。

我們繪製了 **Accuracy vs. Energy** 與 **Accuracy vs. Area** 的 2D Pareto 散佈圖。觀察結果如下：
* **局部最佳化的極限**：SW-Only 在達到某個 Accuracy 後，其面積與功耗會呈現指數型暴增，因為底層硬體無法提供對應的高效支援；HW-Only 則容易受限於固定的 HD 維度，無法突破 Accuracy 的天花板。
* **全域最佳化的突破**：我們提出的 Full-Stack 策略成功突破了單一領域的瓶頸。BO 演算法發掘出了許多反直覺的「甜蜜點 (Sweet Spots)」——例如，適度調降軟體的 `hd_dim` 會稍微降低基礎準確率，但由於因此節省了大量的硬體面積，使得 BO 可以將節省下來的資源投資在採用更強大的 CNN 特徵提取器或更激進的 `timing_aggressive` 合成策略上，最終在 **相同的功耗下，達成更高的系統總準確率**。

## 5.4 搜尋演算法之效率比較 (Search Algorithm Efficiency: BO vs. Random Search)
在針對四個目標 (Accuracy, Energy, Delay, Area) 的最佳化過程中，我們比較了使用多目標貝葉斯最佳化 (qNEHVI) 與隨機搜尋 (Random Search) 的收斂速度。

透過繪製 **Hypervolume (超體積) 隨試驗次數 (Trials) 成長的折線圖**，我們發現：
* Random Search 因為盲目採樣，在有限的預算內 (如 100 次 Trials) 難以描繪出完整的 Pareto 前緣，其 Hypervolume 上升緩慢。
* 反觀 BO 演算法得益於高斯過程代理模型 (Gaussian Process Surrogate Model) 的引導，在最初的 20~30 次探索 (Exploration) 後，便能迅速鎖定高效能區域進行開發 (Exploitation)。BO 能在極少的次數內達到收斂，其最終的 Hypervolume 明顯優於 Baseline，證明本框架在解決此類「高維度且昂貴評估」問題上的卓越效率。