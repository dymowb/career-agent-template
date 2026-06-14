"""
db/schema.py — SQLite schema and connection helper
"""
import sqlite3
from config import DB_PATH


DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    title             TEXT,
    company           TEXT,
    url               TEXT,
    discovered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score             REAL,
    recommendation    TEXT,
    status            TEXT,
    review_pack_path  TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    jobs_found   INTEGER DEFAULT 0,
    jobs_passed  INTEGER DEFAULT 0,
    jobs_emailed INTEGER DEFAULT 0,
    errors       TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(DDL)
    print(f"[db] initialised at {DB_PATH}")
