"""
eda_client.py — Local polling socket client for the remote EDA Server.

Responsibilities:
  - Convert a params dict to a JSON payload and submit it to the EDA Server.
  - Poll the server every POLL_INTERVAL_S seconds for job status.
  - Enforce a strict CLIENT_TIMEOUT_S wall-clock timeout; if exceeded, treat
    the job as failed.
  - Return a standardised result dict or raise EDAClientError on unrecoverable failure.

The caller (path2_hardware.py) is responsible for interpreting the result and
calling ax_client.mark_trial_failed() when status != "success".
"""

from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Configuration (override via constructor kwargs) ───────────────────────────
DEFAULT_HOST = "EDA_SERVER_IP"       # Set to actual EDA server hostname or IP
DEFAULT_PORT = 5000
POLL_INTERVAL_S = 15.0               # Seconds between status polls
CLIENT_TIMEOUT_S = 1800.0            # 30-min hard wall-clock timeout
SOCKET_CONNECT_TIMEOUT_S = 30.0     # Per-connection TCP timeout


class EDAClientError(RuntimeError):
    """Raised when the EDA Client encounters an unrecoverable error."""


# ── Low-level socket communication ───────────────────────────────────────────

def _send_and_receive(
    host: str, port: int, payload: Dict[str, Any], connect_timeout: float
) -> Dict[str, Any]:
    """
    Open a TCP connection, send a newline-terminated JSON payload, receive the
    newline-terminated JSON response, and close the connection.
    """
    message = (json.dumps(payload) + "\n").encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        sock.connect((host, port))
        sock.sendall(message)

        # Receive until newline
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\n"):
                break
        return json.loads(data.decode("utf-8").strip())
    finally:
        sock.close()


# ── Public client function ────────────────────────────────────────────────────

def evaluate_remote(
    params: Dict[str, Any],
    job_id: int,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    poll_interval: float = POLL_INTERVAL_S,
    timeout: float = CLIENT_TIMEOUT_S,
    hex_data: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Submit a hardware evaluation task to the remote EDA Server and wait (via
    polling) for the result.

    Args:
        params:        Hardware parameter dictionary (the full SW params JSON).
        job_id:        Unique integer job identifier (should match Ax trial index).
        host:          EDA Server hostname or IP.
        port:          EDA Server TCP port.
        poll_interval: Seconds between status poll requests.
        timeout:       Maximum seconds to wait before declaring failure.
        hex_data:      Optional dict with keys "inputs", "labels", "weights"
                       (plaintext hex strings). When provided (Path 3 only),
                       the server writes these to hardware/data/ before running
                       VCS simulation. Set to None for Path 2 (synthesis only).

    Returns:
        A dict with at minimum:
          {"status": "success", "metrics": { ... }}
        or
          {"status": "error" | "timeout" | "timing_violated", "reason": "..."}

    Raises:
        EDAClientError: On network-level failures (cannot connect, protocol error).
    """
    # Step 1: Submit the task (include hex_data payload only when provided)
    submit_payload: Dict[str, Any] = {
        "action": "submit",
        "job_id": job_id,
        "params": params,
    }
    if hex_data is not None:
        submit_payload["hex_data"] = hex_data
        logger.info(
            f"[Job {job_id}] Attaching hex_data payload "
            f"(inputs={len(hex_data.get('inputs',''))} chars, "
            f"labels={len(hex_data.get('labels',''))} chars, "
            f"weights={len(hex_data.get('weights',''))} chars)."
        )
    try:
        submit_response = _send_and_receive(
            host, port, submit_payload, connect_timeout=SOCKET_CONNECT_TIMEOUT_S
        )
    except (OSError, socket.timeout) as exc:
        raise EDAClientError(f"Cannot connect to EDA Server at {host}:{port}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EDAClientError(f"Malformed response from EDA Server on submit: {exc}") from exc

    if submit_response.get("status") not in ("accepted", "queued"):
        return {
            "status": "error",
            "reason": f"Server rejected submit: {submit_response}",
        }

    logger.info(f"[Job {job_id}] Accepted by EDA Server. Starting to poll every {poll_interval}s.")

    # Step 2: Poll for completion
    deadline = time.monotonic() + timeout
    poll_payload = {"action": "status", "job_id": job_id}

    while time.monotonic() < deadline:
        time.sleep(poll_interval)

        try:
            status_response = _send_and_receive(
                host, port, poll_payload, connect_timeout=SOCKET_CONNECT_TIMEOUT_S
            )
        except (OSError, socket.timeout) as exc:
            logger.warning(f"[Job {job_id}] Poll connection error (retrying): {exc}")
            continue
        except json.JSONDecodeError as exc:
            logger.warning(f"[Job {job_id}] Malformed poll response (retrying): {exc}")
            continue

        job_status = status_response.get("status", "unknown")
        logger.debug(f"[Job {job_id}] Status: {job_status}")

        if job_status in ("queued", "running"):
            continue

        # Terminal states
        if job_status == "success":
            logger.info(f"[Job {job_id}] Completed successfully.")
            return status_response

        if job_status in ("error", "timeout", "timing_violated"):
            reason = status_response.get("reason", job_status)
            logger.warning(f"[Job {job_id}] Terminal failure — status={job_status}, reason={reason}")
            return status_response

        logger.warning(f"[Job {job_id}] Unknown status: {job_status!r}")

    # Client-side timeout reached
    logger.error(f"[Job {job_id}] Client-side timeout after {timeout}s. Treating as failed.")
    return {
        "status": "timeout",
        "reason": f"Client-side timeout after {timeout}s with no terminal result.",
    }
