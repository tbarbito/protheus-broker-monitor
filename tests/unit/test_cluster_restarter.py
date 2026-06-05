"""Unit tests for cluster_restarter (Windows Failover Cluster mode)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from broker_monitor.cluster_restarter import (
    restart_cluster_slaves,
    start_resource_with_wait,
    stop_resources_parallel,
    taskkill_resource,
)
from broker_monitor.restarter import ServiceInfo

CLUSTER = "TESTCLUSTER"

SLAVE_A = ServiceInfo("10.0.0.1:10001", 10001, resource_name="Totvs AppServer Slv01 PRD", role="ROLE_A")
SLAVE_B = ServiceInfo("10.0.0.1:10002", 10002, resource_name="Totvs AppServer Slv02 PRD", role="ROLE_A")


def _ps_ok(stdout: str = "") -> tuple[int, str, str]:
    return (0, stdout, "")


def _ps_fail(stderr: str = "error") -> tuple[int, str, str]:
    return (1, "", stderr)


class TestStopResourcesParallel:
    def test_stops_all_resources(self):
        with patch("broker_monitor.cluster_restarter._run_ps", return_value=_ps_ok()):
            results = stop_resources_parallel(CLUSTER, ["Res01", "Res02"])

        assert results["Res01"] == (True, "")
        assert results["Res02"] == (True, "")

    def test_failed_stop_returns_false(self):
        with patch("broker_monitor.cluster_restarter._run_ps", return_value=_ps_fail("denied")):
            results = stop_resources_parallel(CLUSTER, ["Res01"])

        assert results["Res01"][0] is False

    def test_empty_list_returns_empty(self):
        results = stop_resources_parallel(CLUSTER, [])
        assert results == {}


class TestTaskkillResource:
    def test_success(self):
        with patch("broker_monitor.cluster_restarter._run_ps", return_value=_ps_ok()):
            assert taskkill_resource(CLUSTER, "Res01") is True

    def test_failure(self):
        with patch("broker_monitor.cluster_restarter._run_ps", return_value=_ps_fail()):
            assert taskkill_resource(CLUSTER, "Res01") is False


class TestStartResourceWithWait:
    def test_already_online(self):
        with patch("broker_monitor.cluster_restarter._run_ps", return_value=_ps_ok("Online")):
            ok, state = start_resource_with_wait(CLUSTER, "Res01", start_timeout=10)
        assert ok is True
        assert "already" in state

    def test_starts_and_reaches_online(self):
        responses = [
            _ps_ok("Offline"),   # initial state check
            _ps_ok(""),          # Start-ClusterResource
            _ps_ok("Online"),    # wait loop
        ]
        with patch("broker_monitor.cluster_restarter._run_ps", side_effect=responses), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            ok, state = start_resource_with_wait(CLUSTER, "Res01", start_timeout=10)

        assert ok is True
        assert "Online" in state

    def test_reaches_failed_state(self):
        responses = [
            _ps_ok("Offline"),
            _ps_ok(""),
            _ps_ok("Failed"),
        ]
        with patch("broker_monitor.cluster_restarter._run_ps", side_effect=responses), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            ok, state = start_resource_with_wait(CLUSTER, "Res01", start_timeout=10)

        assert ok is False
        assert "Failed" in state

    def test_start_command_fails(self):
        responses = [
            _ps_ok("Offline"),
            _ps_fail("permission denied"),
        ]
        with patch("broker_monitor.cluster_restarter._run_ps", side_effect=responses), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            ok, state = start_resource_with_wait(CLUSTER, "Res01", start_timeout=10)

        assert ok is False
        assert "Start-ClusterResource falhou" in state

    def test_timeout(self):
        responses = [_ps_ok("Offline"), _ps_ok("")] + [_ps_ok("Pending")] * 20
        with patch("broker_monitor.cluster_restarter._run_ps", side_effect=responses), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            ok, state = start_resource_with_wait(CLUSTER, "Res01", start_timeout=4)

        assert ok is False
        assert "Timeout" in state


class TestRestartClusterSlaves:
    def test_all_restarted(self):
        with patch("broker_monitor.cluster_restarter.stop_resources_parallel",
                   return_value={"Totvs AppServer Slv01 PRD": (True, ""),
                                 "Totvs AppServer Slv02 PRD": (True, "")}), \
             patch("broker_monitor.cluster_restarter.taskkill_resource", return_value=True), \
             patch("broker_monitor.cluster_restarter.start_resource_with_wait",
                   return_value=(True, "Online (2s)")), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            restarted, failed = restart_cluster_slaves(CLUSTER, [SLAVE_A, SLAVE_B], 60, 60)

        assert len(restarted) == 2
        assert len(failed) == 0

    def test_partial_failure(self):
        def _start(cluster, name, timeout):
            return (True, "Online") if "Slv01" in name else (False, "Failed")

        with patch("broker_monitor.cluster_restarter.stop_resources_parallel",
                   return_value={"Totvs AppServer Slv01 PRD": (True, ""),
                                 "Totvs AppServer Slv02 PRD": (True, "")}), \
             patch("broker_monitor.cluster_restarter.taskkill_resource", return_value=True), \
             patch("broker_monitor.cluster_restarter.start_resource_with_wait", side_effect=_start), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            restarted, failed = restart_cluster_slaves(CLUSTER, [SLAVE_A, SLAVE_B], 60, 60)

        assert len(restarted) == 1
        assert len(failed) == 1
        assert restarted[0].resource_name == "Totvs AppServer Slv01 PRD"

    def test_slave_without_resource_name_goes_to_failed(self):
        no_resource = ServiceInfo("10.0.0.1:10005", 10005, service_name="Svc05")

        with patch("broker_monitor.cluster_restarter.stop_resources_parallel", return_value={}), \
             patch("broker_monitor.cluster_restarter.taskkill_resource", return_value=True), \
             patch("broker_monitor.cluster_restarter.start_resource_with_wait",
                   return_value=(True, "Online")), \
             patch("broker_monitor.cluster_restarter.time.sleep"):
            restarted, failed = restart_cluster_slaves(CLUSTER, [no_resource], 60, 60)

        assert len(restarted) == 0
        assert len(failed) == 1
