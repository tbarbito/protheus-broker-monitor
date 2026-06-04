from __future__ import annotations

import json
from pathlib import Path

import pytest

from broker_monitor.config import Config, EmailConfig, SlaveRange, load_config


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

    def test_slave_range(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert cfg.slave_range.min == 1
        assert cfg.slave_range.max == 7

    def test_email_config(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert cfg.email.enabled is False
        assert cfg.email.smtp_server == "smtp.test.com"
        assert cfg.email.smtp_port == 587
        assert cfg.email.to_addrs == ["admin@test.com"]

    def test_defaults(self, tmp_path):
        minimal = {"brokerUrl": "http://host:10000/status"}
        cfg = load_config(_write(tmp_path, minimal))
        assert cfg.log_retention_days == 7
        assert cfg.auto_restart is True
        assert cfg.start_timeout_seconds == 60
        assert cfg.slave_range.min == 1
        assert cfg.slave_range.max == 7
        assert cfg.email.enabled is False

    def test_service_name_pattern(self, tmp_path, config_data):
        cfg = load_config(_write(tmp_path, config_data))
        assert cfg.service_name_pattern == "TestSlv{:02d}PRD"
        assert cfg.service_name_pattern.format(3) == "TestSlv03PRD"

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
