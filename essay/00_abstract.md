# 摘要 (Abstract)

記憶體內運算 (Processing-in-Memory, PIM) 結合超維度運算 (Hyperdimensional Computing, HDC) 的架構 (HDnn-PIM)，展現出極具潛力的邊緣運算能效。然而，要針對這類架構進行設計空間探索 (Design Space Exploration, DSE) 是一項艱鉅的挑戰。其設計空間橫跨了軟體演算法參數、硬體 RTL 架構規模，乃至於底層 EDA 工具的合成策略，傳統的孤立優化方法往往無法觸及全域的 Pareto 最佳解 (Pareto Optimum)。此外，硬體邏輯合成的高昂時間成本 (動輒數小時) 成為了阻礙高維度 DSE 的最大瓶頸。

為此，本論文提出了一套自動化的全端協同設計框架 (Full-Stack Co-Design Framework)。本框架以多目標貝葉斯最佳化 (Multi-Objective Bayesian Optimization, BO) 為核心，創新地將軟體模型、硬體陣列，以及 EDA 綜合旗標 (Synthesis Flags) 同時納入搜尋空間中。為克服評估耗時的瓶頸，我們設計了具備提早停止 (Gatekeeping) 機制的多層次保真度評估管道，並首創了「黑盒子快速合成模式 (Fast Black-Box Synthesis Mode)」。該模式透過將不隨參數變動的大型模組自合成清單中抽離，成功將單次邏輯合成時間縮短超過 10 倍，且完美保留了 PPA (Power, Performance, Area) 的相對趨勢。

實驗結果顯示，相較於單獨優化軟體或硬體，本框架能夠在極短的時間內收斂，並發掘出兼具高準確率與低功耗面積的隱藏最佳解，顯著推動了 HDnn-PIM 架構的效能極限。

**關鍵字 (Keywords)**：硬體加速器 (Hardware Accelerator)、超維度運算 (Hyperdimensional Computing)、記憶體內運算 (Processing-in-Memory)、設計空間探索 (Design Space Exploration)、貝葉斯最佳化 (Bayesian Optimization)、邏輯合成 (Logic Synthesis)。