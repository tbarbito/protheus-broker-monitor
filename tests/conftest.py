"""Shared fixtures for unit and E2E tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# HTML fixtures that simulate the Protheus Broker status page
# ---------------------------------------------------------------------------

_ROW = """
<tr>
  <td><a href="/path/ServerStatus/{ip}:{port}">{ip}:{port}</a></td>
  <td>Active</td>
  <td>{quarantine}</td>
</tr>
"""


def make_broker_html(slaves: list[dict]) -> str:
    """
    slaves: list of dicts with keys: ip, port, quarantine ("-" means OK).
    """
    rows = "".join(
        _ROW.format(ip=s["ip"], port=s["port"], quarantine=s.get("quarantine", "-"))
        for s in slaves
    )
    return f"<html><body><table>{rows}</table></body></html>"


BROKER_HTML_ALL_OK = make_broker_html([
    {"ip": "10.0.0.1", "port": 10001, "quarantine": "-"},
    {"ip": "10.0.0.1", "port": 10002, "quarantine": "-"},
    {"ip": "10.0.0.1", "port": 10003, "quarantine": "-"},
])

BROKER_HTML_ONE_QUARANTINED = make_broker_html([
    {"ip": "10.0.0.1", "port": 10001, "quarantine": "-"},
    {"ip": "10.0.0.1", "port": 10002, "quarantine": "QUARANTINE_TIMEOUT"},
    {"ip": "10.0.0.1", "port": 10003, "quarantine": "-"},
])

BROKER_HTML_ALL_QUARANTINED = make_broker_html([
    {"ip": "10.0.0.1", "port": 10001, "quarantine": "QUARANTINE_TIMEOUT"},
    {"ip": "10.0.0.1", "port": 10002, "quarantine": "QUARANTINE_TIMEOUT"},
])

BROKER_HTML_EMPTY = "<html><body><table></table></body></html>"


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "brokerUrl": "http://test-server:10000/totvs_broker_query/status",
    "logDir": "",
    "logRetentionDays": 7,
    "autoRestart": True,
    "startTimeoutSeconds": 5,
    "serviceNamePattern": "TestSlv{:02d}PRD",
    "slaveRange": {"min": 1, "max": 7},
    "email": {
        "enabled": False,
        "smtpServer": "smtp.test.com",
        "smtpPort": 587,
        "useSSL": False,
        "from": "monitor@test.com",
        "to": ["admin@test.com"],
        "username": "monitor@test.com",
        "password": "secret",
    },
}


@pytest.fixture
def config_data(tmp_path):
    data = dict(_BASE_CONFIG)
    data["logDir"] = str(tmp_path / "logs")
    return data


@pytest.fixture
def config_file(tmp_path, config_data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config_data), encoding="utf-8")
    return path


@pytest.fixture
def config_obj(config_file):
    from broker_monitor.config import load_config
    return load_config(config_file)
