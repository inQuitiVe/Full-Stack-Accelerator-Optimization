`ifndef __PARAM_OPT_VH
`define __PARAM_OPT_VH

// Dynamic DSE-driven macros (HV_LENGTH, HV_SEG_WIDTH, RRAM_ROW_ADDR_WIDTH, etc.)
// Generated at runtime by json_to_svh.py.
`include "config_macros.svh"

// Base static parameters copied from param.vh, but with
// RRAM_ROW_ADDR_WIDTH and HV_SEG_WIDTH removed so that the
// values from config_macros.svh take effect.

`define USE_DW                  1 // use Synopsys Designware, for simulation+synthesis
// `define USE_CW                  1 // use Candence Chipware, for synthesis

/////////// Definition of HD instructions
`define READ_FEAT_PATTERNET     1
`define STORE_BUF               2
`define READ_BUF                3
`define STORE_RRAM              4
`define READ_RRAM               5
`define STORE_HAM_WEIGHT        6
`define HAM_SEG_COMPUTE         7

`define HD_ENC_PRELOAD_WEIGHT   8
`define HD_ENC_SEG              9
`define HD_LOAD_TRAIN_SEG       11
`define HD_SP_TRAIN_SEG         12
`define HD_ST_LD_TRAIN_SEG      13
`define HD_HAM_SEG              14
`define HD_PRED                 15

/////////// Chip infrastructures ///////////
// Chip JTAG
`define JTAG_LEN                15

// Chip FIFOs
`define CDC_INST_FIFO_DEPTH     32
`define CDC_IO_FIFO_DEPTH       32

`define INST_FIFO_DEPTH         16
`define IO_FIFO_DEPTH           16

`define INST_FIFO_WIDTH         3
`define INP_FIFO_PUSH_WIDTH     34
`define INP_FIFO_POP_WIDTH      68
`define OUT_FIFO_PUSH_WIDTH     68
`define OUT_FIFO_POP_WIDTH      34

`define PATTERNET_INP_FIFO_PUSH_WIDTH     64
`define PATTERNET_INP_FIFO_POP_WIDTH      32
`define PATTERNET_OUT_FIFO_PUSH_WIDTH     32
`define PATTERNET_OUT_FIFO_POP_WIDTH      64

`define RRAM_INP_FIFO_WIDTH       64
`define RRAM_OUT_FIFO_WIDTH       64

//////////////////////////////////////////


/////////// Instruction format ///////////
`define INST_WIDTH              4
`define OP_CODE_WIDTH           16
`define PAD_INST_WIDTH          5
`define STATE_WIDTH             4
//////////////////////////////////////////


//////////// FSL-HD module ////////////
// Top
`define HD_INP_FIFO_WIDTH       64
`define HD_OUT_FIFO_WIDTH       64

`define INP_BUF_ADDR_WIDTH      8
`define DATA_BUF_ADDR_WIDTH     12

// Encoding
`define INPUTS_NUM              8
`define IDATA_WIDTH             8

`define OUTPUTS_NUM             32
`define ODATA_WIDTH             16

`define WEIGHT_MEM_ADDR_WIDTH   5
`define WEIGHT_MEM_DATA_WIDTH   32

`define INPUT_MEM_ADDR_WIDTH    5
`define INPUT_MEM_DATA_WIDTH    32

`define NUM_RF_BANK             8   // OUTPUTS_NUM*IDATA_WIDTH/WEIGHT_MEM_DATA_WIDTH 
`define WEIGHT_BUS_WIDTH        256 //  WEIGHT_MEM_DATA_WIDTH*NUM_RF_BANK 

// Search
// HV_SEG_WIDTH comes from config_macros.svh
`define MAX_CLASS_NUM           128
`define CLASS_LABEL_WIDTH       7   // $clog2(MAX_CLASS_NUM)
`define HAMMING_DIST_WIDTH      13

`define PRE_FETCH_SIZE          128
`define PREFETCH_MEM_ADDR_WIDTH 7   // $clog2(PRE_FETCH_SIZE),
`define POPCNT_WIDTH            7   // $clog2(HV_SEG_WIDTH)+1,
`define CLASS_LABEL_WIDTH       7   // $clog2(MAX_CLASS_NUM)

// Training
// `define        64
// `define      8

`define TRAINING_DATA_NUM       8   // SP_TRAINING_WIDTH//HV_SEG_WIDTH
`define TRAINING_ADDR_WIDTH     3   // $clog2(TRAINING_DATA_NUM)

`define SP_TRAINING_WIDTH       512
`define TRAINING_DATA_WIDTH     8

// Interface with PatterNet
`define PATTERNET_FEAT_SRAM_DATA_WIDTH       8
`define PATTERNET_FEAT_SRAM_ADDR_WIDTH       11
//////////////////////////////////////////

`endif

