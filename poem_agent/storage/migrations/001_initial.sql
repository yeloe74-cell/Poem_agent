"""Explicit versioned SQL schema for deployments that track migration files."""
CREATE TABLE IF NOT EXISTS migration_log (
 version INTEGER PRIMARY KEY,
 applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO migration_log(version) VALUES(1);
