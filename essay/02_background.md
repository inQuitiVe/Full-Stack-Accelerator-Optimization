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
