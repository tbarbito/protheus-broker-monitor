from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SlaveConfig:
    port: int
    service_name: str


@dataclass
class EmailConfig:
    enabled: bool
    smtp_server: str
    smtp_port: int
    use_ssl: bool
    from_addr: str
    to_addrs: list[str]
    username: str
    password: str


@dataclass
class Config:
    broker_url: str
    log_dir: Path
    log_retention_days: int
    auto_restart: bool
    start_timeout_seconds: int
    slaves: list[SlaveConfig]
    email: EmailConfig

    @property
    def slave_port_map(self) -> dict[int, str]:
        """Returns a dict mapping port -> service_name for quick lookup."""
        return {s.port: s.service_name for s in self.slaves}


def load_config(path: Path) -> Config:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    em = data.get("email", {})

    slaves = [
        SlaveConfig(port=int(s["port"]), service_name=s["serviceName"])
        for s in data.get("slaves", [])
    ]

    return Config(
        broker_url=data["brokerUrl"],
        log_dir=Path(data.get("logDir", "logs")),
        log_retention_days=int(data.get("logRetentionDays", 7)),
        auto_restart=bool(data.get("autoRestart", True)),
        start_timeout_seconds=int(data.get("startTimeoutSeconds", 60)),
        slaves=slaves,
        email=EmailConfig(
            enabled=bool(em.get("enabled", False)),
            smtp_server=em.get("smtpServer", ""),
            smtp_port=int(em.get("smtpPort", 587)),
            use_ssl=bool(em.get("useSSL", False)),
            from_addr=em.get("from", ""),
            to_addrs=em.get("to", []),
            username=em.get("username", ""),
            password=em.get("password", ""),
        ),
    )
