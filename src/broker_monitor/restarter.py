from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


@dataclass
class ServiceInfo:
    address: str
    slave_number: int
    service_name: str


def resolve_service(
    address: str,
    pattern: str,
    slave_min: int,
    slave_max: int,
) -> ServiceInfo | None:
    """Maps an IP:port address to a Windows service name using the port-to-slave formula."""
    parts = address.split(":")
    if len(parts) < 2:
        return None

    try:
        port = int(parts[1])
    except ValueError:
        return None

    slave_num = port - 10000
    if not (slave_min <= slave_num <= slave_max):
        return None

    return ServiceInfo(
        address=address,
        slave_number=slave_num,
        service_name=pattern.format(slave_num),
    )


def get_service_state(service_name: str) -> str:
    result = subprocess.run(
        ["sc", "query", service_name],
        capture_output=True,
        text=True,
    )
    if "RUNNING" in result.stdout:
        return "RUNNING"
    if "STOPPED" in result.stdout:
        return "STOPPED"
    return "UNKNOWN"


def restart_service(service_name: str, start_timeout: int) -> tuple[bool, str]:
    """
    Stops and starts a Windows service via sc.exe.
    Returns (success, description).
    Error code 1062 means the service was already stopped -- treated as OK.
    """
    stop = subprocess.run(
        ["sc", "stop", service_name],
        capture_output=True,
        text=True,
    )
    if stop.returncode not in (0, 1062):
        return False, f"sc stop falhou (rc={stop.returncode}): {stop.stderr.strip()}"

    time.sleep(2)

    start = subprocess.run(
        ["sc", "start", service_name],
        capture_output=True,
        text=True,
    )
    if start.returncode != 0:
        return False, f"sc start falhou (rc={start.returncode}): {start.stderr.strip()}"

    for _ in range(start_timeout):
        if get_service_state(service_name) == "RUNNING":
            return True, "RUNNING"
        time.sleep(1)

    final = get_service_state(service_name)
    return False, f"Timeout aguardando RUNNING -- estado final: {final}"
