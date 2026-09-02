import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import VideoToSkillError
from .provenance import write_json


SCHEMA_VERSION = 1
STAGES = ("source", "probe", "transcript", "frames", "ocr", "finalize")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.database = root / "workspace.sqlite3"
        self.progress_file = root / "progress.json"

    def initialize(self, source: str, configuration: dict, resume: bool) -> None:
        if resume and not self.database.is_file():
            raise VideoToSkillError(f"No resumable workspace exists at: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stages (
                    name TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'complete', 'failed')),
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            existing_source = self._meta(connection, "source")
            existing_config = self._meta(connection, "configuration")
            encoded_config = json.dumps(configuration, sort_keys=True)
            if resume:
                if existing_source != source or existing_config != encoded_config:
                    raise VideoToSkillError(
                        "Resume source or extraction settings do not match the existing workspace"
                    )
            else:
                connection.execute("DELETE FROM workspace_meta")
                connection.execute("DELETE FROM stages")
                connection.execute("DELETE FROM events")
                self._set_meta(connection, "schema_version", str(SCHEMA_VERSION))
                self._set_meta(connection, "source", source)
                self._set_meta(connection, "configuration", encoded_config)
                self._set_meta(connection, "created_at", _now())
                connection.executemany(
                    "INSERT INTO stages(name, status, updated_at) VALUES (?, 'pending', ?)",
                    ((stage, _now()) for stage in STAGES),
                )
        self.write_progress()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _meta(connection: sqlite3.Connection, key: str) -> str | None:
        row = connection.execute("SELECT value FROM workspace_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    @staticmethod
    def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            "INSERT OR REPLACE INTO workspace_meta(key, value) VALUES (?, ?)", (key, value)
        )

    def complete(self, stage: str, detail: dict | None = None) -> None:
        self._update(stage, "complete", detail or {})

    def running(self, stage: str) -> None:
        self._update(stage, "running", {})

    def fail(self, stage: str, message: str) -> None:
        self._update(stage, "failed", {"error": message}, message)

    def is_complete(self, stage: str) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM stages WHERE name = ?", (stage,)).fetchone()
        return bool(row and row["status"] == "complete")

    def detail(self, stage: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT detail_json FROM stages WHERE name = ?", (stage,)).fetchone()
        return json.loads(row["detail_json"]) if row else {}

    def _update(self, stage: str, status: str, detail: dict, message: str | None = None) -> None:
        if stage not in STAGES:
            raise VideoToSkillError(f"Unknown workspace stage: {stage}")
        now = _now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE stages SET status = ?, detail_json = ?, updated_at = ? WHERE name = ?",
                (status, json.dumps(detail, sort_keys=True), now, stage),
            )
            connection.execute(
                "INSERT INTO events(stage, status, message, created_at) VALUES (?, ?, ?, ?)",
                (stage, status, message, now),
            )
        self.write_progress()

    def report(self) -> dict:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name, status, detail_json, updated_at FROM stages ORDER BY rowid"
            ).fetchall()
            source = self._meta(connection, "source")
        complete = sum(row["status"] == "complete" for row in rows)
        return {
            "schema_version": SCHEMA_VERSION,
            "source": source,
            "complete_stages": complete,
            "total_stages": len(rows),
            "percent_complete": round(complete / len(rows) * 100, 1) if rows else 0.0,
            "stages": [
                {
                    "name": row["name"],
                    "status": row["status"],
                    "detail": json.loads(row["detail_json"]),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ],
        }

    def write_progress(self) -> None:
        write_json(self.progress_file, self.report())


def workspace_report(root: Path) -> dict:
    workspace = Workspace(root)
    if not workspace.database.is_file():
        raise VideoToSkillError(f"No workspace database found at: {root}")
    return workspace.report()
