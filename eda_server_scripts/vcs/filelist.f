// =============================================================================
// filelist.f — VCS Gate-Level Simulation File List
//
// Deployment target: ~/workspace/fsl-hd/tb/filelist.f
//   (copy alongside tb_top.sv before running `make sim`)
//
// VCS is invoked from fsl-hd/ directory, so paths below are relative to fsl-hd/.
//
// List all files required for gate-level simulation:
//   1. Standard cell simulation models (from your PDK)
//   2. RRAM wrapper behavioral model (if not already covered by stdcell lib)
//
// The synthesized netlist (reports/synth_netlist.v) and testbench (tb/tb_top.sv)
// are passed directly on the VCS command line in the Makefile — do NOT list them here.
// =============================================================================

// TODO: Add PDK standard cell Verilog simulation model path(s) below.
//       Example (TSMC 28nm):
//         /path/to/pdk/tsmc28/digital/Front_End/verilog/tcbn28hpcplusbwp7t30p140.v
//
// TODO: Add RRAM wrapper behavioral model if used in fsl-hd/ RTL.
//       Example:
//         verilog/include/rram_wrapper_behav.v
//
// /path/to/your_pdk/stdcells.v
