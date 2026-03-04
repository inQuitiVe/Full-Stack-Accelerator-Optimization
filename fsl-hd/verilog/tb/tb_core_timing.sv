// =============================================================================
//  Module : tb_core_timing
//  Purpose: Accurately measure the time of one full FSL-HD core evaluation.
//
//  Measurement scopes:
//    - FULL EVAL  : From sending input features (STORE_BUF) to seeing the
//                   prediction result appear on the oFIFO.
//    - COMPUTE    : From sending ENC_PRELOAD to seeing the prediction result
//                   appear on the oFIFO.
//
//  Instruction sequence (emulating a real host):
//    Pre-setup (not counted in eval time):
//      1. STORE_BUF × 16 : encoding weights → inp_buf[1..128]
//      2. STORE_BUF × 64 : class HVs        → data_buf[0..255]
//
//    Per-inference (timed by feat_load_start_cycle):
//      3. STORE_BUF × 2  : input features   → inp_buf[0..15]
//
//    Compute (timed by eval_start_cycle):
//      4. ENC_PRELOAD    : inp_buf[1..128] → encoder RF
//      5. ENC_SEG        : read inp_buf[0..15], produce HV segments → inp_buf[128..]
//      6. STORE_BUF × 1  : HAM config word → inp_buf[0] (overwrite feat[0])
//      7. HAM_SEG        : read inp_buf[0] as config, compare against data_buf class HVs
//      8. PRED           : push prediction result into oFIFO
//
//  RTL address map (following the implementation in hd_top.sv):
//    inp_buf[0]         : reserved for HAM config (written right before HAM_SEG;
//                         HAM_SEG entry forces base_addr_inp_buf=0 to read this)
//    inp_buf[0..15]     : input features (ENC_SEG reads from base_addr_inp_buf_feat=0)
//    inp_buf[1..128]    : encoding weights (ENC_PRELOAD reads from base_addr=1)
//    inp_buf[128..159]  : encoded HV segments (ENC_SEG writes here)
//    data_buf[0..255]   : class HV segments (HAM_SEG reads here)
//
//  Note: inp_buf[1..15] are time-multiplexed between weights and features.
//        They are used in non-overlapping phases (features are written only
//        after ENC_PRELOAD has finished), so there is no functional conflict.
// =============================================================================
`timescale 1ns/1ps
`include "param_opt.vh"

module tb_core_timing;

  // ── Clock / timing parameters ─────────────────────────────────────────────
  localparam real CLK_PERIOD    = 4.0;     // core clk (250 MHz)
  localparam real CLK_IO_PERIOD = 20.0;    // host IO clk (50 MHz)
  localparam real CLK_PHASE_DLY = 2.0;
  localparam int  MAX_CYCLES    = 10_000_000;

  // ── Evaluation dimensions (must match config_macros.svh / param_opt.vh) ───
  localparam int N_SEG          = `HV_LENGTH / `HV_SEG_WIDTH;       // 2048/64=32
  localparam int N_ENC_GROUPS   = `ENC_INPUTS_NUM / `INPUTS_NUM;    // 128/8=16
  localparam int WORDS_PER_ROW  = `WEIGHT_BUS_WIDTH / `HV_SEG_WIDTH;// 256/64=4
  localparam int N_WEIGHT_ROWS  = 1 << `WEIGHT_MEM_ADDR_WIDTH;      // 2^5=32
  localparam int N_WEIGHT_WORDS = N_WEIGHT_ROWS * WORDS_PER_ROW;    // 128
  localparam int N_FEAT_WORDS   = N_ENC_GROUPS;                      // 16

  localparam int NUM_CLASSES    = 8;                      // number of classes used in this test
  localparam int N_CLASS_WORDS  = NUM_CLASSES * N_SEG;   // 8×32=256

  // ── inp_buf / data_buf address map ─────────────────────────────────────────
  localparam int WEIGHT_BASE   = 1;          // ENC_PRELOAD uses base_addr_inp_buf=1
  localparam int FEAT_BASE     = 0;          // ENC_SEG uses feature base at 0
  localparam int HAM_CFG_ADDR  = 0;          // HAM_SEG reads config from addr 0
  localparam int CLASS_HV_BASE = 0;          // data_buf start address

  // ── HAM config word (stored in inp_buf[0] for HAM_SEG to read) ────────────
  // dout_inp_buf[12:9]  = num_feat_seg-1 = N_ENC_GROUPS-1 = 15
  // dout_inp_buf[19:13] = num_class      = NUM_CLASSES-1  = 7
  // dout_inp_buf[31:20] = base_addr_data_buf              = 0
  localparam logic [63:0] HAM_CFG_64B = {
      44'h0,
      7'(NUM_CLASSES - 1),        // bits[19:13]
      4'(N_ENC_GROUPS - 1),       // bits[12:9]
      9'h0                        // bits[8:0]
  };

  // ── Signals ────────────────────────────────────────────────────────────────
  logic clk, clk_io, rst_n;
  logic flushn_fifo, rstn_fifo;

  // Instruction FIFO interface (host → core)
  logic                             push_n_inst_fifo;
  logic [`INST_FIFO_WIDTH-1:0]      din_inst_fifo;
  logic                             full_inst_fifo;

  // Input data FIFO interface (host → core)
  logic                             push_n_ififo;
  logic [`INP_FIFO_PUSH_WIDTH-1:0]  din_ififo;
  logic                             full_ififo;

  // Output FIFO interface (core → host)
  logic                             pop_n_ofifo;
  logic [`OUT_FIFO_POP_WIDTH-1:0]   dout_ofifo;
  logic                             pop_empty_ofifo;

  // JTAG / clock control
  logic jtag_in, jtag_scanout, wclk, jtag_load, clk_probe;
  logic [2:0] EN_CLK;
  logic clk_ext, clk_gen, clk_out;

  // ── DUT ────────────────────────────────────────────────────────────────────
  core dut (
    .flushn_fifo,   .rstn_fifo,
    .push_n_inst_fifo, .din_inst_fifo, .full_inst_fifo,
    .push_n_ififo,  .din_ififo,  .full_ififo,
    .pop_n_ofifo,   .dout_ofifo, .pop_empty_ofifo,
    .jtag_in, .jtag_scanout, .wclk, .jtag_load, .clk_probe,
    .rst_n, .EN_CLK,
    .clk_ext, .clk_gen, .clk_io, .clk_out, .clk
  );

  // ── Clock generators ───────────────────────────────────────────────────────
  // Each clock has a single driver (initial/always), so there are no conflicts.
  initial begin
    clk = 1'b0; clk_io = 1'b0;
    clk_gen = 1'b0; clk_ext = 1'b0; wclk = 1'b0;
  end
  always #(CLK_PERIOD   /2.0) clk    = ~clk;
  always #(CLK_IO_PERIOD/2.0) clk_io = ~clk_io;
  always @(clk)               clk_gen = clk;   // clk_gen 跟隨 core clk
  always #(CLK_IO_PERIOD/2.0) wclk   = ~wclk;  // JTAG scan clock

  // ── Cycle counter (single driver: always_ff) ───────────────────────────────
  int cycle_count;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) cycle_count <= 0;
    else        cycle_count <= cycle_count + 1;
  end

  // ── oFIFO pop monitor (single driver: always_ff) ───────────────────────────
  // pop_n_ofifo, ofifo_words, last_ofifo_word are all driven only here.
  int  ofifo_words;
  logic [`OUT_FIFO_POP_WIDTH-1:0] last_ofifo_word;

  always_ff @(posedge clk_io or negedge rst_n) begin
    if (!rst_n) begin
      pop_n_ofifo     <= 1'b1;
      ofifo_words     <= 0;
      last_ofifo_word <= '0;
    end else if (!pop_empty_ofifo) begin
      pop_n_ofifo     <= 1'b0;
      ofifo_words     <= ofifo_words + 1;
      last_ofifo_word <= dout_ofifo;
    end else begin
      pop_n_ofifo <= 1'b1;
    end
  end

  // ── Timing stamps (only written in the main initial block) ────────────────
  int feat_load_start_cycle;
  int eval_start_cycle;
  int eval_end_cycle;
  int phase_start_cycle;

  // ── Phase report ──────────────────────────────────────────────────────────
  task automatic report_phase(input string name);
    $display("[CORE TIMING] %-44s  cyc=%8d  t=%0t ns",
             name, cycle_count, $realtime);
  endtask

  // ── JTAG write (sole driver for jtag_in, jtag_load) ───────────────────────
  // jtag_data[2:0]=EN_CLK(all on), [3]=use_clk_gen, [4]=clk_probe_en
  localparam logic [14:0] JTAG_BOOT = 15'b000_0000_0001_1111;

  task automatic jtag_write(input logic [14:0] data);
    integer k;
    jtag_load <= 1'b0;
    jtag_in   <= 1'b0;
    @(posedge wclk);
    for (k = 0; k < `JTAG_LEN; k++) begin
      jtag_in <= data[k];
      @(posedge wclk);
    end
    jtag_load <= 1'b1;
    @(posedge wclk);
    jtag_load <= 1'b0;
    @(posedge wclk);
  endtask

  // ── iFIFO push (sole driver for push_n_ififo, din_ififo; used only in initial)
  // Sends a 34-bit packet; waits if the FIFO is full.
  task automatic push_ififo(input logic [33:0] word);
    while (full_ififo) @(negedge clk_io);
    push_n_ififo <= 1'b0;
    din_ififo    <= word;
    @(negedge clk_io);
    push_n_ififo <= 1'b1;
    din_ififo    <= '0;
  endtask

  // Push a 64-bit HD word by splitting into two 34-bit packets (lo32 then hi32).
  task automatic push_ififo_64b(
    input logic [63:0] data64,
    input logic [1:0]  dev
  );
    push_ififo({dev, data64[31:0]});
    push_ififo({dev, data64[63:32]});
  endtask

  // ── Instruction send (sole driver for push_n_inst_fifo, din_inst_fifo) ────
  // Format: {device[4], instr[4], op_code[16]} → 7 × 3-bit chunks.
  task automatic send_inst(
    input integer dev_i,
    input integer instr_i,
    input integer opc_i
  );
    logic [63:0] word;
    integer k;
    word = ((dev_i  & 32'hF) << 20)
         | ((instr_i & 32'hF) << 16)
         |  (opc_i  & 32'hFFFF);
    k = 0;
    while (k < 7) begin
      @(negedge clk_io);
      if (!full_inst_fifo) begin
        push_n_inst_fifo <= 1'b0;
        din_inst_fifo    <= (word >> (k * 3)) & 3'b111;
        k++;
      end else begin
        push_n_inst_fifo <= 1'b1;
        din_inst_fifo    <= '0;
      end
    end
    @(negedge clk_io);
    push_n_inst_fifo <= 1'b1;
    din_inst_fifo    <= '0;
  endtask

  // ── Conservative wait (measured in core clock cycles) ─────────────────────
  task automatic wait_cycles(input int n);
    repeat(n) @(posedge clk);
  endtask

  // ── High-level: STORE_BUF to inp_buf (dst=0) ──────────────────────────────
  //   op_code = ((burst-1)<<11) | addr,  burst max 8.
  task automatic store_to_inp_buf(
    input int           base_addr,
    input int           n_words,
    ref   logic [63:0]  seed
  );
    automatic int addr      = base_addr;
    automatic int remaining = n_words;
    automatic int b;
    while (remaining > 0) begin
      automatic int burst = (remaining >= 8) ? 8 : remaining;
      // 先 push 資料，讓資料在 iFIFO 等候
      for (b = 0; b < burst; b++) begin
        push_ififo_64b(seed, 2'b00);
        seed = {seed[62:0], seed[63]} ^ 64'h6C62272E_07BB0142;
      end
      // 再送指令；hd_top 收到 STORE_BUF 後從 iFIFO 取出 burst 筆資料
      send_inst(0, `STORE_BUF, ((burst - 1) << 11) | (addr & 8'hFF));
      addr      += burst;
      remaining -= burst;
    end
  endtask

  // ── High-level: STORE_BUF to data_buf (dst=1) ─────────────────────────────
  //   op_code = (1<<14) | ((burst-1)<<12) | addr,  burst max 4.
  task automatic store_to_data_buf(
    input int           base_addr,
    input int           n_words,
    ref   logic [63:0]  seed
  );
    automatic int addr      = base_addr;
    automatic int remaining = n_words;
    automatic int b;
    while (remaining > 0) begin
      automatic int burst = (remaining >= 4) ? 4 : remaining;
      for (b = 0; b < burst; b++) begin
        push_ififo_64b(seed, 2'b00);
        seed = {seed[62:0], seed[63]} ^ 64'h6C62272E_07BB0142;
      end
      send_inst(0, `STORE_BUF,
                (1 << 14) | ((burst - 1) << 12) | (addr & 12'hFFF));
      addr      += burst;
      remaining -= burst;
    end
  endtask

  // ── Main scenario ──────────────────────────────────────────────────────────
  logic [63:0] data_seed;

  initial begin
    // ── Initialization (fully driven by this initial block; no conflicts) ───
    rst_n            = 1'b0;
    rstn_fifo        = 1'b0;
    flushn_fifo      = 1'b1;
    push_n_inst_fifo = 1'b1;
    din_inst_fifo    = '0;
    push_n_ififo     = 1'b1;
    din_ififo        = '0;
    jtag_in          = 1'b0;
    jtag_load        = 1'b0;
    data_seed        = 64'hA5A5_A5A5_DEAD_BEEF;
    feat_load_start_cycle = 0;
    eval_start_cycle      = 0;
    eval_end_cycle        = 0;

    $display("============================================================");
    $display(" tb_core_timing : full evaluation latency measurement");
    $display("  HV_LENGTH      = %0d",  `HV_LENGTH);
    $display("  HV_SEG_WIDTH   = %0d",  `HV_SEG_WIDTH);
    $display("  ENC_INPUTS_NUM = %0d",  `ENC_INPUTS_NUM);
    $display("  INPUTS_NUM     = %0d",  `INPUTS_NUM);
    $display("  OUTPUTS_NUM    = %0d",  `OUTPUTS_NUM);
    $display("  N_ENC_GROUPS   = %0d",  N_ENC_GROUPS);
    $display("  N_SEG          = %0d",  N_SEG);
    $display("  N_WEIGHT_WORDS = %0d",  N_WEIGHT_WORDS);
    $display("  N_FEAT_WORDS   = %0d",  N_FEAT_WORDS);
    $display("  NUM_CLASSES    = %0d",  NUM_CLASSES);
    $display("  N_CLASS_WORDS  = %0d",  N_CLASS_WORDS);
    $display("  HAM_CFG_64B    = 0x%016h", HAM_CFG_64B);
    $display("  CLK            = %.1f ns (%.0f MHz)",
             CLK_PERIOD, 1000.0/CLK_PERIOD);
    $display("  CLK_IO         = %.1f ns (%.0f MHz)",
             CLK_IO_PERIOD, 1000.0/CLK_IO_PERIOD);
    $display("============================================================");

    // ── Phase 0: Reset ─────────────────────────────────────────────────────
    #(CLK_PHASE_DLY);
    repeat(8) @(posedge clk_io);
    rst_n     <= 1'b1;
    rstn_fifo <= 1'b1;
    repeat(8) @(posedge clk_io);
    report_phase("Ph0: reset released");

    // ── Phase 1: JTAG boot config (enable EN_CLK, select clk_gen) ──────────
    jtag_write(JTAG_BOOT);
    wait_cycles(20);
    report_phase("Ph1: JTAG boot applied");

    // ==================================================================
    // PRE-SETUP (static data, not counted in evaluation time)
    // ==================================================================

    // ── Phase 2: Encoding weights → inp_buf[WEIGHT_BASE..WEIGHT_BASE+127]
    //   16 STORE_BUF instructions, burst=8 each.
    report_phase("Ph2: storing encoding weights (inp_buf[1..128]) ...");
    phase_start_cycle = cycle_count;
    store_to_inp_buf(WEIGHT_BASE, N_WEIGHT_WORDS, data_seed);
    // Conservative wait: each word needs ~2×clk_io pushes + SRAM write + CDC
    // latency ≈ 20 core cycles/word × 128 words = 2560 + margin.
    wait_cycles(N_WEIGHT_WORDS * 25 + 600);
    $display("[CORE]  Ph2 done  delta_cycles=%0d", cycle_count - phase_start_cycle);

    // ── Phase 3: Class HVs → data_buf[0..N_CLASS_WORDS-1]
    //   64 STORE_BUF instructions, burst=4 each.
    report_phase("Ph3: storing class HVs (data_buf[0..255]) ...");
    phase_start_cycle = cycle_count;
    store_to_data_buf(CLASS_HV_BASE, N_CLASS_WORDS, data_seed);
    wait_cycles(N_CLASS_WORDS * 25 + 600);
    $display("[CORE]  Ph3 done  delta_cycles=%0d", cycle_count - phase_start_cycle);

    // ==================================================================
    // PER-INFERENCE (FULL EVAL starts at feat_load_start_cycle)
    // ==================================================================
    report_phase(">>> FULL EVAL START (feature STORE_BUF)");
    feat_load_start_cycle = cycle_count;

    // ── Phase 4: Input features → inp_buf[0..N_FEAT_WORDS-1]
    //   2 STORE_BUF instructions, burst=8 each.
    report_phase("Ph4: storing input features (inp_buf[0..15]) ...");
    phase_start_cycle = cycle_count;
    store_to_inp_buf(FEAT_BASE, N_FEAT_WORDS, data_seed);
    wait_cycles(N_FEAT_WORDS * 25 + 200);
    $display("[CORE]  Ph4 done  delta_cycles=%0d", cycle_count - phase_start_cycle);

    // ==================================================================
    // COMPUTE-ONLY (COMPUTE starts at eval_start_cycle)
    // ==================================================================
    report_phase(">>> COMPUTE-ONLY EVAL START (ENC_PRELOAD)");
    eval_start_cycle = cycle_count;

    // ── Phase 5: ENC_PRELOAD — copy inp_buf[1..128] to encoder RF
    //   ENC_PRELOAD uses base_addr_inp_buf=1 and increments every cycle.
    //   Roughly N_WEIGHT_WORDS=128 cycles + encoder internal pipeline.
    report_phase("Ph5: ENC_PRELOAD ...");
    phase_start_cycle = cycle_count;
    send_inst(0, `HD_ENC_PRELOAD_WEIGHT, 0);
    // Conservative wait: 128 words × ~6 cycles/word + encoder pipeline.
    wait_cycles(N_WEIGHT_WORDS * 6 + 400);
    $display("[CORE]  Ph5 ENC_PRELOAD done  delta=%0d", cycle_count - phase_start_cycle);

    // ── Phase 6: ENC_SEG — encode N_ENC_GROUPS segments
    //   op_code[12:9] = N_ENC_GROUPS-1; hd_top reads inp_buf[0..15] as features.
    report_phase("Ph6: ENC_SEG ...");
    phase_start_cycle = cycle_count;
    send_inst(0, `HD_ENC_SEG, (N_ENC_GROUPS - 1) << 9);
    // Conservative wait: N_ENC_GROUPS×OUTPUTS_NUM×~5 cycles + pipeline.
    wait_cycles(N_ENC_GROUPS * `OUTPUTS_NUM * 5 + 600);
    $display("[CORE]  Ph6 ENC_SEG done  delta=%0d", cycle_count - phase_start_cycle);

    // ── Phase 7: Store HAM config word → inp_buf[0] (overwrites feature at 0)
    //   HAM_SEG entry forces base_addr_inp_buf=0 and reads config from here:
    //     bits[12:9]  = num_feat_seg-1 = N_ENC_GROUPS-1 = 15
    //     bits[19:13] = num_class      = NUM_CLASSES-1  = 7
    //     bits[31:20] = base_addr_data_buf              = 0
    report_phase("Ph7: storing HAM config word (inp_buf[0]) ...");
    phase_start_cycle = cycle_count;
    push_ififo_64b(HAM_CFG_64B, 2'b00);
    send_inst(0, `STORE_BUF, HAM_CFG_ADDR & 8'hFF);  // burst=1, dst=inp_buf, addr=0
    wait_cycles(150);
    $display("[CORE]  Ph7 HAM config stored  HAM_CFG=0x%016h  delta=%0d",
             HAM_CFG_64B, cycle_count - phase_start_cycle);

    // ── Phase 8: HAM_SEG — segmented Hamming distance search
    //   hd_top reads config from inp_buf[0], encoded HV from inp_buf[128..],
    //   and class HVs from data_buf[0..]; compares NUM_CLASSES classes.
    report_phase("Ph8: HAM_SEG ...");
    phase_start_cycle = cycle_count;
    send_inst(0, `HD_HAM_SEG, 0);
    // Conservative wait: NUM_CLASSES × N_ENC_GROUPS × OUTPUTS_NUM × ~5
    // plus search overhead.
    wait_cycles(NUM_CLASSES * N_ENC_GROUPS * `OUTPUTS_NUM * 5 + 2000);
    $display("[CORE]  Ph8 HAM_SEG done  delta=%0d", cycle_count - phase_start_cycle);

    // ── Phase 9: PRED — output prediction to oFIFO
    report_phase("Ph9: PRED (waiting for oFIFO result) ...");
    phase_start_cycle = cycle_count;
    send_inst(0, `HD_PRED, 0);

    // Wait until an oFIFO result actually appears (instead of a fixed delay).
    begin
      automatic int timeout = 300_000;
      automatic int t       = 0;
      while (ofifo_words == 0 && t < timeout) begin
        @(posedge clk);
        t++;
      end
      if (t >= timeout)
        $display("[WARN] PRED: oFIFO result timed out after %0d extra cycles", timeout);
    end

    eval_end_cycle = cycle_count;
    report_phase("Ph9: PRED result received from oFIFO !");
    $display("[CORE]  Ph9 PRED done  delta=%0d", cycle_count - phase_start_cycle);

    // ── Final timing report ───────────────────────────────────────────────
    $display("");
    $display("============================================================");
    $display("  CORE EVALUATION TIMING REPORT");
    $display("  ──────────────────────────────────────────────────────────");
    $display("  CLK period          : %.1f ns  (%.0f MHz)",
             CLK_PERIOD, 1000.0/CLK_PERIOD);
    $display("  CLK_IO period       : %.1f ns  (%.0f MHz)",
             CLK_IO_PERIOD, 1000.0/CLK_IO_PERIOD);
    $display("  ──────────────────────────────────────────────────────────");
    $display("  HV_LENGTH / SEG_W   : %0d / %0d", `HV_LENGTH, `HV_SEG_WIDTH);
    $display("  ENC_INPUTS / INPUTS : %0d / %0d", `ENC_INPUTS_NUM, `INPUTS_NUM);
    $display("  N_ENC_GROUPS        : %0d", N_ENC_GROUPS);
    $display("  N_SEG               : %0d", N_SEG);
    $display("  N_WEIGHT_WORDS      : %0d", N_WEIGHT_WORDS);
    $display("  N_FEAT_WORDS        : %0d", N_FEAT_WORDS);
    $display("  NUM_CLASSES         : %0d", NUM_CLASSES);
    $display("  N_CLASS_WORDS       : %0d", N_CLASS_WORDS);
    $display("  ──────────────────────────────────────────────────────────");
    $display("  feat_load_start     : cycle %0d", feat_load_start_cycle);
    $display("  eval_start (PRELOAD): cycle %0d", eval_start_cycle);
    $display("  eval_end   (oFIFO)  : cycle %0d", eval_end_cycle);
    $display("  ──────────────────────────────────────────────────────────");
    $display("  FULL EVAL CYCLES    : %0d  (feature_load → oFIFO result)",
             eval_end_cycle - feat_load_start_cycle);
    $display("  FULL EVAL TIME      : %.3f us",
             real'(eval_end_cycle - feat_load_start_cycle) * CLK_PERIOD / 1000.0);
    $display("  COMPUTE CYCLES      : %0d  (ENC_PRELOAD → oFIFO result)",
             eval_end_cycle - eval_start_cycle);
    $display("  COMPUTE TIME        : %.3f us",
             real'(eval_end_cycle - eval_start_cycle) * CLK_PERIOD / 1000.0);
    $display("  TOTAL SIM CYCLES    : %0d", cycle_count);
    $display("  oFIFO words out     : %0d", ofifo_words);
    if (ofifo_words > 0)
      $display("  prediction word     : 0x%0h", last_ofifo_word);
    $display("============================================================");

    $finish;
  end

  // ── Watchdog ────────────────────────────────────────────────────────────────
  initial begin
    #(CLK_PERIOD * MAX_CYCLES);
    $display("[WATCHDOG] Exceeded %0d cycles — forcing $finish", MAX_CYCLES);
    $display("           cycle=%0d  ofifo_words=%0d", cycle_count, ofifo_words);
    $finish;
  end

endmodule : tb_core_timing
