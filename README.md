# Network Sentinel

A starter project for privacy-preserving Raspberry Pi telemetry and a reproducible offline anomaly-detection demo. This guide is deliberately copy-paste oriented. Complete **Part 1** first. Parts 2–5 are optional Pi, VPN, MQTT, capture, and GCP setup.

## What is implemented

| Component | Status | Files |
| --- | --- | --- |
| Synthetic labelled data, model training, evaluation | Ready | `ml/`, `scripts/run_ml_demo.sh` |
| Unit tests | Ready | `tests/test_ml.py` |
| Pi interval telemetry collector | Ready | `collector.py` |
| Dedicated SSH account and mDNS hostname | Ready | `pi/setup_ssh.sh` |
| TLS MQTT presence, PCAP metadata export, and capture services | Ready | `pi/mqtt_agent.py`, `pi/pcap_exporter.py`, `pi/install_agent.sh` |
| GCP MQTT bridge to BigQuery / optional manifest bucket | Ready to configure | `services/gcp_mqtt_bridge.py`, `infra/gcp/` |
| Pi capture, disk, NTP, and export health reports | Ready to configure | `pi/health_reporter.py`, `pi/systemd/network-sentinel-health.service` |
| Development Mosquitto broker configuration | Ready | `infra/mqtt/` |
| HTTPS API, flow aggregation, RAG/LLM, and managed GCP deployment | Not implemented | — |

The ML demo works without a Pi, Docker, VPN, MQTT broker, GCP account, or API key.

## Prerequisites

### Laptop/local ML demo

- Linux, macOS, or WSL
- Python 3.10+ with `venv` support
- Git (only if cloning from GitHub)

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

### Optional Pi and broker setup

- Raspberry Pi running Ubuntu/Debian, with a local console or an existing SSH session
- Laptop and Pi on the same Tailscale tailnet for remote access
- Docker Engine plus Docker Compose plugin on the computer/server hosting Mosquitto
- `openssl` on the broker host

## Part 1 — Run the complete local ML demo

### 1. Get the source

If the repository is already present, enter it:

```bash
cd /path/to/network-sentinel
```

Otherwise clone your GitHub repository, replacing the placeholder:

```bash
git clone https://github.com/YOUR_GITHUB_USER/network-sentinel.git
cd network-sentinel
```

### 2. Generate every local demo file, train, evaluate, and test

```bash
bash scripts/run_ml_demo.sh
```

The script creates and/or updates:

```text
.venv/                    local Python virtual environment
data/flows.csv             deterministic synthetic labelled traffic
artifacts/detector.joblib  trained Isolation Forest model
```

Both `data/` and `artifacts/` are generated files and are intentionally ignored by Git. A successful run ends with `3 passed` and an evaluation report. Re-run the same script safely whenever you want a clean, reproducible result.

### 3. Run individual commands instead (optional)

```bash
.venv/bin/python -m ml.simulator --output data/flows.csv --seed 7
.venv/bin/python -m ml.train --input data/flows.csv --model artifacts/detector.joblib
.venv/bin/python -m ml.evaluate --input data/flows.csv --model artifacts/detector.joblib
.venv/bin/python -m pytest -q
```

## Part 2 — Set up safe SSH access to the Pi

> Keep a local Pi terminal or existing administrator SSH session open. The setup disables password and root SSH login, so verify the new key login before closing it.

### 1. Create a dedicated laptop key

On the laptop:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/network_sentinel_pi -C "network-sentinel-pi"
cat ~/.ssh/network_sentinel_pi.pub
```

Copy the one-line output. Do **not** copy or share `~/.ssh/network_sentinel_pi` (the private key).

### 2. Copy this repository to the Pi

On the Pi’s local terminal, replacing the clone URL:

```bash
sudo apt update
sudo apt install -y git rsync
cd ~
git clone https://github.com/YOUR_GITHUB_USER/network-sentinel.git
printf '%s\n' 'PASTE_THE_PUBLIC_KEY_HERE' > /tmp/network_sentinel_pi.pub
chmod 600 /tmp/network_sentinel_pi.pub
```

### 3. Create the restricted account and stable local hostname

Still on the Pi:

```bash
sudo bash ~/network-sentinel/pi/setup_ssh.sh "$(cat /tmp/network_sentinel_pi.pub)" network-sentinel-pi
rm -f /tmp/network_sentinel_pi.pub
```

The script creates the `sentinel` account, allows only its public-key SSH login, disables root/password SSH, and enables mDNS. From the laptop on the same LAN:

```bash
ssh -i ~/.ssh/network_sentinel_pi sentinel@network-sentinel-pi.local
```

If `.local` does not resolve on your laptop, use Tailscale in Part 3; do not expose port 22 to the public internet.

## Part 3 — Use Tailscale for stable remote SSH (recommended)

Install Tailscale on both the laptop and Pi from its official instructions. On the Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh=false
sudo tailscale status
```

On the laptop, log into the same tailnet and find the Pi name with:

```bash
tailscale status
ssh -i ~/.ssh/network_sentinel_pi sentinel@network-sentinel-pi
```

Use the tailnet DNS name shown by `tailscale status`; it remains usable when the Pi changes LAN or WAN IP. `--ssh=false` keeps access controlled by the dedicated Linux `sentinel` account and the key configured above.

## Part 4 — MQTT presence service (optional)

The agent publishes a retained JSON message to:

```text
network-sentinel/<device-id>/presence
```

on every connection. It contains device ID, hostname, LAN IP, platform, and UTC timestamp. It publishes a retained `offline` status if it disconnects unexpectedly. It subscribes only to:

```text
network-sentinel/<device-id>/commands
```

The sole supported command is `{"action":"presence"}`. MQTT payloads are never executed as shell commands.

### A. Create broker credentials and TLS files

On a Docker-capable broker host that the Pi can reach through Tailscale or a firewall-restricted network:

```bash
cd /path/to/network-sentinel/infra/mqtt
bash scripts/generate_tls.sh mqtt.example.net
bash scripts/create_user.sh pi-4
```

Use the stable Tailscale DNS name (or another real DNS name) as `mqtt.example.net`. The certificate includes this name for Pi clients and `mosquitto` for the colocated Docker bridge; the Pi `NS_MQTT_HOST` must match the supplied name. Regenerate the certificate whenever that supplied name changes. The second command prompts for the Pi’s MQTT password; save it in a password manager.

The example ACL is for device/user `pi-4`. For another device, change every `pi-4` in `acl` before starting the broker. Then start it:

```bash
bash scripts/start_broker.sh
```

This generates `infra/mqtt/certs/`, `passwords/`, `data/`, and `log/`. They contain secrets or runtime data and are ignored by Git. Do not commit them. The example publishes TLS MQTT on port `8883`; do not publish that port openly to the internet.

### B. Install and configure the Pi MQTT agent

On the Pi, copy the source to its stable service location:

```bash
sudo mkdir -p /opt/network-sentinel
sudo rsync -a --delete ~/network-sentinel/ /opt/network-sentinel/
sudo bash /opt/network-sentinel/pi/install_agent.sh
```

The first run intentionally stops after creating `/etc/network-sentinel/mqtt.env`. Copy the broker CA certificate securely from the broker host to the Pi, then install it:

```bash
sudo install -o root -g sentinel -m 640 /path/to/ca.crt /etc/network-sentinel/ca.crt
sudo nano /etc/network-sentinel/mqtt.env
```

Set the values exactly:

```dotenv
NS_DEVICE_ID=pi-4
NS_MQTT_HOST=mqtt.example.net
NS_MQTT_PORT=8883
NS_MQTT_USERNAME=pi-4
NS_MQTT_PASSWORD=THE_PASSWORD_CREATED_ON_THE_BROKER
NS_MQTT_TOPIC_ROOT=network-sentinel
NS_MQTT_CA_CERT=/etc/network-sentinel/ca.crt
```

Run the installer again. It then creates `/etc/network-sentinel/pcap.env` and stops so you can verify the capture interface:

```bash
sudo bash /opt/network-sentinel/pi/install_agent.sh
ip -br link
sudo nano /etc/network-sentinel/pcap.env
```

Set `NS_CAPTURE_INTERFACE` to the Pi interface carrying its traffic, for example `eth0` or `wlan0`. Do not use a router mirror interface unless you have explicit authorization to capture other devices. Then run the installer a final time:

```bash
sudo bash /opt/network-sentinel/pi/install_agent.sh
sudo systemctl status --no-pager network-sentinel-mqtt network-sentinel-capture network-sentinel-pcap-export network-sentinel-health
```

## Part 5 — Continuous PCAP metadata upload to GCP

### What is captured and uploaded

`dumpcap` continuously writes a bounded local PCAPNG ring buffer. `tshark` reads only completed files and exports packet metadata over TLS MQTT in batches of at most 100 records:

```text
observed time, frame length, IP protocol, destination port,
TCP SYN/ACK/RST flags, device ID, source capture filename
```

It does **not** export packet payloads, IP addresses, MAC addresses, DNS names, or raw PCAP bytes. Raw PCAP remains on the Pi in `/var/lib/network-sentinel/pcap`, with the retention configured by `NS_PCAP_ROTATE_SECONDS` and `NS_PCAP_MAX_FILES`. The default is 60 files × 60 seconds (about one hour). MQTT is for bounded telemetry, not bulk PCAP transport.

### Configure the GCP bridge

The GCP bridge is a persistent MQTT subscriber. Run it on the same private Docker host as Mosquitto, normally a small Compute Engine VM protected by Tailscale. Google Cloud IoT Core is retired; Cloud Run cannot host a raw TCP MQTT broker.

1. Follow `infra/gcp/README.md` to create the BigQuery tables, least-privilege bridge service account, and optional manifest bucket.
2. On the broker host, create the bridge MQTT account and configuration:

   ```bash
   cd /path/to/network-sentinel/infra/mqtt
   bash scripts/create_user.sh gcp-bridge
   cp gcp-bridge.env.example gcp-bridge.env
   chmod 600 gcp-bridge.env gcp-service-account.json
   nano gcp-bridge.env
   ```

   Copy the GCP service-account JSON to `gcp-service-account.json`; this is a demo-only authentication method. Set `PROJECT_ID` and the MQTT bridge password in `gcp-bridge.env`.

3. Start the broker and bridge:

   ```bash
   docker compose --profile gcp up -d --build
   docker compose logs -f gcp-bridge
   ```

The bridge subscribes to:

```text
network-sentinel/+/telemetry/packets
network-sentinel/+/telemetry/capture-manifests
network-sentinel/+/telemetry/health
```

Before acknowledging MQTT, the bridge durably stores each metadata payload in `infra/mqtt/gcp-bridge-data/` on the broker host. This SQLite spool retries failed BigQuery or Cloud Storage writes with exponential backoff. It is bounded by `NS_GCP_SPOOL_MAX_BYTES` (default 1 GiB); monitor free disk space and bridge logs. Messages that fail schema validation are quarantined in the same spool rather than retried indefinitely. It stores packets in BigQuery with stable `packet_id` insert IDs and capture manifests with their SHA-256 ID. Delivery is **at least once**: BigQuery streaming insert-ID deduplication is best effort and has a limited window, so downstream queries should deduplicate by `packet_id` or manifest SHA-256 if exact counts matter. If `NS_GCP_MANIFEST_BUCKET` is set, manifests are also stored as deterministic JSON objects in Cloud Storage. The bridge never receives raw PCAP bytes.

### Operational health reports

The Pi health service sends a periodic, allow-listed report through the same private MQTT bridge to the `pipeline_health` BigQuery table. It includes the capture interface's kernel RX/TX drop counters (these are **not** dumpcap-specific loss counts), PCAP filesystem capacity, NTP synchronization status, and latency of the most recently completed metadata export. It does not contain packet data, addresses, hostnames, or capture file names. Health inserts use a device-and-report-time ID and remain at-least-once like the rest of the bridge. `NS_HEALTH_REPORT_SECONDS` defaults to 60 and must be at least 10.

### Check the Pi pipeline

```bash
sudo journalctl -u network-sentinel-capture -f
sudo journalctl -u network-sentinel-pcap-export -f
ls -lh /var/lib/network-sentinel/pcap
```

## Pi collector

The collector is separate from MQTT presence. It prints the Pi’s aggregate traffic deltas and established **port numbers**; it never captures packet payloads or destination addresses.

```bash
cd /opt/network-sentinel
.venv/bin/python collector.py --device-id pi-4 --interval 60
```

To send collector events to a future HTTPS ingestion API (not implemented yet):

```bash
.venv/bin/python collector.py --device-id pi-4 --interval 60 --endpoint https://YOUR_API/events
```

Do not send these collector events directly to `artifacts/detector.joblib`. The current detector expects synthetic NetFlow-like features, while the collector emits aggregate interval telemetry. A future aggregation service must bridge this schema boundary.

## Useful checks and recovery

```bash
# Local demo health
bash scripts/run_ml_demo.sh

# SSH configuration on Pi
sudo sshd -t
getent hosts network-sentinel-pi.local

# MQTT presence and PCAP pipeline logs on Pi
sudo journalctl -u network-sentinel-mqtt -f
sudo journalctl -u network-sentinel-capture -n 50 --no-pager
sudo journalctl -u network-sentinel-pcap-export -n 50 --no-pager
sudo journalctl -u network-sentinel-health -n 50 --no-pager

# Stop the development broker
cd /path/to/network-sentinel/infra/mqtt
docker compose down
```

Never commit `.env`, private SSH keys, MQTT passwords, CA keys, or TLS certificates.
