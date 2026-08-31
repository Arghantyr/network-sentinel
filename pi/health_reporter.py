"""Publish privacy-preserving Pi pipeline health over the private MQTT broker.

The report deliberately excludes packet contents, addresses, hostnames, and file names.
Interface drop counters describe kernel interface drops, not an estimate of packets
captured by dumpcap.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt


def _integer_file(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def ntp_synchronized() -> bool | None:
    """Return NTP synchronization status, or None when timedatectl is unavailable."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized", "--value"],
            check=True, text=True, capture_output=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip().lower()
    return True if value == "yes" else False if value == "no" else None


def last_export(path: Path) -> tuple[float | None, float | None]:
    try:
        data = json.loads(path.read_text())
        exported_at = float(data["exported_at_epoch"])
        latency = float(data["export_latency_seconds"])
        return exported_at, latency
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None, None


def health_report(device_id: str, capture_interface: str, pcap_directory: Path, export_state: Path,
                  sys_class_net: Path = Path("/sys/class/net")) -> dict[str, Any]:
    """Build an allow-listed health report with no network-identifying data."""
    usage = shutil.disk_usage(pcap_directory)
    stats = sys_class_net / capture_interface / "statistics"
    exported_at, latency = last_export(export_state)
    return {
        "schema_version": 1,
        "device_id": device_id,
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "capture_interface": capture_interface,
        # These are NIC/kernel counters, not dumpcap-specific loss measurements.
        "interface_rx_dropped": _integer_file(stats / "rx_dropped"),
        "interface_tx_dropped": _integer_file(stats / "tx_dropped"),
        "pcap_disk_total_bytes": usage.total,
        "pcap_disk_used_bytes": usage.used,
        "pcap_disk_free_bytes": usage.free,
        "ntp_synchronized": ntp_synchronized(),
        "last_exported_at_epoch": exported_at,
        "export_latency_seconds": latency,
    }


def run() -> None:
    device_id = os.environ["NS_DEVICE_ID"]
    root = os.getenv("NS_MQTT_TOPIC_ROOT", "network-sentinel")
    pcap_directory = Path(os.getenv("NS_PCAP_DIRECTORY", "/var/lib/network-sentinel/pcap"))
    interface = os.environ["NS_CAPTURE_INTERFACE"]
    interval = int(os.getenv("NS_HEALTH_REPORT_SECONDS", "60"))
    if interval < 10:
        raise ValueError("NS_HEALTH_REPORT_SECONDS must be at least 10")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device_id}-health")
    client.username_pw_set(os.environ["NS_MQTT_USERNAME"], os.environ["NS_MQTT_PASSWORD"])
    client.tls_set(ca_certs=os.getenv("NS_MQTT_CA_CERT") or None)
    client.connect(os.environ["NS_MQTT_HOST"], int(os.getenv("NS_MQTT_PORT", "8883")), keepalive=60)
    client.loop_start()
    try:
        while True:
            report = health_report(device_id, interface, pcap_directory, pcap_directory.parent / "pcap-export-health.json")
            result = client.publish(f"{root}/{device_id}/telemetry/health", json.dumps(report, separators=(",", ":")), qos=1)
            result.wait_for_publish(timeout=30)
            if not result.is_published():
                raise RuntimeError("MQTT health publish timed out")
            time.sleep(interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    run()
