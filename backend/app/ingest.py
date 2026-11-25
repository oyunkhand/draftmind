"""Load a normalized Dataset into SQLite (idempotent: replaces esports tables, keeps coach state)."""
import hashlib
import json
import sqlite3
from typing import Optional

from .adapters.base import Dataset

ESPORTS_TABLES = ["teams", "players", "series", "matches", "draft_actions", "participants",
                  "priors_matchup", "priors_synergy"]


def fingerprint(data: Dataset) -> str:
    h = hashlib.sha1()
    h.update(data.get("source", "").encode())
    h.update(str(len(data["matches"])).encode())
    for m in data["matches"][:5] + data["matches"][-5:]:
        h.update(json.dumps(m, sort_keys=True).encode())
    return h.hexdigest()[:16]


def ingest(conn: sqlite3.Connection, data: Dataset, info: Optional[dict] = None) -> dict:
    fp = fingerprint(data)
    cur = conn.execute("SELECT value FROM settings WHERE key='dataset'").fetchone()
    if cur and json.loads(cur[0]).get("fingerprint") == fp:
        return json.loads(cur[0])
    for t in ESPORTS_TABLES:
        conn.execute(f"DELETE FROM {t}")
    for t in data["teams"]:
        conn.execute("INSERT INTO teams VALUES (?,?,?,?,?)",
                     (t["id"], t["name"], t.get("tag"), t.get("color"), t.get("region")))
        for p in t.get("players", []):
            conn.execute("INSERT INTO players VALUES (?,?,?,?)", (p["id"], t["id"], p["name"], p.get("role")))
    for s in data.get("series", []):
        score = s.get("score") or [None, None]
        conn.execute("INSERT INTO series VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (s["id"], s.get("tournament"), s.get("date"), s.get("best_of"), int(bool(s.get("fearless"))),
                      s.get("team_a"), s.get("team_b"), s.get("winner"), score[0], score[1]))
    for m in data["matches"]:
        o = m.get("objectives") or {}
        conn.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (m["id"], m.get("series_id"), m.get("game_number"), m["date"], m.get("patch"), m.get("tournament"),
                      m["blue_team"], m["red_team"], m["winner"], m.get("duration_s"), o.get("first_blood"),
                      o.get("first_dragon"), o.get("first_herald"), o.get("first_tower"), o.get("gold_diff_15")))
        for a in m.get("draft", []):
            conn.execute("INSERT INTO draft_actions VALUES (?,?,?,?,?,?)",
                         (m["id"], a["seq"], a.get("side"), a["type"], a.get("team"), a["champion"]))
        for p in m.get("participants", []):
            conn.execute("INSERT INTO participants VALUES (?,?,?,?,?,?,?)",
                         (m["id"], p["team"], p.get("side"), p["player"], p.get("role"), p["champion"],
                          int(p["team"] == m["winner"])))
    pri = data.get("priors") or {}
    conn.executemany("INSERT OR REPLACE INTO priors_matchup VALUES (?,?,?,?)",
                     [(x["a"], x["b"], x["wr_a"], x["games"]) for x in pri.get("matchups", [])])
    conn.executemany("INSERT OR REPLACE INTO priors_synergy VALUES (?,?,?,?)",
                     [(x["a"], x["b"], x["wr"], x["games"]) for x in pri.get("synergies", [])])
    meta = {"fingerprint": fp, "source": data.get("source"), "teams": len(data["teams"]),
            "matches": len(data["matches"]), "series": len(data.get("series", [])), "adapter": info or {}}
    conn.execute("INSERT OR REPLACE INTO settings VALUES ('dataset', ?)", (json.dumps(meta),))
    conn.commit()
    return meta
