"""
EDA Socket Server — Deploy on the licensed EDA host machine.

Responsibilities:
  - Listen for incoming JSON task payloads from the Client (Docker).
  - Enqueue tasks and execute them serially (one DC license).
  - Run json_to_svh.py -> make synth -> parse_dc.py entirely on-server.
  - Return a compact JSON result dict; never transfer .rpt or .fsdb files.
  - Support a Polling protocol so Client does not need a long-lived TCP connection.
  - (Path 3) Accept optional hex_data payload and write to hardware/data/
    before running make sim → VCS gate-level simulation.

Protocol (all messages newline-delimited JSON):
  Submit (Path 2): {"action": "submit",  "job_id": <int>, "params": {...}}
  Submit (Path 3): {"action": "submit",  "job_id": <int>, "params": {...},
                    "hex_data": {"inputs": "...", "labels": "...", "weights": "..."}}
  Poll:            {"action": "status",  "job_id": <int>}
  Reply:           {"job_id": <int>, "status": "accepted"|"queued"|"running"|"success"|"error"|"timeout",
                    "metrics": {...} | "reason": "..."}
"""

from __future__ import annotations

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
WORK_DIR = Path(__file__).parent      # Server script directory
MAKEFILE_DIR = WORK_DIR / "hardware"  # Directory containing the synthesis Makefile
REPORTS_DIR = MAKEFILE_DIR / "reports"

# ── Job Registry & Queue ──────────────────────────────────────────────────────
task_queue: queue.Queue = queue.Queue()
job_registry: Dict[int, Dict[str, Any]] = {}
registry_lock = threading.Lock()


# ── Worker Thread ─────────────────────────────────────────────────────────────

def _write_hex_data(hex_data: Dict[str, str]) -> None:
    """
    Write hex data strings (from the Client JSON payload) to the server's
    hardware/data/ directory so the VCS Testbench can read them via $readmemh.

    Expected keys: "inputs", "labels", "weights".
    Missing keys are silently skipped (allows partial updates).
    """
    data_dir = MAKEFILE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    file_map = {
        "inputs":  data_dir / "inputs.hex",
        "labels":  data_dir / "labels.hex",
        "weights": data_dir / "weights.hex",
    }
    for key, path in file_map.items():
        if key in hex_data and hex_data[key]:
            path.write_text(hex_data[key], encoding="utf-8")
            logger.info(f"[hex_data] Written {path.name} ({len(hex_data[key])} chars)")


def _run_synthesis(job_id: int, params: Dict[str, Any], hex_data: Optional[Dict[str, str]] = None) -> None:
    """
    Called from the worker thread: translate params, run DC synthesis, parse results.
    When hex_data is provided (Path 3), also runs VCS gate-level simulation.
    """
    _set_status(job_id, "running")
    is_path3 = hex_data is not None
    logger.info(f"[Job {job_id}] Starting {'Path 3 (sim)' if is_path3 else 'Path 2 (synth)'} with params: {params}")

    try:
        # Step 0 (Path 3 only): Write hex data to hardware/data/ before translation
        if is_path3:
            _write_hex_data(hex_data)
            logger.info(f"[Job {job_id}] Hex data written to hardware/data/.")

        # Step 1: Translate JSON params → config_macros.svh + synth.tcl + tb_macros.svh
        json_to_svh_script = WORK_DIR / "json_to_svh.py"
        translate_result = subprocess.run(
            ["python", str(json_to_svh_script)],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if translate_result.returncode != 0:
            raise RuntimeError(
                f"json_to_svh.py failed: {translate_result.stderr.strip()}"
            )
        logger.info(f"[Job {job_id}] Translation complete.")

        # Step 2: Run Design Compiler via Makefile
        synth_result = subprocess.run(
            ["make", "synth"],
            cwd=str(MAKEFILE_DIR),
            capture_output=True,
            text=True,
            timeout=SYNTH_TIMEOUT_SECONDS,
        )
        if synth_result.returncode != 0:
            raise RuntimeError(
                f"make synth failed (exit {synth_result.returncode}):\n"
                f"{synth_result.stderr[-2000:]}"
            )
        logger.info(f"[Job {job_id}] Synthesis complete.")

        # Step 3: Parse DC report files
        metrics = parse_dc_reports(str(REPORTS_DIR))
        logger.info(f"[Job {job_id}] Parsed DC metrics: {metrics}")

        # Step 4: Gate 2 — check timing
        if metrics.get("timing_slack_ns", 0.0) < 0.0:
            _set_status(job_id, "timing_violated", metrics=metrics)
            logger.warning(f"[Job {job_id}] Timing VIOLATED (slack={metrics['timing_slack_ns']:.3f} ns).")
            return  # do not proceed to simulation if timing is violated

        if not is_path3:
            # Path 2: synthesis metrics are the final result
            _set_status(job_id, "success", metrics=metrics)
            logger.info(f"[Job {job_id}] Path 2 success.")
            return

        # ── Path 3: Gate-Level Simulation ────────────────────────────────────
        logger.info(f"[Job {job_id}] Starting gate-level simulation (VCS).")
        sim_result = subprocess.run(
            ["make", "sim"],
            cwd=str(MAKEFILE_DIR),
            capture_output=True,
            text=True,
            timeout=SYNTH_TIMEOUT_SECONDS,
        )
        if sim_result.returncode != 0:
            raise RuntimeError(
                f"make sim failed (exit {sim_result.returncode}):\n"
                f"{sim_result.stderr[-2000:]}"
            )
        logger.info(f"[Job {job_id}] VCS simulation complete.")

        # Step 5: Run PrimeTime PX for dynamic power
        logger.info(f"[Job {job_id}] Starting PtPX power analysis.")
        power_result = subprocess.run(
            ["make", "power"],
            cwd=str(MAKEFILE_DIR),
            capture_output=True,
            text=True,
            timeout=SYNTH_TIMEOUT_SECONDS,
        )
        if power_result.returncode != 0:
            raise RuntimeError(
                f"make power failed (exit {power_result.returncode}):\n"
                f"{power_result.stderr[-2000:]}"
            )
        logger.info(f"[Job {job_id}] PtPX power analysis complete.")

        # Step 6: Parse VCS + PtPX reports
        from parsers.parse_vcs import parse_vcs_reports
        vcs_metrics = parse_vcs_reports(str(REPORTS_DIR))
        logger.info(f"[Job {job_id}] Parsed VCS/PtPX metrics: {vcs_metrics}")

        # Merge: Path 3 upgrades power and adds cycle count; keeps area from DC
        combined_metrics = {**metrics, **vcs_metrics}
        _set_status(job_id, "success", metrics=combined_metrics)
        logger.info(f"[Job {job_id}] Path 3 success.")

    except subprocess.TimeoutExpired:
        logger.error(f"[Job {job_id}] Timed out after {SYNTH_TIMEOUT_SECONDS}s.")
        _set_status(job_id, "timeout", reason=f"Exceeded {SYNTH_TIMEOUT_SECONDS}s hard limit.")
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
        job_id, params, hex_data = task_queue.get()
        try:
            _run_synthesis(job_id, params, hex_data=hex_data)
        finally:
            task_queue.task_done()


# ── Request Handlers ──────────────────────────────────────────────────────────

def _handle_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id: int = payload.get("job_id", int(uuid.uuid4().int % 1_000_000))
    params: Dict[str, Any] = payload["params"]
    hex_data: Optional[Dict[str, str]] = payload.get("hex_data")  # None for Path 2

    with registry_lock:
        if job_id in job_registry:
            return {"job_id": job_id, "status": "error", "reason": "duplicate job_id"}
        job_registry[job_id] = {
            "status": "queued",
            "submitted_at": time.time(),
            "updated_at": time.time(),
            "path3": hex_data is not None,
        }

    task_queue.put((job_id, params, hex_data))
    logger.info(
        f"[Job {job_id}] Accepted and queued "
        f"({'Path 3 w/ hex_data' if hex_data else 'Path 2 synth only'}, "
        f"queue depth: {task_queue.qsize()})."
    )
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
