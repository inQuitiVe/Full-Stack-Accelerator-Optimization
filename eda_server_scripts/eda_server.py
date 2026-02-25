"""
EDA Socket Server — Deploy on the licensed EDA host machine.

Responsibilities:
  - Listen for incoming JSON task payloads from the Client (Docker).
  - Enqueue tasks and execute them serially (one DC license).
  - Run json_to_svh.py -> make synth -> parse_dc.py entirely on-server.
  - Return a compact JSON result dict; never transfer .rpt or .fsdb files.
  - Support a Polling protocol so Client does not need a long-lived TCP connection.

Protocol (all messages newline-delimited JSON):
  Submit:  {"action": "submit",  "job_id": <int>, "params": {...}}
  Poll:    {"action": "status",  "job_id": <int>}
  Reply:   {"job_id": <int>, "status": "accepted"|"queued"|"running"|"success"|"error"|"timeout",
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

def _run_synthesis(job_id: int, params: Dict[str, Any]) -> None:
    """Called from the worker thread: translate params, run DC, parse results."""
    _set_status(job_id, "running")
    logger.info(f"[Job {job_id}] Starting synthesis with params: {params}")

    try:
        # Step 1: Translate JSON params → config_macros.svh + patch TCL clock
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
        logger.info(f"[Job {job_id}] Parsed metrics: {metrics}")

        # Step 4: Gate 2 — check timing
        if metrics.get("timing_slack_ns", 0.0) < 0.0:
            _set_status(job_id, "timing_violated", metrics=metrics)
            logger.warning(f"[Job {job_id}] Timing VIOLATED (slack={metrics['timing_slack_ns']:.3f} ns).")
        else:
            _set_status(job_id, "success", metrics=metrics)
            logger.info(f"[Job {job_id}] Success.")

    except subprocess.TimeoutExpired:
        logger.error(f"[Job {job_id}] Synthesis timed out after {SYNTH_TIMEOUT_SECONDS}s.")
        _set_status(job_id, "timeout", reason=f"Synthesis exceeded {SYNTH_TIMEOUT_SECONDS}s hard limit.")
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
        job_id, params = task_queue.get()
        try:
            _run_synthesis(job_id, params)
        finally:
            task_queue.task_done()


# ── Request Handlers ──────────────────────────────────────────────────────────

def _handle_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id: int = payload.get("job_id", int(uuid.uuid4().int % 1_000_000))
    params: Dict[str, Any] = payload["params"]

    with registry_lock:
        if job_id in job_registry:
            return {"job_id": job_id, "status": "error", "reason": "duplicate job_id"}
        job_registry[job_id] = {
            "status": "queued",
            "submitted_at": time.time(),
            "updated_at": time.time(),
        }

    task_queue.put((job_id, params))
    logger.info(f"[Job {job_id}] Accepted and queued (queue depth: {task_queue.qsize()}).")
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
