#!/usr/bin/env bash
# Start the TLS MQTT broker only after its required credentials exist.
set -euo pipefail
cd "$(dirname "$0")/.."
for file in certs/ca.crt certs/server.crt certs/server.key passwords/passwd; do
  [ -s "$file" ] || { echo "Missing $file. Read README.md MQTT broker setup." >&2; exit 1; }
done
docker compose up -d
docker compose ps
