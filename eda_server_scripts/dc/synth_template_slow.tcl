# =============================================================================
# synth_template_slow.tcl — Design Compiler Synthesis Script Template (SLOW MODE)
#
# Slow mode: all RTL sources (including PatterNet, SRAMs, chip_interface) are
# analyzed and synthesized from scratch in DC.
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
#   TOP_MODULE_PLACEHOLDER     → synthesis/sim scope: "core" or "hd_top"
# =============================================================================

# ── Environment / Library Setup ───────────────────────────────────────────────
# Keep this section close to the project's original DC script so includes and
# libraries resolve correctly (param.vh, stdcells, SRAM/RRAM wrappers, etc.).
set_host_options -max_cores 12

# Top module: injected at runtime by json_to_svh.py (core | hd_top)
set top_module TOP_MODULE_PLACEHOLDER

# Technology/library search paths
set TSMC_PDK_PATH /opt/lib/tsmc/211005/tcbn40ulpbwp40_c170815_130d/TSMCHOME/digital/Front_End/timing_power_noise/NLDM/tcbn40ulpbwp40_c170815_130d

# Patternet update location varies by deployment. Prefer a sibling directory,
# otherwise fall back to the common local checkout path.
if {[file isdirectory [file normalize [pwd]/../patternet_update]]} {
    set PNET_PATH [file normalize [pwd]/../patternet_update]
} elseif {[file isdirectory /home/cyyang/hdnn-pim-opt/patternet_update]} {
    set PNET_PATH /home/cyyang/hdnn-pim-opt/patternet_update
} else {
    puts "ERROR: Cannot find patternet_update. Tried: [file normalize [pwd]/../patternet_update] and /home/cyyang/hdnn-pim-opt/patternet_update"
    exit 1
}

set search_path [ list \
    [pwd]/verilog/include \
    [pwd]/verilog/hdl \
    [pwd]/mem_rf/compiled \
    [pwd]/syn \
    $PNET_PATH/verilog \
    $PNET_PATH/include \
    /opt/lib/tsmc/compiled/synopsys \
    $TSMC_PDK_PATH \
]

set target_library [ list \
    tcbn40ulpbwp40_c170815tt1p1v25c.db \
    tcbn40ulpbwp40_c170815ssg0p99v125c.db \
    tcbn40ulpbwp40_c170815ffg1p21vm40c.db \
    ts5n40lphsa32x32m2s_tt1p1v25c.db \
    ts5n40lphsa32x32m2s_200a_ss0p99v125c.db \
    ts5n40lphsa32x32m2s_200a_ff1p21vm40c.db \
    ts1n40lpb256x32m4mwba_tt1p1v25c.db \
    ts1n40lpb256x32m4mwba_260a_ss0p99v125c.db \
    ts1n40lpb256x32m4mwba_260a_ff1p21vm40c.db \
    ts1n40lpb4096x64m4swba_tt1p1v25c.db \
    ts1n40lpb4096x64m4swba_260a_ss0p99v125c.db \
    ts1n40lpb4096x64m4swba_260a_ff1p21vm40c.db \
    ts1n40lpb2048x16m8swba_tt1p1v25c.db \
    ts1n40lpb520x36m4swba_tt1p1v25c.db \
    ts1n40lpb8192x16m8swba_tt1p1v25c.db \
    ts5n40lphsa136x16m4s_tt1p1v25c.db \
    ts1n40lpb2048x16m8swba_ff1p21vm40c.db \
    ts1n40lpb520x36m4swba_ff1p21vm40c.db \
    ts1n40lpb8192x16m8swba_ff1p21vm40c.db \
    ts5n40lphsa136x16m4s_ff1p21vm40c.db \
    ts1n40lpb2048x16m8swba_ss0p99v125c.db \
    ts1n40lpb520x36m4swba_ss0p99v125c.db \
    ts1n40lpb8192x16m8swba_ss0p99v125c.db \
    ts5n40lphsa136x16m4s_ss0p99v125c.db \
    pe_new.bc.db pe_new.tc.db pe_new.wc.db \
    rram_wrapper.bc.db rram_wrapper.tc.db rram_wrapper.wc.db \
]

set link_library [concat "*" $target_library]
set symbol_library {}
set wire_load_mode enclosed
set timing_use_enhanced_capacitance_modeling true
set synthetic_library [list dw_foundation.sldb]
set link_path [concat  $link_library $synthetic_library]

# ── Read Sources ──────────────────────────────────────────────────────────────
# Define a persistent WORK library so designs end up in a known place.
file mkdir reports/dc_work
define_design_lib WORK -path reports/dc_work

# 1) Auto-generated DSE macro header + baseline params
# Use bare filenames here; include resolution relies on search_path above.
analyze -format sverilog -lib WORK {config_macros.svh}
analyze -format sverilog -lib WORK {param.vh}

# 2) RTL sources — explicit white-list to match original flow.
# These filenames are resolved via search_path (verilog/hdl and $PNET_PATH/verilog).
set rtl_files [ list \
    core.sv \
    chip_interface.sv \
    hd_top.sv \
    hd_enc.sv \
    hd_search.sv \
    hd_train.sv \
    cdc_fifo.sv \
    rf_sp_32x32.sv \
    sram_sp_256x64.sv \
    sram_sp_4096x64.sv \
    sub_module.sv \
    pulse_gen.syn.v \
    top.sv \
    pnet_hd_iface.sv \
    ctrl.sv \
    pe_array.sv \
    row_bus.sv \
    col_bus.sv \
    bf16.sv \
    sram520x36.sv \
    sram8192x16.sv \
    sram2048x16.sv \
    rfsp136x16.sv \
]
analyze -format sverilog -lib WORK $rtl_files

# ── Elaborate ─────────────────────────────────────────────────────────────────
elaborate $top_module
current_design $top_module
link

# ── Timing Constraints ────────────────────────────────────────────────────────
# Clock period is patched at runtime from the BO `frequency` parameter (Hz → ns).
create_clock -period CLOCK_PERIOD_PLACEHOLDER -name clk [get_ports clk]
set_clock_uncertainty 0.1  [get_clocks clk]
set_clock_transition  0.05 [get_clocks clk]

# Input/output delays (30% of clock period — adjust to your interface budget)
set_input_delay  [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_inputs]
set_output_delay [expr CLOCK_PERIOD_PLACEHOLDER * 0.3] -clock clk [all_outputs]

# ── Synthesis Strategy ────────────────────────────────────────────────────────
# SYNTH_DSE_OPTIONS_PLACEHOLDER
# (replaced at runtime: set_app_var compile_map_effort, compile_opt_effort, optional clock gating)
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
