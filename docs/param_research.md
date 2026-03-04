## `param.vh` 關鍵參數深度解析（L24–L112）

本節針對 `param.vh` 第 24–112 行的所有巨集，說明它們在整個 FSL‑HD / hd_top 架構中的**角色、數學關係與設計考量**，方便之後把 DSE 參數（例如 `hd_dim`, `reram_size`）與這些 RTL level 參數對起來。

> 參考範圍（節錄）：
> 
> ```verilog
> /////////// Chip infrastructures ///////////
> // Chip JTAG
> `define JTAG_LEN                15
> 
> // Chip FIFOs
> `define CDC_INST_FIFO_DEPTH     32
> `define CDC_IO_FIFO_DEPTH       32
> 
> `define INST_FIFO_DEPTH         16
> `define IO_FIFO_DEPTH           16
> 
> `define INST_FIFO_WIDTH         3
> `define INP_FIFO_PUSH_WIDTH     34
> `define INP_FIFO_POP_WIDTH      68
> `define OUT_FIFO_PUSH_WIDTH     68
> `define OUT_FIFO_POP_WIDTH      34
> 
> `define PATTERNET_INP_FIFO_PUSH_WIDTH     64
> `define PATTERNET_INP_FIFO_POP_WIDTH      32
> `define PATTERNET_OUT_FIFO_PUSH_WIDTH     32
> `define PATTERNET_OUT_FIFO_POP_WIDTH      64
> 
> `define RRAM_INP_FIFO_WIDTH       64
> `define RRAM_OUT_FIFO_WIDTH       64
> 
> `define RRAM_ROW_ADDR_WIDTH       10
> 
> //////////////////////////////////////////
> 
> /////////// Instruction format ///////////
> `define INST_WIDTH              4
> `define OP_CODE_WIDTH           16
> `define PAD_INST_WIDTH          5
> `define STATE_WIDTH             4
> //////////////////////////////////////////
> 
> //////////// FSL-HD module ////////////
> // Top
> `define HD_INP_FIFO_WIDTH       64
> `define HD_OUT_FIFO_WIDTH       64
> 
> `define INP_BUF_ADDR_WIDTH      8
> `define DATA_BUF_ADDR_WIDTH     12
> 
> // Encoding
> `define INPUTS_NUM              8
> `define IDATA_WIDTH             8
> 
> `define OUTPUTS_NUM             32
> `define ODATA_WIDTH             16
> 
> `define WEIGHT_MEM_ADDR_WIDTH   5
> `define WEIGHT_MEM_DATA_WIDTH   32
> 
> `define INPUT_MEM_ADDR_WIDTH    5
> `define INPUT_MEM_DATA_WIDTH    32
> 
> `define NUM_RF_BANK             8
> `define WEIGHT_BUS_WIDTH        256
> 
> // Search
> `define HV_SEG_WIDTH            64
> `define MAX_CLASS_NUM           128
> `define CLASS_LABEL_WIDTH       7
> `define HAMMING_DIST_WIDTH      13
> 
> `define PRE_FETCH_SIZE          128
> `define PREFETCH_MEM_ADDR_WIDTH 7
> `define POPCNT_WIDTH            7
> `define CLASS_LABEL_WIDTH       7
> 
> // Training
> `define TRAINING_DATA_NUM       8
> `define TRAINING_ADDR_WIDTH     3
> 
> `define SP_TRAINING_WIDTH       512
> `define TRAINING_DATA_WIDTH     8
> 
> // Interface with PatterNet
> `define PATTERNET_FEAT_SRAM_DATA_WIDTH       8
> `define PATTERNET_FEAT_SRAM_ADDR_WIDTH       11
> //////////////////////////////////////////
> ```

---

### 1. Chip infrastructures（晶片基礎設施）

#### 1.1 `JTAG_LEN`

- **定義**：`JTAG_LEN = 15`
- **意義**：JTAG shift register 長度。代表一次 JTAG scan chain 會 shift 15 bit。
- **用途**：
  - 影響 TAP controller / JTAG wrapper 裡 register 長度。
  - 若之後想透過 JTAG 下指令、讀 debug 狀態，這個長度要與 RTL 中 JTAG module 一致。
- **與 DSE/hd_dimension 關係**：目前**無直接關聯**，純屬晶片 bring‑up / debug 介面設定，通常不會進入 BO 參數空間。

#### 1.2 CDC FIFO 相關

- **`CDC_INST_FIFO_DEPTH = 32`**
- **`CDC_IO_FIFO_DEPTH   = 32`**

**意義**：

- 這兩個 FIFO 是 clock‑domain crossing（CDC）用的 instruction / IO FIFO 深度，通常位在 chip I/O 或 top‑level wrapper，負責：
  - 匯流排 domain ↔ core domain 之間的資料緩衝。
  - 平衡吞吐量與 \( \text{latency / backpressure} \)。

**設計考量**：

- 越大：
  - **Pros**：對 burst traffic 更友善，不容易 backpressure。
  - **Cons**：面積增加、可能增加路徑長度／時脈收斂難度。
- 深度 32 是一個折衷（常見 power‑of‑two config）。

**與 DSE 關係**：

- 若未來要探索「IO 吞吐 vs 面積 / 時序」，可以把這兩個深度當成 BO 參數，但目前 DSE 主要 focus 在 `HV_LENGTH`, CNN dim, reram size，因此暫時可以視為固定架構參數。

#### 1.3 Top‑level instruction / data FIFO

- **`INST_FIFO_DEPTH = 16`**
- **`IO_FIFO_DEPTH   = 16`**

**意義**：

- 這兩個是 core 內部 instruction FIFO / IO FIFO 的深度。
- 深度 16 代表：
  - 最多可預先 queue 16 筆指令或 IO entry，減少 host 端每一 cycle 都要餵資料的壓力。

**與 `INST_FIFO_WIDTH`, push/pop 寬度的關係**：

- 以下寬度巨集搭配這些深度使用：
  - `INST_FIFO_WIDTH = 3`
  - `INP_FIFO_PUSH_WIDTH = 34`
  - `INP_FIFO_POP_WIDTH  = 68`
  - `OUT_FIFO_PUSH_WIDTH = 68`
  - `OUT_FIFO_POP_WIDTH  = 34`

#### 1.4 Instruction / IO FIFO 寬度族

##### `INST_FIFO_WIDTH = 3`

- **意義**：
  - 單次 push 進 instruction FIFO 的「片段寬度」為 3 bit。
  - 配合 `INST_WIDTH = 4` 和 FIFO 深度 16，通常會搭配多拍 shift/pack。
- 在 `tb_top_warpper.sv` 中可看到使用方式：
  - testbench 把 `{device, instruction, op_code}` 打包成 64 bit，然後每次送 3 bit 進 `din_inst_fifo`。DUT 端會再重新組合成完整指令。

##### `INP_FIFO_PUSH_WIDTH = 34` / `INP_FIFO_POP_WIDTH = 68`

- **意義**：
  - **push 寬度 34 bit**：host / testbench 往 input FIFO 送資料時一次 34 bit。
  - **pop 寬度 68 bit**：core 取出時一次讀 68 bit（可能對應兩筆 34bit entry 或對齊到內部 64bit + 控制標籤）。
- 猜測使用模式：
  - 34 = 32 (data) + 2 或其它 control bit，實際 mapping 在 `sub_module.sv` / FIFO wrapper 裡。

##### `OUT_FIFO_PUSH_WIDTH = 68` / `OUT_FIFO_POP_WIDTH = 34`

- 與 input FIFO 剛好相反：
  - **push 68 bit**：core 把結果/中繼資料一次塞 68 bit。
  - **pop 34 bit**：host 減半讀出。
- 這組寬度組合是**對外介面協議**的一部份，而不是超高層的 DSE hyperparameter。

#### 1.5 PatterNet ↔ HD 之 FIFO 寬度

- **`PATTERNET_INP_FIFO_PUSH_WIDTH = 64`**
- **`PATTERNET_INP_FIFO_POP_WIDTH  = 32`**
- **`PATTERNET_OUT_FIFO_PUSH_WIDTH = 32`**
- **`PATTERNET_OUT_FIFO_POP_WIDTH  = 64`**

**意義**：

- 這是 PatterNet 模組與 HD core 之間 FIFO 的 bit 寬：
  - 從 PatterNet 過來的 feature / activation，push 64、pop 32，代表方向、時序與對齊策略。
  - 往 PatterNet 回傳時，方向反過來。
- 這些值與你在 `top.v`（PatterNet 真實 RTL）中看到的 SRAM / bus 寬一致。

**與 DSE 的關係**：

- 若未來 DSE 想掃 CNN channel / feature map 寬度，最終會對應到：
  - CNN dim → PatterNet SRAM/data 寬 → 這些 FIFO width。
- 目前專案中，CNN/encoder 維度主要透過 `config_macros.svh` 的 `CNN1_INPUTS_NUM`, `CNN2_OUTPUTS_NUM`, `ENC_INPUTS_NUM` 反映到 `hd_top` 內部，而這幾個 FIFO 寬度被設計成**固定值**，避免 interface 爆炸。

#### 1.6 RRAM FIFO 寬度與 row addr 寬度

- **`RRAM_INP_FIFO_WIDTH  = 64`**
- **`RRAM_OUT_FIFO_WIDTH  = 64`**

**意義**：

- RRAM controller 和 HD 之間的 input / output FIFO 寬度皆為 64 bit。
- 對應到：
  - 實際 RRAM array 的 row/col 寬度與 data 位寬。

- **`RRAM_ROW_ADDR_WIDTH = 10`（在 `param_opt.vh` 中已移除，改由 `config_macros.svh` 決定）**

**意義**：

- RRAM row address 的 bit 數，代表：
  \[
    \text{RRAM row 數} = 2^{\text{RRAM\_ROW\_ADDR\_WIDTH}}
  \]
- 在 `hd_top_ctrl` 裡使用方式（節錄）：
  ```verilog
  row_addr        <= op_code[`RRAM_ROW_ADDR_WIDTH-1:0];
  col_addr        <= op_code[`RRAM_ROW_ADDR_WIDTH+2:`RRAM_ROW_ADDR_WIDTH];
  burst_size_data <= op_code[`RRAM_ROW_ADDR_WIDTH+5:`RRAM_ROW_ADDR_WIDTH+3];
  ```
  - 也就是說一個 `op_code` 的低幾個 bit 被切成：
    - row_addr
    - col_addr（較少 bit）
    - burst_size（讀/寫幾行）

**與 DSE / reram_size 關係**：

- 這個欄位就是我之前幫你改成**動態來自 `config_macros.svh`** 的部分，目標是：
  - DSE 會決定 `reram_size`（例如幾個 row × 幾個 column）。
  - `json_to_svh.py` 依 DSE 值推導一個合適的 `RRAM_ROW_ADDR_WIDTH`，寫入 `config_macros.svh`。
  - 於是 `hd_top_ctrl` / RRAM controller 會用正確的 op_code bit 切割方式控制 RRAM。

---

### 2. Instruction format（指令格式）

#### 2.1 `INST_WIDTH = 4`

- **意義**：
  - 每一個「高階指令類型」使用 4 bit 表示，可支援最多 16 種 instruction。
- 在 `hd_top.sv` 中的定義：
  ```verilog
  parameter I_HD_INIT           = 4'b0000;
  parameter I_HD_READ_PATTERNET = 4'b0001;
  parameter I_HD_STORE_BUF      = 4'b0010;
  ...
  parameter I_HD_HAM_SEG        = 4'b1110;
  parameter I_HD_PRED           = 4'b1111;
  ```
  - 這些 `I_*` 常數就是 instruction 類別，與 `INST_WIDTH` 直接對應。

#### 2.2 `OP_CODE_WIDTH = 16`

- **意義**：
  - 每個指令除了 4 bit opcode（`INST_WIDTH`）外，還有 16 bit 的 `op_code` 當作補充參數。
  - 例如在 `hd_top_ctrl`：
    - `HD_ENC_SEG`：用 `op_code[12:9]` 來描述「有幾個 feature segment」。
    - `HD_HAM_SEG`：用 `op_code` 指向 config word 的 buffer 地址。

**數學關係**：

- 一個完整 instruction word 的總寬度：
  \[
    \text{INST\_WORD\_WIDTH} = INST\_WIDTH + OP\_CODE\_WIDTH = 4 + 16 = 20
  \]
- 在 FIFO / tb 中，常見的是把這 20bit 再 embed 到更寬的外部匯流排（例如 64bit），以保留空間給 `device` / tag 等欄位。

#### 2.3 `PAD_INST_WIDTH = 5`

- **意義**（推測）：
  - 通常是用來 pad instruction 到固定寬度對齊（例如對齊到 32 或 64bit）。
  - e.g. 可能有某些地方使用：
    \[
      \text{PAD\_INST\_WIDTH} = INST\_WIDTH + 1 \text{（或與 other meta bit 的組合）}
    \]
  - 因原始檔中 `PAD_INST_WIDTH` 用得不多，此處先標記為**保留欄位**。

#### 2.4 `STATE_WIDTH = 4`

- **意義**：
  - 用於 encoding、search、train 等 state machine 的 state bit 數。
  - 每個 FSM 使用 4 bit 表現狀態，可支援最多 16 個不同 state。
- 在 `hd_top_ctrl` / `hd_enc_ctrl` / `hd_search` 中皆可看到：
  ```verilog
  logic [`STATE_WIDTH-1:0] curr_state;
  ```

**與 DSE 關係**：

- `STATE_WIDTH` 一般不會被 DSE 掃描，因為它與功能正確性密切相關，改小可能 overflow，改大只是 waste bit；屬於純 RTL 實作細節。

---

### 3. FSL‑HD module（核心超維模組）

#### 3.1 Top level FIFO & buffer 地址寬度

- **`HD_INP_FIFO_WIDTH = 64`**
- **`HD_OUT_FIFO_WIDTH = 64`**

**意義**：

- hd_top 與外界交握的 input/output FIFO 都是 64bit。
- 這與：
  - `INP_FIFO_PUSH_WIDTH / POP_WIDTH`
  - PatterNet / RRAM FIFO 寬度
  共同構成整個系統 data path 的「位寬骨架」。

- **`INP_BUF_ADDR_WIDTH  = 8`**
  - input buffer SRAM（`sram_sp_256x64`）的地址寬度。
  - 對應實體深度：
    \[
      \text{DEPTH}_{inp\_buf} = 2^{INP\_BUF\_ADDR\_WIDTH} = 256
    \]

- **`DATA_BUF_ADDR_WIDTH = 12`**
  - data buffer SRAM（`sram_sp_4096x64`）的地址寬度。
  - 實體深度：
    \[
      \text{DEPTH}_{data\_buf} = 2^{DATA\_BUF\_ADDR\_WIDTH} = 4096
    \]

**與 `HV_LENGTH` / hd_dimension 的關係**：

- input / data buffer 深度，決定可以容納多少：
  - feature segment
  - class hypervector segment
  - encoded HV / training HV 等中介結果
- 例如：若一個 class HV 長度是 `HV_LENGTH=2048`，`HV_SEG_WIDTH=64`，則一個 class 需要：
  \[
    N_{seg} = 2048 / 64 = 32 \text{ 個 64bit segment}
  \]
  - data buffer depth 4096 → 最多可放約 4096 / 32 ≈ 128 個 class（與 `MAX_CLASS_NUM` 對應）。

#### 3.2 Encoding 相關維度

- **`INPUTS_NUM = 8`**
  - 每次 encoder 處理的「輸入 feature 數目」。
  - 搭配 `IDATA_WIDTH = 8`，一次處理 8 個 8bit feature → 64bit。

- **`IDATA_WIDTH = 8`**
  - 單一輸入 feature 的 bit 數。

- **`OUTPUTS_NUM = 32`**
  - encoder 輸出的 hypervector 維度（在內部是 32 個「累加器輸出」）。
  - 這個值與高階 hyperdimension（`HV_LENGTH`）有關，但不是同一個：
    - `OUTPUTS_NUM`：encoding module 一次產生 32 維「partial HV」。
    - `HV_LENGTH`：最終 hypervector 維度，多半為 `OUTPUTS_NUM` × 某種展開或組合（這部分在原論文 / 架構論述中定義）。

- **`ODATA_WIDTH = 16`**
  - 單一輸出累加結果的 bit 數。

**與 DSE 之 `hd_dim` 關係**：

- 最可能的 mapping 之一（需要結合原論文）：
  \[
    \text{HV\_LENGTH (hd\_dim)} \approx OUTPUTS\_NUM \times \text{某種 segment 或 encoding 展開因子}
  \]
- 在目前 RTL 寫法中，`HV_LENGTH` 是獨立巨集（在 `config_macros.svh`），但實際上應該由 `OUTPUTS_NUM` 與設計選擇推導；只是在實作階段方便起見用了固定值。

#### 3.3 Weight / input SRAM 參數

- **`WEIGHT_MEM_ADDR_WIDTH = 5` / `WEIGHT_MEM_DATA_WIDTH = 32`**
  - weight memory 為：
    \[
      \text{DEPTH}_{weight} = 2^5 = 32, \quad \text{WIDTH}_{weight} = 32
    \]
  - 再配合 `NUM_RF_BANK = 8`，組成：
    \[
      WEIGHT\_BUS\_WIDTH = WEIGHT\_MEM\_DATA\_WIDTH \times NUM\_RF\_BANK = 32 \times 8 = 256
    \]
  - 在 `hd_enc.sv` 中，可看到：
    ```verilog
    logic [`WEIGHT_BUS_WIDTH-1:0] dout_mem_weight;
    ```

- **`INPUT_MEM_ADDR_WIDTH = 5` / `INPUT_MEM_DATA_WIDTH = 32`**
  - input memory 結構類似（深度 32、寬度 32）。
  - 與 encoding pipeline 共同決定一次可處理的輸入 window 長度、重用策略。

#### 3.4 `NUM_RF_BANK` / `WEIGHT_BUS_WIDTH`

- **`NUM_RF_BANK = 8`**
  - 代表有 8 個 RF bank 並列；可同時讀出 8×32 bit weight。

- **`WEIGHT_BUS_WIDTH = 256`**
  - 即 `32 × 8`，是 weight 匯流排的總寬度。

**與 DSE 關係**：

- 若 DSE 想掃「encoder hidden dimension」或「hypervector 寬度」，可能會：
  - 透過 `OUTPUTS_NUM`、`NUM_RF_BANK`、`WEIGHT_BUS_WIDTH` 之間的關係調整平行度與資源使用。
  - 目前專案中，這些維度是固定，DSE 只動外部 CNN / encoder 維度與 HV 長度（`HV_LENGTH`）。

---

### 4. Search（搜尋與 Hamming 距離）

（這一節前一個回答已針對 `HV_SEG_WIDTH`, `CLASS_LABEL_WIDTH`, `HAMMING_DIST_WIDTH`, `PRE_FETCH_SIZE` 做過詳細說明，這裡整理成 concise 版並補上剩餘巨集。）

#### 4.1 `HV_SEG_WIDTH = 64`

- 每個 Hypervector segment 的 bit 數。
- 與 `HV_LENGTH` 關係：
  \[
    N_{seg} = HV\_LENGTH / HV\_SEG\_WIDTH
  \]
- 與 `{class_label, distance}` 打包關係：
  \[
    HV\_SEG\_WIDTH \ge HAMMING\_DIST\_WIDTH + CLASS\_LABEL\_WIDTH
  \]
  目前：\(64 \ge 13 + 7 = 20\)，安全。

#### 4.2 `MAX_CLASS_NUM`, `CLASS_LABEL_WIDTH`

- `MAX_CLASS_NUM = 128`
- `CLASS_LABEL_WIDTH = 7`（兩次定義，實際值一致）

**意義**：

- 可以支援最多 128 個 class。
- `CLASS_LABEL_WIDTH = log2(MAX_CLASS_NUM)`，用在：
  - `top_k` 模組的 `TOTAL_WIDTH = HAMMING_DIST_WIDTH + CLASS_LABEL_WIDTH`。
  - 儲存 class ID + distance 的 packed 格式。

#### 4.3 `HAMMING_DIST_WIDTH = 13`

- 全 hypervector 的 Hamming 距離 bit 數。
- 需滿足：
  \[
    2^{13} = 8192 > HV\_LENGTH (=2048)
  \]
- 在 `hd_search.sv` 中用於：
  - `Hamming_dist_full`、`din_topk`/`dout_topk` 以及 `dist_margin` 等訊號。

#### 4.4 `PRE_FETCH_SIZE`, `PREFETCH_MEM_ADDR_WIDTH`

- `PRE_FETCH_SIZE = 128`
- `PREFETCH_MEM_ADDR_WIDTH = 7 (= log2(128))`

**意義**：

- search 模組在計算 Hamming 距離時會預先將 class HV segment 載入 prefetch buffer：
  ```verilog
  logic [`HV_SEG_WIDTH-1:0] hvs_prefetched [`PRE_FETCH_SIZE-1: 0];
  logic [`PREFETCH_MEM_ADDR_WIDTH-1:0] addr_mem_prefetch;
  ```
- 這代表一次 search window 最多同時處理 128 個 segment（可視為 128 個 class 或多段 class+segment 組合，依實作而定）。

#### 4.5 `POPCNT_WIDTH = 7`

- popcount（對 `HV_SEG_WIDTH` bit 計算 1 的個數）的輸出寬度。
- 理論上應該滿足：
  \[
    2^{POPCNT\_WIDTH} > HV\_SEG\_WIDTH
  \]
  目前：
  - `HV_SEG_WIDTH = 64`
  - `POPCNT_WIDTH = 7 → 2^7 = 128 > 64` ✅

---

### 5. Training（訓練路徑）

#### 5.1 `TRAINING_DATA_NUM`, `TRAINING_ADDR_WIDTH`

- `TRAINING_DATA_NUM  = 8`
- `TRAINING_ADDR_WIDTH = 3`（log2(8)）

**意義**：

- 在 `hd_train.sv` 內部的 training buffer：
  ```verilog
  logic [`HV_SEG_WIDTH-1:0] buffer [`TRAINING_DATA_NUM-1:0]; // 8 個 segment
  ```
- 代表一次訓練 session 中，暫存的 hypervector segment 數量為 8。

#### 5.2 `SP_TRAINING_WIDTH`, `TRAINING_DATA_WIDTH`

- `SP_TRAINING_WIDTH = 512`
  - 代表 training accumulator 的長度（512bit），對應 hypervector 的 segment/bit 細節。
- `TRAINING_DATA_WIDTH = 8`
  - 單一累加器 output 的位寬。

**與 `HV_SEG_WIDTH` 關係**：

- 在 `hd_train.sv`：
  ```verilog
  for(k=0; k<`TRAINING_DATA_NUM; k++) begin
    for(j=0; j<`HV_SEG_WIDTH; j++) begin
      localparam idx = k*`HV_SEG_WIDTH + j;
      ...
      dout[idx][TRAINING_DATA_WIDTH-1:0] ...
    end
  end
  ```
- 於是有效 training 狀態空間長度為：
  \[
    TRAINING\_DATA\_NUM \times HV\_SEG\_WIDTH
  \]
  - 目前：\(8 \times 64 = 512 = SP\_TRAINING\_WIDTH\)，完全對齊。

---

### 6. PatterNet 介面

- `PATTERNET_FEAT_SRAM_DATA_WIDTH = 8`
- `PATTERNET_FEAT_SRAM_ADDR_WIDTH = 11`

**意義**：

- Feature SRAM 每個 cell 寬度為 8bit（對應 CNN/feature map output）。
- 地址寬 11 → 深度 2048。
  \[
    DEPTH_{feat\_sram} = 2^{11} = 2048
  \]

**與 `ENC_INPUTS_NUM` / CNN dim / `HV_LENGTH` 關係**：

- CNN / encoder 的 feature map 維度，會對應到：
  - 多少 feature 需要被搬入 `hd_enc`。
  - PatterNet feature SRAM 的大小和這裡的 `DATA_WIDTH` + `ADDR_WIDTH`。
  - 目前這兩個值是固定的基礎設施設定；DSE 若要掃 CNN dim，通常會多配一層 mapping，而不是直接改這兩個宏。

---

### 7. 總結：這一批 `param.vh` 宏在整體架構中的層級

- **晶片基礎設施（JTAG + CDC FIFO + 外部 FIFO 寬度）**
  - 定義對外介面的協議與穩定性。
  - 通常不會納入 DSE；改動風險大（影響整個 SoC）。

- **Instruction format**
  - `INST_WIDTH = 4`, `OP_CODE_WIDTH = 16` 決定「指令集編碼空間」。
  - 這裡是「微架構 ISA」的一部份，而非 DSE 搜尋空間。

- **FSL‑HD module（buffer / memory / encoding）**
  - `INP_BUF_ADDR_WIDTH`, `DATA_BUF_ADDR_WIDTH`, `OUTPUTS_NUM`, `WEIGHT_*`, `INPUT_*` 等決定：
    - 可支援的最大 `MAX_CLASS_NUM`、最大 hypervector 長度、可 cache 多少 class/feature。
  - 若未來想讓 `hd_dim` 非常大（>2048），這一區才是需要一起調整的地方。

- **Search / Training / PatterNet**
  - 多數參數（`HV_SEG_WIDTH`, `HAMMING_DIST_WIDTH`, `CLASS_LABEL_WIDTH`, `PRE_FETCH_SIZE`, `TRAINING_*`, `PATTERNET_*`）彼此有精確的數學關係：
    - segment 切割 vs hypervector 長度
    - buffer 深度 vs 最大 class 數
    - popcount / distance bit 寬 vs hypervector 長度
  - 目前我們已經把「真正會被 DSE 控制」的東西（例如 `HV_SEG_WIDTH`, `RRAM_ROW_ADDR_WIDTH` 等）搬到 `config_macros.svh`，其他維持固定可保證設計合法性與穩定性。

後續若你希望，我可以在這份說明上再加一節「**適合放進 DSE 的候選參數清單**」，整理出哪些宏可以安全變、它們的約束條件、以及對應到 JSON/DSE 參數的建議 mapping。 

---

### 8. 合法 DSE 參數區域總結（目前實驗設定）

根據前述所有數學關係與 RTL 約束，特別是：

- \( HV\_SEG\_WIDTH = \dfrac{HV\_LENGTH}{\text{ENC\_INPUTS\_NUM}} = \dfrac{hd\_dim}{encoder\_x\_dim \times encoder\_y\_dim} \)
- \( HV\_SEG\_WIDTH \ge HAMMING\_DIST\_WIDTH + CLASS\_LABEL\_WIDTH = 13 + 7 = 20 \)
- `hd_dim % (encoder_x_dim * encoder_y_dim) == 0`

本論文實驗中採用的一組**簡潔且保證合法**的搜尋空間為：

- `hd_dim ∈ {2048, 4096}`
- `encoder_x_dim = 8`
- `encoder_y_dim = 8`

對應得到：

- 若 `hd_dim = 2048`：
  - `ENC_INPUTS_NUM = 8 × 8 = 64`
  - `HV_SEG_WIDTH = 2048 / 64 = 32 ≥ 20` ✅
- 若 `hd_dim = 4096`：
  - `ENC_INPUTS_NUM = 64`
  - `HV_SEG_WIDTH = 4096 / 64 = 64 ≥ 20` ✅

這樣可同時滿足：

1. `json_to_svh.py` 中的整除檢查：`hd_dim % (encoder_x_dim * encoder_y_dim) == 0`。
2. search / train 路徑中對 `HV_SEG_WIDTH` 的需求：
   - `HV_SEG_WIDTH ≥ HAMMING_DIST_WIDTH + CLASS_LABEL_WIDTH = 20`。
   - `TRAINING_DATA_NUM × HV_SEG_WIDTH = 8 × 64 = 512 = SP_TRAINING_WIDTH` 在 `hd_dim=4096` 的 extreme case 仍維持一致。
3. `PREFETCH_MEM_ADDR_WIDTH`, `POPCNT_WIDTH` 等位寬關係（例如 `2^7 = 128 > 64`）在這個區域內全部維持合法。

實作上，這組條件已體現在：

- `workspace/conf/params_prop/cimloop.yaml`：
  - `hd_dim` 為 `{2048, 4096}`。
  - `encoder_x_dim = 8`、`encoder_y_dim = 8`（皆設定為單一 choice）。
- `eda_server_scripts/json_to_svh.py`：
  - 依上述公式計算 `HV_SEG_WIDTH`，並在 `hv_seg_width < 20` 或無法整除時直接 raise error。

未來若要擴張合法 DSE 區域（例如打開更多 `hd_dim` 或 `encoder_*` 候選值），可以以此為基準，先驗證：

- 是否仍滿足 `HV_SEG_WIDTH ≥ 20`、`TRAINING_DATA_NUM × HV_SEG_WIDTH = SP_TRAINING_WIDTH` 等等條件，
- 再決定要不要同步調整 `param.vh` 中 search / training 模組的相關巨集。 
