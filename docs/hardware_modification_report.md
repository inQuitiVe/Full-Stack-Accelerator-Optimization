# Testbench 完整模擬 Inference Trial — Hardware 端修改報告

**日期**：2025-02-25  
**目的**：讓 testbench 能依 `inner_dim`、`hd_dim` 正確模擬一個 inference trial，並量測實際 cycle 數與功耗。

---

## 一、背景與動機

目前 testbench 存在以下問題：

1. **`WEIGHT_MEM_ADDR_WIDTH` 寫死**：encoder RF rows 固定為 32，無法隨 `inner_dim` 變化（如 `inner_dim=2048` 需 64 rows）。
2. **`NUM_CLASSES` 固定為 8**：MNIST/CIFAR-10 為 10 classes，HAM_SEG 比較的 class 數與實際不符。
3. **`tb_hd_top_timing` 的 `N_WEIGHT_WORDS_CAP`**：上限 128 會截斷 weight 數量，導致 encoder RF 未填滿。

DSE 端（`json_to_svh.py`、`param_opt.vh`、testbench）已完成修改。**本報告列出 Hardware 端需配合的 RTL 變更**。

---

## 二、DSE / Testbench 端已完成的修改（供參考）

| 項目 | 說明 |
|------|------|
| `json_to_svh.py` | 依 `inner_dim` 計算 `WEIGHT_MEM_ADDR_WIDTH`，寫入 `config_macros.svh` |
| `param_opt.vh` | 移除靜態 `WEIGHT_MEM_ADDR_WIDTH`，改由 `config_macros.svh` 提供 |
| `tb_core_timing.sv` | `NUM_CLASSES=10`，動態 `N_WEIGHT_WORDS`，新增 INNER_DIM 顯示 |
| `tb_hd_top_timing.sv` | 移除 cap，`NUM_CLASSES_SIM=10`，HAM config 改為 `[15:12]` / `[11:8]` |

---

## 三、Hardware 端需修改項目

### 3.1 `WEIGHT_MEM_ADDR_WIDTH` 改為參數化

**現況**：`hd_enc` 等模組若仍使用固定 `WEIGHT_MEM_ADDR_WIDTH`，需改為使用 `config_macros.svh` 的定義。

**作法**：
- 確保所有使用 `WEIGHT_MEM_ADDR_WIDTH` 的 RTL 皆 `include "config_macros.svh"`（透過 `param_opt.vh` 已會 include）。
- 不再在 RTL 中重新定義或覆寫 `WEIGHT_MEM_ADDR_WIDTH`。

**關係式**：
```
inner_dim = OUTPUTS_NUM × RF_ROWS  (OUTPUTS_NUM=32)
WEIGHT_MEM_ADDR_WIDTH = ceil(log2(RF_ROWS))
```
- `inner_dim=1024` → `WEIGHT_MEM_ADDR_WIDTH=5` (32 rows)
- `inner_dim=2048` → `WEIGHT_MEM_ADDR_WIDTH=6` (64 rows)

---

### 3.2 HAM_SEG Config Word 格式 — `hd_top` 路徑

**影響模組**：`hd_top_ctrl` 或負責解析 HAM_SEG config 的邏輯。

**原格式（tb_hd_top_timing 舊版）**：
- Config word 寬度：16 bits（或 `HV_SEG_WIDTH`）
- `[15:13]` = num_class - 1（3 bits，最多 8 classes）
- `[12:9]`  = num_feat_seg - 1（4 bits）

**新格式（tb_hd_top_timing 已採用）**：
- Config word 寬度：16 bits
- `[15:12]` = num_class - 1（4 bits，支援 0..15，對應 1..16 classes）
- `[11:8]`  = num_feat_seg - 1（4 bits）
- `[7:0]`   = 保留（addr / shift = 0）

**請修改 RTL**：將 num_class 的讀取由 `[15:13]` 改為 `[15:12]`，以支援 10 classes（MNIST/CIFAR-10）。

---

### 3.3 HAM_SEG Config Word 格式 — `core` 路徑（tb_core_timing）

**影響模組**：`core` 內負責 HAM_SEG config 的邏輯。

**現有格式（64-bit）**：
- `[19:13]` = num_class - 1（7 bits，支援最多 128 classes）
- `[12:9]`  = num_feat_seg - 1（4 bits）
- `[8:0]`   = base_addr_data_buf 等

此格式已支援 10 classes，**無需修改**。僅需確認 RTL 確實從上述 bit 位置讀取。

---

### 3.4 Config Word 儲存位址差異

| Testbench | Config 儲存位址 | 說明 |
|-----------|-----------------|------|
| `tb_core_timing` | inp_buf[0] | HAM_SEG 強制 base_addr_inp_buf=0 讀取 |
| `tb_hd_top_timing` | inp_buf[64] | 避免與 weights(1..N_WEIGHT_WORDS) 或 features(0..15) 重疊 |

兩者 config 格式不同（64-bit vs 16-bit），但皆由 HAM_SEG 的 op_code 指定讀取位址，請確認 RTL 依各自介面正確解析。

---

## 四、驗證檢查清單

完成 RTL 修改後，建議驗證：

1. **`inner_dim=1024`**：`WEIGHT_MEM_ADDR_WIDTH=5`，N_WEIGHT_WORDS=128（HV_SEG_WIDTH=64 時）
2. **`inner_dim=2048`**：`WEIGHT_MEM_ADDR_WIDTH=6`，N_WEIGHT_WORDS=256
3. **`NUM_CLASSES=10`**：HAM_SEG 能正確解析並比較 10 個 class
4. **tb_core_timing**：FULL EVAL / COMPUTE CYCLES 能正確量測至 oFIFO 輸出
5. **tb_hd_top_timing**：Phase 1 能載入完整 N_WEIGHT_WORDS，無截斷

---

## 五、相關檔案路徑

| 類型 | 路徑 |
|------|------|
| Config 產生 | `eda_server_scripts/json_to_svh.py` |
| RTL 參數 | `fsl-hd/verilog/include/param_opt.vh` |
| 動態 macro | `fsl-hd/verilog/include/config_macros.svh` |
| Core TB | `fsl-hd/verilog/tb/tb_core_timing.sv` |
| HD_top TB | `fsl-hd/verilog/tb/tb_hd_top_timing.sv` |

---

## 六、聯絡與後續

若 RTL 中 HAM config 的 bit 位置與本報告不符，請提供實際解析邏輯，DSE 端可配合調整 testbench 的 config 格式。
