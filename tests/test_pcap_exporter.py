import os
import time
from pathlib import Path

from pi.pcap_exporter import completed_captures, file_sha256, parse_tshark_line


def test_parse_tshark_line_exports_only_allowlisted_metadata() -> None:
    event = parse_tshark_line("1735689600.25\t60\t6\t443\t\t1\t1\t0", "pi-4", "capture.pcapng", 7)
    assert event is not None
    assert event["device_id"] == "pi-4"
    assert event["destination_port"] == 443
    assert event["frame_length"] == 60
    assert event["tcp_syn"] is True
    assert event["tcp_ack"] is True
    assert event["tcp_reset"] is False
    assert "ip_address" not in event
    assert "payload" not in event


def test_completed_captures_skips_active_newest_file(tmp_path: Path) -> None:
    old = tmp_path / "old.pcapng"
    active = tmp_path / "active.pcapng"
    old.write_bytes(b"old")
    time.sleep(0.01)
    active.write_bytes(b"active")
    os.utime(old, (time.time() - 60, time.time() - 60))
    paths = list(completed_captures(tmp_path, minimum_age=1, seen=set()))
    assert paths == [old]
    assert file_sha256(old) != file_sha256(active)
