CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.network_sentinel`;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.network_sentinel.packet_metadata` (
  packet_id STRING NOT NULL,
  device_id STRING NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  frame_length INT64 NOT NULL,
  ip_protocol INT64,
  destination_port INT64,
  tcp_syn BOOL,
  tcp_ack BOOL,
  tcp_reset BOOL,
  source_pcap STRING NOT NULL
)
PARTITION BY DATE(observed_at)
CLUSTER BY device_id, destination_port;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.network_sentinel.capture_manifests` (
  schema_version INT64,
  device_id STRING NOT NULL,
  source_pcap STRING NOT NULL,
  packet_count INT64 NOT NULL,
  file_bytes INT64 NOT NULL,
  sha256 STRING NOT NULL,
  exported_at TIMESTAMP NOT NULL,
  received_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(received_at)
CLUSTER BY device_id;


CREATE TABLE IF NOT EXISTS `PROJECT_ID.network_sentinel.pipeline_health` (
  schema_version INT64,
  device_id STRING NOT NULL,
  reported_at TIMESTAMP NOT NULL,
  capture_interface STRING NOT NULL,
  interface_rx_dropped INT64,
  interface_tx_dropped INT64,
  pcap_disk_total_bytes INT64 NOT NULL,
  pcap_disk_used_bytes INT64 NOT NULL,
  pcap_disk_free_bytes INT64 NOT NULL,
  ntp_synchronized BOOL,
  last_exported_at_epoch FLOAT64,
  export_latency_seconds FLOAT64
)
PARTITION BY DATE(reported_at)
CLUSTER BY device_id;
