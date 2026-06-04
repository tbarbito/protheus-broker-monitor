from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup


@dataclass
class SlaveStatus:
    address: str
    quarantine: str

    @property
    def is_quarantined(self) -> bool:
        return self.quarantine not in ("", "-")


def check_broker(url: str, timeout: int = 30) -> tuple[bool, list[SlaveStatus]]:
    """
    Requests the broker status page.
    Returns (reachable, slaves). reachable=False means the broker did not respond.
    """
    try:
        response = requests.get(url, timeout=timeout, verify=True)
        response.raise_for_status()
        return True, parse_broker_page(response.text)
    except requests.RequestException:
        return False, []


def parse_broker_page(html: str) -> list[SlaveStatus]:
    """
    Parses the Protheus Broker status HTML page and returns all slaves found.
    Uses BeautifulSoup for robust parsing -- resilient to minor layout changes.
    """
    soup = BeautifulSoup(html, "html.parser")
    slaves: list[SlaveStatus] = []

    for a_tag in soup.find_all("a", href=True):
        match = re.search(r"ServerStatus/([\d.]+):(\d+)", a_tag["href"])
        if not match:
            continue

        address = f"{match.group(1)}:{match.group(2)}"
        row = a_tag.find_parent("tr")
        if not row:
            continue

        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        quarantine = cells[2].get_text(strip=True)
        slaves.append(SlaveStatus(address=address, quarantine=quarantine))

    return slaves


def get_quarantined(slaves: list[SlaveStatus]) -> list[SlaveStatus]:
    return [s for s in slaves if s.is_quarantined]
