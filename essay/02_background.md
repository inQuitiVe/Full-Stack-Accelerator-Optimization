# 2. 背景與相關工作 (Background and Related Work)

本節將介紹 HDnn-PIM 作為驗證案例的代表性，討論在昂貴 RTL 反饋下設計空間探索 (DSE) 的挑戰，並系統性回顧相關文獻，以確立本框架的定位。

## 2.1 HDnn-PIM 作為代表性驗證案例 (HDnn-PIM as a Representative Case Study)

本研究採用 **HDnn-PIM** [@dutta2022hdnn] 作為具體的驗證案例。該架構結合了**超維度運算 (HDC)** [@kanerva2009hyperdimensional] 與**記憶體內運算 (PIM)** [@mutlu2022modern]。HDC 是一種輕量級機器學習典範，具備高度平行性與容錯能力，極適合邊緣運算；而 PIM 陣列則透過在資料儲存處直接執行運算，來突破范紐曼架構的「記憶體牆」。

我們選擇 HDnn-PIM 作為驗證目標，不僅是因為其卓越的能效潛力，更是因為**其設計涉及深度的跨層級耦合 (Cross-Layer Coupling)**。在軟體層面，超維度向量的維度直接決定了硬體所需的記憶體容量；在硬體層面，PIM 陣列的配置與頻率則限制了演算法所能達到的準確率上限。要最佳化這種高度耦合的系統，必須跨越所有抽象層次進行聯合推理，使其成為展示本全端多保真度流程效力的完美載體。

## 2.2 昂貴 RTL 反饋下的設計空間探索 (Design Space Exploration Under Expensive RTL Feedback)

**設計空間探索 (DSE)** 的核心目標是在龐大的參數空間中，系統性地逼近 Pareto 最佳前緣。傳統純分析模型 (Analytical Models) 評估速度快，但無法捕捉實際電路在佈線後的面積與時序違例等物理真實情況。反之，完全依賴邏輯合成與閘級模擬的評估雖具備高保真度，但時間成本極高（單次通常需要數十分鐘至數小時）。

這種「保真度與成本」的權衡，突顯了一種迫切的需求：**選擇性調用與提早修剪機制 (Selective Invocation and Early Pruning)**。在將運算資源投入昂貴的高保真度 RTL 模擬前，必須先透過廉價、低保真度的評估來過濾掉明顯劣質的設計。

## 2.3 相關工作 (Related Work)

表 2 系統性地比較了本研究提出的框架與代表性先進文獻在技術涵蓋範圍上的差異。

**表 2：相關工作比較**

| 相關工作 | 軟硬體聯合設計 | EDA 策略探索 | 閘級保真度 | RTL 評估加速 | 可配置流程 | 全端涵蓋 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Timeloop [@parashar2019timeloop] | ✗ | ✗ | 分析模型 | ✓ | ✗ | ✗ |
| CiMLoop [@andrulis2024cimloop] | ✗ | ✗ | 分析模型 | ✓ | ✗ | ✗ |
| HDnn-PIM [@dutta2022hdnn] | 部分 | ✗ | — | ✗ | ✗ | ✗ |
| Yang et al. [@yang2024multi] | ✓ | ✗ | 僅模擬 | 部分 | ✗ | ✓ |
| HierCGRA [@chen2024hiercgra] | ✓ | ✗ | 邏輯合成 | 部分 | 部分 | ✗ |
| Sun et al. [@sun2022correlated] | ✗ | ✓ | 邏輯合成 | 部分 | ✗ | ✗ |
| REMOTune [@zheng2023boosting] | ✗ | ✓ | 邏輯合成 | 部分 | ✗ | ✗ |
| **本研究** | ✓ | ✓ | 閘級模擬 | ✓ (Fast Mode) | ✓ | ✓ |

*註：「部分」表示僅涵蓋特定階段、特定參數或架構；「僅模擬」表示評估缺乏實際 RTL 合成或閘級驗證。*

### 2.3.1 分析模型與架構探索
**Timeloop** [@parashar2019timeloop] 與 **CiMLoop** [@andrulis2024cimloop] 提供了快速的架構與對映探索分析模型。然而，它們的評估完全止步於軟體分析層面，缺乏實際的邏輯合成來反映真實世界約束。原始的 **HDnn-PIM** [@dutta2022hdnn] 依賴人工靜態決定參數，缺乏自動化的 DSE 機制。而 **HierCGRA** [@chen2024hiercgra] 雖提供了自動化 DSE，但其搜尋空間並未包含底層的 EDA 合成旗標。

### 2.3.2 EDA 參數調校
**Sun 等人** [@sun2022correlated] 與 **REMOTune** [@zheng2023boosting] 證實了 EDA 參數對 PPA 指標的決定性影響，並利用先進演算法來最佳化實體設計流程。儘管如此，它們的最佳化範圍受限於硬體與 EDA 層級，未能向上延伸與頂層軟體演算法產生聯合設計的綜效。

### 2.3.3 特定領域軟硬體協同最佳化
**Yang 等人** [@yang2024multi] 針對 HD-PIM 提出了多目標軟硬體協同最佳化框架。儘管在範圍上具前瞻性，但其評估仍停留在軟體模擬層次，缺乏 EDA 細粒度旗標的探索，也未進行閘級保真度的驗證。

## 2.4 本研究的定位 (Positioning of This Work)

總結來說，本研究**既不是單純的 HDnn-PIM 最佳化研究，也不是純粹的 EDA 調校論文**。我們提出的是一個**可重複利用的多保真度協調流程 (Reusable Multi-Fidelity Orchestration Flow)**，旨在橋接分析模型與實體合成之間的鴻溝。

我們汲取了 Sun 等人 [@sun2022correlated] 與 REMOTune [@zheng2023boosting] 對 EDA 參數化的概念，並將其提升至與頂層軟體演算法聯合最佳化的層次。**本研究與 Yang 等人 [@yang2024multi] 的核心差異有三**：(1) 我們將超過 13 項 Design Compiler 合成旗標參數化並納入搜尋空間；(2) 我們透過邏輯合成與閘級模擬提取高保真度的 PPA 指標；(3) 我們建立了一個高度靈活、可配置的管道，其適用範圍不侷限於單一架構。我們選擇了緊密耦合的 HDnn-PIM 架構作為實例，來具體驗證這項方法論層面上的貢獻。
