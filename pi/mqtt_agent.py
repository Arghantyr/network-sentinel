"""MQTT presence agent for a Raspberry Pi.

Publishes retained, non-sensitive presence metadata after connecting and listens
for a small set of future-safe commands. It never executes MQTT payloads.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

LOG = logging.getLogger("network-sentinel.mqtt")


def local_ip() -> str:
    """Return the Pi's LAN address without sending application data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((os.getenv("NS_IP_CHECK_HOST", "1.1.1.1"), 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "unknown"
    finally:
        sock.close()


def presence(device_id: str) -> dict[str, str]:
    return {
        "device_id": device_id,
        "hostname": socket.gethostname(),
        "local_ip": local_ip(),
        "platform": platform.platform(),
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }


def run() -> None:
    broker = os.environ["NS_MQTT_HOST"]
    port = int(os.getenv("NS_MQTT_PORT", "8883"))
    device = os.getenv("NS_DEVICE_ID", socket.gethostname())
    username = os.environ["NS_MQTT_USERNAME"]
    password = os.environ["NS_MQTT_PASSWORD"]
    topic_root = os.getenv("NS_MQTT_TOPIC_ROOT", "network-sentinel")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device)
    client.username_pw_set(username, password)
    client.tls_set(ca_certs=os.getenv("NS_MQTT_CA_CERT") or None)  # Verify the broker certificate.

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            LOG.error("MQTT connection failed: %s", reason_code)
            return
        client.subscribe(f"{topic_root}/{device}/commands", qos=1)
        client.publish(
            f"{topic_root}/{device}/presence",
            json.dumps(presence(device), separators=(",", ":")),
            qos=1,
            retain=True,
        )
        LOG.info("published presence for %s", device)

    def on_message(client, userdata, message):
        # Deliberately no shell/eval: this is only a control-plane extension point.
        try:
            command = json.loads(message.payload)
        except json.JSONDecodeError:
            LOG.warning("ignored non-JSON command")
            return
        if command.get("action") == "presence":
            client.publish(f"{topic_root}/{device}/presence", json.dumps(presence(device)), qos=1, retain=True)
        else:
            LOG.warning("ignored unsupported command: %r", command.get("action"))

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{topic_root}/{device}/presence", json.dumps({"device_id": device, "status": "offline"}), qos=1, retain=True)
    client.connect(broker, port, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
