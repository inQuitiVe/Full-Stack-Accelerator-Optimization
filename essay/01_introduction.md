# 1. 簡介 (Introduction)

## 1.1 研究背景與動機 (Background and Motivation)

隨著人工智慧與邊緣運算的發展，特定領域加速器 (Domain-Specific Accelerators) 的設計需在功耗、效能與面積 (PPA) 等嚴格約束下尋求最佳權衡。現代加速器的最佳化已不再侷限於單一層次，而是需要跨越**軟體演算法**、**硬體架構**與 **EDA 合成策略**的全端聯合探索 (Cross-Layer Co-Design)。然而，要取得真實且具保真度 (High-Fidelity) 的 PPA 數據，必須將硬體 RTL 投入 EDA 工具（如邏輯合成與閘級模擬）中進行迭代評估。這帶來了極高昂的運算成本，使得傳統的設計空間探索 (Design Space Exploration, DSE) 面臨嚴重的評估瓶頸。

## 1.2 問題陳述與研究缺口 (Problem Statement and Research Gap)

設計最佳化的現代加速器面臨以下雙重挑戰：

**1. 跨層級設計空間的深度耦合 (Cross-Layer Design Space Coupling)**：
設計參數橫跨模型層、架構層與合成層，且彼此存在非線性耦合。以表 1 所示之代表性實例為例，增加軟體演算法的模型維度有助於提升準確率，但會引發硬體面積與功耗的急遽上升。傳統「先定軟體、後做硬體」的脫節流程難以捕捉此耦合，無法逼近全域 Pareto 最佳解。

**表 1：跨層級搜尋參數類別與 PPA 影響（以 HDnn-PIM 為代表性實例）**

| 抽象層級 (Abstraction Level) | 代表性設計參數 (Representative Parameters) | 對 PPA 與約束的影響 (Impact on PPA & Constraints) |
| :--- | :--- | :--- |
| **Model / Software** | \(D\) (hd_dim)、inner_dim、out_channels | 決定軟體準確率門檻；與硬體資源呈非線性耦合 |
| **Hardware Architecture** | reram_size、encoder_x/y_dim、frequency | 直接決定硬體的面積 (Area)、功耗 (Power) 與效能 (Timing) |
| **EDA Synthesis Strategy** | enable_retime、syn_map_effort、enable_clock_gating | 透過細粒度旗標動態調控合成最佳化方向 |

**2. 缺乏可重複利用的多保真度評估流程 (Lack of Reusable Multi-Fidelity Orchestration)**：
在動輒數萬種組合的高維搜尋空間中，若對每組設計皆執行完整的 RTL 邏輯合成（約 30–60 分鐘）與閘級模擬（10–30 分鐘），將耗費龐大成本。現有研究缺口在於：部分文獻專注於軟硬體聯合設計但**僅依賴純軟體分析模型** [@parashar2019timeloop; @andrulis2024cimloop]，無法反映真實的時序違例與佈線後面積；另一部分文獻專注於 EDA 參數調校卻**未與頂層演算法聯合最佳化** [@sun2022correlated; @zheng2023boosting]。目前領域內仍缺乏一個能有效協調軟體篩選、RTL 合成與閘級驗證的**可配置多保真度流程 (Configurable Multi-Fidelity Flow)**。

## 1.3 提出的方法論與貢獻 (Proposed Methodology and Contributions)

為了解決上述流程層級 (Flow-Level) 的缺口，本研究提出一套**自動化、多保真度且高度可配置的全端協同設計框架 (Customizable Full-Stack Co-Design Framework)**。為驗證框架於高度耦合問題上的效力，我們選擇結合超維度運算與記憶體內運算的 **HDnn-PIM** [@dutta2022hdnn] 作為代表性驗證平台 (Validation Case Study)。本框架的核心設計邏輯為**可配置性 (Customizability)**，本文主要貢獻如下：

1. **可配置的跨層級參數化流程 (Configurable Cross-Layer Parameterization Flow)**：打破單一抽象層界線，將模型層參數、硬體架構參數以及底層 EDA 合成旗標（如 enable_retime 等 13+ 項參數）整合至單一最佳化介面。
2. **具守門機制的多保真度評估管道 (Gated Multi-Fidelity Evaluation Methodology)**：建立「軟體模擬 → 邏輯合成 → 閘級模擬」三階段評估管道。利用軟體準確率與硬體時序違例作為守門機制 (Gatekeeping) 提早淘汰不良設計，極大化昂貴 RTL 評估的價值。
3. **閉環內的 EDA 協調與高保真度反饋 (EDA-in-the-Loop Orchestration)**：提出遠端 EDA 協調機制，使得繁重的 RTL 合成與閘級模擬能無縫整合入反覆運算的搜尋迴圈中；其中 Path 3 更採用真實閘級波形進行功耗預測，大幅消除了純軟體模擬的準確度落差。

## 1.4 論文組織 (Paper Organization)

本文其餘部分組織如下：第 2 節透過 HDnn-PIM 案例介紹跨層耦合挑戰與相關工作；第 3 節詳述所提多保真度評估流程的架構與 EDA 策略探索；第 4 節說明實驗設定並呈現結果；第 5 節討論實驗意涵、需改進之處與未來工作，並總結全文。
