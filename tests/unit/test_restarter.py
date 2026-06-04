from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from broker_monitor.restarter import (
    ServiceInfo,
    get_service_state,
    resolve_service,
    restart_service,
)

PATTERN = "TestSlv{:02d}PRD"


class TestResolveService:
    def test_valid_address(self):
        info = resolve_service("10.0.0.1:10003", PATTERN, 1, 7)
        assert info is not None
        assert info.slave_number == 3
        assert info.service_name == "TestSlv03PRD"
        assert info.address == "10.0.0.1:10003"

    def test_boundary_min(self):
        info = resolve_service("10.0.0.1:10001", PATTERN, 1, 7)
        assert info is not None
        assert info.slave_number == 1

    def test_boundary_max(self):
        info = resolve_service("10.0.0.1:10007", PATTERN, 1, 7)
        assert info is not None
        assert info.slave_number == 7

    def test_below_range_returns_none(self):
        assert resolve_service("10.0.0.1:10000", PATTERN, 1, 7) is None

    def test_above_range_returns_none(self):
        assert resolve_service("10.0.0.1:10008", PATTERN, 1, 7) is None

    def test_invalid_port_returns_none(self):
        assert resolve_service("10.0.0.1:abc", PATTERN, 1, 7) is None

    def test_missing_port_returns_none(self):
        assert resolve_service("10.0.0.1", PATTERN, 1, 7) is None


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
        stop_ok = self._make_proc(0)
        start_ok = self._make_proc(0)
        running = self._make_proc(0, "STATE: RUNNING")

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_ok, running]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is True
        assert state == "RUNNING"

    def test_already_stopped_service(self):
        # Error code 1062 = service not started, should be OK
        stop_already = self._make_proc(1062)
        start_ok = self._make_proc(0)
        running = self._make_proc(0, "STATE: RUNNING")

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
        stop_ok = self._make_proc(0)
        start_fail = self._make_proc(1)

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_fail]), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=5)

        assert ok is False
        assert "sc start falhou" in state

    def test_timeout_waiting_for_running(self):
        stop_ok = self._make_proc(0)
        start_ok = self._make_proc(0)
        not_running = self._make_proc(0, "STATE: STOPPED")

        with patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_ok] + [not_running] * 10), \
             patch("broker_monitor.restarter.time.sleep"):
            ok, state = restart_service("TestSvc", start_timeout=3)

        assert ok is False
        assert "Timeout" in state
