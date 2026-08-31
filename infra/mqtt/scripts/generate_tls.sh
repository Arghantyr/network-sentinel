#!/usr/bin/env bash
# Generate a development-only private CA and server certificate for Mosquitto.
set -euo pipefail
cd "$(dirname "$0")/.."
HOSTNAME=${1:?"usage: $0 MQTT_DNS_NAME (for example mqtt.example.net)"}
mkdir -p certs
umask 077
openssl genrsa -out certs/ca.key 4096
openssl req -x509 -new -key certs/ca.key -sha256 -days 3650 -out certs/ca.crt \
  -subj "/CN=Network Sentinel development CA"
openssl genrsa -out certs/server.key 2048
openssl req -new -key certs/server.key -out certs/server.csr -subj "/CN=${HOSTNAME}"
# `mosquitto` lets the colocated Docker bridge validate TLS over the Compose network.
# The supplied hostname remains the name used by Pi clients.
printf 'subjectAltName=DNS:%s,DNS:mosquitto\nextendedKeyUsage=serverAuth\n' "$HOSTNAME" > certs/server.ext
openssl x509 -req -in certs/server.csr -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
  -out certs/server.crt -days 825 -sha256 -extfile certs/server.ext
rm certs/server.csr certs/server.ext certs/ca.srl
printf 'Created certs/. Copy certs/ca.crt securely to the Pi. Never copy ca.key.\n'
