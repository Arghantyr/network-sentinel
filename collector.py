"""Collect privacy-preserving Raspberry Pi network telemetry.

This program collects local aggregate counters and destination port numbers only.
It does not inspect packet payloads or retain destination addresses.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psutil
import requests

LOG = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class NetworkCounters:
    bytes_sent: int
    bytes_received: int

    @classmethod
    def read(cls) -> "NetworkCounters":
        counters = psutil.net_io_counters()
        return cls(bytes_sent=counters.bytes_sent, bytes_received=counters.bytes_recv)


def established_destination_ports() -> list[int]:
    """Return unique established remote ports, without addresses or payload data."""
    try:
        connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        LOG.warning("Cannot read socket metadata; continuing without ports.")
        return []
    return sorted({connection.raddr.port for connection in connections
                   if connection.raddr and connection.status == psutil.CONN_ESTABLISHED})


def make_event(device_id: str, previous: NetworkCounters, current: NetworkCounters) -> dict[str, Any]:
    """Create one interval event. Counter resets are reported as zero traffic."""
    return {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bytes_out": max(0, current.bytes_sent - previous.bytes_sent),
        "bytes_in": max(0, current.bytes_received - previous.bytes_received),
        "destination_ports": established_destination_ports(),
    }


def send_event(endpoint: str, event: dict[str, Any]) -> None:
    """Send one event. A failed upload must not stop local collection."""
    try:
        response = requests.post(endpoint, json=event, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        LOG.warning("Event upload failed: %s", error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="pi-4")
    parser.add_argument("--endpoint", help="Optional HTTPS ingestion endpoint")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise ValueError("--interval must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    previous = NetworkCounters.read()
    while True:
        time.sleep(args.interval)
        current = NetworkCounters.read()
        event = make_event(args.device_id, previous, current)
        previous = current
        print(json.dumps(event), flush=True)
        if args.endpoint:
            send_event(args.endpoint, event)


if __name__ == "__main__":
    main()
