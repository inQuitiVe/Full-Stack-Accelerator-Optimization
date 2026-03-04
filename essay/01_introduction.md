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