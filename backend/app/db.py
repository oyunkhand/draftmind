"""SQLite storage. Normalized esports tables (filled by a DataAdapter) + coach app state."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, tag TEXT, color TEXT, region TEXT
);
CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY, team_id TEXT NOT NULL, name TEXT NOT NULL, role TEXT
);
CREATE TABLE IF NOT EXISTS series (
  id TEXT PRIMARY KEY, tournament TEXT, date TEXT, best_of INTEGER, fearless INTEGER,
  team_a TEXT, team_b TEXT, winner TEXT, score_a INTEGER, score_b INTEGER
);
CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY, series_id TEXT, game_number INTEGER, date TEXT, patch TEXT, tournament TEXT,
  blue_team TEXT, red_team TEXT, winner TEXT, duration_s INTEGER,
  first_blood TEXT, first_dragon TEXT, first_herald TEXT, first_tower TEXT, gold_diff_15 INTEGER
);
CREATE INDEX IF NOT EXISTS ix_matches_date ON matches(date);
CREATE TABLE IF NOT EXISTS draft_actions (
  match_id TEXT, seq INTEGER, side TEXT, type TEXT, team_id TEXT, champion TEXT,
  PRIMARY KEY (match_id, seq)
);
CREATE TABLE IF NOT EXISTS participants (
  match_id TEXT, team_id TEXT, side TEXT, player_id TEXT, role TEXT, champion TEXT, win INTEGER
);
CREATE INDEX IF NOT EXISTS ix_part_player ON participants(player_id);
CREATE TABLE IF NOT EXISTS priors_matchup (a TEXT, b TEXT, wr_a REAL, games INTEGER, PRIMARY KEY (a, b));
CREATE TABLE IF NOT EXISTS priors_synergy (a TEXT, b TEXT, wr REAL, games INTEGER, PRIMARY KEY (a, b));

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS coach_series (
  id TEXT PRIMARY KEY, our_team TEXT, opponent TEXT, best_of INTEGER, fearless_mode TEXT,
  title TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS draft_sessions (
  id TEXT PRIMARY KEY, series_id TEXT, game_number INTEGER, our_team TEXT, opponent TEXT,
  our_side TEXT, state TEXT, result TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, series_id TEXT, our_team TEXT, opponent TEXT,
  step INTEGER, action_type TEXT, suggested_champion TEXT, suggested_rank INTEGER, suggested_score REAL,
  decision TEXT, final_champion TEXT, note TEXT, top_suggestions TEXT, created_at TEXT
);
"""

_lock = threading.RLock()


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
    return _conn


def set_conn(conn: sqlite3.Connection) -> None:
    """Used by tests to point the app at an isolated database."""
    global _conn
    _conn = conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    with _lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows(sql: str, params: tuple = ()) -> list:
    with _lock:
        return [dict(r) for r in get_conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> Optional[dict]:
    with _lock:
        r = get_conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def get_setting(key: str, default: Any = None) -> Any:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
