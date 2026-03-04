// ============================================================================
//  Module : tb_hd_top_timing
//  Purpose: Measure the total clock-cycle latency of one complete hd_top
//           inference pass (preload → encode → ham_seg → predict) under the
//           parameters defined in param_opt.vh / config_macros.svh.
//
//  Interfaces driven by this testbench:
//    ┌─────────────────┬──────────────────────────────────────────────────┐
//    │  External       │  Model / stub strategy                           │
//    ├─────────────────┼──────────────────────────────────────────────────┤
//    │  inst_fifo      │  Queue-based model; TB pops on pop_n == 0        │
//    │  iFIFO          │  Continuous random data; empty_ififo = 0 always  │
//    │  oFIFO          │  full_ofifo = 0 always; TB captures pushes       │
//    │  PatterNet      │  Tied: ready=1, valid_odata=0                    │
//    │  RRAM           │  Tied: full_*=0, empty_*=1, dout=0               │
//    └─────────────────┴──────────────────────────────────────────────────┘
//
//  Instruction sequence:
//    1. STORE_BUF (→inp_buf, addr=1)  : load encoding weight HVs
//    2. HD_ENC_PRELOAD                : transfer weights inp_buf→RF
//    3. STORE_BUF (→inp_buf, addr=0)  : load input feature data
//    4. HD_ENC_SEG                    : encode (ENC_INPUTS_NUM/INPUTS_NUM segs)
//    5. STORE_BUF (→data_buf, addr=0) : load class HVs for search
//    6. HD_HAM_SEG                    : Hamming distance over all classes
//    7. HD_PRED                       : select best-match class
//
//  Reported metrics:
//    - Simulation time (ns) at end of each phase
//    - Total clock cycles consumed
// ============================================================================
`timescale 1ns/1ps
`include "param_opt.vh"

module tb_hd_top_timing;

// ---------------------------------------------------------------------------
//  Timing parameters
// ---------------------------------------------------------------------------
localparam real CLK_PERIOD  = 4.0;        // ns  (250 MHz)
localparam int  MAX_CYCLES  = 2_000_000;  // watchdog

// ---------------------------------------------------------------------------
//  Derived sizes (computed from param_opt.vh macros)
// ---------------------------------------------------------------------------
// Number of HV segments per full hypervector
localparam int N_SEG        = `HV_LENGTH / `HV_SEG_WIDTH;         // 128

// Encoding: how many INPUTS_NUM-groups cover all ENC_INPUTS_NUM features
localparam int N_ENC_GROUPS = `ENC_INPUTS_NUM / `INPUTS_NUM;       // 16

// inp_buf words reserved for encoding weights (WEIGHT_MEM_ADDR_WIDTH = 5 → 32 entries)
// Each hd_enc RF entry = WEIGHT_BUS_WIDTH bits; inp_buf word = HV_SEG_WIDTH bits
// words_per_rf_row = WEIGHT_BUS_WIDTH / HV_SEG_WIDTH = 256/HV_SEG_WIDTH
localparam int WORDS_PER_RF_ROW = `WEIGHT_BUS_WIDTH / `HV_SEG_WIDTH;  // e.g. 16 if HV_SEG_WIDTH=16
localparam int RF_ROWS          = 1 << `WEIGHT_MEM_ADDR_WIDTH;         // 32
localparam int N_WEIGHT_WORDS   = RF_ROWS * WORDS_PER_RF_ROW;          // 512 (worst case)
// Cap to a safe upper bound to avoid test running forever
localparam int N_WEIGHT_WORDS_CAP = (N_WEIGHT_WORDS > 128) ? 128 : N_WEIGHT_WORDS;

// Input feature words: one 64-bit iFIFO word carries INPUTS_NUM × IDATA_WIDTH bits = 64 bits
// hd_top reads features from inp_buf[0..N_ENC_GROUPS-1]; we pre-load N_ENC_GROUPS words
localparam int N_FEAT_WORDS = N_ENC_GROUPS;                            // 16

// Class HV data in data_buf: each class needs N_SEG words of HV_SEG_WIDTH bits.
// data_buf word = 64 bits → words_per_class = N_SEG * HV_SEG_WIDTH / 64
localparam int WORDS_PER_CLASS = (N_SEG * `HV_SEG_WIDTH) / 64;        // 32 when HV_SEG_WIDTH=16

// HAM_SEG op_code_cached_long derives num_class from inp_buf config word bits[19:13].
// Since inp_buf word width = HV_SEG_WIDTH (16 bits), only bits[15:13] are valid.
// → max 3 bits → num_class 0..7.  We test 8 classes to keep sim time bounded.
localparam int NUM_CLASSES_SIM  = 8;
localparam int N_CLASS_WORDS    = NUM_CLASSES_SIM * WORDS_PER_CLASS;   // 256

// ---------------------------------------------------------------------------
//  DUT signal declarations
// ---------------------------------------------------------------------------
// inst_fifo (hd_top pops)
logic                                   pop_n_inst_fifo;
logic                                   empty_inst_fifo;
logic [`INST_WIDTH+`OP_CODE_WIDTH-1:0]  din_inst_op;

// iFIFO (hd_top pops)
logic                                   pop_n_ififo;
logic                                   empty_ififo;
logic [`HD_INP_FIFO_WIDTH-1:0]          din_ififo;

// oFIFO (hd_top pushes)
logic                                   push_n_ofifo;
logic                                   full_ofifo;
logic [`HD_OUT_FIFO_WIDTH-1:0]          dout_ofifo;

// PatterNet interface
logic                                           ready_patternet;
logic                                           en_patternet_buf;
logic [`PATTERNET_FEAT_SRAM_ADDR_WIDTH-1:0]     addr_patternet_buf;
logic                                           valid_odata_patternet;
logic [`PATTERNET_FEAT_SRAM_DATA_WIDTH-1:0]     din_patternet_feat;
logic [10:0]                                    addr_from_patternet;

// RRAM interface
logic                                           push_n_inst_fifo_rram_hd;
logic                                           full_inst_fifo_rram_hd;
logic [`INST_WIDTH+`OP_CODE_WIDTH-1:0]          din_inst_op_rram_hd;

logic                                           push_n_ififo_rram_hd;
logic                                           full_ififo_rram_hd;
logic [`RRAM_INP_FIFO_WIDTH-1:0]                din_ififo_rram_hd;

logic                                           pop_n_ofifo_rram_hd;
logic                                           empty_ofifo_rram_hd;
logic [`RRAM_OUT_FIFO_WIDTH-1:0]                dout_ofifo_rram_hd;

// Clock / reset
logic clk, rst_n;

// ---------------------------------------------------------------------------
//  DUT instantiation
// ---------------------------------------------------------------------------
hd_top dut (
    .pop_n_inst_fifo,
    .empty_inst_fifo,
    .din_inst_op,

    .pop_n_ififo,
    .empty_ififo,
    .din_ififo,

    .push_n_ofifo,
    .full_ofifo,
    .dout_ofifo,

    .ready_patternet,
    .en_patternet_buf,
    .addr_patternet_buf,
    .valid_odata_patternet,
    .din_patternet_feat,
    .addr_from_patternet,

    .push_n_inst_fifo_rram_hd,
    .full_inst_fifo_rram_hd,
    .din_inst_op_rram_hd,

    .push_n_ififo_rram_hd,
    .full_ififo_rram_hd,
    .din_ififo_rram_hd,

    .pop_n_ofifo_rram_hd,
    .empty_ofifo_rram_hd,
    .dout_ofifo_rram_hd,

    .rst_n,
    .clk
);

// ---------------------------------------------------------------------------
//  Clock generator
// ---------------------------------------------------------------------------
initial clk = 1'b0;
always #(CLK_PERIOD / 2.0) clk = ~clk;

// ---------------------------------------------------------------------------
//  Cycle counter
// ---------------------------------------------------------------------------
int cycle_count;
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) cycle_count <= 0;
    else        cycle_count <= cycle_count + 1;
end

// ---------------------------------------------------------------------------
//  Stub: PatterNet — always ready, never sends data
// ---------------------------------------------------------------------------
assign ready_patternet      = 1'b1;
assign valid_odata_patternet = 1'b0;
assign din_patternet_feat   = '0;
assign addr_from_patternet  = '0;

// ---------------------------------------------------------------------------
//  Stub: RRAM — always ready to receive, never returns data
// ---------------------------------------------------------------------------
assign full_inst_fifo_rram_hd = 1'b0;
assign full_ififo_rram_hd     = 1'b0;
assign empty_ofifo_rram_hd    = 1'b1;
assign dout_ofifo_rram_hd     = '0;

// ---------------------------------------------------------------------------
//  oFIFO sink — always accepts output
// ---------------------------------------------------------------------------
assign full_ofifo = 1'b0;

int  out_count;   // number of oFIFO words captured
logic [`HD_OUT_FIFO_WIDTH-1:0] last_out;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        out_count <= 0;
        last_out  <= '0;
    end else if (!push_n_ofifo) begin
        out_count <= out_count + 1;
        last_out  <= dout_ofifo;
    end
end

// ---------------------------------------------------------------------------
//  inst_fifo model
//    - Array-based FIFO; TB pushes from initial block, DUT pops via pop_n_inst_fifo
// ---------------------------------------------------------------------------
typedef logic [`INST_WIDTH+`OP_CODE_WIDTH-1:0] inst_word_t;
inst_word_t inst_queue[$];

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        empty_inst_fifo <= 1'b1;
        din_inst_op     <= '0;
    end else begin
        empty_inst_fifo <= (inst_queue.size() == 0);
        din_inst_op     <= (inst_queue.size() > 0) ? inst_queue[0] : '0;

        if (!pop_n_inst_fifo && inst_queue.size() > 0)
            void'(inst_queue.pop_front());
    end
end

// ---------------------------------------------------------------------------
//  iFIFO model
//    - Provides an infinite stream of pseudo-random 64-bit words.
//    - The DUT pops by asserting pop_n_ififo = 0; we cycle to the next word.
// ---------------------------------------------------------------------------
logic [`HD_INP_FIFO_WIDTH-1:0] ififo_data;

assign empty_ififo = 1'b0;          // always data available
assign din_ififo   = ififo_data;

// Advance to a new pseudo-random word each time DUT pops
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        ififo_data <= 64'hA5A5_A5A5_5A5A_5A5A;
    end else if (!pop_n_ififo) begin
        // Simple LFSR-style rotation with XOR for variety
        ififo_data <= {ififo_data[62:0], ififo_data[63]} ^ 64'hDEAD_BEEF_CAFE_1234;
    end
end

// ---------------------------------------------------------------------------
//  Helper: push one instruction into inst_queue
//    inst   : 4-bit instruction code
//    op_code: 16-bit op_code
// ---------------------------------------------------------------------------
task automatic push_inst(
    input logic [3:0]  inst,
    input logic [15:0] op_code
);
    inst_queue.push_back({inst, op_code});
endtask

// ---------------------------------------------------------------------------
//  Helper: wait until inst_queue is empty AND a minimum of extra_cycles have
//          passed, with a timeout guard.
// ---------------------------------------------------------------------------
task automatic wait_queue_empty(input int timeout_cycles, input int extra_cycles);
    int t;
    for (t = 0; t < timeout_cycles; t++) begin
        @(posedge clk);
        if (inst_queue.size() == 0) break;
    end
    if (t == timeout_cycles)
        $display("[WARN] wait_queue_empty: timeout after %0d cycles (cycle=%0d)",
                 timeout_cycles, cycle_count);
    // Additional settling time for the DUT to complete internal FSM
    repeat(extra_cycles) @(posedge clk);
endtask

// ---------------------------------------------------------------------------
//  Helper: issue a series of STORE_BUF instructions targeting inp_buf
//    src  = 0 (iFIFO → inp_buf)
//    dst  = 0 → inp_buf; burst max 8 per instruction (3-bit field)
//    op_code: [15]=src=0, [14]=dst=0, [13:11]=burst-1, [7:0]=base_addr
// ---------------------------------------------------------------------------
task automatic store_to_inp_buf(
    input int base_addr,
    input int n_words
);
    automatic int addr      = base_addr;
    automatic int remaining = n_words;
    while (remaining > 0) begin
        automatic int burst = (remaining >= 8) ? 8 : remaining;
        automatic logic [15:0] opc;
        // src=0 [15], dst=0 [14], burst-1 [13:11], addr [7:0]
        opc = {2'b00, 3'(burst - 1), 3'b000, 8'(addr & 8'hFF)};
        @(posedge clk);
        push_inst(4'b0010, opc);   // I_HD_STORE_BUF = 4'b0010
        addr      += burst;
        remaining -= burst;
    end
endtask

// ---------------------------------------------------------------------------
//  Helper: issue a series of STORE_BUF instructions targeting data_buf
//    src  = 0 (iFIFO → data_buf)
//    dst  = 1 → data_buf; burst max 4 per instruction (2-bit field)
//    op_code: [15]=0, [14]=1(dst), [13:12]=burst-1, [11:0]=base_addr
// ---------------------------------------------------------------------------
task automatic store_to_data_buf(
    input int base_addr,
    input int n_words
);
    automatic int addr      = base_addr;
    automatic int remaining = n_words;
    while (remaining > 0) begin
        automatic int burst = (remaining >= 4) ? 4 : remaining;
        automatic logic [15:0] opc;
        // src=0 [15], dst=1 [14], burst-1 [13:12], addr [11:0]
        opc = {2'b01, 2'(burst - 1), 12'(addr & 12'hFFF)};
        @(posedge clk);
        push_inst(4'b0010, opc);   // I_HD_STORE_BUF = 4'b0010
        addr      += burst;
        remaining -= burst;
    end
endtask

// ---------------------------------------------------------------------------
//  Timestamp helper
// ---------------------------------------------------------------------------
task automatic report_phase(input string phase_name);
    $display("[TIMING] %-40s  cycle=%8d  time=%0t ns",
             phase_name, cycle_count, $realtime);
endtask

// ---------------------------------------------------------------------------
//  HAM_SEG config word
//    Stored at inp_buf[64] so it doesn't overlap weights(1..32) or features(0..15).
//    op_code_cached_long (16 bits, HV_SEG_WIDTH) layout (from hd_top_ctrl):
//      [12:9]  = num_feat_seg - 1  → 4'b(N_ENC_GROUPS-1)
//      [15:13] = num_class bits 2:0 → NUM_CLASSES_SIM - 1 (max 7, fits in 3 bits)
//      [1:0]   = seg_shift_bits offset (0 → addr_step = 1<<4 = 16)
//    HAM_SEG instruction op_code = inp_buf address holding this config word
// ---------------------------------------------------------------------------
localparam int    HAM_CFG_ADDR       = 64;
localparam int    HAM_NUM_CLASS_BITS = NUM_CLASSES_SIM - 1;   // 3-bit value 0..7
localparam logic [15:0] HAM_CFG_WORD =
    { 3'(HAM_NUM_CLASS_BITS),          // [15:13] num_class
      4'(N_ENC_GROUPS - 1),             // [12:9]  num_feat_seg - 1
      9'b0 };                           // [8:0]   addr / shift = 0

// ---------------------------------------------------------------------------
//  Main test sequence
// ---------------------------------------------------------------------------
int phase_start_cycle;

initial begin
    // ── Init ────────────────────────────────────────────────────────────────
    rst_n      = 1'b0;
    inst_queue = '{};

    $display("============================================================");
    $display(" hd_top Timing Testbench");
    $display("  HV_LENGTH        = %0d",  `HV_LENGTH);
    $display("  HV_SEG_WIDTH     = %0d",  `HV_SEG_WIDTH);
    $display("  N_SEG            = %0d",  N_SEG);
    $display("  ENC_INPUTS_NUM   = %0d",  `ENC_INPUTS_NUM);
    $display("  INPUTS_NUM       = %0d",  `INPUTS_NUM);
    $display("  N_ENC_GROUPS     = %0d",  N_ENC_GROUPS);
    $display("  MAX_CLASS_NUM    = %0d",  `MAX_CLASS_NUM);
    $display("  NUM_CLASSES_SIM  = %0d",  NUM_CLASSES_SIM);
    $display("  N_WEIGHT_WORDS   = %0d (capped to %0d)", N_WEIGHT_WORDS, N_WEIGHT_WORDS_CAP);
    $display("  N_FEAT_WORDS     = %0d",  N_FEAT_WORDS);
    $display("  WORDS_PER_CLASS  = %0d",  WORDS_PER_CLASS);
    $display("  N_CLASS_WORDS    = %0d",  N_CLASS_WORDS);
    $display("  CLK_PERIOD       = %0.1f ns", CLK_PERIOD);
    $display("  HAM_CFG_WORD     = 0x%04h (at inp_buf[%0d])", HAM_CFG_WORD, HAM_CFG_ADDR);
    $display("============================================================");

    repeat(16) @(posedge clk);
    rst_n = 1'b1;
    repeat(4) @(posedge clk);
    report_phase("Reset complete");

    // ================================================================
    // Phase 1: Load encoding weights → inp_buf[1..N_WEIGHT_WORDS_CAP]
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 1] Store encoding weights to inp_buf (addr=1, %0d words)",
             N_WEIGHT_WORDS_CAP);
    store_to_inp_buf(1, N_WEIGHT_WORDS_CAP);
    wait_queue_empty(50_000, 100);
    report_phase("Phase 1 done: weights loaded");
    $display("          Phase 1 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 2: I_HD_ENC_PRELOAD — transfer weights from inp_buf → hd_enc RF
    //   op_code: don't-care for this instruction
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 2] I_HD_ENC_PRELOAD");
    push_inst(4'b1000, 16'h0000);   // I_HD_ENC_PRELOAD
    wait_queue_empty(50_000, 500);  // extra cycles for hd_enc RF load FSM
    report_phase("Phase 2 done: preload complete");
    $display("          Phase 2 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 3: Load input feature data → inp_buf[0..N_FEAT_WORDS-1]
    //   (must be done after preload so there is no address conflict)
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 3] Store input features to inp_buf (addr=0, %0d words)",
             N_FEAT_WORDS);
    store_to_inp_buf(0, N_FEAT_WORDS);
    wait_queue_empty(10_000, 50);
    report_phase("Phase 3 done: features loaded");
    $display("          Phase 3 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 4: I_HD_ENC_SEG — encode all feature segments
    //   op_code[12:9] = N_ENC_GROUPS - 1
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 4] I_HD_ENC_SEG (num_feat_seg=%0d)", N_ENC_GROUPS);
    begin
        automatic logic [15:0] enc_op = '0;
        enc_op[12:9] = 4'(N_ENC_GROUPS - 1);
        push_inst(4'b1001, enc_op);  // I_HD_ENC_SEG
    end
    wait_queue_empty(200_000, 200);
    report_phase("Phase 4 done: encoding complete");
    $display("          Phase 4 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 5: Store HAM_SEG config word → inp_buf[HAM_CFG_ADDR]
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 5] Store HAM_SEG config word to inp_buf[%0d] = 0x%04h",
             HAM_CFG_ADDR, HAM_CFG_WORD);
    begin
        // Single-word STORE_BUF: burst=1, addr=HAM_CFG_ADDR
        automatic logic [15:0] opc = {2'b00, 3'b000, 3'b000, 8'(HAM_CFG_ADDR & 8'hFF)};
        // Override iFIFO word so exactly the config word is stored
        // (iFIFO is continuous; we accept that actual stored data comes from
        //  ififo_data at that cycle.  The HAM_SEG config word format can be
        //  imposed by pre-loading ififo_data through a register write here.)
        force ififo_data = {{(`HD_INP_FIFO_WIDTH - 16){1'b0}}, HAM_CFG_WORD};
        @(posedge clk);
        push_inst(4'b0010, opc);
        wait_queue_empty(1000, 10);
        release ififo_data;
    end
    report_phase("Phase 5 done: HAM config word stored");

    // ================================================================
    // Phase 6: Load class HVs → data_buf[0..N_CLASS_WORDS-1]
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 6] Store class HVs to data_buf (%0d classes × %0d words = %0d words)",
             NUM_CLASSES_SIM, WORDS_PER_CLASS, N_CLASS_WORDS);
    store_to_data_buf(0, N_CLASS_WORDS);
    wait_queue_empty(200_000, 200);
    report_phase("Phase 6 done: class HVs loaded");
    $display("          Phase 6 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 7: I_HD_HAM_SEG — Hamming distance over all classes
    //   op_code = inp_buf address of the config word
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 7] I_HD_HAM_SEG (config at inp_buf[%0d])", HAM_CFG_ADDR);
    push_inst(4'b1110, 16'(HAM_CFG_ADDR));   // I_HD_HAM_SEG
    wait_queue_empty(500_000, 500);
    report_phase("Phase 7 done: HAM_SEG complete");
    $display("          Phase 7 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Phase 8: I_HD_PRED — pick winning class
    // ================================================================
    phase_start_cycle = cycle_count;
    $display("[PHASE 8] I_HD_PRED");
    push_inst(4'b1111, 16'h0000);  // I_HD_PRED
    wait_queue_empty(50_000, 500);
    report_phase("Phase 8 done: prediction complete");
    $display("          Phase 8 cycles = %0d", cycle_count - phase_start_cycle);

    // ================================================================
    // Final report
    // ================================================================
    $display("============================================================");
    $display(" FINAL TIMING REPORT");
    $display("  Total cycles        = %0d",  cycle_count);
    $display("  Total sim time      = %0t",  $realtime);
    $display("  Clock period        = %0.1f ns", CLK_PERIOD);
    $display("  Equivalent latency  = %0.3f us",
             real'(cycle_count) * CLK_PERIOD / 1000.0);
    $display("  oFIFO output words  = %0d",  out_count);
    if (out_count > 0)
        $display("  Last output word    = 0x%0h", last_out);
    $display("============================================================");
    $finish;
end

// ---------------------------------------------------------------------------
//  Watchdog
// ---------------------------------------------------------------------------
initial begin
    #(CLK_PERIOD * MAX_CYCLES);
    $display("[WATCHDOG] Simulation exceeded %0d cycles — forcing $finish", MAX_CYCLES);
    $display("           cycle_count=%0d  out_count=%0d  inst_queue_size=%0d",
             cycle_count, out_count, inst_queue.size());
    $finish;
end

endmodule : tb_hd_top_timing
