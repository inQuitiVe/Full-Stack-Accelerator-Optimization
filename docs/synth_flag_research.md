# Synthesis Flag Research — Synopsys Design Compiler (DC)

本文件針對 **Synopsys Design Compiler (dc_shell)** 的合成選項做整理，供 Full-Stack-Accelerator-Optimization 專案之 DSE 使用。  
**您先前貼上的參數列表（interconnect_mode, auto_partition, Floorplan, Placement, Routing 等）並非 DC 的選項**，而是其他 EDA 工具（例如 PnR 或其它合成引擎）的參數；DC 僅負責 RTL → Gate-level 合成，不做 Floorplan/Placement/Routing。

---

## 1. 工具與版本範圍

- **工具**：Synopsys Design Compiler（dc_shell / DC Ultra）。
- **參考**：Synopsys DC Ultra 產品說明、Synthesis Variables and Attributes 文件、社群 TCL 範例與討論。  
- **本專案現況**：`eda_server_scripts/json_to_svh.py` 已依 `synth_profile` 注入 TCL（`compile_ultra`、`insert_clock_gating`、`set_dp_smartgen_options` 等），以下選項空間可作為擴充 DSE 或新增 profile 的依據。

---

## 2. compile_ultra 指令選項（完整搜尋空間）

`compile_ultra` 為 DC 的主要高品質合成指令，可搭配下列旗標（依文件與常見用法整理）。

| 選項 | 說明 | 搜尋空間（可納入 DSE 的值） |
|------|------|-----------------------------|
| （無額外旗標） | 預設並行優化 timing/area/power | `default`（代表不帶旗標） |
| `-retime` | 暫存器重定時，改善 timing | `true` / `false` |
| `-timing_high_effort_script` | 高時序優化腳本 | `true` / `false` |
| `-area_high_effort_script` | 高面積優化腳本 | `true` / `false` |
| `-exact_map` | 依 RTL 精確對應 sequential，少做轉換 | `true` / `false` |
| `-no_autoungroup` | 不自動 ungroup，保留階層 | `true` / `false` |
| `-gate_clock` | 閘級 clock gating 優化 | `true` / `false`（多數版本預設 on） |
| `-scan` | 考量 scan 插入 | `true` / `false` |
| `-incremental` | 僅做增量優化，不重做 mapping | `true` / `false` |
| `-no_boundary_optimization` | 關閉邊界最佳化 | `true` / `false` |
| `-no_design_rule` | 不做 DRC | `true` / `false` |
| `-only_design_rule` | 僅做 DRC | `true` / `false` |
| `-check_only` | 只檢查不合成 | `true` / `false` |
| `-top` | 僅對 current design 做 compile_ultra | `true` / `false` |
| `-num_cpus n` | 使用 n 個 CPU | 整數，例如 `1`–`16` |
| `-congestion` | 考量擁塞（需 topographical） | `true` / `false` |

**本專案已使用**：  
- `timing_aggressive` → `compile_ultra -retime -timing_high_effort_script`  
- `power_aggressive` → `compile_ultra -area_high_effort_script`  
- `balanced_default` → `compile_ultra`  
- `exact_map` → `compile_ultra -exact_map -no_autoungroup`

---

## 3. 時脈 gating 相關（完整搜尋空間）

| 指令/變數 | 說明 | 搜尋空間 |
|-----------|------|-----------|
| `insert_clock_gating` | 插入 RTL 層級 clock gating | 執行 / 不執行（由 profile 決定） |
| `set_clock_gating_style -sequential_cell` | 使用之 sequential 單元型態 | `latch` / `integrated_clock_gating_cell` / 等（依 library） |
| `compile_ultra -gate_clock` | 閘級 clock gating | `true` / `false` |

本專案已在 `balanced_default`、`power_aggressive` 使用 `set_clock_gating_style -sequential_cell latch` + `insert_clock_gating`。

---

## 4. set_dp_smartgen_options（完整搜尋空間）

用於 datapath 優化策略，與 `compile_ultra` 搭配。

| 選項 | 說明 | 搜尋空間 |
|------|------|----------|
| `-optimization_strategy` | 優化重心 | `timing` / `area` / `power`（依版本與文件） |

本專案已使用：  
- `timing_aggressive` → `-optimization_strategy timing`  
- `power_aggressive` → `-optimization_strategy area`

---

## 5. set_app_var 常用合成變數（完整搜尋空間）

以下為 DC 常見之 `set_app_var` 變數，可用於 DSE 或手動 TCL 微調。

| 變數 | 說明 | 搜尋空間 |
|------|------|----------|
| `syn_map_effort` | mapping 階段努力度 | `low` / `medium` / `high` / `express` / `none`（依版本） |
| `syn_opt_effort` | 優化階段努力度 | `low` / `medium` / `high` / `express` / `none` |
| `syn_generic_effort` | generic 階段努力度 | `low` / `medium` / `high` / `express` / `none` |
| `hdlin_enable_hier_map` | 階層 mapping | `true` / `false` |
| `compile_clock_gating_through_hierarchy` | 跨階層 clock gating | `true` / `false` |
| `compile_ultra_ungroup_dw` | DesignWare ungroup | `true` / `false` |

**注意**：實際支援之值與版本有關，需以 `man set_app_var` 或 Synopsys Synthesis Variables 文件為準。

---

## 6. 本專案適合納入 DSE 的 DC 選項建議

在維持目前四種 `synth_profile` 的前提下，可考慮以下擴充（皆為**真實 DC 指令/變數**）：

1. **compile_ultra 旗標組合**  
   - 已涵蓋：`-retime`、`-timing_high_effort_script`、`-area_high_effort_script`、`-exact_map`、`-no_autoungroup`。  
   - 可再加：`-gate_clock` 開/關、`-num_cpus`（若需控制 run time）。

2. **set_dp_smartgen_options**  
   - 已用 `timing` / `area`；若 DC 版本支援，可將 `power` 納入 `-optimization_strategy` 的選項空間。

3. **set_app_var 努力度**  
   - 可新增一層 DSE：在呼叫 `compile_ultra` 前設定 `syn_map_effort` / `syn_opt_effort` 為 `medium` 或 `high`，觀察 PPA 與 run time 取捨。

4. **時脈 gating**  
   - 已用 `set_clock_gating_style` + `insert_clock_gating`；可選配「僅 `compile_ultra -gate_clock`、不做 insert_clock_gating」作為另一 profile，比較 power/area。

上述每一項的「搜尋空間」已寫在對應表格中，可直接用來定義 BO 的 discrete 參數或新 profile。

---

## 7. 您貼上參數的來源說明（非 DC）

您提供的清單中包含例如：

- **Synthesis 區塊**：`interconnect_mode`、`auto_partition`、`bank_based_multibit_inferencing`、`boundary_optimize_*`、`dp_*`、`hdl_*`、`multibit_*`、`retime_*`、`syn_generic_effort`、`syn_map_effort`、`syn_opt_effort`、`ultra_global_mapping`、`use_multibit_cells` 等。  
- **Floorplan / Placement / Routing**：`margin_by`、`origin`、`mode`、`aspect`、`density`、`global_*`、`detail_*`、`post_*`、`timing_driven`、`hold` 等。

這些名稱與 DC 標準指令/變數不盡一致，且 **Floorplan / Placement / Routing 屬於 PnR 工具**（如 Synopsys Fusion Compiler、IC Compiler II，或 Cadence Innovus 等），**不是 Design Compiler 的管轄範圍**。  
若要做「合成 + PnR」的聯合 DSE，需要：  
- 合成階段：僅使用 DC 的選項（即本文件 2–5 節）；  
- PnR 階段：另查該 PnR 工具之指令與變數，並在另一份文件中整理其搜尋空間。

---

## 8. 參考與注意事項

- Synopsys DC Ultra 產品說明與 datasheet。  
- Synthesis Variables and Attributes（Synopsys 版本對應文件）。  
- 實際支援的選項與取值以您環境中的 DC 版本為準（`dc_shell -version`），建議在正式納入 DSE 前於單一 TCL 腳本中逐項驗證。

以上為針對 **Synopsys Design Compiler** 的合成旗標研究與完整選項空間整理，可直接用於擴充 `synth_profile` 或新增合成相關 DSE 參數。
