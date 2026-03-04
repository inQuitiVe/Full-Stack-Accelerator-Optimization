CWD = $(shell pwd)
UTILS = 
VV         = vcs -full64 -R -cpp g++ -cc gcc -LDFLAGS -Wl,--no-as-needed +lint=TFIPC-L -notice
VVOPTS     = -o $@ +v2k +vc +warn=all -sverilog -timescale=1ns/1ps +incdir+$(CWD)/include -y ${SYNOPSYS}/../dc-R-2020.09-SP3/dw/sim_ver +libext+.v+
COVARGS = 

ifdef WAVES
VVOPTS += -debug_access+all +define+COCOTB_SIM=1 +memcbk +vcs+dumparrays +sdfverbose
endif

ifdef GUI
VVOPTS += -R
VVOPTS += -gui
endif

ifdef DEBUG
VVOPTS += -debug_access+all
endif

ifdef COVERAGE
VVOPTS += -cm line+cond+tgl
COVARGS += -cm line+cond+tgl
endif

TOP ?= tb_top_warpper

clean:
	rm -rf build/sim

TESTBENCH = \
	$(CWD)/tb/tb_top_warpper.sv \
	$(CWD)/tb/tb_jtag.sv \
	$(CWD)/tb/tb_clk_gen.sv \
	$(CWD)/tb/tb_fifo_interface.sv 

# Dedicated testbench for hd_top only (old functional tb)
TESTBENCH_HD_TOP = \
	$(CWD)/tb/tb_hd_top.sv

# Timing testbench for hd_top: measures full-flow cycle latency
TESTBENCH_HD_TOP_TIMING = \
	$(CWD)/tb/tb_hd_top_timing.sv

# Timing testbench for core (host-view end-to-end)
TESTBENCH_CORE_TIMING = \
	$(CWD)/tb/tb_core_timing.sv

# Full-chip (top_warpper) simulation RTL set
VERILOG = \
	$(CWD)/hdl/top_warpper.sv \
	$(CWD)/hdl/chip_interface.sv \
	$(CWD)/hdl/top_pnet_stub.sv \
	$(CWD)/hdl/hd_top.sv \
	$(CWD)/hdl/hd_enc.sv \
	$(CWD)/hdl/hd_search.sv \
	$(CWD)/hdl/hd_train.sv \
	$(CWD)/hdl/sub_module.sv \
	$(CWD)/hdl/cdc_fifo.sv \
	$(CWD)/hdl/rf_sp_32x32.sv \
	$(CWD)/hdl/sram_sp_256x64.sv \
	$(CWD)/hdl/sram_sp_4096x64.sv \
    /opt/lib/tsmc/211005//tcbn40ulpbwp40_c170815_130d/TSMCHOME/digital/Front_End/verilog/tcbn40ulpbwp40_c170815_130a/tcbn40ulpbwp40_c170815.v 

# Minimal RTL set for hd_top-only simulation
VERILOG_HD_TOP = \
	$(CWD)/hdl/hd_top.sv \
	$(CWD)/hdl/hd_enc.sv \
	$(CWD)/hdl/hd_search.sv \
	$(CWD)/hdl/hd_train.sv \
	$(CWD)/hdl/sub_module.sv \
	$(CWD)/hdl/cdc_fifo.sv \
	$(CWD)/hdl/rf_sp_32x32.sv \
	$(CWD)/hdl/sram_sp_256x64.sv \
	$(CWD)/hdl/sram_sp_4096x64.sv

RF_INCLUDE = \
    $(PWD)/../mem_rf/ts5n40lphsa32x32m2s_200a/VERILOG/ts5n40lphsa32x32m2s_200a_tt1p1v25c.v \
    $(PWD)/../mem_rf/ts1n40lpb256x32m4mwba_260a/VERILOG/ts1n40lpb256x32m4mwba_260a_tt1p1v25c.v \
    $(PWD)/../mem_rf/ts1n40lpb4096x64m4swba_260a/VERILOG/ts1n40lpb4096x64m4swba_260a_tt1p1v25c.v 

sim: $(TESTBENCH) $(VERILOG) $(UTILS)
	mkdir -p build/sim/; cd build/sim/; \
	$(VV) $(VVOPTS) -top $(TOP) +define+UNIT_DELAY=1 $(TESTBENCH) $(VERILOG) $(RF_INCLUDE) $(UTILS); 

sim_hd_top: $(TESTBENCH_HD_TOP) $(VERILOG_HD_TOP) $(UTILS)
	mkdir -p build/sim/; cd build/sim/; \
	$(VV) $(VVOPTS) -top hd_top_tb +define+UNIT_DELAY=1 $(TESTBENCH_HD_TOP) $(VERILOG_HD_TOP) $(RF_INCLUDE) $(UTILS);

# Timing benchmark: measure full-flow latency for current param_opt.vh config
sim_hd_top_timing: $(TESTBENCH_HD_TOP_TIMING) $(VERILOG_HD_TOP) $(UTILS)
	mkdir -p build/sim/; cd build/sim/; \
	$(VV) $(VVOPTS) -top tb_hd_top_timing +define+UNIT_DELAY=1 $(TESTBENCH_HD_TOP_TIMING) $(VERILOG_HD_TOP) $(RF_INCLUDE) $(UTILS);

# Timing benchmark: measure end-to-end latency of core (host perspective)
sim_core_timing: $(TESTBENCH_CORE_TIMING) $(VERILOG) $(UTILS)
	mkdir -p build/sim/; cd build/sim/; \
	$(VV) $(VVOPTS) -top tb_core_timing +define+UNIT_DELAY=1 $(TESTBENCH_CORE_TIMING) $(VERILOG) $(RF_INCLUDE) $(UTILS);


.PHONY: clean sim_hd_top_timing sim_core_timing