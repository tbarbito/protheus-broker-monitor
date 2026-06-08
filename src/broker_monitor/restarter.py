from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass

from .config import SlaveConfig


@dataclass
class ServiceInfo:
    address: str
    port: int
    service_name: str | None = None      # standard mode
    resource_name: str | None = None     # cluster mode
    role: str | None = None              # cluster mode

    @property
    def display_name(self) -> str:
        """Human-readable identifier regardless of mode."""
        return self.resource_name or self.service_name or f"port:{self.port}"


def resolve_service(address: str, port_map: dict[int, SlaveConfig]) -> ServiceInfo | None:
    """
    Maps an IP:port address to a ServiceInfo using the explicit port map
    defined in config.json. Returns None if the port is not mapped.
    Works for both standard (serviceName) and cluster (resourceName/role) modes.
    """
    parts = address.split(":")
    if len(parts) < 2:
        return None

    try:
        port = int(parts[1])
    except ValueError:
        return None

    slave = port_map.get(port)
    if not slave:
        return None

    return ServiceInfo(
        address=address,
        port=port,
        service_name=slave.service_name,
        resource_name=slave.resource_name,
        role=slave.role,
    )


# ---------------------------------------------------------------------------
# Public dispatch -- selects the backend at runtime based on the host OS.
#
# Windows -> sc.exe (Service Control Manager)
# Linux   -> systemctl (systemd)
#
# The standard (non-cluster) mode works on both platforms. The cluster mode
# (cluster_restarter.py) relies on Windows Failover Clustering and is therefore
# Windows-only; the CLI blocks cluster.enabled on non-Windows hosts.
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return sys.platform == "win32"


def get_service_state(service_name: str) -> str:
    """Returns RUNNING / STOPPED / UNKNOWN for the given service/unit."""
    if _is_windows():
        return _get_service_state_windows(service_name)
    return _get_service_state_systemd(service_name)


def restart_service(service_name: str, start_timeout: int) -> tuple[bool, str]:
    """
    Stops and starts a service, then waits until it reaches RUNNING.
    Returns (success, description). Dispatches to the platform backend.
    """
    if _is_windows():
        return _restart_service_windows(service_name, start_timeout)
    return _restart_service_systemd(service_name, start_timeout)


# ---------------------------------------------------------------------------
# Windows backend -- sc.exe
# ---------------------------------------------------------------------------

def _get_service_state_windows(service_name: str) -> str:
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


def _restart_service_windows(service_name: str, start_timeout: int) -> tuple[bool, str]:
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
        if _get_service_state_windows(service_name) == "RUNNING":
            return True, "RUNNING"
        time.sleep(1)

    final = _get_service_state_windows(service_name)
    return False, f"Timeout aguardando RUNNING -- estado final: {final}"


# ---------------------------------------------------------------------------
# Linux backend -- systemctl (systemd)
#
# O AppServer Protheus precisa estar registrado como uma unit systemd, ex:
#   /etc/systemd/system/appserver_slave01.service
# Nesse cenario o campo "serviceName" do config.json deve conter o nome da
# unit (ex: "appserver_slave01" ou "appserver_slave01.service").
#
# O processo que executa o monitor precisa de permissao para reiniciar a unit
# (rodar como root, ou via regra sudoers/polkit para "systemctl restart").
# ---------------------------------------------------------------------------

def _get_service_state_systemd(service_name: str) -> str:
    """
    Uses `systemctl is-active`. Possible stdout values: active, inactive,
    failed, activating, deactivating, unknown.
    """
    result = subprocess.run(
        ["systemctl", "is-active", service_name],
        capture_output=True,
        text=True,
    )
    state = result.stdout.strip()
    if state == "active":
        return "RUNNING"
    if state in ("inactive", "failed", "deactivating"):
        return "STOPPED"
    return "UNKNOWN"


def _restart_service_systemd(service_name: str, start_timeout: int) -> tuple[bool, str]:
    """
    Restarts a systemd unit via `systemctl restart` (stop+start atomic),
    then waits until it reports `active`. Returns (success, description).
    """
    restart = subprocess.run(
        ["systemctl", "restart", service_name],
        capture_output=True,
        text=True,
    )
    if restart.returncode != 0:
        return False, f"systemctl restart falhou (rc={restart.returncode}): {restart.stderr.strip()}"

    for _ in range(start_timeout):
        if _get_service_state_systemd(service_name) == "RUNNING":
            return True, "RUNNING"
        time.sleep(1)

    final = _get_service_state_systemd(service_name)
    return False, f"Timeout aguardando active -- estado final: {final}"
