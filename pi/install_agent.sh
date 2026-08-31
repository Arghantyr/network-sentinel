#!/usr/bin/env bash
# Run as root on the Pi after the repository is copied to /opt/network-sentinel.
# It deliberately does not start with example MQTT credentials or an unchecked interface.
set -euo pipefail
cd /opt/network-sentinel
id sentinel >/dev/null 2>&1 || { echo "Run pi/setup_ssh.sh first." >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv ca-certificates tshark
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --requirement requirements.txt
install -d -m 750 -o sentinel -g sentinel /var/lib/network-sentinel/pcap
install -d -m 750 -o root -g sentinel /etc/network-sentinel
if [ ! -f /etc/network-sentinel/mqtt.env ]; then
  install -m 640 -o root -g sentinel pi/network-sentinel.env.example /etc/network-sentinel/mqtt.env
  echo "Created /etc/network-sentinel/mqtt.env. Configure it, install the broker CA, then run this script again." >&2
  exit 0
fi
if [ ! -f /etc/network-sentinel/pcap.env ]; then
  install -m 640 -o root -g sentinel pi/pcap.env.example /etc/network-sentinel/pcap.env
  echo "Created /etc/network-sentinel/pcap.env. Verify NS_CAPTURE_INTERFACE, then run this script again." >&2
  exit 0
fi
if grep -q 'replace-with-a-long-random-secret' /etc/network-sentinel/mqtt.env; then
  echo "Replace the example MQTT password in /etc/network-sentinel/mqtt.env, then run this script again." >&2
  exit 1
fi
install -m 644 pi/systemd/network-sentinel-mqtt.service /etc/systemd/system/
install -m 644 pi/systemd/network-sentinel-capture.service /etc/systemd/system/
install -m 644 pi/systemd/network-sentinel-pcap-export.service /etc/systemd/system/
install -m 644 pi/systemd/network-sentinel-health.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now network-sentinel-mqtt network-sentinel-capture network-sentinel-pcap-export network-sentinel-health
systemctl status --no-pager network-sentinel-mqtt network-sentinel-capture network-sentinel-pcap-export network-sentinel-health
