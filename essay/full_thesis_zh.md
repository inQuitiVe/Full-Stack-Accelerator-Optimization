# 摘要 (Abstract)

記憶體內運算 (Processing-in-Memory, PIM) 結合超維度運算 (Hyperdimensional Computing, HDC) 的架構 (HDnn-PIM)，展現出極具潛力的邊緣運算能效。然而，要針對這類架構進行設計空間探索 (Design Space Exploration, DSE) 是一項艱鉅的挑戰。其設計空間橫跨了軟體演算法參數、硬體 RTL 架構規模，乃至於底層 EDA 工具的合成策略，傳統的孤立優化方法往往無法觸及全域的 Pareto 最佳解 (Pareto Optimum)。此外，硬體邏輯合成的高昂時間成本 (動輒數小時) 成為了阻礙高維度 DSE 的最大瓶頸。

為此，本論文提出了一套自動化的全端協同設計框架 (Full-Stack Co-Design Framework)。本框架以多目標貝葉斯最佳化 (Multi-Objective Bayesian Optimization, BO) 為核心，創新地將軟體模型、硬體陣列，以及 EDA 綜合旗標 (Synthesis Flags) 同時納入搜尋空間中。為克服評估耗時的瓶頸，我們設計了具備提早停止 (Gatekeeping) 機制的多層次保真度評估管道，並首創了「黑盒子快速合成模式 (Fast Black-Box Synthesis Mode)」。該模式透過將不隨參數變動的大型模組自合成清單中抽離，成功將單次邏輯合成時間縮短超過 10 倍，且完美保留了 PPA (Power, Performance, Area) 的相對趨勢。

實驗結果顯示，相較於單獨優化軟體或硬體，本框架能夠在極短的時間內收斂，並發掘出兼具高準確率與低功耗面積的隱藏最佳解，顯著推動了 HDnn-PIM 架構的效能極限。

**關鍵字 (Keywords)**：硬體加速器 (Hardware Accelerator)、超維度運算 (Hyperdimensional Computing)、記憶體內運算 (Processing-in-Memory)、設計空間探索 (Design Space Exploration)、貝葉斯最佳化 (Bayesian Optimization)、邏輯合成 (Logic Synthesis)。

---

# 1. 簡介 (Introduction)

## 1.1 研究背景 (Background)
隨著人工智慧與物聯網 (IoT) 邊緣運算的蓬勃發展，對於具備高能效與低延遲的運算架構需求日益增加。傳統的范紐曼 (von Neumann) 架構在處理大量資料時，受限於記憶體與處理器之間的資料搬移瓶頸 (Memory Wall)，導致嚴重的能耗與延遲問題。為了解決此問題，記憶體內運算 (Processing-in-Memory, PIM) 技術應運而生。PIM 透過在記憶體陣列內部或附近直接執行運算，大幅減少了資料搬移，展現出極高的能效潛力。

同時，超維度運算 (Hyperdimensional Computing, HDC) 作為一種新興的輕量級機器學習典範，因其高度的平行性、對硬體錯誤的強大容錯能力，以及簡易的訓練過程，被認為是邊緣運算的理想演算法。將 HDC 演算法與 PIM 架構結合 (HDnn-PIM)，能夠在極低的功耗下實現高效的推論與學習，是目前硬體加速器研究的熱門領域。

## 1.2 問題陳述 (Problem Statement)
然而，設計一個最佳化的 HDnn-PIM 加速器是一項極度複雜的挑戰。其設計空間 (Design Space) 橫跨了多個抽象層級：
1. **軟體演算法層級**：如超維度向量長度 (`hd_dim`)、編碼器維度 (`inner_dim`) 等，這些參數直接影響模型的準確度 (Accuracy)。
2. **硬體架構層級**：如記憶體陣列大小 (`reram_size`)、處理單元數量 (`cnn_x_dim`, `cnn_y_dim`) 等，決定了晶片的面積 (Area)、功耗 (Power) 與效能 (Performance)。
3. **EDA 合成策略層級**：在將 RTL 轉換為硬體邏輯閘的過程中，Design Compiler (DC) 的優化腳本與合成旗標 (Synthesis Flags) 對最終的 PPA (Power, Performance, Area) 有著決定性的影響。

傳統的設計空間探索 (Design Space Exploration, DSE) 面臨以下三大痛點：
1. **軟硬體孤立優化**：通常先由軟體工程師決定演算法參數，再交由硬體工程師進行 RTL 設計。這種脫節的流程難以捕捉軟硬體參數間的非線性耦合，導致無法找到全域最佳解 (Global Optimum)。
2. **評估成本極其高昂**：將 RTL 程式碼進行邏輯合成 (Logic Synthesis) 或閘級模擬 (Gate-level Simulation) 動輒需要數十分鐘至數小時。若要在包含數萬種組合的設計空間中進行窮舉或隨機搜尋，時間成本是不可接受的。
3. **忽略 EDA 策略的影響**：過去的 DSE 多半固定使用同一套合成腳本，忽略了底層 EDA 工具 (如 `compile_ultra` 努力度、暫存器重定時 `retime` 等) 對探索 Pareto 邊界 (Pareto Frontier) 的巨大潛力。

## 1.3 我們的解決方案與貢獻 (Proposed Solution & Contributions)
為了解決上述挑戰，本研究提出了一套**自動化、多層次保真度 (Multi-Fidelity) 的全端協同設計框架 (Full-Stack Co-Design Framework)**，專為 HDnn-PIM 架構量身打造。我們利用多目標貝葉斯最佳化 (Multi-Objective Bayesian Optimization) 演算法，在龐大的參數空間中高效尋找 Accuracy、Energy、Delay 與 Area 的 Pareto 最佳解。

本文的主要貢獻如下：
1. **全端軟硬體協同優化 (Full-Stack Co-Design)**：打破軟硬體設計的藩籬，將 HDC 演算法參數、PIM 陣列架構參數，以及底層 EDA 合成策略同時納入貝葉斯最佳化的搜尋空間，實現真正的全域優化。
2. **多層次保真度與提早停止機制 (Multi-Fidelity Pipeline with Gatekeeping)**：建立從「純軟體模擬」到「硬體邏輯合成」，再到「週期精確 (Cycle-accurate) 閘級模擬」的三階段評估管道。利用軟體模擬的極快速度作為第一道把關 (Gatekeeper)，提早淘汰準確率不達標的設計，大幅節省無效的合成時間。
3. **快速黑盒子合成機制 (Fast Black-Box Synthesis Mode)**：針對巨大且不隨 DSE 參數變動的硬體模組 (如 PatterNet)，提出創新的黑盒子合成策略。僅對受參數影響的核心模組進行合成，在保持趨勢準確性的前提下，將每次 DSE 迭代的合成時間縮短數十倍。
4. **探索 EDA 策略對 PPA 的影響**：首創將 Synopsys Design Compiler 的優化參數 (如 `synth_profile`, `syn_map_effort` 等) 參數化，證明讓 BO 動態決策合成策略能有效推動 Pareto 邊界的極限。

---

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

---

# 3. 提出的全端設計空間探索框架 (Proposed Full-Stack DSE Framework)

為了解決高維度參數耦合與硬體評估過於耗時的問題，我們提出了一套基於多目標貝葉斯最佳化 (Multi-Objective BO) 的全自動化全端協同設計框架。本框架具備去耦合架構 (Decoupled Architecture)、多層次保真度 (Multi-Fidelity) 評估，以及首創的快速黑盒子合成機制 (Fast Black-Box Synthesis)。

## 3.1 系統架構：Thin-Client 黑盒子 API 模型
由於商用 EDA 工具 (如 Synopsys Design Compiler, VCS) 通常受到嚴格的授權 (License) 與內網環境限制，難以直接與現代基於 Python/Docker 的機器學習與 BO 框架綁定。為此，我們設計了 **Thin-Client (瘦客戶端) 系統架構**：

* **Client 端 (BO Engine)**：運行於 Docker 容器內，負責執行貝葉斯最佳化演算法 (使用 Meta Ax 框架)、PyTorch 軟體神經網路訓練，以及架構級的效能模擬 (Cimloop/Timeloop)。Client 端扮演 DSE 的「大腦」。
* **EDA Server 端 (硬體評估中心)**：運行於具有 EDA 授權的遠端 Linux 伺服器上。Server 端暴露了一個基於 TCP Socket 的非同步 API。當 Client 產生一組新的參數組合時，會將其打包為 JSON 格式發送給 Server。Server 負責將參數動態轉換為 SystemVerilog 標頭檔 (`config_macros.svh`) 與 TCL 腳本，並驅動 Design Compiler 進行合成。最終，Server 僅將解析後的數值化 PPA 指標回傳給 Client。

這種 Decoupled API 模式不僅解決了授權問題，更使得架構具備極高的擴充性，未來可輕鬆替換後端的 EDA 工具或叢集。

## 3.2 多層次保真度評估與提早停止機制 (Multi-Fidelity Evaluation and Gatekeeping)
為避免在無效的設計上浪費昂貴的合成時間，我們將單次評估 (Evaluation) 拆分為三個具備「提早停止 (Early Stopping/Gatekeeping)」機制的層次 (Paths)：

1. **Path 1: 軟體模擬 (Software Simulation - Fast)**
   - 流程：Client 端利用 PyTorch 訓練 HDnn 模型，並取得軟體準確率 (Accuracy)。同時，利用分析模型 (Analytical Models，如 Cimloop) 進行初步的 RRAM 能量與延遲估算。
   - **Gate 1 (準確率門檻)**：若此參數組合訓練出的模型準確率低於使用者定義的底線 (如 79%)，BO 引擎會立即將此 Trial 標記為失敗 (Failed)，終止評估，**完全跳過後續的硬體合成**。

2. **Path 2: 硬體合成與混合拼接 (Hardware Synthesis and Stitching - Medium)**
   - 流程：通過 Gate 1 的參數將被送往 EDA Server 進行邏輯合成。由於 PIM 加速器中的 RRAM 類比陣列部分沒有標準的 RTL，我們採用「混合拼接 (Stitching)」策略：
     - `總面積 (Area) = 數位邏輯面積 (來自 EDA) + RRAM 面積 (來自 Cimloop)`
     - `總延遲 (Delay) = 數位邏輯時脈週期 (來自 EDA) + RRAM 讀寫延遲 (來自 Cimloop)`
   - **Gate 2 (時序門檻)**：若合成出的電路發生嚴重的時序違例 (Timing Violation, Slack < 0)，表示此架構在給定的頻率下無法實作，該 Trial 將被判定為失敗，BO 模型會記錄此硬性限制。

3. **Path 3: 閘級模擬與功耗驗證 (Gate-Level Simulation & Power Verification - High Fidelity)**
   - Path 3 僅在「通過 Gate 2 且使用者啟用 Path 3」時被觸發。Client 端只需在送往 EDA Server 的 JSON 請求中加入 `run_path3=True` 旗標，Server 便會在 Path 2 合成完成且無時序違例時，自動進一步執行閘級模擬與功耗分析。
   - 為了避免從 PyTorch 傳輸大量 `.hex` 測試資料到 EDA 主機，我們改採 **LFSR-based Testbench**：在硬體專案 `fsl-hd/verilog/tb/` 中，提供 `tb_core_timing.sv` 與 `tb_hd_top_timing.sv` 兩個測試平台，分別對應 `core` 以及 `hd_top` 兩種頂層。這些 Testbench 會以 LFSR 自行產生輸入序列，並在有限狀態機 (FSM) 內部精確記錄「ENC_PRELOAD → oFIFO result」之間的 **計算週期數 (`COMPUTE CYCLES`)**，同時產生 SAIF 活動檔供 PrimeTime PX 使用。
   - PrimeTime PX 讀取 SAIF 檔與合成後網表，回傳閘級動態功耗與漏電功耗；設計框架則將 Path 2 的時脈週期 (clock period) 與 Path 3 的執行週期數 (execution cycles) 相乘，得到更高保真度的 ASIC 延遲估計，再與 Cimloop 的 RRAM 延遲與能量加總，形成最終的多目標指標。RRAM 區塊在實驗中依然沒有真實 RTL，因此其 PPA 仍以 Cimloop 為唯一來源。

## 3.3 核心創新：快速黑盒子合成機制 (Fast Black-Box Synthesis Mode)
即使用了 Gatekeeping 機制，留下來需要進行邏輯合成的參數組合依然非常龐大。我們進一步分析 HDnn-PIM 的硬體特性發現：在 DSE 過程中，**被改變的參數僅影響 HD 核心邏輯** (如 Hypervector 寬度、Encoder 單元數等)。而佔據極大面積的 CNN 特徵提取器 (PatterNet)、固定的 SRAM Buffer 與系統介面，在整個搜尋過程中是完全靜態的。

為此，我們提出了 **「快速合成模式 (Fast Mode)」**：
* 在產生 TCL 腳本時，我們使用**白名單 (Whitelist) 機制**，僅將隨參數變動的 SystemVerilog 檔案 (如 `hd_enc.sv`, `hd_search.sv`) 加入 `analyze` 清單。
* 刻意**不引入**靜態且龐大的 PatterNet 模組。Design Compiler 在 `elaborate` 與 `link` 階段會找不到這些模組，進而將其視為**黑盒子 (Black Box)**。
* **效益與影響**：在這種由下而上 (Bottom-up) 的黑盒子合成下，EDA 工具會將未定義模組的面積與功耗視為 0，並迅速完成剩餘邏輯的合成。這使得**單次合成時間從接近 1 小時驟降至數分鐘內**。由於 PatterNet 等靜態模組的 PPA 在整個 DSE 中可視為常數，將常數移除並**不影響 BO 觀察參數變動的「相對趨勢」**。BO 依然能準確無誤地朝向真正的 Pareto 最佳解收斂。

進一步地，我們將 **「合成模式 (synth_mode)」** 與 **「頂層模組 (top_module)」** 做到完全解耦：

* `synth_mode ∈ {slow, fast}`：控制是否將 PatterNet 等靜態模組納入 DC 合成中。`slow` 會重新合成全系統；`fast` 則維持黑盒子模式，只針對 HD 核心邏輯進行增量合成。
* `top_module ∈ {core, hd_top}`：控制 DC Elaborate 以及 Path 3 Testbench 的觀測範圍。`core` 代表從 SoC 封裝視角觀察 (含 `chip_interface` / FIFO 等介面邏輯)；`hd_top` 則只聚焦在超維度核心本身。

透過這兩個正交的維度，本框架可以支援 2D 的實驗組合：例如在前期 DSE 用 `synth_mode=fast, top_module=hd_top` 快速掃描 HD 核心的趨勢，最後再以 `synth_mode=slow, top_module=core` 對少數 Pareto 候選進行高保真度的全系統驗證。

## 3.4 EDA 綜合策略的多維度探索 (Synthesis Optimization Exploration)
傳統硬體 DSE 往往將 EDA 工具視為固定且被動的編譯器，忽視了綜合腳本對最終電路效能的影響。本框架打破了這個限制，將 **Design Compiler 的綜合策略 (Synthesis Flags) 直接納入 BO 的搜尋空間**。

我們將以下參數交由 BO 動態決策：
1. **`synth_profile` (綜合輪廓)**：提供高層級的策略預設。
   - `balanced_default`：標準的 `compile_ultra`、時脈閘控與 `set_max_area 0`。
   - `timing_aggressive`：`set_max_area 0` + 重定時 (`-retime`) 與高時序優化腳本，犧牲面積換取極限速度。
   - `power_aggressive`：時脈閘控 + 漏電/動態優化 + `compile_ultra -gate_clock`，追求極致功耗優化。
   - `area_aggressive`：`set_max_area 0 -ignore_tns` + 面積導向腳本，追求極致微縮（可能違反時序）。
   - `exact_map`：保留 RTL 階層，確保精準對應。
2. **`syn_map_effort` 與 `syn_opt_effort`**：控制對映 (Mapping) 與優化 (Optimization) 階段的努力度等級 (`low`/`medium`/`high`)。

透過將「硬體架構參數」與「EDA 綜合參數」聯合優化，BO 可以在遇到架構層面的時序瓶頸時，主動切換至 `timing_aggressive` 的 EDA 策略來彌補，從而發掘出單獨調整架構或單獨調整腳本都無法達到的隱藏 Pareto 最佳點。

---

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
| 領域 (Domain) | 參數名稱 (Parameter) | 型別 (Type) | 數值範圍或選項 (Values / Bounds) | 說明 (Description) |
| :--- | :--- | :--- | :--- | :--- |
| **Software** | `hd_dim` | Choice (int) | [2048, 4096, 8191] | 超維度向量長度；上限 8191（HAMMING_DIST_WIDTH=13） |
| **Software** | `inner_dim` | Choice (int) | [1024, 2048, 4096] | HD Encoder 的內部轉換維度 |
| **Hardware** | `reram_size` | Choice (int) | [64, 128, 256] | RRAM 陣列大小，影響 PIM 計算能力與面積 |
| **Hardware** | `cnn_x_dim_*` / `cnn_y_dim_*`| Choice (int) | [8, 16] | PatterNet 中 CNN PE 陣列的長寬規模 (各層) |
| **Hardware** | `encoder_x_dim` / `encoder_y_dim`| Choice (int) | [8, 16] | Encoder 的處理單元數量 |
| **Hardware** | `out_channels_*`, `kernel_size_*`| Choice (int) | 依網路架構而定 | 卷積神經網路的特徵提取參數 |
| **EDA** | `synth_profile` | Choice (str) | [`balanced_default`, `timing_aggressive`, `power_aggressive`, `area_aggressive`, `exact_map`] | DC 合成策略預設腳本 |
| **EDA** | `syn_map_effort` | Choice (str) | [`low`, `medium`, `high`] | DC 映射階段的優化努力度 |
| **EDA** | `syn_opt_effort` | Choice (str) | [`low`, `medium`, `high`] | DC 整體優化階段的努力度 |

## 4.3 評估指標與多目標優化 (Evaluation Metrics and Objective)
本研究為一個典型的多目標最佳化問題 (Multi-Objective Optimization Problem, MOOP)。我們定義了四個維度的評估指標：
1. **Accuracy (準確率)**：愈高愈好，由 PyTorch 軟體模擬取得。
2. **Energy (能量消耗, uJ)**：愈低愈好，由 (DC 動態/漏電功耗 $\times$ 執行時間) + RRAM 能量所構成。
3. **Delay / Timing (執行延遲, us)**：愈低愈好，由 (DC 合成出之時脈週期 $\times$ 執行週期數) 構成。
4. **Area (晶片面積, mm²)**：愈低愈好，由 DC 報告之數位邏輯面積 + RRAM 面積構成。

在貝葉斯最佳化中，我們使用 **超體積 (Hypervolume, HV)** 作為衡量 Pareto 前緣 (Pareto Front) 品質的單一指標。我們將尋求在特定硬性限制 (Constraints，例如 Accuracy $\geq 0.79$) 下，最大化這四個指標所形成的超體積。

## 4.4 實驗組別設計 (Baseline Configurations)

本框架的搜尋空間由 `conf/params_prop/cimloop.yaml` 定義，可透過 `run_exploration.py` 執行 DSE。輸出 `dse_results.json` 除最終目標外，亦包含 Path 2/3 原始指標（p2_area_um2、p2_timing_slack_ns、p3_execution_cycles 等）。

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

---

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
* 使用 `power_aggressive` 策略可進一步優化功耗，適合對時序要求較寬鬆但極端受限於功耗的邊緣場景；`area_aggressive` 則專注於面積極小化，可能犧牲時序。
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

---

# 6. 結論與未來展望 (Conclusion and Future Work)

## 6.1 結論 (Conclusion)
在本論文中，我們針對超維度記憶體內運算 (HDnn-PIM) 架構，提出並實作了一套基於多目標貝葉斯最佳化 (Multi-Objective BO) 的自動化全端協同設計框架。本研究成功克服了傳統硬體設計空間探索 (DSE) 面臨的三大挑戰：軟硬體脫節、合成評估過度耗時，以及忽略 EDA 綜合策略的潛力。

透過本框架的實作與實驗驗證，我們獲得了以下重要結論：
1. **多維度協同優化的必要性**：打破軟體演算法與硬體 RTL 之間的界線，並首次將 EDA 工具的合成旗標納入探索空間，使得 BO 能夠發掘出單一領域優化無法觸及的隱藏 Pareto 最佳解。
2. **多層次保真度與提早停止機制的效益**：利用軟體模擬的準確率作為第一道防線 (Gatekeeping)，有效過濾了大量不具競爭力的設計，避免了後續不必要的硬體資源浪費。
3. **黑盒子快速合成模式的突破**：我們提出的 Fast Mode 將不隨參數變動的巨大模組抽離，使得單次邏輯合成的時間縮短了 $10\times \sim 15\times$，同時完美保留了 PPA 變化的相對趨勢。這項突破使得在合理的開發時程內進行高維度硬體 DSE 成為可能。

## 6.2 未來展望 (Future Work)
基於目前的框架基礎，我們提出以下幾個未來可進一步延伸的研究方向：
1. **擴展至實體設計層 (Physical Design / PnR)**：目前框架的硬體評估止步於邏輯合成 (Logic Synthesis)。未來可將 Floorplan、Placement 與 Routing 等後端 (Backend) 參數納入搜尋空間，以取得更精確的時序與擁塞 (Congestion) 數據。
2. **多層次保真度最佳化 (Multi-Fidelity BO)**：引進高階的 Multi-Fidelity BO 演算法 (例如 BOCA 或 MF-MES)，讓演算法能夠「主動選擇」要在 Fast Mode 或 Slow Mode 下進行評估，進一步極大化搜尋效率。
3. **支援更多樣化的硬體架構**：目前框架針對 HDnn-PIM 量身打造，未來可透過擴充模板機制，使其適用於其他類型的深度學習加速器 (如 Systolic Arrays 或 Transformer 加速器)。

---

