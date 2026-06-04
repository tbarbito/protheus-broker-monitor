from __future__ import annotations

import json
from pathlib import Path

import pytest

from broker_monitor.config import Config, EmailConfig, SlaveConfig, load_config


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestLoadConfig:
    def test_required_fields(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert cfg.broker_url == "http://test-server:10000/totvs_broker_query/status"

    def test_log_dir_as_path(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert isinstance(cfg.log_dir, Path)

    def test_slaves_loaded(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert len(cfg.slaves) == 3
        assert cfg.slaves[0].port == 10001
        assert cfg.slaves[0].service_name == "TestSlv01PRD"

    def test_slave_port_map(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        m = cfg.slave_port_map
        assert m[10001] == "TestSlv01PRD"
        assert m[10002] == "TestSlv02PRD"
        assert m[10003] == "TestSlv03PRD"

    def test_slaves_empty_by_default(self, tmp_path):
        cfg = load_config(_write(tmp_path, {"brokerUrl": "http://host/status"}))
        assert cfg.slaves == []
        assert cfg.slave_port_map == {}

    def test_email_config(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert cfg.email.enabled is False
        assert cfg.email.smtp_server == "smtp.test.com"
        assert cfg.email.smtp_port == 587
        assert cfg.email.to_addrs == ["admin@test.com"]

    def test_defaults(self, tmp_path):
        cfg = load_config(_write(tmp_path, {"brokerUrl": "http://host/status"}))
        assert cfg.log_retention_days == 7
        assert cfg.auto_restart is True
        assert cfg.start_timeout_seconds == 60
        assert cfg.email.enabled is False

    def test_custom_ports_and_service_names(self, tmp_path):
        data = {
            "brokerUrl": "http://host:9999/status",
            "slaves": [
                {"port": 9001, "serviceName": "MeuServico_A"},
                {"port": 9002, "serviceName": "MeuServico_B"},
            ],
        }
        cfg = load_config(_write(tmp_path, data))
        assert cfg.slave_port_map[9001] == "MeuServico_A"
        assert cfg.slave_port_map[9002] == "MeuServico_B"

    def test_missing_required_field_raises(self, tmp_path):
        with pytest.raises(KeyError):
            load_config(_write(tmp_path, {}))

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nao_existe.json")

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("{ invalido", encoding="utf-8")
        with pytest.raises(Exception):
            load_config(p)
