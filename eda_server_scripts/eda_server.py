"""
EDA Socket Server — Deploy on the licensed EDA host machine.

Server deployment layout assumed:
  ~/workspace/
    ├── fsl-hd/                ← existing hardware project (RTL, libs, reports)
    └── full-stack-opt/        ← THIS script lives here
        ├── eda_server.py
        ├── json_to_svh.py
        ├── parsers/
        ├── dc/                ← TCL templates (synth_template.tcl / synth_template_fast.tcl)
        └── Makefile           ← invokes EDA tools with CWD = fsl-hd/

Responsibilities:
  - Listen for incoming JSON task payloads from the Client (Docker).
  - Enqueue tasks and execute them serially (one DC license).
  - Run json_to_svh.py → make synth → parse_dc.py entirely on-server.
  - Return a compact JSON result dict; never transfer .rpt or .fsdb files.
  - Support a Polling protocol so Client does not need a long-lived TCP connection.
  - (Path 3) Run VCS gate-level simulation using LFSR-based testbench when
    run_path3=True is set in the payload.  No hex data transfer is required;
    the testbench (tb_core_timing.sv or tb_hd_top_timing.sv) auto-generates LFSR stimuli.
    Testbench selection is controlled by top_module inside params.

Protocol (all messages newline-delimited JSON):
  Submit (Path 2): {"action": "submit", "job_id": <int>, "params": {...}}
  Submit (Path 3): {"action": "submit", "job_id": <int>, "params": {...}, "run_path3": true}
  Poll:            {"action": "status",  "job_id": <int>}
  Reply (success): {"job_id": <int>, "status": "success", "metrics": {...}}
  Reply (failure): {"job_id": <int>, "status": "error"|"timeout"|"timing_violated",
                    "reason": "..."}
"""

import json
import logging
import os
import queue
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from parsers.parse_dc import parse_dc_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eda_server")

# ── Configuration ────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 5000
SYNTH_TIMEOUT_SECONDS = 1800          # 30-minute hard timeout for DC synthesis

# This server script lives in full-stack-opt/; hardware project is the sibling fsl-hd/.
# Resolve to absolute paths so report lookup works regardless of process cwd.
WORK_DIR    = Path(__file__).resolve().parent   # ~/workspace/full-stack-opt/
FSL_HD_DIR  = (WORK_DIR.parent / "fsl-hd").resolve()  # ~/workspace/fsl-hd/
MAKEFILE_DIR = WORK_DIR                        # Makefile lives in full-stack-opt/
REPORTS_DIR = (FSL_HD_DIR / "reports").resolve()  # DC/VCS reports written to fsl-hd/reports/

# ── Job Registry & Queue ──────────────────────────────────────────────────────
task_queue: queue.Queue = queue.Queue()
job_registry: Dict[int, Dict[str, Any]] = {}
registry_lock = threading.Lock()

# ── Params Logging Categories ──────────────────────────────────────────────────
PARAMS_HARDWARE = frozenset({
    "hd_dim", "reram_size", "inner_dim", "frequency",
    "encoder_x_dim", "encoder_y_dim",
    "cnn_x_dim_1", "cnn_y_dim_1", "cnn_x_dim_2", "cnn_y_dim_2",
    "out_channels_1", "out_channels_2",
})
PARAMS_SOFTWARE = frozenset({
    "kernel_size_1", "kernel_size_2",
    "stride_1", "stride_2", "padding_1", "padding_2", "dilation_1", "dilation_2",
})
PARAMS_SYNTH_FLOW = frozenset({
    "synth_mode", "top_module",
    "syn_map_effort", "syn_opt_effort",
    "enable_clock_gating", "max_area_ignore_tns", "enable_retime",
    "compile_timing_high_effort", "compile_area_high_effort", "compile_ultra_gate_clock",
    "compile_exact_map", "compile_no_autoungroup", "compile_clock_gating_through_hierarchy",
    "enable_leakage_optimization", "enable_dynamic_optimization", "enable_enhanced_resource_sharing",
    "dp_smartgen_strategy",
})


def _format_params_for_log(params: Dict[str, Any]) -> str:
    """Format params into categorized multi-line log for readability."""
    hw = {k: v for k, v in params.items() if k in PARAMS_HARDWARE}
    sw = {k: v for k, v in params.items() if k in PARAMS_SOFTWARE}
    flow = {k: v for k, v in params.items() if k in PARAMS_SYNTH_FLOW}
    other = {k: v for k, v in params.items()
             if k not in PARAMS_HARDWARE and k not in PARAMS_SOFTWARE and k not in PARAMS_SYNTH_FLOW}

    def _fmt_section(title: str, items: dict) -> str:
        if not items:
            return ""
        pairs = [f"{k}={v}" for k, v in sorted(items.items())]
        # Wrap at ~100 chars, join with ", " for readability
        lines, buf = [], []
        for p in pairs:
            if buf and sum(len(x) for x in buf) + len(buf) * 2 + len(p) > 100:
                lines.append("    " + ", ".join(buf))
                buf = []
            buf.append(p)
        if buf:
            lines.append("    " + ", ".join(buf))
        return f"  {title}\n" + "\n".join(lines)

    parts = []
    if hw:
        parts.append(_fmt_section("Hardware:", hw))
    if sw:
        parts.append(_fmt_section("Software:", sw))
    if flow:
        parts.append(_fmt_section("Synth/Flow:", flow))
    if other:
        parts.append(_fmt_section("Other:", other))
    return "\n".join(p for p in parts if p) or "(empty)"


def _format_metrics_for_log(metrics: Dict[str, Any]) -> str:
    """Format metrics dict into short lines (one key=value per line)."""
    lines = []
    for k, v in sorted(metrics.items()):
        if isinstance(v, float):
            lines.append(f"    {k}={v:.4g}")
        elif isinstance(v, int) and abs(v) >= 1e6:
            lines.append(f"    {k}={float(v):.4g}")
        else:
            lines.append(f"    {k}={v}")
    return "\n".join(lines) if lines else "    (empty)"


def _run_synthesis(job_id: int, params: Dict[str, Any], run_path3: bool = False) -> None:
    """
    Called from the worker thread: translate params, run DC synthesis, parse results.
    When run_path3=True, also runs VCS gate-level simulation (PtPX power analysis disabled).

    Path 3 uses LFSR-based testbenches (tb_core_timing.sv or tb_hd_top_timing.sv)
    selected by top_module in params. No hex data transfer is required.

    IMPORTANT:
      - For Path 2 (run_path3=False), we always run DC synthesis (+parse DC reports).
      - For Path 3 (run_path3=True), we **reuse** the most recent DC artifacts for
        this design point and only run VCS + PtPX (no second DC call), while still
        re-parsing DC reports for timing/area consistency.

    Because the server processes jobs serially (single worker thread) and Path 3
    jobs are submitted immediately after their corresponding Path 2 jobs, the DC
    reports / netlist in REPORTS_DIR are guaranteed to belong to the same design.
    """
    _set_status(job_id, "running")
    synth_mode = str(params.get("synth_mode", "slow")).strip().lower()
    top_module = str(params.get("top_module", "core")).strip().lower()

    phase_label = "Path 3 (VCS+PtPX only, reuse DC)" if run_path3 else "Path 2 (synth only)"
    logger.info("[Job %d] Starting %s  [synth_mode=%s, top_module=%s]",
                job_id, phase_label, synth_mode, top_module)
    for line in _format_params_for_log(params).splitlines():
        if line.strip():
            logger.info("[Job %d] %s", job_id, line.rstrip())

    try:
        if not run_path3:
            # ── Path 2: fresh DC synthesis ──────────────────────────────────────
            # Step 1: Translate JSON params → config_macros.svh + synth_dse.tcl
            json_to_svh_script = WORK_DIR / "json_to_svh.py"
            translate_result = subprocess.run(
                ["python3", str(json_to_svh_script)],
                input=json.dumps(params),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=60,
            )
            if translate_result.returncode != 0:
                err = (translate_result.stderr or translate_result.stdout or "").strip()
                raise RuntimeError("json_to_svh.py failed: " + err)
            logger.info(f"[Job {job_id}] Translation complete.")

            # Step 2: Run Design Compiler synthesis
            # Pass SYNTH_MODE and TOP_MODULE to the Makefile for correct TCL selection
            synth_result = subprocess.run(
                ["make", "synth",
                 "SYNTH_MODE=" + synth_mode,
                 "TOP_MODULE=" + top_module],
                cwd=str(MAKEFILE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=SYNTH_TIMEOUT_SECONDS,
            )
            if synth_result.returncode != 0:
                err_out = (synth_result.stderr or synth_result.stdout or "")[-2000:]
                raise RuntimeError(
                    "make synth failed (exit %s):\n%s" % (synth_result.returncode, err_out)
                )
            logger.info(f"[Job {job_id}] Synthesis complete.")
        else:
            # ── Path 3: reuse existing DC artifacts ────────────────────────────
            logger.info("[Job %d] Path 3: reusing existing DC netlist/reports.", job_id)
            logger.info("[Job %d]   (skipping make synth)", job_id)

        # Step 3: Parse DC report files (both Path 2 and Path 3 need these metrics)
        metrics = parse_dc_reports(str(REPORTS_DIR))
        logger.info("[Job %d] Parsed DC metrics:", job_id)
        for line in _format_metrics_for_log(metrics).splitlines():
            logger.info("[Job %d] %s", job_id, line.strip())

        # Step 4: Gate 2 — check timing
        if metrics.get("timing_slack_ns", 0.0) < 0.0:
            _set_status(job_id, "timing_violated", metrics=metrics)
            logger.warning(f"[Job {job_id}] Timing VIOLATED (slack={metrics['timing_slack_ns']:.3f} ns).")
            return  # do not proceed to simulation if timing is violated

        if not run_path3:
            # Path 2 only: synthesis metrics are the final result
            _set_status(job_id, "success", metrics=metrics)
            logger.info(f"[Job {job_id}] Path 2 success.")
            return

        # ── Path 3: Gate-Level Simulation (LFSR testbench, no hex transfer) ─────
        # The Makefile selects the correct TB based on TOP_MODULE:
        #   top_module=core    → tb_core_timing.sv  (full wrapper, off-chip FIFO protocol)
        #   top_module=hd_top  → tb_hd_top_timing.sv (HD core only, direct interface)
        logger.info("[Job %d] Starting gate-level simulation (VCS).", job_id)
        logger.info("[Job %d]   top_module=%s", job_id, top_module)
        sim_result = subprocess.run(
            ["make", "sim",
             "SYNTH_MODE=" + synth_mode,
             "TOP_MODULE=" + top_module],
            cwd=str(MAKEFILE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=SYNTH_TIMEOUT_SECONDS,
        )
        if sim_result.returncode != 0:
            err_out = (sim_result.stderr or sim_result.stdout or "")[-2000:]
            raise RuntimeError(
                "make sim failed (exit %s):\n%s" % (sim_result.returncode, err_out)
            )
        logger.info(f"[Job {job_id}] VCS simulation complete.")

        # Step 5 (power analysis disabled): parse VCS simulation log only
        from parsers.parse_vcs import parse_vcs_reports
        vcs_metrics = parse_vcs_reports(str(REPORTS_DIR))
        logger.info("[Job %d] Parsed VCS metrics:", job_id)
        for line in _format_metrics_for_log(vcs_metrics).splitlines():
            logger.info("[Job %d] %s", job_id, line.strip())

        # Merge: Path 3 upgrades power + adds cycle count; keeps DC area (unchanged by sim)
        combined_metrics = {**metrics, **vcs_metrics}
        _set_status(job_id, "success", metrics=combined_metrics)
        logger.info(f"[Job {job_id}] Path 3 success.")

    except subprocess.TimeoutExpired:
        logger.error(f"[Job {job_id}] Timed out after {SYNTH_TIMEOUT_SECONDS}s.")
        _set_status(job_id, "timeout", reason="Exceeded %ds hard limit." % SYNTH_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.error(f"[Job {job_id}] Error: {exc}")
        _set_status(job_id, "error", reason=str(exc))


def _set_status(
    job_id: int,
    status: str,
    metrics: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> None:
    with registry_lock:
        entry = job_registry.setdefault(job_id, {})
        entry["status"] = status
        entry["updated_at"] = time.time()
        if metrics is not None:
            entry["metrics"] = metrics
        if reason is not None:
            entry["reason"] = reason


def _worker_loop() -> None:
    """Single worker thread: pops jobs from queue and runs synthesis serially."""
    logger.info("Worker thread started — waiting for tasks.")
    while True:
        job_id, params, run_path3 = task_queue.get()
        try:
            _run_synthesis(job_id, params, run_path3=run_path3)
        finally:
            task_queue.task_done()


# ── Request Handlers ──────────────────────────────────────────────────────────

def _handle_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id: int = payload.get("job_id", int(uuid.uuid4().int % 1_000_000))
    params: Dict[str, Any] = payload["params"]
    # Path 3 is now triggered by a boolean flag, not by presence of hex_data.
    # The testbench uses LFSR stimuli, so no hex transfer is required.
    run_path3: bool = bool(payload.get("run_path3", False))

    TERMINAL_STATUSES = frozenset({"success", "error", "timeout", "timing_violated"})
    with registry_lock:
        existing = job_registry.get(job_id)
        if existing is not None and existing["status"] not in TERMINAL_STATUSES:
            return {"job_id": job_id, "status": "error", "reason": "duplicate job_id"}
        job_registry[job_id] = {
            "status": "queued",
            "submitted_at": time.time(),
            "updated_at": time.time(),
            "path3": run_path3,
            "top_module": str(params.get("top_module", "core")),
            "synth_mode": str(params.get("synth_mode", "slow")),
        }

    task_queue.put((job_id, params, run_path3))
    phase = "Path 3 (VCS+PtPX)" if run_path3 else "Path 2 (synth only)"
    logger.info("[Job %d] Accepted and queued.", job_id)
    logger.info("[Job %d]   %s", job_id, phase)
    logger.info("[Job %d]   synth_mode=%s  top_module=%s  queue=%d",
                job_id, params.get("synth_mode", "slow"),
                params.get("top_module", "core"), task_queue.qsize())
    return {"job_id": job_id, "status": "accepted"}


def _handle_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id: int = payload["job_id"]
    with registry_lock:
        entry = job_registry.get(job_id)

    if entry is None:
        return {"job_id": job_id, "status": "error", "reason": "unknown job_id"}

    response: Dict[str, Any] = {"job_id": job_id, "status": entry["status"]}
    if "metrics" in entry:
        response["metrics"] = entry["metrics"]
    if "reason" in entry:
        response["reason"] = entry["reason"]
    return response


def _dispatch(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action", "")
    if action == "submit":
        return _handle_submit(payload)
    elif action == "status":
        return _handle_status(payload)
    else:
        return {"status": "error", "reason": f"unknown action: {action!r}"}


# ── Connection Handler ────────────────────────────────────────────────────────

def _handle_connection(conn: socket.socket, addr) -> None:
    logger.info(f"Connection from {addr}")
    try:
        data = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\n"):
                break

        payload = json.loads(data.decode("utf-8").strip())
        response = _dispatch(payload)
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    except json.JSONDecodeError as exc:
        error = json.dumps({"status": "error", "reason": f"JSON decode error: {exc}"}) + "\n"
        conn.sendall(error.encode("utf-8"))
    except Exception as exc:
        logger.exception(f"Unexpected error handling {addr}: {exc}")
        error = json.dumps({"status": "error", "reason": str(exc)}) + "\n"
        try:
            conn.sendall(error.encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


# ── Main Server Loop ──────────────────────────────────────────────────────────

def main() -> None:
    # Start the single worker thread (serializes EDA jobs for license compliance)
    worker = threading.Thread(target=_worker_loop, daemon=True, name="eda-worker")
    worker.start()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(16)
    logger.info(f"EDA Server listening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_sock.accept()
            conn_thread = threading.Thread(
                target=_handle_connection,
                args=(conn, addr),
                daemon=True,
            )
            conn_thread.start()
    except KeyboardInterrupt:
        logger.info("Shutting down EDA Server.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
