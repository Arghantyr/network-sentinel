from pathlib import Path

import pytest

from services.gcp_spool import Spool, SpoolFull


class Sink:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def packets(self, payload):
        self.calls += 1
        if self.fail:
            raise RuntimeError("temporary outage")


def test_spool_survives_reopen_and_deletes_on_success(tmp_path: Path):
    path = tmp_path / "spool.sqlite3"
    first = Spool(str(path), max_bytes=1000)
    item = first.enqueue("network-sentinel/pi-4/telemetry/packets", b'{"packets": []}')
    first.close()
    second = Spool(str(path), max_bytes=1000)
    claimed = second.claim()
    assert claimed[:2] == (item, "network-sentinel/pi-4/telemetry/packets")
    second.succeed(item)
    assert second.depth() == 0
    second.close()


def test_spool_retries_and_reclaims_expired_lease(tmp_path: Path):
    spool = Spool(str(tmp_path / "spool.sqlite3"))
    item = spool.enqueue("topic", b"{}")
    claimed = spool.claim(lease_seconds=0)
    assert claimed[0] == item
    spool.retry(item, claimed[3], "offline", base=1, maximum=1)
    assert spool.claim() is None
    spool.db.execute("UPDATE pending SET next_attempt=0")
    assert spool.claim()[0] == item
    spool.close()


def test_spool_rejects_payload_over_limit(tmp_path: Path):
    spool = Spool(str(tmp_path / "spool.sqlite3"), max_bytes=2)
    with pytest.raises(SpoolFull):
        spool.enqueue("topic", b"123")
    spool.close()


def test_quarantine_removes_poison_message(tmp_path: Path):
    spool = Spool(str(tmp_path / "spool.sqlite3"))
    item = spool.enqueue("topic", b"not-json")
    spool.quarantine(item, "bad JSON")
    assert spool.depth() == 0
    assert spool.db.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 1
    spool.close()
