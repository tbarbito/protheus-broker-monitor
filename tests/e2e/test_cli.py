"""E2E tests for the broker-monitor CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from typer.testing import CliRunner

from broker_monitor import __version__
from broker_monitor.cli import app
from tests.conftest import (
    BROKER_HTML_ALL_OK,
    BROKER_HTML_ALL_QUARANTINED,
    BROKER_HTML_ONE_QUARANTINED,
)

runner = CliRunner()


def _mock_response(html: str) -> MagicMock:
    m = MagicMock()
    m.text = html
    m.raise_for_status.return_value = None
    return m


def _mock_sc_ok(returncode: int = 0, stdout: str = "STATE: RUNNING") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


class TestVersionFlag:
    def test_shows_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestRunCommand:
    def test_missing_config_exits_1(self, tmp_path):
        result = runner.invoke(app, ["run", "--config", str(tmp_path / "nope.json")])
        assert result.exit_code == 1

    def test_broker_ok_exits_0(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ALL_OK)
        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            result = runner.invoke(app, ["run", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "Nenhum slave em quarentena" in result.output

    def test_broker_unreachable_exits_1(self, config_file):
        with patch("broker_monitor.monitor.requests.get", side_effect=requests.ConnectionError()):
            result = runner.invoke(app, ["run", "--config", str(config_file)])
        assert result.exit_code == 1
        assert "inacessivel" in result.output.lower()

    def test_quarantined_triggers_restart(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ONE_QUARANTINED)
        stop_ok   = _mock_sc_ok(0, "STATE: STOPPED")
        start_ok  = _mock_sc_ok(0)
        running   = _mock_sc_ok(0, "STATE: RUNNING")

        with patch("broker_monitor.restarter._is_windows", return_value=True), \
             patch("broker_monitor.monitor.requests.get", return_value=mock_resp), \
             patch("broker_monitor.restarter.subprocess.run", side_effect=[stop_ok, start_ok, running]), \
             patch("broker_monitor.restarter.time.sleep"):
            result = runner.invoke(app, ["run", "--config", str(config_file)])

        assert "Reiniciando" in result.output
        assert "OK" in result.output

    def test_dry_run_skips_restart(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ONE_QUARANTINED)
        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp), \
             patch("broker_monitor.restarter.subprocess.run") as mock_sc:
            result = runner.invoke(app, ["run", "--config", str(config_file), "--dry-run"])

        assert result.exit_code == 0
        mock_sc.assert_not_called()
        assert "dry-run" in result.output.lower()

    def test_failed_restart_exits_1(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ONE_QUARANTINED)
        fail_sc   = _mock_sc_ok(1)

        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp), \
             patch("broker_monitor.restarter.subprocess.run", return_value=fail_sc), \
             patch("broker_monitor.restarter.time.sleep"):
            result = runner.invoke(app, ["run", "--config", str(config_file)])

        assert result.exit_code == 1
        assert "FALHOU" in result.output

    def test_all_quarantined_all_restarted(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ALL_QUARANTINED)
        stop_ok  = _mock_sc_ok(0, "STATE: STOPPED")
        start_ok = _mock_sc_ok(0)
        running  = _mock_sc_ok(0, "STATE: RUNNING")

        with patch("broker_monitor.restarter._is_windows", return_value=True), \
             patch("broker_monitor.monitor.requests.get", return_value=mock_resp), \
             patch("broker_monitor.restarter.subprocess.run",
                   side_effect=[stop_ok, start_ok, running, stop_ok, start_ok, running]), \
             patch("broker_monitor.restarter.time.sleep"):
            result = runner.invoke(app, ["run", "--config", str(config_file)])

        assert "Reiniciados: 2" in result.output


class TestClusterGuard:
    def test_cluster_blocked_on_non_windows(self, tmp_path, config_data):
        config_data["cluster"] = {"enabled": True, "name": "MyCluster", "stopTimeoutSeconds": 60}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("broker_monitor.cli.sys.platform", "linux"):
            result = runner.invoke(app, ["run", "--config", str(path)])

        assert result.exit_code == 1
        assert "cluster" in result.output.lower()

    def test_cluster_allowed_on_windows(self, tmp_path, config_data):
        config_data["cluster"] = {"enabled": True, "name": "MyCluster", "stopTimeoutSeconds": 60}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config_data), encoding="utf-8")

        mock_resp = _mock_response(BROKER_HTML_ALL_OK)
        with patch("broker_monitor.cli.sys.platform", "win32"), \
             patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            result = runner.invoke(app, ["run", "--config", str(path)])

        # Broker sem quarentena -> nao tenta cluster, apenas conclui sem ser bloqueado
        assert result.exit_code == 0


class TestCheckCommand:
    def test_all_ok(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ALL_OK)
        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            result = runner.invoke(app, ["check", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_shows_quarantined(self, config_file):
        mock_resp = _mock_response(BROKER_HTML_ONE_QUARANTINED)
        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            result = runner.invoke(app, ["check", "--config", str(config_file)])
        assert result.exit_code == 1
        assert "QUARANTINE_TIMEOUT" in result.output

    def test_broker_unreachable(self, config_file):
        with patch("broker_monitor.monitor.requests.get", side_effect=requests.ConnectionError()):
            result = runner.invoke(app, ["check", "--config", str(config_file)])
        assert result.exit_code == 1
