#!/usr/bin/env bash
# Continuous, bounded PCAP capture. Invoked by systemd; do not run as an untrusted user.
set -euo pipefail
: "${NS_CAPTURE_INTERFACE:?Missing NS_CAPTURE_INTERFACE}"
: "${NS_PCAP_DIRECTORY:?Missing NS_PCAP_DIRECTORY}"
mkdir -p "$NS_PCAP_DIRECTORY"
exec /usr/bin/dumpcap -i "$NS_CAPTURE_INTERFACE" -p -f "$NS_CAPTURE_FILTER" \
  -b "duration:${NS_PCAP_ROTATE_SECONDS:-60}" -b "files:${NS_PCAP_MAX_FILES:-60}" \
  -w "$NS_PCAP_DIRECTORY/capture.pcapng"
