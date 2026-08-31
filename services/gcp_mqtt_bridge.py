"""MQTT subscriber that stores Pi packet metadata in GCP.

Run this as a container on a GCP Compute Engine VM beside Mosquitto, or anywhere
with a GCP service account and private MQTT connectivity. Cloud Run cannot host
a raw TCP MQTT broker; it can be used for a separate HTTP API later.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from gcp_spool import Spool, SpoolFull, decode_payload

import paho.mqtt.client as mqtt
from google.cloud import bigquery, storage

LOG = logging.getLogger("network-sentinel.gcp-bridge")

PACKET_REQUIRED = {"packet_id", "device_id", "observed_at", "frame_length", "source_pcap"}
HEALTH_REQUIRED = {"device_id", "reported_at", "capture_interface", "pcap_disk_total_bytes", "pcap_disk_used_bytes", "pcap_disk_free_bytes"}


def configured_table(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required (PROJECT.DATASET.TABLE)")
    return value


def valid_packet(record: object) -> bool:
    return isinstance(record, dict) and PACKET_REQUIRED.issubset(record) and isinstance(record["frame_length"], int)


def valid_health(record: object) -> bool:
    return (isinstance(record, dict) and HEALTH_REQUIRED.issubset(record)
            and all(isinstance(record[key], int) for key in ("pcap_disk_total_bytes", "pcap_disk_used_bytes", "pcap_disk_free_bytes")))


class GcpSink:
    def __init__(self) -> None:
        self.bigquery = bigquery.Client()
        self.packet_table = configured_table("NS_GCP_BQ_PACKET_TABLE")
        self.manifest_table = configured_table("NS_GCP_BQ_MANIFEST_TABLE")
        self.health_table = configured_table("NS_GCP_BQ_HEALTH_TABLE")
        bucket_name = os.getenv("NS_GCP_MANIFEST_BUCKET")
        self.bucket = storage.Client().bucket(bucket_name) if bucket_name else None

    def packets(self, payload: dict[str, Any]) -> None:
        records = payload.get("packets", [])
        if not isinstance(records, list) or not all(valid_packet(record) for record in records):
            raise ValueError("invalid packet batch")
        errors = self.bigquery.insert_rows_json(self.packet_table, records, row_ids=[record["packet_id"] for record in records])
        if errors:
            raise RuntimeError(f"BigQuery packet insert failed: {errors}")

    def health(self, payload: dict[str, Any]) -> None:
        if not valid_health(payload):
            raise ValueError("invalid health report")
        row_id = f"{payload['device_id']}:{payload['reported_at']}"
        errors = self.bigquery.insert_rows_json(self.health_table, [payload], row_ids=[row_id])
        if errors:
            raise RuntimeError(f"BigQuery health insert failed: {errors}")

    def manifest(self, payload: dict[str, Any]) -> None:
        required = {"device_id", "source_pcap", "packet_count", "file_bytes", "sha256", "exported_at"}
        if not required.issubset(payload):
            raise ValueError("invalid capture manifest")
        payload = {**payload, "received_at": datetime.now(timezone.utc).isoformat()}
        errors = self.bigquery.insert_rows_json(self.manifest_table, [payload], row_ids=[payload["sha256"]])
        if errors:
            raise RuntimeError(f"BigQuery manifest insert failed: {errors}")
        if self.bucket:
            blob = self.bucket.blob(f"capture-manifests/{payload['device_id']}/{payload['sha256']}.json")
            blob.upload_from_string(json.dumps(payload), content_type="application/json")


def process_one(spool: Spool, sink: GcpSink) -> bool:
    item = spool.claim()
    if not item:
        return False
    item_id, topic, raw_payload, attempts = item
    try:
        payload = decode_payload(raw_payload)
        if topic.endswith("/telemetry/packets"):
            sink.packets(payload)
        elif topic.endswith("/telemetry/capture-manifests"):
            sink.manifest(payload)
        elif topic.endswith("/telemetry/health"):
            sink.health(payload)
        else:
            raise ValueError("unknown telemetry topic")
    except (ValueError, json.JSONDecodeError) as error:
        spool.quarantine(item_id, str(error))
        LOG.error("quarantined bridge message %s: %s", item_id, error)
    except Exception as error:
        spool.retry(item_id, attempts, str(error), base=int(os.getenv("NS_GCP_RETRY_BASE_SECONDS", "5")), maximum=int(os.getenv("NS_GCP_RETRY_MAX_SECONDS", "3600")))
        LOG.warning("will retry bridge message %s: %s", item_id, error)
    else:
        spool.succeed(item_id)
    return True


def run() -> None:
    root = os.getenv("NS_MQTT_TOPIC_ROOT", "network-sentinel")
    spool = Spool(os.getenv("NS_GCP_SPOOL_PATH", "/var/lib/network-sentinel/gcp-bridge/spool.sqlite3"), int(os.getenv("NS_GCP_SPOOL_MAX_BYTES", "1073741824")))
    sink = GcpSink()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=os.getenv("NS_BRIDGE_CLIENT_ID", "network-sentinel-gcp-bridge"), clean_session=False, manual_ack=True)
    client.username_pw_set(os.environ["NS_MQTT_USERNAME"], os.environ["NS_MQTT_PASSWORD"])
    client.tls_set(ca_certs=os.getenv("NS_MQTT_CA_CERT") or None)

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code != 0:
            LOG.error("MQTT connect failed: %s", reason_code)
            return
        client.subscribe(f"{root}/+/telemetry/packets", qos=1)
        client.subscribe(f"{root}/+/telemetry/capture-manifests", qos=1)
        client.subscribe(f"{root}/+/telemetry/health", qos=1)
        LOG.info("subscribed to telemetry topics")

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            spool.enqueue(message.topic, bytes(message.payload))
            client.ack(message.mid, message.qos)
        except SpoolFull as error:
            LOG.error("cannot acknowledge MQTT message: %s", error)
            client.disconnect()
        except Exception:
            LOG.exception("failed to enqueue MQTT message")
            client.disconnect()

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(os.environ["NS_MQTT_HOST"], int(os.getenv("NS_MQTT_PORT", "8883")), keepalive=60)
    client.loop_start()
    try:
        while True:
            process_one(spool, sink)
            time.sleep(float(os.getenv("NS_GCP_SPOOL_POLL_SECONDS", "1")))
    finally:
        client.loop_stop()
        client.disconnect()
        spool.close()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    run()
