# Path 1 參數使用驗證報告

## 1. 參數傳遞流程

```
run_15_experiments
  → _merge_params(exp, synth_mode, top_module)
  → params = {DEFAULT_PARAMS} ∪ {EXPERIMENTS 覆寫}
  → evaluate_path1(params, data_args, training_args, hardware_args, cwd)
  → Evaluator.evaluate([params])
  → CiMLoop.evaluate(params)  # sim/metrics/cimloop/cimloop.py
```

**結論**：實驗定義的 `params` 會完整傳入 Path 1，但 **Path 1 內部只使用其中一部分**。

---

## 2. Path 1 實際使用的 params

### 2.1 Accuracy（`sim/metrics/cimloop/accuracy.py`）

| 參數 | 使用處 | 實驗是否有覆寫 |
|------|--------|----------------|
| `hd_dim` | HDFactory | ✓ B, C, E |
| `reram_size` | noisy_encoder, noisy_inference | ✓ B |
| `frequency` | noisy_encoder, noisy_inference | ✓ D, E, G, H |
| `out_channels_1` | set_cnn | ✓ B |
| `kernel_size_1` | set_cnn | ✓ B |
| `stride_1` | set_cnn | 預設 |
| `padding_1` | set_cnn | 預設 |
| `dilation_1` | set_cnn | 預設 |
| `out_channels_2` | set_cnn | ✓ B |
| `kernel_size_2` | set_cnn | ✓ B |
| `stride_2` | set_cnn | 預設 |
| `padding_2` | set_cnn | 預設 |
| `dilation_2` | set_cnn | 預設 |
| `inner_dim` | set_cnn | ✓ C, G |
| `kron`, `f1`, `d1` | set_kronecker（cnn=False 時） | 未使用 |

### 2.2 Power / Performance / Area（`sim/metrics/cimloop/cimloop.py`）

| 參數 | 使用處 | 實驗是否有覆寫 |
|------|--------|----------------|
| `reram_size` | cimloop_ppa | ✓ B |
| `frequency` | timeloop_ppa_hdnn, cimloop_ppa | ✓ D, E, G, H |
| `cnn_x_dim_1` | timeloop_ppa_hdnn | 預設 |
| `cnn_y_dim_1` | timeloop_ppa_hdnn | 預設 |
| `cnn_x_dim_2` | timeloop_ppa_hdnn | 預設 |
| `cnn_y_dim_2` | timeloop_ppa_hdnn | 預設 |
| `encoder_x_dim` | timeloop_ppa_hdnn | 預設 |
| `encoder_y_dim` | timeloop_ppa_hdnn | 預設 |
| `kron` | 分支選擇 | 未使用 |
| `hd_model` | 來自 accuracy，間接依賴 accuracy 的 params | — |

---

## 3. Path 1 完全不使用的 params（僅 Path 2/3 使用）

| 參數 | 用途 | 影響 |
|------|------|------|
| `syn_map_effort` | DC set_app_var | Path 2 合成 |
| `syn_opt_effort` | DC set_app_var | Path 2 合成 |
| `enable_clock_gating` | insert_clock_gating | Path 2 合成 |
| `enable_retime` | compile_ultra -retime | Path 2 合成 |
| `compile_timing_high_effort` | compile_ultra 旗標 | Path 2 合成 |
| `compile_area_high_effort` | compile_ultra 旗標 | Path 2 合成 |
| `compile_ultra_gate_clock` | compile_ultra -gate_clock | Path 2 合成 |
| `compile_exact_map` | compile_ultra -exact_map | Path 2 合成 |
| `compile_no_autoungroup` | compile_ultra -no_autoungroup | Path 2 合成 |
| `compile_clock_gating_through_hierarchy` | DC 變數 | Path 2 合成 |
| `enable_leakage_optimization` | set_leakage_optimization | Path 2 合成 |
| `enable_dynamic_optimization` | set_dynamic_optimization | Path 2 合成 |
| `enable_enhanced_resource_sharing` | compile_enhanced_resource_sharing | Path 2 合成 |
| `max_area_ignore_tns` | set_max_area 0 -ignore_tns | Path 2 合成 |
| `dp_smartgen_strategy` | set_dp_smartgen_options | Path 2 合成 |
| `synth_mode` | EDA 模式選擇 | Path 2/3 |
| `top_module` | 合成/模擬 scope | Path 2/3 |

---

## 4. 各實驗組與 Path 1 的對應關係

### Group A（EDA 策略）

| 實驗 | 變動的 params | Path 1 是否使用 |
|------|---------------|-----------------|
| A1–A5 | syn_map_effort, syn_opt_effort, enable_clock_gating, enable_retime, compile_*, max_area_ignore_tns, dp_smartgen_strategy, enable_leakage_optimization, enable_dynamic_optimization | ❌ 全部未使用 |

**結論**：Group A 的 EDA 參數對 Path 1 完全無影響。A1–A5 的架構相同，Path 1 理論上應得到相同結果；實際差異來自訓練隨機性。

### Group B（架構規模）

| 變動 | Path 1 使用 |
|------|-------------|
| hd_dim, reram_size, out_channels_1/2, kernel_size_1/2 | ✓ 有使用 |

### Group C（inner_dim）

| 變動 | Path 1 使用 |
|------|-------------|
| inner_dim | ✓ 有使用 |

### Group D, E, G, H（頻率）

| 變動 | Path 1 使用 |
|------|-------------|
| frequency | ✓ 有使用（noisy_inference, timeloop, cimloop） |

---

## 5. 潛在問題與建議

### 5.1 實驗設計問題

1. **Group A**：EDA 參數不影響 Path 1，若目的是觀察 EDA 對 PPA 的影響，應以 Path 2/3 的結果為主，Path 1 僅作為 Gate 1 篩選。
2. **cnn_x_dim, encoder_x_dim**：實驗未覆寫，皆用 DEFAULT_PARAMS，若需探索 encoder 維度，需在 EXPERIMENTS 中明確加入。

### 5.2 參數完整性檢查

| 實驗覆寫的 param | Path 1 是否使用 |
|------------------|-----------------|
| hd_dim | ✓ |
| reram_size | ✓ |
| frequency | ✓ |
| out_channels_1/2 | ✓ |
| kernel_size_1/2 | ✓ |
| inner_dim | ✓ |
| 其餘 EDA 相關 | ❌ |

### 5.3 建議

1. 若 Group A 要觀察 EDA 對 **Path 1** 的影響：目前設計無法達成，需改為變動架構參數。
2. 若 Group A 要觀察 EDA 對 **Path 2/3** 的影響：設計合理，但 Path 1 的 accuracy 會沿用，應在論文/報告中說明 Path 1 的 accuracy 與 EDA 無關。
3. 若需探索 `cnn_x_dim`, `encoder_x_dim`：在 EXPERIMENTS 中加入這些參數的覆寫。
