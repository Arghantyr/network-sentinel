"""Durable, bounded SQLite queue for bridge MQTT payloads."""
from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from pathlib import Path
from typing import Callable


class SpoolFull(RuntimeError):
    pass


class Spool:
    def __init__(self, path: str, max_bytes: int = 1_073_741_824) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY, topic TEXT NOT NULL, payload BLOB NOT NULL,
            created_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '')""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS quarantine (
            id INTEGER PRIMARY KEY, topic TEXT NOT NULL, payload BLOB NOT NULL,
            created_at REAL NOT NULL, quarantined_at REAL NOT NULL, reason TEXT NOT NULL)""")

    def close(self) -> None:
        self.db.close()

    def size_bytes(self) -> int:
        row = self.db.execute("SELECT COALESCE(SUM(length(payload)), 0) FROM pending").fetchone()
        return int(row[0])

    def enqueue(self, topic: str, payload: bytes) -> int:
        if self.size_bytes() + len(payload) > self.max_bytes:
            raise SpoolFull("bridge spool is full")
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO pending(topic,payload,created_at,next_attempt) VALUES(?,?,?,?)",
            (topic, sqlite3.Binary(payload), now, now),
        )
        return int(cur.lastrowid)

    def claim(self, lease_seconds: int = 60) -> tuple | None:
        now = time.time()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT id,topic,payload,attempts FROM pending WHERE next_attempt<=? AND lease_until<=? ORDER BY id LIMIT 1",
                (now, now),
            ).fetchone()
            if row:
                self.db.execute("UPDATE pending SET lease_until=? WHERE id=?", (now + lease_seconds, row[0]))
            self.db.execute("COMMIT")
            return row
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def succeed(self, item_id: int) -> None:
        self.db.execute("DELETE FROM pending WHERE id=?", (item_id,))

    def retry(self, item_id: int, attempts: int, error: str, base: int = 5, maximum: int = 3600) -> None:
        delay = min(maximum, base * (2 ** min(attempts, 10))) * random.uniform(0.8, 1.2)
        self.db.execute("UPDATE pending SET attempts=?, next_attempt=?, lease_until=0, last_error=? WHERE id=?",
                        (attempts + 1, time.time() + delay, error[:500], item_id))

    def quarantine(self, item_id: int, reason: str) -> None:
        now = time.time()
        self.db.execute("INSERT INTO quarantine(id,topic,payload,created_at,quarantined_at,reason) SELECT id,topic,payload,created_at,?,? FROM pending WHERE id=?",
                        (now, reason[:500], item_id))
        self.succeed(item_id)

    def depth(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM pending").fetchone()[0])


def decode_payload(payload: bytes) -> dict:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    return value
