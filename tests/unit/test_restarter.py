from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from broker_monitor.config import SlaveConfig
from broker_monitor.restarter import (
    ServiceInfo,
    _get_service_state_systemd,
    _get_service_state_windows,
    _restart_service_systemd,
    _restart_service_windows,
    get_service_state,
    resolve_service,
    restart_service,
)

PORT_MAP = {
    10001: SlaveConfig(port=10001, service_name="TestSlv01PRD"),
    10002: SlaveConfig(port=10002, service_name="TestSlv02PRD"),
    10003: SlaveConfig(port=10003, service_name="TestSlv03PRD"),
}

CLUSTER_PORT_MAP = {
    10001: SlaveConfig(port=10001, resource_name="Totvs AppServer Slv01 PRD", role="ROLE_A"),
    10002: SlaveConfig(port=10002, resource_name="Totvs AppServer Slv02 PRD", role="ROLE_A"),
}


class TestServiceInfo:
    def test_display_name_uses_service_name(self):
        info = ServiceInfo("10.0.0.1:10001", 10001, service_name="MySvc")
        assert info.display_name == "MySvc"

    def test_display_name_uses_resource_name(self):
        info = ServiceInfo("10.0.0.1:10001", 10001, resource_name="My Resource")
        assert info.display_name == "My Resource"

    def test_display_name_resource_takes_priority(self):
        info = ServiceInfo("10.0.0.1:10001", 10001, service_name="Svc", resource_name="Resource")
        assert info.display_name == "Resource"

    def test_display_name_fallback(self):
        info = ServiceInfo("10.0.0.1:10001", 10001)
        assert info.display_name == "port:10001"


class TestResolveService:
    def test_valid_address_standard(self):
        info = resolve_service("10.0.0.1:10002", PORT_MAP)
        assert info is not None
        assert info.port == 10002
        assert info.service_name == "TestSlv02PRD"
        assert info.address == "10.0.0.1:10002"

    def test_valid_address_cluster(self):
        info = resolve_service("10.0.0.1:10001", CLUSTER_PORT_MAP)
        assert info is not None
        assert info.resource_name == "Totvs AppServer Slv01 PRD"
        assert info.role == "ROLE_A"

    def test_unmapped_port_returns_none(self):
        assert resolve_service("10.0.0.1:9999", PORT_MAP) is None

    def test_invalid_port_returns_none(self):
        assert resolve_service("10.0.0.1:abc", PORT_MAP) is None

    def test_missing_port_returns_none(self):
        assert resolve_service("10.0.0.1", PORT_MAP) is None

    def test_empty_map_returns_none(self):
        assert resolve_service("10.0.0.1:10001", {}) is None


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Platform dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_restart_dispatches_to_windows(self):
        with patch("broker_monitor.restarter._is_windows", return_value=True), \
             patch("broker_monitor.restarter._restart_service_windows", return_value=(True, "RUNNING")) as win, \
             patch("broker_monitor.restarter._restart_service_systemd") as lin:
            assert restart_service("Svc", 5) == (True, "RUNNING")
            win.assert_called_once()
            lin.assert_not_called()

    def test_restart_dispatches_to_systemd(self):
        with patch("broker_monitor.restarter._is_windows", return_value=False), \
             patch("broker_monitor.restarter._restart_service_systemd", return_value=(True, "RUNNING")) as lin, \
             patch("broker_monitor.restarter._restart_service_windows") as win:
            assert restart_service("Svc", 5) == (True, "RUNNING")
            lin.assert_called_once()
            win.assert_not_called()

    def test_state_dispatches_to_systemd(self):
        with patch("broker_monitor.restarter._is_windows", return_value=False), \
             patch("broker_monitor.restarter._get_service_state_systemd", return_value="RUNNING") as lin:
            assert get_service_state("Svc") == "RUNNING"
            lin.assert_called_once()


# ---------------------------------------------------------------------------
# Windows backend (sc.exe)
# ---------------------------------------------------------------------------

class TestWindowsState:
    def test_running(self):
        with patch("broker_monitor.restarter.subprocess.run", return_value=_make_proc(stdout="STATE: RUNNING")):
            assert _get_service_state_windows("SomeService") == "RUNNING"

    def test_stopped(self):
        with patch("broker_monitor.restarter.subprocess.run", return_value=_make_proc(stdout="STATE: STOPPED")):
            assert _get_service_state_windows("SomeService") == "STOPPED"

    def test_unknown(self):
        with patch("broker_monitor.restarter.subprocess.run", return_value=_make_proc(stdout="SERVICE_NAME: x")):
            assert _get_service_state_windows("SomeService") == "UNKNOWN"


class TestWindowsRestart:
    def test_successful_restart(self):
        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[_make_proc(0), _make_proc(0), _make_proc(0, "STATE: RUNNING")]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_windows("TestSvc", start_timeout=5)
        assert ok is True
        assert state == "RUNNING"

    def test_already_stopped_service(self):
        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[_make_proc(1062), _make_proc(0), _make_proc(0, "STATE: RUNNING")]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, _ = _restart_service_windows("TestSvc", start_timeout=5)
        assert ok is True

    def test_stop_fails(self):
        with patch("broker_monitor.restarter.subprocess.run", return_value=_make_proc(1, stderr="Access denied")), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_windows("TestSvc", start_timeout=5)
        assert ok is False
        assert "sc stop falhou" in state

    def test_start_fails(self):
        with patch("broker_monitor.restarter.subprocess.run", side_effect=[_make_proc(0), _make_proc(1)]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_windows("TestSvc", start_timeout=5)
        assert ok is False
        assert "sc start falhou" in state

    def test_timeout_waiting_for_running(self):
        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[_make_proc(0), _make_proc(0)] + [_make_proc(0, "STATE: STOPPED")] * 10), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_windows("TestSvc", start_timeout=3)
        assert ok is False
        assert "Timeout" in state


# ---------------------------------------------------------------------------
# Linux backend (systemctl)
# ---------------------------------------------------------------------------

class TestSystemdState:
    @pytest.mark.parametrize("active_out,expected", [
        ("active", "RUNNING"),
        ("inactive", "STOPPED"),
        ("failed", "STOPPED"),
        ("deactivating", "STOPPED"),
        ("activating", "UNKNOWN"),
        ("unknown", "UNKNOWN"),
    ])
    def test_state_mapping(self, active_out, expected):
        with patch("broker_monitor.restarter.subprocess.run", return_value=_make_proc(stdout=active_out + "\n")):
            assert _get_service_state_systemd("appserver_slave01") == expected


class TestSystemdRestart:
    def test_successful_restart(self):
        # restart ok, then is-active -> active
        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[_make_proc(0), _make_proc(0, "active")]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_systemd("appserver_slave01", start_timeout=5)
        assert ok is True
        assert state == "RUNNING"

    def test_restart_command_fails(self):
        with patch("broker_monitor.restarter.subprocess.run",
                   return_value=_make_proc(1, stderr="Unit appserver_slave01.service not found.")), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_systemd("appserver_slave01", start_timeout=5)
        assert ok is False
        assert "systemctl restart falhou" in state

    def test_timeout_waiting_for_active(self):
        # restart ok, but never becomes active within timeout
        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[_make_proc(0)] + [_make_proc(0, "activating")] * 10), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = _restart_service_systemd("appserver_slave01", start_timeout=3)
        assert ok is False
        assert "Timeout" in state
