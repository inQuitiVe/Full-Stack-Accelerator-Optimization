# =============================================================================
# synth_template.tcl — Design Compiler Synthesis Script Template
#
# Deployment target: ~/workspace/fsl-hd/tcl/synth_dse.tcl
#   (written at runtime by json_to_svh.py from this template)
#
# Invocation: dc_shell is run with CWD = ~/workspace/fsl-hd/
#   All relative paths below are therefore relative to fsl-hd/.
#
# Runtime patches applied by json_to_svh.py:
#   CLOCK_PERIOD_PLACEHOLDER   → ns period derived from `frequency` parameter
#   SYNTH_PROFILE_PLACEHOLDER  → compile_ultra strategy block for chosen profile
# =============================================================================

# ── Library Setup ─────────────────────────────────────────────────────────────
# TODO: Set your PDK standard cell timing library (.db) below.
#       The rram_wrapper libraries ship with the fsl-hd project.
#       Use tc (typical corner) for exploration; switch to wc for signoff.
set_app_var target_library "verilog/include/rram_wrapper.tc.db"
set_app_var link_library   "* verilog/include/rram_wrapper.tc.db"

# ── Read Sources ──────────────────────────────────────────────────────────────
# 1. Auto-generated DSE macro header (written to fsl-hd/verilog/include/ by json_to_svh.py)
analyze -format sverilog {verilog/include/config_macros.svh}

# 2. Existing design parameters (keep param.vh for any macros not overridden by DSE)
analyze -format sverilog {verilog/include/param.vh}

# 3. RTL source files from fsl-hd/verilog/hdl/
#    Using Tcl glob — DC requires explicit file list; adjust compile order if needed.
set _hdl_files [lsort [glob -nocomplain verilog/hdl/*.v verilog/hdl/*.sv]]
if {[llength $_hdl_files] == 0} {
    puts "ERROR: No RTL files found in verilog/hdl/. Verify path."
    exit 1
}
foreach _f $_hdl_files {
    analyze -format sverilog $_f
}

# ── Elaborate ─────────────────────────────────────────────────────────────────
# TODO: Replace 'hdnn_top' with the actual top-level module name in fsl-hd/verilog/hdl/
#       (check fsl-hd/verilog/hdl/ for the correct top module)
elaborate hdnn_top

# ── Timing Constraints ────────────────────────────────────────────────────────
# Clock period is patched at runtime from the BO `frequency` parameter (Hz → ns).
create_clock -period CLOCK_PERIOD_PLACEHOLDER -name clk [get_ports clk]
set_clock_uncertainty 0.1  [get_clocks clk]
set_clock_transition  0.05 [get_clocks clk]

# Input/output delays (30% of clock period — adjust to your interface budget)
set_input_delay  [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_inputs]
set_output_delay [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_outputs]

# ── Synthesis Strategy ────────────────────────────────────────────────────────
# SYNTH_PROFILE_PLACEHOLDER
# (replaced at runtime with the profile-specific compile_ultra command block)

# ── Reports ───────────────────────────────────────────────────────────────────
report_area       > reports/report_area.rpt
report_timing     > reports/report_timing.rpt
report_power      > reports/report_power.rpt
report_constraint -all_violators > reports/report_constraint.rpt

# ── Write Netlist ─────────────────────────────────────────────────────────────
write -format verilog -hierarchy -output reports/synth_netlist.v

exit
