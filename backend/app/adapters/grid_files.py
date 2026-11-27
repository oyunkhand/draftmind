"""Adapter for the Sky's The Limit 2026 GRID data starter (local clone of
github.com/cloud9esports/stl-hackathon-2026-grid-starter).

The data is licensed for the hackathon only and must never be committed or redistributed, so this
adapter reads it from a directory *outside* the project (STL_DATA_DIR) and caches the normalized
dataset in an ignored directory (backend/var/).

Sources per game:
- meta/games.csv    -> series, game number, date, patch, sides, winner, session validity
- meta/rosters.csv  -> player -> champion per game (GRID gives no roles; they are inferred)
- lol/events_*.jsonl.zst -> the ordered draft (team-banned/picked-character) and first objectives
"""
import csv
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from itertools import permutations
from pathlib import Path
from typing import Dict, List, Optional

from .. import config
from ..champions import ROLES, resolve, roles_of
from .base import DataAdapter, Dataset

log = logging.getLogger("draftmind.grid_files")

CACHE_VERSION = 4
_DRAFT_TYPES = ("team-banned-character", "team-picked-character")
_OBJECTIVES = {
    "player-killed-player": "first_blood",
    "player-completed-slayDragon": "first_dragon",
    "player-completed-slayVoidGrub": "first_herald",
    "player-completed-slayRiftHerald": "first_herald",
    "player-destroyed-tower": "first_tower",
}
_NEEDLES = _DRAFT_TYPES + tuple(_OBJECTIVES) + ("team-won-game",)
_TAGS = {"Cloud9 Kia": "C9", "Cloud9": "C9", "Team Liquid": "TL", "Team Liquid Alienware": "TL", "100 Thieves": "100", "FlyQuest": "FLY",
         "Shopify Rebellion": "SR", "Dignitas": "DIG", "LYON": "LYON", "Disguised": "DSG", "T1": "T1",
         "Gen.G Esports": "GEN", "Hanwha Life Esports": "HLE", "G2 Esports": "G2", "Fnatic": "FNC",
         "Team Vitality": "VIT", "Karmine Corp": "KC", "Movistar KOI": "MKOI"}
_COLORS = ["#38bdf8", "#f97316", "#a78bfa", "#22c55e", "#f43f5e", "#eab308", "#14b8a6", "#ec4899",
           "#6366f1", "#84cc16", "#06b6d4", "#fb7185"]


def data_dir() -> Path:
    return Path(config.STL_DATA_DIR)


def available() -> bool:
    d = data_dir()
    return (d / "meta" / "games.csv").is_file() and (d / "lol" / "series.csv").is_file()


def _rows(path: Path, title: Optional[str] = "lol") -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if title is None or r.get("title", title) == title]


def _open_zst(path: Path):
    try:
        from compression import zstd  # Python 3.14+
        return zstd.open(path, "rt", encoding="utf-8")
    except ImportError:
        import zstandard
        return zstandard.open(path, "rt", encoding="utf-8")


def _region(event: str) -> str:
    for key in ("LTA North", "LTA South", "LTA", "LCS", "LCK", "LEC", "MSI", "Worlds", "First Stand"):
        if key.lower() in event.lower():
            return key
    return event.split(" - ")[0]


def _tag(name: str, used: set) -> str:
    tag = _TAGS.get(name)
    if not tag:
        words = [w for w in re.split(r"[\s\-.]+", name) if w and w.lower() not in ("esports", "gaming", "team")]
        tag = "".join(w[0] for w in words[:4]).upper() if len(words) > 1 else (words[0] if words else name)[:4].upper()
    base, n = tag, 2
    while tag in used:
        tag, n = f"{base}{n}", n + 1
    used.add(tag)
    return tag


class GridFilesAdapter(DataAdapter):
    name = "grid-files"

    def __init__(self, root: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.root = Path(root or data_dir())
        self.cache_dir = Path(cache_dir or config.CACHE_DIR)
        self.info: Dict = {}

    # ------------------------------------------------------------------ public
    def load(self) -> Dataset:
        key = self._fingerprint()
        cache = self.cache_dir / f"grid_dataset_{key}.json"
        if cache.is_file():
            data = json.loads(cache.read_text())
        else:
            data = self._build()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            for old in self.cache_dir.glob("grid_dataset_*.json"):
                old.unlink()
            cache.write_text(json.dumps(data))
        self.info = {"name": self.name, "path": str(self.root), "series": len(data["series"]),
                     "matches": len(data["matches"]), "teams": len(data["teams"]),
                     "note": "Official GRID data (Sky's The Limit 2026 starter), read from a local clone."}
        return data

    def describe(self):
        return self.info or {"name": self.name, "path": str(self.root)}

    # ------------------------------------------------------------------ build
    def _fingerprint(self) -> str:
        h = hashlib.sha1(str(CACHE_VERSION).encode())
        for p in (self.root / "meta" / "games.csv", self.root / "meta" / "rosters.csv", self.root / "lol" / "series.csv"):
            st = p.stat()
            h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
        return h.hexdigest()[:12]

    def _build(self) -> Dataset:
        series_rows = {r["series_id"]: r for r in _rows(self.root / "lol" / "series.csv", None)}
        games = [g for g in _rows(self.root / "meta" / "games.csv")
                 if g["session_valid"] == "True" and g["finished"] == "True" and g["winner_team_id"]]
        valid_ids = {g["game_id"] for g in games}
        roster: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
        for r in _rows(self.root / "meta" / "rosters.csv"):
            if r["game_id"] in valid_ids and r["participation_status"] == "active":
                roster[r["game_id"]][r["team_id"]].append(r)

        drafts: Dict[str, List[dict]] = {}
        objectives: Dict[str, Dict[str, Optional[str]]] = {}
        for sid in sorted({g["series_id"] for g in games}):
            row = series_rows.get(sid)
            if not row:
                continue
            path = self.root / row["file"]
            if not path.is_file():
                log.warning("missing feed %s", path)
                continue
            self._scan_feed(path, valid_ids, drafts, objectives)

        # ---- matches (roles inferred in two passes: champion fit, then player's usual role)
        tmp = []
        player_votes: Dict[str, Counter] = defaultdict(Counter)
        for g in games:
            d = drafts.get(g["game_id"])
            if not d or len(d) != 20:
                continue
            sides = {g["team1_id"]: g["team1_side"], g["team2_id"]: g["team2_side"]}
            if sorted(sides.values()) != ["blue", "red"]:
                continue
            parts = []
            for team_id, side in sides.items():
                players = roster[g["game_id"]].get(team_id, [])
                if len(players) != 5:
                    break
                for p in players:
                    parts.append({"team": team_id, "side": side, "player": p["player_id"],
                                  "player_name": p["player_name"], "champion": resolve(p["character_name"])})
            if len(parts) != 10:
                continue
            for team_id in sides:
                tp = [p for p in parts if p["team"] == team_id]
                for p, role in zip(tp, self._assign(tp, None)):
                    player_votes[p["player"]][role] += 1
            tmp.append((g, sides, d, parts))
        primary = {pid: v.most_common(1)[0][0] for pid, v in player_votes.items()}

        matches, team_names, team_events, team_last = [], {}, defaultdict(Counter), {}
        for g, sides, d, parts in tmp:
            for team_id in sides:
                tp = [p for p in parts if p["team"] == team_id]
                for p, role in zip(tp, self._assign(tp, primary)):
                    p["role"] = role
            blue = next(t for t, s in sides.items() if s == "blue")
            red = next(t for t, s in sides.items() if s == "red")
            srow = series_rows[g["series_id"]]
            for tid, name in ((g["team1_id"], g["team1_name"]), (g["team2_id"], g["team2_name"])):
                team_names[tid] = name
                team_events[tid][srow["event"]] += 1
                team_last[tid] = max(team_last.get(tid, ""), g["started_at"])
            obj = objectives.get(g["game_id"], {})
            matches.append({
                "id": g["game_id"], "series_id": g["series_id"], "game_number": int(g["game_number"]),
                "date": g["started_at"][:19], "patch": g["patch"],
                "tournament": f"{srow['event']} — {srow['stage']}".strip(" —"),
                "blue_team": blue, "red_team": red, "winner": g["winner_team_id"], "duration_s": None,
                "draft": [{"seq": i, "side": sides.get(a["team"], "blue"), "type": a["type"], "team": a["team"],
                           "champion": a["champion"]} for i, a in enumerate(d)],
                "participants": [{k: p[k] for k in ("team", "side", "player", "role", "champion")} for p in parts],
                "objectives": {k: obj.get(k) for k in ("first_blood", "first_dragon", "first_herald", "first_tower")}
                              | {"gold_diff_15": None},
            })

        # ---- series
        by_series: Dict[str, List[dict]] = defaultdict(list)
        for m in matches:
            by_series[m["series_id"]].append(m)
        series = []
        for sid, ms in by_series.items():
            ms.sort(key=lambda m: m["game_number"])
            a, b = ms[0]["blue_team"], ms[0]["red_team"]
            wins = Counter(m["winner"] for m in ms)
            need = max(wins.values())
            srow = series_rows[sid]
            series.append({"id": sid, "tournament": f"{srow['event']} — {srow['stage']}".strip(" —"),
                           "date": ms[0]["date"], "best_of": max(1, 2 * need - 1), "fearless": True,
                           "team_a": a, "team_b": b, "winner": wins.most_common(1)[0][0],
                           "score": [wins.get(a, 0), wins.get(b, 0)], "games": [m["id"] for m in ms]})

        # ---- teams: latest five players by role
        # a player belongs to the team they played for most recently (transfers happen mid-dataset)
        seen: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
        last_team: Dict[str, tuple] = {}
        last_role: Dict[tuple, tuple] = {}
        names = {}
        for m in matches:
            for p in m["participants"]:
                if m["date"] > last_role.get((p["team"], p["player"]), ("",))[0]:
                    last_role[(p["team"], p["player"])] = (m["date"], p["role"])
                prev = seen[p["team"]][p["role"]].get(p["player"], "")
                seen[p["team"]][p["role"]][p["player"]] = max(prev, m["date"])
                if m["date"] > last_team.get(p["player"], ("",))[0]:
                    last_team[p["player"]] = (m["date"], p["team"])
        latest: Dict[str, Dict[str, tuple]] = defaultdict(dict)
        for tid, by_role in seen.items():
            for role, players in by_role.items():
                for pid, date in sorted(players.items(), key=lambda kv: kv[1], reverse=True):
                    if last_team[pid][1] == tid and last_role[(tid, pid)][1] == role:
                        latest[tid][role] = (date, pid)
                        break
        for g, sides, d, parts in tmp:
            for p in parts:
                names[p["player"]] = p["player_name"]
        used, teams = set(), []
        for i, tid in enumerate(sorted(team_names, key=lambda t: team_names[t].lower())):
            name = team_names[tid]
            region = _region(team_events[tid].most_common(1)[0][0])
            teams.append({"id": tid, "name": name, "tag": _tag(name, used), "region": region,
                          "color": "#00aeef" if name.startswith("Cloud9") else _COLORS[i % len(_COLORS)],
                          "players": [{"id": latest[tid][r][1], "name": names.get(latest[tid][r][1], "?"), "role": r}
                                      for r in ROLES if r in latest[tid]]})
        log.info("GRID files: %d teams, %d series, %d games", len(teams), len(series), len(matches))
        return {"source": "grid", "teams": teams, "series": series, "matches": matches, "priors": {},
                "meta": {"source": "grid-files", "data_dir": str(self.root)}}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _assign(players: List[dict], primary: Optional[Dict[str, str]]) -> List[str]:
        """Best role permutation for five players: champion role fit, plus the player's usual role."""
        best, best_score = list(ROLES), -1e9
        for perm in permutations(ROLES):
            s = 0.0
            for p, r in zip(players, perm):
                rs = roles_of(p["champion"])
                s += (1.0 - 0.2 * rs.index(r)) if r in rs else -2.0
                if primary and primary.get(p["player"]) == r:
                    s += 1.5
            if s > best_score:
                best, best_score = list(perm), s
        return best

    @staticmethod
    def _scan_feed(path: Path, valid_ids: set, drafts: dict, objectives: dict) -> None:
        with _open_zst(path) as f:
            for line in f:
                if not any(n in line for n in _NEEDLES):
                    continue
                env = json.loads(line)
                for e in env.get("events", []):
                    t = e.get("type")
                    if t not in _NEEDLES:
                        continue
                    games = (e.get("seriesStateDelta") or {}).get("games") or []
                    gid = games[0].get("id") if games else None
                    if gid not in valid_ids:
                        continue
                    if t in _DRAFT_TYPES:
                        d = drafts.setdefault(gid, [])
                        if len(d) < 20:
                            d.append({"type": "ban" if "banned" in t else "pick",
                                                "team": e["actor"]["id"],
                                                "champion": resolve(e["target"]["state"]["name"])})
                    elif t in _OBJECTIVES:
                        key = _OBJECTIVES[t]
                        o = objectives.setdefault(gid, {})
                        if key not in o:
                            team = (e["actor"].get("state") or {}).get("teamId")
                            if team:
                                o[key] = team
