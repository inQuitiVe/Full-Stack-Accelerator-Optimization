# Path 1 frequency 傳遞與 timing 驗證

## 1. frequency 是否有傳入 Path 1？

**有傳入。** 流程如下：

```
run_15_experiments / run_5_aggressive_freq
  → params = {..., "frequency": 200e6} 等（來自實驗定義）
  → evaluate_path1(params, data_args, training_args, hardware_args, cwd)
  → Evaluator.evaluate([params])
  → CiMLoop metric manager: 從 params 取出 frequency
  → timeloop_ppa_hdnn(..., frequency)
  → cimloop_ppa(..., reram_size, frequency, 5)
```

依據 `path1_params_verification.md` 與 `sim/metrics/cimloop/cimloop.py` 流程，`frequency` 會傳入：
- `timeloop_ppa_hdnn`（ASIC delay/energy/area）
- `cimloop_ppa`（RRAM delay/energy/area）

---

## 2. 為何 5 個實驗的 P1 timing 都是 0.062 µs？

可能原因：

### 2.1 底層 delay 未隨 frequency 變化

`timeloop_ppa_hdnn` 與 `cimloop_ppa` 雖有收到 `frequency`，但若：

- 回傳的是**固定 cycles**，且未用 `cycles / frequency` 轉成時間，或
- 回傳的 delay 與 frequency 無關（例如只與架構有關），

則不同 frequency 會得到相同 delay，進而得到相同的 timing。

### 2.2 Path 1 使用 normalized 值當 timing_us

在 `sim/metrics/cimloop/performance.py` 中：

```python
def evaluate(self, asic_delay: float, reram_delay: float, logger):
    total_delay = asic_delay + reram_delay
    performance = total_delay * UNIT   # UNIT=1
    ret = self._normalize(performance)  # performance / 3000.0，clamp 到 1.0
    return (ret, 0.0)
```

`path1_software.py` 第 99 行：

```python
timing_us: float = result["performance"][0]  # 實際拿到的是 normalized 值
```

因此 `result["performance"][0]` 是 **normalized 值（0–1）**，不是原始微秒。  
若 `asic_delay + reram_delay` 對 200–300 MHz 都相同，normalized 後就會都是 0.062。

### 2.3 RRAM delay 可能主導 total delay

若 `reram_delay` 遠大於 `asic_delay`，且 `cimloop_ppa` 的 delay 與 frequency 無關，則 total delay 會幾乎不隨 frequency 變化。

---

## 3. 建議檢查項目

1. **`cimloop.workspace.cimloop_ppa`**  
   - 回傳的 `reram_delay` 單位為何（cycles / ns / µs）？  
   - 是否有用 `frequency` 將 cycles 轉成時間？

2. **`timeloop_ppa_hdnn`**  
   - `asic_delay` 的單位與計算方式？  
   - 是否依 frequency 轉成時間？

3. **Path 1 的 timing 輸出**  
   - 應使用 **raw delay（µs）**，而非 normalized 值。  
   - 若需保留 normalized 給 BO，可同時回傳 raw 與 normalized。

---

## 4. 已修正（path1_software.py）

`path1_software.py` 已改為對 power、performance、area 做 **denormalize**（× 3000）：
- `timing_us = result["performance"][0] * 3000.0` → 正確的 µs
- `energy_uj = result["power"][0] * 3000.0`
- `area_mm2 = result["area"][0] * 3000.0`

原先 0.062 為 normalized 值，對應 raw ≈ 186 µs。

---

## 5. 中繼檢查（送進 timeloop 前的 frequency）

為確保送進 timeloop 前 frequency 正確，在 `path1_software.py` 加入檢查：

- 呼叫 `Evaluator.evaluate()` 前：驗證 `params["frequency"]` ≥ 200 MHz，不足則 clamp 並 log
- 記錄傳入 Evaluator 的 frequency（即送進 timeloop 的值）

**驗證腳本**：`workspace/verify_frequency_passthrough.py`

```bash
cd workspace
python verify_frequency_passthrough.py           # 靜態檢查
python verify_frequency_passthrough.py --run-path1  # 含實際 Path 1 執行
```

---

## 6. 結論

| 項目 | 狀態 |
|------|------|
| frequency 是否傳入 Path 1 | ✓ 有，經 `params` 傳入 `timeloop_ppa_hdnn` 與 `cimloop_ppa` |
| 為何 timing 都相同 | 可能：底層 delay 未隨 frequency 變化，或 Path 1 使用 normalized 值 |
| Path 1 輸出修正 | ✓ 已改為 denormalize（×3000），輸出 raw µs / uJ / mm² |
| 送進 timeloop 前檢查 | ✓ path1_software 含 frequency 驗證與 log |
