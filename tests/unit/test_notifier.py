from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from broker_monitor.config import EmailConfig
from broker_monitor.monitor import SlaveStatus
from broker_monitor.notifier import _build_email, send_alert
from broker_monitor.restarter import ServiceInfo


def _email_cfg(enabled: bool = True) -> EmailConfig:
    return EmailConfig(
        enabled=enabled,
        smtp_server="smtp.test.com",
        smtp_port=587,
        use_ssl=False,
        from_addr="monitor@test.com",
        to_addrs=["admin@test.com"],
        username="monitor@test.com",
        password="secret",
    )


QUARANTINED = [SlaveStatus("10.0.0.1:10002", "QUARANTINE_TIMEOUT")]
RESTARTED   = [ServiceInfo("10.0.0.1:10002", 10002, service_name="TestSlv02PRD")]
FAILED      = [ServiceInfo("10.0.0.1:10003", 10003, service_name="TestSlv03PRD")]


class TestBuildEmail:
    def test_broker_unreachable_subject(self):
        subject, _ = _build_email([], [], [], [], broker_unreachable=True)
        assert "inacessivel" in subject.lower()

    def test_quarantine_subject_contains_count(self):
        subject, _ = _build_email(QUARANTINED, [], [], [])
        assert "1" in subject

    def test_body_contains_slave_address(self):
        _, body = _build_email(QUARANTINED, [], [], [])
        assert "10.0.0.1:10002" in body

    def test_body_contains_restarted_service(self):
        _, body = _build_email(QUARANTINED, RESTARTED, [], [])
        assert "TestSlv02PRD" in body  # display_name
        assert "Reiniciados" in body

    def test_body_contains_failed_service(self):
        _, body = _build_email(QUARANTINED, [], FAILED, [])
        assert "TestSlv03PRD" in body  # display_name
        assert "FALHA" in body

    def test_body_contains_skipped(self):
        _, body = _build_email(QUARANTINED, [], [], ["10.0.0.1:10005"])
        assert "10.0.0.1:10005" in body

    def test_body_is_html(self):
        _, body = _build_email(QUARANTINED, [], [], [])
        assert "<html>" in body
        assert "</html>" in body


class TestSendAlert:
    def test_does_nothing_when_disabled(self):
        cfg = _email_cfg(enabled=False)
        with patch("broker_monitor.notifier.smtplib.SMTP") as mock_smtp:
            send_alert(cfg, QUARANTINED, [], [], [])
            mock_smtp.assert_not_called()

    def test_calls_smtp_when_enabled(self):
        cfg = _email_cfg(enabled=True)
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)

        with patch("broker_monitor.notifier.smtplib.SMTP", return_value=mock_smtp_instance):
            send_alert(cfg, QUARANTINED, RESTARTED, [], [])

        mock_smtp_instance.sendmail.assert_called_once()

    def test_smtp_error_propagates(self):
        cfg = _email_cfg(enabled=True)
        with patch("broker_monitor.notifier.smtplib.SMTP", side_effect=OSError("connection refused")):
            with pytest.raises(OSError):
                send_alert(cfg, QUARANTINED, [], [], [])
