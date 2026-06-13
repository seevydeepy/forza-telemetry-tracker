"""Helpers for detecting and resolving Windows port conflicts."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PortBinding:
    """A local port the tracker needs before it can start."""

    protocol: str
    host: str
    port: int
    label: str


@dataclass(frozen=True)
class ProcessConflict:
    """A running process that already owns a required local port."""

    binding: PortBinding
    pid: int
    process_name: str = ""
    executable_path: str = ""
    command_line: str = ""


def _run_powershell_json(script: str) -> list[dict]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _query_windows_port_owners(binding: PortBinding) -> list[dict]:
    cmdlet = "Get-NetTCPConnection -State Listen" if binding.protocol.upper() == "TCP" else "Get-NetUDPEndpoint"
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$rows = @()
{cmdlet} -LocalPort {int(binding.port)} | ForEach-Object {{
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
    $rows += [pscustomobject]@{{
        local_address = $_.LocalAddress
        local_port = $_.LocalPort
        pid = $_.OwningProcess
        process_name = $process.Name
        executable_path = $process.ExecutablePath
        command_line = $process.CommandLine
    }}
}}
$rows | ConvertTo-Json -Depth 4 -Compress
"""
    return _run_powershell_json(script)


def _host_matches(requested_host: str, existing_address: str) -> bool:
    requested = (requested_host or "").strip().lower()
    existing = (existing_address or "").strip().lower()
    wildcards = {"", "0.0.0.0", "::", "[::]"}

    if requested in wildcards or existing in wildcards:
        return True
    if requested == existing:
        return True
    if requested == "localhost" and existing in {"127.0.0.1", "::1"}:
        return True
    if existing == "localhost" and requested in {"127.0.0.1", "::1"}:
        return True
    return False


def find_port_conflicts(bindings: list[PortBinding], *, windows_only: bool = True) -> list[ProcessConflict]:
    if windows_only and os.name != "nt":
        return []

    conflicts: list[ProcessConflict] = []
    for binding in bindings:
        for owner in _query_windows_port_owners(binding):
            if not _host_matches(binding.host, str(owner.get("local_address") or "")):
                continue
            pid = int(owner.get("pid") or 0)
            conflicts.append(
                ProcessConflict(
                    binding=binding,
                    pid=pid,
                    process_name=str(owner.get("process_name") or ""),
                    executable_path=str(owner.get("executable_path") or ""),
                    command_line=str(owner.get("command_line") or ""),
                )
            )
    return conflicts


def kill_process_tree(pid: int) -> None:
    if pid <= 0:
        raise RuntimeError(f"Cannot kill invalid owning process PID {pid}.")

    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Failed to kill PID {pid}: {detail}")


def wait_for_bindings_to_clear(bindings: list[PortBinding], timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        conflicts = find_port_conflicts(bindings)
        if not conflicts:
            return
        time.sleep(0.2)

    remaining = find_port_conflicts(bindings)
    if remaining:
        ports = ", ".join(
            f"{conflict.binding.protocol.upper()} {conflict.binding.host}:{conflict.binding.port}"
            f" (PID {conflict.pid})"
            for conflict in remaining
        )
        raise RuntimeError(f"Port conflict remains after killing process(es): {ports}")
