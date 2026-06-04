from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


@dataclass
class ServiceInfo:
    address: str
    port: int
    service_name: str


def resolve_service(address: str, port_map: dict[int, str]) -> ServiceInfo | None:
    """
    Maps an IP:port address to a Windows service name using the explicit port map
    defined in config.json. Returns None if the port is not mapped.
    """
    parts = address.split(":")
    if len(parts) < 2:
        return None

    try:
        port = int(parts[1])
    except ValueError:
        return None

    service_name = port_map.get(port)
    if not service_name:
        return None

    return ServiceInfo(address=address, port=port, service_name=service_name)


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
