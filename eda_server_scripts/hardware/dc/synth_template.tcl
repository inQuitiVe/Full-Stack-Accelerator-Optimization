# =============================================================================
# synth_template.tcl — Design Compiler Synthesis Script Template
#
# This file is patched at runtime by json_to_svh.py:
#   - CLOCK_PERIOD_PLACEHOLDER  → derived from `frequency` parameter (ns)
#   - SYNTH_PROFILE_PLACEHOLDER → replaced with the compile_ultra strategy block
#
# IMPORTANT: Adapt library paths and design names to your PDK and project.
# =============================================================================

# ── Library Setup ─────────────────────────────────────────────────────────────
set_app_var target_library "path/to/your_stdcell.db"
set_app_var link_library   "* path/to/your_stdcell.db"

# ── Read RTL ──────────────────────────────────────────────────────────────────
# Include the auto-generated macro header first
analyze -format sverilog {
    include/config_macros.svh
}

# Add your RTL source files here (relative to hardware/ directory)
analyze -format sverilog {
    rtl/hdnn_top.sv
    rtl/encoder.sv
    rtl/hd_inference.sv
    rtl/rram_array.sv
}

elaborate hdnn_top

# ── Timing Constraints ────────────────────────────────────────────────────────
# Clock period injected by json_to_svh.py from the `frequency` parameter
create_clock -period CLOCK_PERIOD_PLACEHOLDER -name clk [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks clk]
set_clock_transition  0.05 [get_clocks clk]

# Input/output delays (adjust to your interface timing budget)
set_input_delay  [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_inputs]
set_output_delay [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_outputs]

# ── Synthesis Strategy ────────────────────────────────────────────────────────
# SYNTH_PROFILE_PLACEHOLDER
# (replaced with profile-specific compile_ultra commands at runtime)

# ── Reports ───────────────────────────────────────────────────────────────────
report_area    > reports/report_area.rpt
report_timing  > reports/report_timing.rpt
report_power   > reports/report_power.rpt
report_constraint -all_violators > reports/report_constraint.rpt

# ── Write Netlist ─────────────────────────────────────────────────────────────
write -format verilog -hierarchy -output reports/synth_netlist.v

exit
