import json
from pathlib import Path

from pi.health_reporter import health_report, last_export
from pi.pcap_exporter import _save_export_health


def test_health_report_is_aggregate_and_allowlisted(tmp_path: Path) -> None:
    pcap = tmp_path / "pcap"
    pcap.mkdir()
    stats = tmp_path / "sys" / "eth0" / "statistics"
    stats.mkdir(parents=True)
    (stats / "rx_dropped").write_text("3\n")
    (stats / "tx_dropped").write_text("4\n")
    state = tmp_path / "pcap-export-health.json"
    state.write_text(json.dumps({"exported_at_epoch": 100.0, "export_latency_seconds": 1.5}))
    report = health_report("pi-4", "eth0", pcap, state, tmp_path / "sys")
    assert report["interface_rx_dropped"] == 3
    assert report["interface_tx_dropped"] == 4
    assert report["last_exported_at_epoch"] == 100.0
    assert report["export_latency_seconds"] == 1.5
    assert {"payload", "ip_address", "hostname", "source_pcap"}.isdisjoint(report)


def test_export_health_records_only_timing(tmp_path: Path) -> None:
    state = tmp_path / "health.json"
    _save_export_health(state, 0.25)
    exported_at, latency = last_export(state)
    assert exported_at is not None
    assert latency == 0.25
    assert not (tmp_path / ".health.json.tmp").exists()


def test_missing_export_health_is_unknown(tmp_path: Path) -> None:
    assert last_export(tmp_path / "missing.json") == (None, None)
