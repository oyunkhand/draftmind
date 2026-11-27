"""Fearless series profile and "how to win" ban impact for one team.

Answers two coaching questions directly from match data:
* How does this team's draft shift from Game 1 to Game 3+ of a fearless series?
  (win rate, first-pick role, favourite picks, and how deep into their pool they have to go)
* Which bans hurt them most? Their win rate in games where a champion was banned vs. their overall rate,
  shrunk toward zero for small samples, with the raw counts shown.
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from ..champions import name_of

SHRINK_K = 10.0
CORE_POOL = 15  # a team's "core pool" = its 15 most-picked champions


def _bucket(n: int) -> str:
    return "G1" if n == 1 else "G2" if n == 2 else "G3+"


def _pct(x: Optional[float]) -> str:
    return "–" if x is None else f"{round(100 * x)}%"


def _team_games(matches: List[dict], team: str) -> List[dict]:
    return [m for m in matches if team in (m["blue_team"], m["red_team"])]


def fearless_profile(matches: List[dict], team: str) -> dict:
    games = _team_games(matches, team)
    if not games:
        return {"available": False}
    pick_count = Counter(p["champion"] for m in games for p in m["participants"] if p["team"] == team)
    core = {c for c, _ in pick_count.most_common(CORE_POOL)}

    agg: Dict[str, dict] = defaultdict(lambda: {"games": 0, "wins": 0, "first_roles": Counter(), "picks": Counter(),
                                                 "bans": Counter(), "core_picks": 0, "all_picks": 0})
    for m in games:
        b = agg[_bucket(m.get("game_number") or 1)]
        b["games"] += 1
        b["wins"] += int(m["winner"] == team)
        role_of = {p["champion"]: p["role"] for p in m["participants"] if p["team"] == team}
        mine = [a for a in sorted(m["draft"], key=lambda a: a["seq"]) if a["team"] == team]
        picks = [a["champion"] for a in mine if a["type"] == "pick"]
        if picks and picks[0] in role_of:
            b["first_roles"][role_of[picks[0]]] += 1
        b["picks"].update(picks)
        b["bans"].update(a["champion"] for a in mine if a["type"] == "ban")
        b["core_picks"] += sum(1 for c in picks if c in core)
        b["all_picks"] += len(picks)

    buckets = []
    for key in ("G1", "G2", "G3+"):
        b = agg.get(key)
        if not b or not b["games"]:
            continue
        fr_total = sum(b["first_roles"].values()) or 1
        buckets.append({
            "game": key, "games": b["games"], "wins": b["wins"], "wr": b["wins"] / b["games"],
            "first_pick_roles": [{"role": r, "rate": n / fr_total, "count": n} for r, n in b["first_roles"].most_common(3)],
            "top_picks": [{"champion": c, "name": name_of(c), "count": n, "rate": n / b["games"]} for c, n in b["picks"].most_common(5)],
            "top_bans": [{"champion": c, "name": name_of(c), "count": n, "rate": n / b["games"]} for c, n in b["bans"].most_common(5)],
            "core_share": b["core_picks"] / b["all_picks"] if b["all_picks"] else None,
        })

    shifts = []
    first, late = next((x for x in buckets if x["game"] == "G1"), None), next((x for x in buckets if x["game"] == "G3+"), None)
    if first and late and late["games"] >= 5:
        shifts.append(f"Win rate {_pct(first['wr'])} in Game 1 → {_pct(late['wr'])} in Game 3+ "
                      f"({first['games']} vs {late['games']} games).")
        if first["core_share"] is not None and late["core_share"] is not None:
            shifts.append(f"{_pct(first['core_share'])} of Game 1 picks come from their core {CORE_POOL}-champion pool, "
                          f"{_pct(late['core_share'])} in Game 3+: the pool {'thins out' if late['core_share'] < first['core_share'] - 0.05 else 'holds up'} under fearless.")
        if first["first_pick_roles"] and late["first_pick_roles"]:
            r1, r3 = first["first_pick_roles"][0], late["first_pick_roles"][0]
            if r1["role"] != r3["role"]:
                shifts.append(f"First pick moves from {r1['role']} ({_pct(r1['rate'])}) in Game 1 to {r3['role']} ({_pct(r3['rate'])}) in Game 3+.")
            else:
                shifts.append(f"First pick stays on {r1['role']} ({_pct(r1['rate'])} in Game 1, {_pct(r3['rate'])} in Game 3+).")
        g1_top = [x["name"] for x in first["top_picks"][:3]]
        if g1_top:
            shifts.append(f"They spend {', '.join(g1_top)} early: in fearless those are gone for the rest of the series.")
    return {"available": True, "games": len(games), "core_pool": CORE_POOL, "buckets": buckets, "shifts": shifts}


def ban_impact(matches: List[dict], team: str, top: int = 6, min_banned: int = 4) -> dict:
    """Their win rate when a champion from their pool was banned (by either side) vs. their overall rate."""
    games = _team_games(matches, team)
    if not games:
        return {"available": False, "items": []}
    overall = sum(m["winner"] == team for m in games) / len(games)
    pick_count = Counter(p["champion"] for m in games for p in m["participants"] if p["team"] == team)
    g1_games = [m for m in games if (m.get("game_number") or 1) == 1]
    g1_pick = Counter(p["champion"] for m in g1_games for p in m["participants"] if p["team"] == team)
    player_of = defaultdict(Counter)
    for m in games:
        for p in m["participants"]:
            if p["team"] == team:
                player_of[p["champion"]][p["player"]] += 1

    items = []
    for c, n_picked in pick_count.most_common(25):
        banned = [m for m in games if any(a["type"] == "ban" and a["champion"] == c for a in m["draft"])]
        picked = [m for m in games if any(p["team"] == team and p["champion"] == c for p in m["participants"])]
        if len(banned) < min_banned:
            continue
        wr_banned = sum(m["winner"] == team for m in banned) / len(banned)
        wr_picked = sum(m["winner"] == team for m in picked) / len(picked) if picked else None
        delta = wr_banned - overall
        shrunk = delta * len(banned) / (len(banned) + SHRINK_K)
        items.append({
            "champion": c, "name": name_of(c), "picked": n_picked, "pick_rate": n_picked / len(games),
            "g1_pick_rate": g1_pick[c] / len(g1_games) if g1_games else None,
            "wr_when_picked": wr_picked, "banned_games": len(banned), "wr_when_banned": wr_banned,
            "delta": delta, "impact": shrunk,
            "text": (f"Ban {name_of(c)}: they win {_pct(wr_banned)} of {len(banned)} games where it was banned, "
                     f"vs {_pct(overall)} overall ({'+' if delta >= 0 else '−'}{abs(round(100 * delta))} pts). "
                     f"They pick it in {_pct(n_picked / len(games))} of games"
                     + (f", {_pct(g1_pick[c] / len(g1_games))} of Game 1s" if g1_games else "")
                     + (f", winning {_pct(wr_picked)}." if wr_picked is not None else ".")),
        })
    items.sort(key=lambda x: x["impact"])
    return {"available": True, "overall_wr": overall, "games": len(games),
            "items": [x for x in items if x["impact"] < 0][:top],
            "method": f"Win rate in games where the champion was banned vs. overall; deltas shrunk toward 0 "
                      f"(half weight at {int(SHRINK_K)} banned games). Correlation, not proof: a ban also shapes the rest of the draft."}
