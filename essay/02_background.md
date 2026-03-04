# 2. 背景與動機 (Background and Motivation)

## 2.1 超維度運算與記憶體內運算 (Hyperdimensional Computing and PIM)
**超維度運算 (Hyperdimensional Computing, HDC)** 是一種基於高維度空間 (通常為 $D = 1000$ 至 $10000$) 隨機向量特性的機器學習典範。在 HDC 中，所有資料皆被編碼為超維度向量 (Hypervectors)，運算過程僅涉及簡單的位元運算 (如 XOR、Majority Vote) 與加法。相較於傳統深度學習 (Deep Learning) 需要大量的浮點乘加運算 (MAC)，HDC 具備極低的運算複雜度，且其將資訊分散於所有維度中的特性，使其對硬體雜訊與錯誤具有極高的容錯能力。

**記憶體內運算 (Processing-in-Memory, PIM)** 是一種為了打破「記憶體牆 (Memory Wall)」而生的硬體架構。傳統加速器在執行神經網路推論時，絕大部分的功耗與延遲皆耗費在從 SRAM 或 DRAM 搬移權重與特徵資料。PIM 架構 (如基於 ReRAM 憶阻器或 SRAM 的交叉陣列) 允許在資料儲存的位置直接利用克希荷夫定律 (Kirchhoff's law) 執行類比或數位的矩陣向量乘法 (MVM)。將 HDC 簡單的位元運算映射至 PIM 架構上 (即 HDnn-PIM)，能夠最大化平行處理能力，達成極低功耗的邊緣運算方案。

## 2.2 全端設計空間探索的挑戰 (The Challenge of Full-Stack DSE)
儘管 HDnn-PIM 深具潛力，但要設計出一個在面積、功耗、效能與準確率皆達到最佳平衡的硬體，卻面臨著巨大的「維度災難 (Curse of Dimensionality)」。這是一個典型的黑盒子最佳化問題 (Black-box Optimization Problem)，其挑戰在於：

1. **參數間的深度耦合 (Deep Parameter Coupling)**：
   單一領域的優化往往會顧此失彼。例如，在軟體層面增加超維度向量的長度 (`hd_dim`) 可以提升模型的分類準確率，但這將直接導致硬體層面需要更大的 ReRAM 陣列 (`reram_size`) 與更多的處理單元 (`encoder_x_dim`)，進而讓晶片面積與功耗急遽上升。若軟體與硬體團隊各自為政，幾乎不可能找到真正的 Pareto 最佳解 (Pareto Frontier)。
2. **高昂的硬體評估成本 (Expensive Evaluation Cost)**：
   為了得到精確的硬體 PPA (Power, Performance, Area) 數據，必須將參數化的 RTL (Register Transfer Level) 程式碼送入 EDA 工具 (如 Synopsys Design Compiler) 進行邏輯合成。每一次的合成加上靜態時序分析 (Static Timing Analysis, STA)，可能耗費數十分鐘甚至數小時。若使用傳統的網格搜尋 (Grid Search) 或隨機搜尋 (Random Search)，在數萬種參數組合中尋找最佳解，可能需要耗費數個月的時間，這在實際工程中是不可行的。

## 2.3 貝葉斯最佳化 (Bayesian Optimization)
為了解決評估成本極高的黑盒子優化問題，**貝葉斯最佳化 (Bayesian Optimization, BO)** 被廣泛認為是最具樣本效率 (Sample-efficient) 的演算法之一。BO 包含兩個核心元件：
1. **代理模型 (Surrogate Model)**：通常使用高斯過程 (Gaussian Process, GP) 來擬合目標函數 (如 Accuracy 或 Area) 的真實分佈，並預測未探索區域的均值與不確定性。
2. **擷取函數 (Acquisition Function)**：例如 Expected Improvement (EI) 或針對多目標優化的 qNEHVI (q-Noisy Expected Hypervolume Improvement)。擷取函數負責在「探索 (Exploration：尋找未知的可能優良區域)」與「開發 (Exploitation：在已知的高分區域尋找更好解)」之間取得平衡，指引演算法下一步應該採樣哪一組參數。

在本研究中，我們採用 BO 作為 DSE 的「大腦」，藉此在極少的合成次數 (Trials) 內，快速逼近多目標的 Pareto 邊界。

## 2.4 EDA 合成瓶頸與本研究之動機 (The Synthesis Bottleneck and Motivation)
儘管 BO 能減少採樣次數，但「單次合成依然需要數十分鐘」的瓶頸 (Synthesis Bottleneck) 仍然存在。經過對 HDnn-PIM RTL 程式碼的深度分析，我們發現了一個關鍵特性：**DSE 所探索的參數，實際上只會改變部分核心邏輯 (如 Encoder 與 Hypervector 處理單元) 的硬體結構**。而佔據晶片極大面積與合成時間的模組 (如 CNN 前處理 PatterNet、系統介面、大型暫存器檔案等)，在 DSE 過程中其內部架構是完全固定的。

此外，傳統的 DSE 框架通常將 EDA 工具視為一個固定的黑盒子，忽略了 EDA 工具本身的合成策略 (Synthesis Flags) 對於推動 PPA 極限的潛力。

**基於上述痛點與觀察，本研究的動機如下：**
我們亟需一套框架，不僅能自動化地同步搜尋軟硬體參數 (Full-Stack Co-design)，還必須能夠將 EDA 參數 (如 `syn_map_effort`, `compile_ultra` 旗標) 納入最佳化的一環。更重要的是，該框架必須具備某種機制 (如提早停止或快速黑盒子合成)，來大幅縮短耗時的硬體評估流程，從而讓大規模的高維度 DSE 成為可能。

2.5 相關文獻探討 (Related Works)
要實現高能效的邊緣運算加速器，過去的研究多半從分析模型、架構探索或底層編譯優化等不同切入點進行，可概分為以下三個主要發展方向：

1. 深度學習與記憶體內運算之評估框架 (DNN and PIM Evaluation Frameworks)
針對硬體加速器的設計空間，過去已有諸多分析模型被提出。例如，Timeloop 提出了一套系統化的評估基礎設施，能夠透過精簡的表示法來探索 DNN 加速器的資料流 (Dataflow) 與記憶體階層設計；而 CiMLoop 則是專為記憶體內運算 (Compute-In-Memory) 所設計的靈活建模工具，能跨層次評估 CiM 系統的硬體效能。然而，這類基於分析模型 (Analytical Models) 的工具雖然評估速度極快，卻缺乏真實 RTL 邏輯合成的驗證。它們難以捕捉到實際電路在經過繞線與邏輯閘優化後的真實面積，亦無法精確反映出時序違例 (Timing Violations) 的硬性限制。

2. 架構探索與軟硬體協同設計 (Architecture Exploration and SW-HW Co-Design)
針對超維度運算 (HDC) 與 PIM 的結合，HDnn-PIM 架構 透過結合特徵擷取與 HDC，展現了極佳的高能效潛力，但該研究仰賴人工靜態設計，並未對架構進行自動化的參數探索。在設計空間探索 (DSE) 方面，HierCGRA 針對大規模粗粒度可重組架構 (CGRA) 提出了階層式的建模與探索框架，以應對龐大的設計空間。近期的研究 更進一步針對 HD-PIM 提出了多目標軟硬體協同最佳化，並利用噪音感知 (Noise-Aware) 的貝葉斯最佳化尋找最佳架構參數。儘管這些前瞻研究成功引入了 BO 來處理軟硬體參數的耦合，但它們仍將底層的 EDA 工具視為不可動的黑盒子，且未提出能從根本上加速 RTL 合成時間的機制，導致高維度探索在實務上仍受困於高昂的時間瓶頸。

3. 高階合成與 EDA 參數最佳化 (HLS and EDA Parameter Tuning)
為了解決 EDA 工具預設策略在優化上的侷限性，部分研究開始將焦點轉向硬體編譯與綜合階段的參數調校。例如，Sun 等人 針對高階合成 (High-Level Synthesis, HLS) 指令，提出了具備相關性的多目標多層次保真度 (Multi-fidelity) 最佳化方法；而 REMOTune 則利用隨機嵌入 (Random Embedding) 與多目標信賴區間貝葉斯最佳化 (Trust-region BO)，在高維度的 VLSI 設計流程中調校 EDA 工具的綜合與佈局繞線參數。這些研究明確證實了動態調整 EDA 參數對推動 PPA 極限的巨大貢獻，但它們的優化範圍僅侷限於硬體與 EDA 階層，並未向上延伸至軟體演算法層面產生協同效應。

小結 (Summary)：
綜合上述，目前的文獻要不是「專注於軟硬體參數，但忽略 EDA 策略且受限於 RTL 評估速度」，就是「專注於 EDA 參數調校，卻無法與軟體演算法產生聯合效應」。本研究提出的全端協同設計框架，正是為了填補此一空白：不僅將探索維度擴張至包含軟體、硬體與 EDA 策略，更透過首創的「快速黑盒子合成機制」打破了 RTL 評估的耗時瓶頸，使得真正意義上的全端 (Full-Stack) 多目標最佳化成為可能。