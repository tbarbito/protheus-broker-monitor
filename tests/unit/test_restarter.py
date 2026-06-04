from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from broker_monitor.restarter import (
    ServiceInfo,
    get_service_state,
    resolve_service,
    restart_service,
)

PORT_MAP = {
    10001: "TestSlv01PRD",
    10002: "TestSlv02PRD",
    10003: "TestSlv03PRD",
}


class TestResolveService:
    def test_valid_address(self):
        info = resolve_service("10.0.0.1:10002", PORT_MAP)
        assert info is not None
        assert info.port == 10002
        assert info.service_name == "TestSlv02PRD"
        assert info.address == "10.0.0.1:10002"

    def test_first_and_last_port(self):
        assert resolve_service("10.0.0.1:10001", PORT_MAP) is not None
        assert resolve_service("10.0.0.1:10003", PORT_MAP) is not None

    def test_unmapped_port_returns_none(self):
        assert resolve_service("10.0.0.1:9999", PORT_MAP) is None

    def test_invalid_port_returns_none(self):
        assert resolve_service("10.0.0.1:abc", PORT_MAP) is None

    def test_missing_port_returns_none(self):
        assert resolve_service("10.0.0.1", PORT_MAP) is None

    def test_empty_map_returns_none(self):
        assert resolve_service("10.0.0.1:10001", {}) is None

    def test_custom_non_sequential_ports(self):
        custom_map = {9001: "AppServer_A", 9005: "AppServer_B"}
        info = resolve_service("192.168.1.10:9005", custom_map)
        assert info is not None
        assert info.service_name == "AppServer_B"


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
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is True

    def test_stop_fails(self):
        stop_fail = self._make_proc(1, stderr="Access denied")

        with patch("broker_monitor.restarter.subprocess.run", return_value=stop_fail), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is False
        assert "sc stop falhou" in state

    def test_start_fails(self):
        stop_ok   = self._make_proc(0)
        start_fail = self._make_proc(1)

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_fail]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is False
        assert "sc start falhou" in state

    def test_timeout_waiting_for_running(self):
        stop_ok    = self._make_proc(0)
        start_ok   = self._make_proc(0)
        not_running = self._make_proc(0, "STATE: STOPPED")

        with patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[stop_ok, start_ok] + [not_running] * 10), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=3)

        assert ok is False
        assert "Timeout" in state
