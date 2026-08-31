"""Export privacy-preserving packet metadata from completed PCAP files over MQTT.

Raw PCAP is never placed in an MQTT message.  The local rotating PCAP buffer is
read with tshark and only packet time, length, protocol, destination port, and
TCP control flags are exported.  IP addresses, payloads, MAC addresses, and DNS
names are not requested from tshark and therefore cannot enter the MQTT data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import paho.mqtt.client as mqtt

LOG = logging.getLogger("network-sentinel.pcap-exporter")
FIELDS = ("frame.time_epoch", "frame.len", "ip.proto", "tcp.dstport", "udp.dstport", "tcp.flags.syn", "tcp.flags.ack", "tcp.flags.reset")


def _number(value: str, kind: type[int] | type[float]) -> int | float | None:
    try:
        return kind(value) if value else None
    except ValueError:
        return None


def parse_tshark_line(line: str, device_id: str, source_name: str, sequence: int) -> dict[str, Any] | None:
    """Convert one fixed-width tshark row into an export-safe packet event."""
    values = line.rstrip("\n").split("\t")
    if len(values) != len(FIELDS):
        return None
    timestamp, length, protocol, tcp_port, udp_port, syn, ack, reset = values
    event_time = _number(timestamp, float)
    frame_length = _number(length, int)
    if event_time is None or frame_length is None:
        return None
    destination_port = _number(tcp_port or udp_port, int)
    identity = f"{source_name}:{sequence}:{line}".encode()
    return {
        "packet_id": hashlib.sha256(identity).hexdigest(),
        "device_id": device_id,
        "observed_at": datetime.fromtimestamp(event_time, tz=timezone.utc).isoformat(),
        "frame_length": frame_length,
        "ip_protocol": _number(protocol, int),
        "destination_port": destination_port,
        "tcp_syn": bool(_number(syn, int)),
        "tcp_ack": bool(_number(ack, int)),
        "tcp_reset": bool(_number(reset, int)),
        "source_pcap": source_name,
    }


def packet_events(path: Path, device_id: str) -> list[dict[str, Any]]:
    """Read an already-closed capture file without extracting sensitive fields."""
    command = ["tshark", "-n", "-r", str(path), "-T", "fields", "-E", "separator=\t"]
    command.extend(argument for field in FIELDS for argument in ("-e", field))
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return [event for index, line in enumerate(completed.stdout.splitlines(), start=1)
            if (event := parse_tshark_line(line, device_id, path.name, index)) is not None]


def _load_state(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_state(path: Path, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(completed)[-5000:]))


def completed_captures(directory: Path, minimum_age: int, seen: set[str]) -> Iterable[Path]:
    """Yield old files except the newest one, which dumpcap may still be writing."""
    cutoff = time.time() - minimum_age
    files = sorted(directory.glob("*.pcapng"), key=lambda item: item.stat().st_mtime)
    for path in files[:-1]:
        if path.name not in seen and path.stat().st_mtime < cutoff:
            yield path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as capture:
        for block in iter(lambda: capture.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mqtt_client() -> tuple[mqtt.Client, str, str]:
    device_id = os.environ["NS_DEVICE_ID"]
    root = os.getenv("NS_MQTT_TOPIC_ROOT", "network-sentinel")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device_id}-pcap-export")
    client.username_pw_set(os.environ["NS_MQTT_USERNAME"], os.environ["NS_MQTT_PASSWORD"])
    client.tls_set(ca_certs=os.getenv("NS_MQTT_CA_CERT") or None)
    client.connect(os.environ["NS_MQTT_HOST"], int(os.getenv("NS_MQTT_PORT", "8883")), keepalive=60)
    client.loop_start()
    return client, device_id, root


def publish_file(client: mqtt.Client, root: str, device_id: str, path: Path, batch_size: int) -> None:
    events = packet_events(path, device_id)
    for start in range(0, len(events), batch_size):
        payload = {"schema_version": 1, "device_id": device_id, "packets": events[start:start + batch_size]}
        result = client.publish(f"{root}/{device_id}/telemetry/packets", json.dumps(payload, separators=(",", ":")), qos=1)
        result.wait_for_publish(timeout=30)
        if not result.is_published():
            raise RuntimeError(f"MQTT publish timed out for {path.name}")
    manifest = {"schema_version": 1, "device_id": device_id, "source_pcap": path.name,
                "packet_count": len(events), "file_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "exported_at": datetime.now(timezone.utc).isoformat()}
    result = client.publish(f"{root}/{device_id}/telemetry/capture-manifests", json.dumps(manifest, separators=(",", ":")), qos=1)
    result.wait_for_publish(timeout=30)
    if not result.is_published():
        raise RuntimeError(f"MQTT manifest publish timed out for {path.name}")


def _save_export_health(path: Path, latency_seconds: float) -> None:
    """Atomically persist only aggregate exporter timing for the health reporter."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps({"exported_at_epoch": time.time(), "export_latency_seconds": latency_seconds}))
    os.replace(temporary, path)


def run() -> None:
    directory = Path(os.getenv("NS_PCAP_DIRECTORY", "/var/lib/network-sentinel/pcap"))
    state_path = directory.parent / "pcap-exported.json"
    minimum_age = int(os.getenv("NS_PCAP_MIN_AGE_SECONDS", "10"))
    batch_size = int(os.getenv("NS_PCAP_BATCH_SIZE", "100"))
    if batch_size < 1 or batch_size > 500:
        raise ValueError("NS_PCAP_BATCH_SIZE must be between 1 and 500")
    client, device_id, root = mqtt_client()
    seen = _load_state(state_path)
    try:
        while True:
            for path in completed_captures(directory, minimum_age, seen):
                try:
                    started_at = time.monotonic()
                    publish_file(client, root, device_id, path, batch_size)
                    seen.add(path.name)
                    _save_state(state_path, seen)
                    _save_export_health(directory.parent / "pcap-export-health.json", time.monotonic() - started_at)
                    LOG.info("exported %s", path.name)
                except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
                    LOG.warning("will retry %s: %s", path.name, error)
            time.sleep(5)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    run()
