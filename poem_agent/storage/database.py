"""SQLite persistence; callers use repositories instead of embedding SQL."""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, description TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, plan TEXT NOT NULL DEFAULT '[]', retries INTEGER NOT NULL DEFAULT 0, error TEXT, result TEXT, verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS poems(id TEXT PRIMARY KEY, text TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE, language TEXT NOT NULL, author TEXT, source TEXT, emotion TEXT, themes TEXT NOT NULL DEFAULT '[]', style TEXT, quality REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, title TEXT NOT NULL, role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, poem_id TEXT NOT NULL, channel_id TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, approved_by INTEGER, scheduled_at TEXT, platform_message_id TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, published_at TEXT, FOREIGN KEY(poem_id) REFERENCES poems(id), FOREIGN KEY(channel_id) REFERENCES channels(id));
CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, confidence REAL NOT NULL, source TEXT, verified INTEGER NOT NULL DEFAULT 0, expires_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL, target TEXT, outcome TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS image_cache(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_draft_schedule ON drafts(status,scheduled_at);
CREATE INDEX IF NOT EXISTS idx_task_state ON tasks(state,priority);
CREATE INDEX IF NOT EXISTS idx_memory_owner ON memories(owner_id,kind);
"""


class Database:
    def __init__(self, path: str):
        self.path = path

    def connect(self):
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA user_version=1")

    def execute(self, sql: str, values: tuple = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(sql, values)
            return int(cursor.lastrowid or 0)

    def one(self, sql: str, values: tuple = ()):
        with self.connect() as conn:
            return conn.execute(sql, values).fetchone()

    def all(self, sql: str, values: tuple = ()):
        with self.connect() as conn:
            return conn.execute(sql, values).fetchall()

    def reset(self):
        with self.connect() as conn:
            conn.executescript("DROP TABLE IF EXISTS drafts; DROP TABLE IF EXISTS channels; DROP TABLE IF EXISTS poems; DROP TABLE IF EXISTS tasks; DROP TABLE IF EXISTS memories; DROP TABLE IF EXISTS audit; DROP TABLE IF EXISTS image_cache;")
            conn.executescript(SCHEMA)
