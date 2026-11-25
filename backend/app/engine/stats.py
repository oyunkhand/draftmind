"""Aggregated, recency-weighted statistics over a set of matches.

`StatsIndex` is built from normalized match dicts (same shape the adapters produce), so it can
be built over the whole database or over a time-split subset (see backtest.py).
"""
import datetime as dt
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .. import config
from ..champions import ROLES


@dataclass
class Agg:
    games: int = 0
    wins: int = 0
    w: float = 0.0  # recency-weighted games
    ww: float = 0.0  # recency-weighted wins

    def add(self, win: bool, weight: float) -> None:
        self.games += 1
        self.wins += int(win)
        self.w += weight
        self.ww += weight * int(win)

    @property
    def wr(self) -> float:
        return self.wins / self.games if self.games else 0.0


def smoothed(wins: float, games: float, prior: float = 0.5, k: float = 6.0) -> float:
    return (wins + prior * k) / (games + k)


def _parse(d: str) -> dt.datetime:
    return dt.datetime.fromisoformat(d.replace("Z", "+00:00")).replace(tzinfo=None)


class StatsIndex:
    def __init__(self, matches: List[dict], teams: List[dict], priors: Optional[dict] = None,
                 half_life_days: Optional[float] = None):
        self.matches = sorted(matches, key=lambda m: m["date"])
        self.teams = {t["id"]: t for t in teams}
        self.half_life = half_life_days or config.RECENCY_HALF_LIFE_DAYS
        self.ref_date = _parse(self.matches[-1]["date"]) if self.matches else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        self.roster: Dict[str, Dict[str, dict]] = {}
        self.player_name: Dict[str, str] = {}
        for t in teams:
            self.roster[t["id"]] = {p["role"]: p for p in t.get("players", []) if p.get("role") in ROLES}
            for p in t.get("players", []):
                self.player_name[p["id"]] = p["name"]

        self.total_w = 0.0
        self.total_games = 0
        self.champ_pick: Dict[str, Agg] = defaultdict(Agg)
        self.champ_ban_w: Dict[str, float] = defaultdict(float)
        self.champ_ban_n: Dict[str, int] = defaultdict(int)
        self.player_champ: Dict[str, Dict[str, Agg]] = defaultdict(lambda: defaultdict(Agg))
        self.player_total: Dict[str, Agg] = defaultdict(Agg)
        self.team_games: Dict[str, Agg] = defaultdict(Agg)
        self.team_side: Dict[str, Dict[str, Agg]] = defaultdict(lambda: defaultdict(Agg))
        self.team_pick: Dict[str, Dict[str, Agg]] = defaultdict(lambda: defaultdict(Agg))
        self.team_ban: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.banned_against: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # team -> phase key -> champ -> weighted count ; phase keys: ban1, ban2, pick1, pick2, first
        self.team_phase: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.team_phase_n: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.team_first_role: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.team_obj: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        self.team_gold15: Dict[str, List[int]] = defaultdict(list)
        self.team_duration: Dict[str, List[int]] = defaultdict(list)
        self.lane: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])  # (a,b) -> [games, a wins]
        self.pair: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])  # sorted (a,b) -> [games, wins]
        self.player_last: Dict[str, Dict[str, str]] = defaultdict(dict)

        for m in self.matches:
            self._add_match(m)

        pri = priors or {}
        self.prior_matchup: Dict[Tuple[str, str], Tuple[float, int]] = {}
        for x in pri.get("matchups", []):
            self.prior_matchup[(x["a"], x["b"])] = (x["wr_a"], x["games"])
            self.prior_matchup[(x["b"], x["a"])] = (1 - x["wr_a"], x["games"])
        self.prior_synergy: Dict[Tuple[str, str], Tuple[float, int]] = {}
        for x in pri.get("synergies", []):
            self.prior_synergy[tuple(sorted((x["a"], x["b"])))] = (x["wr"], x["games"])
        self._max_presence = max([self.presence(c)[2] for c in self.champ_pick] or [1.0]) or 1.0

    # ------------------------------------------------------------------ build
    def weight(self, date: str) -> float:
        days = max(0.0, (self.ref_date - _parse(date)).total_seconds() / 86400)
        return 0.5 ** (days / self.half_life)

    def _add_match(self, m: dict) -> None:
        w = self.weight(m["date"])
        self.total_w += w
        self.total_games += 1
        blue, red, winner = m["blue_team"], m["red_team"], m["winner"]
        for side, team in (("blue", blue), ("red", red)):
            self.team_games[team].add(team == winner, w)
            self.team_side[team][side].add(team == winner, w)
        by_side_role: Dict[str, Dict[str, str]] = {"blue": {}, "red": {}}
        side_champs: Dict[str, List[str]] = {"blue": [], "red": []}
        for p in m["participants"]:
            win = p["team"] == winner
            self.champ_pick[p["champion"]].add(win, w)
            self.player_champ[p["player"]][p["champion"]].add(win, w)
            self.player_total[p["player"]].add(win, w)
            self.player_last[p["player"]][p["champion"]] = m["date"]
            self.team_pick[p["team"]][p["champion"]].add(win, w)
            by_side_role[p["side"]][p["role"]] = p["champion"]
            side_champs[p["side"]].append(p["champion"])
        for role in ROLES:
            a, b = by_side_role["blue"].get(role), by_side_role["red"].get(role)
            if a and b:
                bw = winner == blue
                self.lane[(a, b)][0] += 1
                self.lane[(a, b)][1] += int(bw)
                self.lane[(b, a)][0] += 1
                self.lane[(b, a)][1] += int(not bw)
        for side, team in (("blue", blue), ("red", red)):
            ch = side_champs[side]
            for i, a in enumerate(ch):
                for b in ch[i + 1:]:
                    k = tuple(sorted((a, b)))
                    self.pair[k][0] += 1
                    self.pair[k][1] += int(team == winner)
        first_seen = set()
        for a in m["draft"]:
            team = a["team"]
            phase = "ban1" if a["seq"] < 6 else "pick1" if a["seq"] < 12 else "ban2" if a["seq"] < 16 else "pick2"
            self.team_phase[team][phase][a["champion"]] += w
            self.team_phase_n[team][phase][a["champion"]] += 1
            if a["type"] == "ban":
                self.champ_ban_w[a["champion"]] += w
                self.champ_ban_n[a["champion"]] += 1
                self.team_ban[team][a["champion"]] += 1
                opp = red if team == blue else blue
                self.banned_against[opp][a["champion"]] += 1
            elif team not in first_seen:
                first_seen.add(team)
                self.team_phase[team]["first"][a["champion"]] += w
                self.team_phase_n[team]["first"][a["champion"]] += 1
                role = next((p["role"] for p in m["participants"]
                             if p["team"] == team and p["champion"] == a["champion"]), None)
                if role:
                    self.team_first_role[team][role] += 1
        o = {k: m.get(k) for k in ("first_blood", "first_dragon", "first_herald", "first_tower", "gold_diff_15")}
        if "objectives" in m:
            o.update(m["objectives"] or {})
        for key in ("first_blood", "first_dragon", "first_herald", "first_tower"):
            if o.get(key):
                for team in (blue, red):
                    self.team_obj[team][key][1] += 1
                    self.team_obj[team][key][0] += int(o[key] == team)
        if o.get("gold_diff_15") is not None:
            self.team_gold15[blue].append(o["gold_diff_15"])
            self.team_gold15[red].append(-o["gold_diff_15"])
        if m.get("duration_s"):
            for team in (blue, red):
                self.team_duration[team].append(m["duration_s"])

    # ------------------------------------------------------------------ meta
    def presence(self, c: str) -> Tuple[float, float, float]:
        """(pick rate, ban rate, presence) — recency weighted, per game."""
        if not self.total_w:
            return 0.0, 0.0, 0.0
        p = self.champ_pick[c].w / self.total_w if c in self.champ_pick else 0.0
        b = self.champ_ban_w.get(c, 0.0) / self.total_w
        return p, b, min(1.0, p + b)

    def champ_wr(self, c: str) -> float:
        a = self.champ_pick.get(c)
        return smoothed(a.ww, a.w, k=4) if a else 0.5

    def meta_score(self, c: str) -> float:
        """0..1: blend of recency-weighted presence and smoothed win rate."""
        pres = self.presence(c)[2] / self._max_presence
        wr = min(1.0, max(0.0, (self.champ_wr(c) - 0.40) / 0.20))
        return 0.65 * pres + 0.35 * wr

    # ------------------------------------------------------------------ players
    def player_for(self, team: str, role: str) -> Optional[dict]:
        return self.roster.get(team, {}).get(role)

    def comfort(self, pid: Optional[str], c: str) -> dict:
        if not pid:
            return {"games": 0, "wins": 0, "wr": 0.0, "share": 0.0, "score": 0.0, "total": 0}
        pool = self.player_champ.get(pid, {})
        a = pool.get(c)
        total = self.player_total[pid].games if pid in self.player_total else 0
        if not a:
            return {"games": 0, "wins": 0, "wr": 0.0, "share": 0.0, "score": 0.0, "total": total}
        top = max(x.w for x in pool.values()) or 1.0
        share = a.w / top
        wr_s = smoothed(a.wins, a.games, k=3)
        score = max(0.0, min(1.0, share * (0.8 + 0.8 * (wr_s - 0.5)) + min(0.15, a.games * 0.015)))
        return {"games": a.games, "wins": a.wins, "wr": a.wr, "share": share, "score": score, "total": total}

    def player_pool(self, pid: str, limit: int = 12) -> List[dict]:
        pool = self.player_champ.get(pid, {})
        out = []
        for c, a in pool.items():
            out.append({"champion": c, "games": a.games, "wins": a.wins, "wr": a.wr, "weighted": round(a.w, 3),
                        "comfort": round(self.comfort(pid, c)["score"], 3), "last_played": self.player_last[pid][c]})
        out.sort(key=lambda x: (-x["weighted"], -x["games"]))
        return out[:limit]

    # ------------------------------------------------------------------ teams
    def team_phase_rate(self, team: str, phase: str, c: str) -> Tuple[float, int, int]:
        """(normalized 0..1 priority, raw count, team games) for a champion in a draft phase."""
        d = self.team_phase.get(team, {}).get(phase, {})
        if not d or c not in d:
            return 0.0, 0, self.team_games[team].games if team in self.team_games else 0
        top = max(d.values())
        return d[c] / top, self.team_phase_n[team][phase][c], self.team_games[team].games

    # ------------------------------------------------------------------ matchups
    def matchup(self, a: str, b: str) -> dict:
        """Blended win rate of champion a vs b (pro lane data + optional solo-queue prior)."""
        pro_n, pro_w = self.lane.get((a, b), [0, 0])
        prior = self.prior_matchup.get((a, b))
        k_prior = 20.0 if prior else 0.0
        prior_wr = prior[0] if prior else 0.5
        wr = (prior_wr * k_prior + pro_w + 0.5 * 4) / (k_prior + pro_n + 4)
        return {"wr": wr, "pro_games": pro_n, "pro_wins": pro_w,
                "prior_wr": prior[0] if prior else None, "prior_games": prior[1] if prior else 0,
                "evidence": bool(prior) or pro_n > 0}

    def synergy(self, a: str, b: str) -> dict:
        k = tuple(sorted((a, b)))
        n, wins = self.pair.get(k, [0, 0])
        prior = self.prior_synergy.get(k)
        k_prior = 20.0 if prior else 0.0
        prior_wr = prior[0] if prior else 0.5
        base_a, base_b = self.champ_wr(a), self.champ_wr(b)
        expected = (base_a + base_b) / 2
        wr = (prior_wr * k_prior + wins + expected * 6) / (k_prior + n + 6)
        if not prior:
            wr = 0.5 + (wr - expected)  # pro-only: lift over the pair's individual win rates
        return {"wr": wr, "pro_games": n, "pro_wins": wins, "prior_wr": prior[0] if prior else None,
                "prior_games": prior[1] if prior else 0, "evidence": bool(prior) or n >= 2}

    # ------------------------------------------------------------------ summaries
    def team_summary(self, team: str) -> dict:
        g = self.team_games.get(team, Agg())
        sides = {s: {"games": self.team_side[team][s].games, "wins": self.team_side[team][s].wins,
                     "wr": self.team_side[team][s].wr} for s in ("blue", "red")}
        obj = {}
        for k in ("first_blood", "first_dragon", "first_herald", "first_tower"):
            got, n = self.team_obj[team][k]
            obj[k] = {"rate": got / n if n else None, "count": got, "games": n}
        gold = self.team_gold15.get(team, [])
        dur = self.team_duration.get(team, [])
        return {"games": g.games, "wins": g.wins, "wr": g.wr, "sides": sides, "objectives": obj,
                "gold_diff_15": {"avg": sum(gold) / len(gold) if gold else None,
                                 "ahead_rate": sum(1 for x in gold if x > 0) / len(gold) if gold else None,
                                 "games": len(gold)},
                "avg_duration_s": sum(dur) / len(dur) if dur else None,
                "first_pick_roles": dict(self.team_first_role.get(team, {}))}


# ---------------------------------------------------------------------------- loading from DB
_cache_lock = threading.Lock()
_cached: Optional[StatsIndex] = None


def load_from_db(conn) -> StatsIndex:
    teams = []
    for t in conn.execute("SELECT * FROM teams").fetchall():
        t = dict(t)
        t["players"] = [dict(p) for p in conn.execute("SELECT * FROM players WHERE team_id=?", (t["id"],)).fetchall()]
        teams.append(t)
    matches = {}
    for m in conn.execute("SELECT * FROM matches").fetchall():
        m = dict(m)
        m["draft"], m["participants"] = [], []
        matches[m["id"]] = m
    for a in conn.execute("SELECT match_id, seq, side, type, team_id, champion FROM draft_actions ORDER BY match_id, seq"):
        matches[a["match_id"]]["draft"].append({"seq": a["seq"], "side": a["side"], "type": a["type"],
                                                "team": a["team_id"], "champion": a["champion"]})
    for p in conn.execute("SELECT * FROM participants"):
        matches[p["match_id"]]["participants"].append({"team": p["team_id"], "side": p["side"], "player": p["player_id"],
                                                       "role": p["role"], "champion": p["champion"]})
    priors = {"matchups": [dict(r) for r in conn.execute("SELECT a, b, wr_a, games FROM priors_matchup")],
              "synergies": [dict(r) for r in conn.execute("SELECT a, b, wr, games FROM priors_synergy")]}
    return StatsIndex(list(matches.values()), teams, priors)


def get_index(conn=None) -> StatsIndex:
    global _cached
    with _cache_lock:
        if _cached is None:
            from .. import db
            _cached = load_from_db(conn or db.get_conn())
        return _cached


def invalidate() -> None:
    global _cached
    with _cache_lock:
        _cached = None
