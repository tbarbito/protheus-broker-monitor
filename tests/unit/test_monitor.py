from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from broker_monitor.monitor import (
    SlaveStatus,
    check_broker,
    get_quarantined,
    parse_broker_page,
)
from tests.conftest import (
    BROKER_HTML_ALL_OK,
    BROKER_HTML_ALL_QUARANTINED,
    BROKER_HTML_EMPTY,
    BROKER_HTML_ONE_QUARANTINED,
)


class TestSlaveStatus:
    def test_not_quarantined_dash(self):
        assert SlaveStatus("10.0.0.1:10001", "-").is_quarantined is False

    def test_not_quarantined_empty(self):
        assert SlaveStatus("10.0.0.1:10001", "").is_quarantined is False

    def test_quarantined(self):
        assert SlaveStatus("10.0.0.1:10001", "QUARANTINE_TIMEOUT").is_quarantined is True


class TestParseBrokerPage:
    def test_parses_all_slaves(self):
        slaves = parse_broker_page(BROKER_HTML_ALL_OK)
        assert len(slaves) == 3

    def test_slave_addresses(self):
        slaves = parse_broker_page(BROKER_HTML_ALL_OK)
        addresses = [s.address for s in slaves]
        assert "10.0.0.1:10001" in addresses
        assert "10.0.0.1:10002" in addresses

    def test_no_quarantine(self):
        slaves = parse_broker_page(BROKER_HTML_ALL_OK)
        assert all(not s.is_quarantined for s in slaves)

    def test_detects_quarantined(self):
        slaves = parse_broker_page(BROKER_HTML_ONE_QUARANTINED)
        quarantined = [s for s in slaves if s.is_quarantined]
        assert len(quarantined) == 1
        assert quarantined[0].address == "10.0.0.1:10002"
        assert quarantined[0].quarantine == "QUARANTINE_TIMEOUT"

    def test_empty_page_returns_no_slaves(self):
        assert parse_broker_page(BROKER_HTML_EMPTY) == []

    def test_all_quarantined(self):
        slaves = parse_broker_page(BROKER_HTML_ALL_QUARANTINED)
        assert all(s.is_quarantined for s in slaves)

    def test_ignores_unrelated_links(self):
        html = "<a href='/other/link'>something</a>"
        assert parse_broker_page(html) == []


class TestGetQuarantined:
    def test_filters_only_quarantined(self):
        slaves = parse_broker_page(BROKER_HTML_ONE_QUARANTINED)
        quarantined = get_quarantined(slaves)
        assert len(quarantined) == 1

    def test_empty_when_all_ok(self):
        slaves = parse_broker_page(BROKER_HTML_ALL_OK)
        assert get_quarantined(slaves) == []


class TestCheckBroker:
    def test_returns_slaves_on_success(self):
        mock_resp = MagicMock()
        mock_resp.text = BROKER_HTML_ONE_QUARANTINED
        mock_resp.raise_for_status.return_value = None

        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            reachable, slaves = check_broker("http://test/status")

        assert reachable is True
        assert len(slaves) == 3

    def test_returns_false_on_connection_error(self):
        with patch("broker_monitor.monitor.requests.get", side_effect=requests.ConnectionError()):
            reachable, slaves = check_broker("http://test/status")

        assert reachable is False
        assert slaves == []

    def test_returns_false_on_timeout(self):
        with patch("broker_monitor.monitor.requests.get", side_effect=requests.Timeout()):
            reachable, slaves = check_broker("http://test/status")

        assert reachable is False

    def test_returns_false_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")

        with patch("broker_monitor.monitor.requests.get", return_value=mock_resp):
            reachable, slaves = check_broker("http://test/status")

        assert reachable is False
