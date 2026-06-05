from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from broker_monitor.config import SlaveConfig
from broker_monitor.restarter import (
    ServiceInfo,
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


class TestGetServiceState:
    def test_running(self):
        result = MagicMock()
        result.stdout = "STATE: RUNNING"
        with patch("broker_monitor.restarter.subprocess.run", return_value=result):
            assert get_service_state("SomeService") == "RUNNING"

    def test_stopped(self):
        result = MagicMock()
        result.stdout = "STATE: STOPPED"
        with patch("broker_monitor.restarter.subprocess.run", return_value=result):
            assert get_service_state("SomeService") == "STOPPED"

    def test_unknown(self):
        result = MagicMock()
        result.stdout = "SERVICE_NAME: SomeService"
        with patch("broker_monitor.restarter.subprocess.run", return_value=result):
            assert get_service_state("SomeService") == "UNKNOWN"


class TestRestartService:
    def _make_proc(self, returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_successful_restart(self):
        stop_ok  = self._make_proc(0)
        start_ok = self._make_proc(0)
        running  = self._make_proc(0, "STATE: RUNNING")

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_ok, running]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is True
        assert state == "RUNNING"

    def test_already_stopped_service(self):
        stop_already = self._make_proc(1062)
        start_ok     = self._make_proc(0)
        running      = self._make_proc(0, "STATE: RUNNING")

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_already, start_ok, running]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, _ = restart_service("TestSvc", start_timeout=5)

        assert ok is True

    def test_stop_fails(self):
        stop_fail = self._make_proc(1, stderr="Access denied")

        with patch("broker_monitor.restarter.subprocess.run", return_value=stop_fail), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is False
        assert "sc stop falhou" in state

    def test_start_fails(self):
        stop_ok    = self._make_proc(0)
        start_fail = self._make_proc(1)

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_fail]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is False
        assert "sc start falhou" in state

    def test_timeout_waiting_for_running(self):
        stop_ok     = self._make_proc(0)
        start_ok    = self._make_proc(0)
        not_running = self._make_proc(0, "STATE: STOPPED")

        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[stop_ok, start_ok] + [not_running] * 10), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=3)

        assert ok is False
        assert "Timeout" in state
