# =============================================================================
# ptpx.tcl — PrimeTime PX Dynamic Power Analysis Script
#
# Invocation: pt_shell is run with CWD = ~/workspace/fsl-hd/
#   (launched via `make power` from the full-stack-opt/ Makefile)
#   All relative paths below are relative to fsl-hd/.
#
# Prerequisites:
#   - reports/synth_netlist.v   : produced by `make synth`
#   - reports/activity.saif     : produced by `make sim` (VCS toggle dump)
# =============================================================================

# ── Library Setup ─────────────────────────────────────────────────────────────
# TODO: Match the library used during synthesis.
set_app_var target_library "verilog/include/rram_wrapper.tc.db"
set_app_var link_library   "* verilog/include/rram_wrapper.tc.db"

# ── Read Synthesized Netlist ──────────────────────────────────────────────────
read_verilog reports/synth_netlist.v

# TODO: Replace 'hdnn_top' with the actual top-level module name.
link_design hdnn_top

# ── Apply Timing Constraints ──────────────────────────────────────────────────
# Clock period must match the synthesis constraint; use 10 ns (100 MHz) as default.
# The correct value is baked into synth_netlist.v, but PT still needs the constraint.
create_clock -period 10.0 -name clk [get_ports clk]

# ── Read Switching Activity ───────────────────────────────────────────────────
# Activity captured by VCS $toggle_report; instance path must match tb_top.sv DUT name.
read_saif reports/activity.saif -instance tb_top/u_dut

# ── Power Analysis ────────────────────────────────────────────────────────────
update_power
report_power > reports/ptpx_power.rpt

exit
