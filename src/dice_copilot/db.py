from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','in_progress','applied','skipped','blocked')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status_id ON jobs(status, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.execute("UPDATE jobs SET status='pending' WHERE status='in_progress'")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection:
            yield self.connection

    def add(self, url: str, title: str = "", company: str = "", notes: str = "") -> bool:
        stamp = now()
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO jobs(url,title,company,notes,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (url, title, company, notes, stamp, stamp),
            )
        return cursor.rowcount == 1

    def list(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return list(self.connection.execute("SELECT * FROM jobs WHERE status=? ORDER BY id", (status,)))
        return list(self.connection.execute("SELECT * FROM jobs ORDER BY id"))

    def count(self, job_id: int | None = None, status: str | None = None) -> int:
        if job_id is not None:
            return self.connection.execute("SELECT COUNT(*) FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
        if status is not None:
            return self.connection.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (status,)).fetchone()[0]
        return self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def delete(self, job_id: int | None = None, status: str | None = None) -> int:
        with self.transaction() as connection:
            if job_id is not None:
                cursor = connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            elif status is not None:
                cursor = connection.execute("DELETE FROM jobs WHERE status=?", (status,))
            else:
                cursor = connection.execute("DELETE FROM jobs")
        return cursor.rowcount

    def claim_next(self, job_id: int | None = None) -> sqlite3.Row | None:
        with self.transaction() as connection:
            if job_id is None:
                row = connection.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
            else:
                row = connection.execute("SELECT * FROM jobs WHERE status='pending' AND id=?", (job_id,)).fetchone()
            if row:
                connection.execute(
                    "UPDATE jobs SET status='in_progress', attempts=attempts+1, updated_at=? WHERE id=?",
                    (now(), row["id"]),
                )
        return row

    def finish(self, job_id: int, status: str, error: str = "") -> None:
        if status not in {"pending", "applied", "skipped", "blocked"}:
            raise ValueError(f"Invalid final status: {status}")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, last_error=?, updated_at=? WHERE id=?",
                (status, error[:1000], now(), job_id),
            )

    def repair_false_applied(self, reason: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status='pending', last_error='', updated_at=? "
                "WHERE status='applied' AND last_error=?",
                (now(), reason),
            )
        return cursor.rowcount

    def retry_blocked_prefix(self, error_prefix: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status='pending', last_error='', updated_at=? "
                "WHERE status='blocked' AND last_error LIKE ?",
                (now(), error_prefix + "%"),
            )
        return cursor.rowcount
