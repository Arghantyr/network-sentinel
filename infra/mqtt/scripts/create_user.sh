#!/usr/bin/env bash
# Create or replace one broker user. Requires Docker and prompts for its password.
set -euo pipefail
cd "$(dirname "$0")/.."
USER=${1:?"usage: $0 DEVICE_ID_OR_USERNAME"}
mkdir -p passwords
if [ -f passwords/passwd ]; then
  docker run --rm -it -v "$PWD/passwords:/work" eclipse-mosquitto:2 \
    mosquitto_passwd /work/passwd "$USER"
else
  docker run --rm -it -v "$PWD/passwords:/work" eclipse-mosquitto:2 \
    mosquitto_passwd -c /work/passwd "$USER"
fi
chmod 600 passwords/passwd
