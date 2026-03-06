# =============================================================================
# ptpx.tcl — Power Analysis (PrimeTime-APX / PrimeTime-PX)
#
# Invocation: pt_shell with CWD = fsl-hd/ (launched via `make power`)
#
# License: School has PrimeTime-APX (200) but not PrimeTime-PX.
#   - read_saif works (SAIF from vcd2saif)
#   - update_power / report_power require PrimeTime-PX
# If you get "PrimeTime-PX or (null) are not enabled (PT-010)", contact IT to:
#   1. Confirm PrimeTime-APX usage for power (may need different invocation)
#   2. Or obtain PrimeTime-PX license
#
# Prerequisites:
#   - reports/synth_netlist.v   : from `make synth`
#   - reports/activity.saif     : from vcd2saif (make power runs this)
#   - reports/activity.vcd      : from `make sim` (source for vcd2saif)
# =============================================================================

# Enable Power Analysis
set power_enable_analysis true

# ── Library Setup ─────────────────────────────────────────────────────────────
set_app_var target_library "verilog/include/rram_wrapper.tc.db"
set_app_var link_library   "* verilog/include/rram_wrapper.tc.db"

# ── Read Synthesized Netlist ──────────────────────────────────────────────────
read_verilog reports/synth_netlist.v

# Top module: use TOP_MODULE from env (passed by Makefile) or else first design
set design_list [get_designs]
if {[llength $design_list] == 0} {
    puts "ERROR: No designs loaded from reports/synth_netlist.v"
    exit 1
}
if {[info exists env(TOP_MODULE)] && $env(TOP_MODULE) ne ""} {
    set top_module $env(TOP_MODULE)
} else {
    set top_module [get_object_name [lindex $design_list 0]]
}
# Find design by name (get_designs may return refs)
set top_ref [get_designs -quiet $top_module]
if {[llength $top_ref] == 0} {
    # Try finding a design whose name matches (netlist may uniquify)
    foreach d $design_list {
        set dname [get_object_name $d]
        if {$dname eq $top_module || [string match *$top_module* $dname]} {
            set top_module $dname
            break
        }
    }
}
link_design $top_module
puts "INFO: Linked design '$top_module'"

# ── Apply Timing Constraints ──────────────────────────────────────────────────
# Clock period should match the DC synthesis constraint (10 ns default).
set clk_ports [get_ports -quiet clk]
if {[llength $clk_ports] > 0} {
    create_clock -period 10.0 -name clk $clk_ports
} else {
    puts "WARNING: No port 'clk' found; using create_clock on all ports named *clk*"
    set clk_ports [get_ports -quiet *clk*]
    if {[llength $clk_ports] > 0} {
        create_clock -period 10.0 -name clk [lindex $clk_ports 0]
    }
}

# ── Read Switching Activity ───────────────────────────────────────────────────
# Prefer SAIF (uses PrimeTime-APX license). VCD/FSDB require PrimeTime-PX.
# SAIF is produced by: make power (runs vcd2saif on activity.vcd before this script).
if {$top_module eq "hd_top"} {
    set dut_path "tb_hd_top_timing/dut"
} else {
    set dut_path "tb_core_timing/dut"
}

if {[file exists reports/activity.saif]} {
    puts "INFO: Reading SAIF (PrimeTime-APX)  → reports/activity.saif"
    puts "INFO: strip_path = $dut_path"
    read_saif reports/activity.saif -strip_path $dut_path
} elseif {[file exists reports/activity.fsdb]} {
    puts "INFO: Reading FSDB (requires PrimeTime-PX)  → reports/activity.fsdb"
    read_fsdb reports/activity.fsdb -strip_path $dut_path
} elseif {[file exists reports/activity.vcd]} {
    puts "INFO: Reading VCD (requires PrimeTime-PX)   → reports/activity.vcd"
    read_vcd reports/activity.vcd -strip_path $dut_path
} else {
    puts "ERROR: No switching activity file found in reports/."
    puts "       Expected: reports/activity.saif (from vcd2saif, uses PrimeTime-APX)"
    puts "                 reports/activity.vcd  (run 'make sim' first)"
    exit 1
}

# ── Power Analysis ────────────────────────────────────────────────────────────
update_power
report_power > reports/ptpx_power.rpt

exit
