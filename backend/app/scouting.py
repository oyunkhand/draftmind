"""Opponent scouting report (JSON + Markdown export)."""
from typing import List, Optional

from . import db
from .champions import ROLES, name_of
from .engine.stats import StatsIndex


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{round(100 * x)}%"


def _top(d: dict, n: int) -> List[tuple]:
    return sorted(d.items(), key=lambda kv: -kv[1])[:n]


def recent_matches(team: str, limit: int = 10, opponent: Optional[str] = None) -> List[dict]:
    q = "SELECT * FROM matches WHERE (blue_team=? OR red_team=?)"
    params: list = [team, team]
    if opponent:
        q += " AND (blue_team=? OR red_team=?)"
        params += [opponent, opponent]
    q += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    out = []
    for m in db.rows(q, tuple(params)):
        side = "blue" if m["blue_team"] == team else "red"
        opp = m["red_team"] if side == "blue" else m["blue_team"]
        parts = db.rows("SELECT team_id, role, champion, player_id FROM participants WHERE match_id=?", (m["id"],))
        draft = db.rows("SELECT seq, side, type, team_id, champion FROM draft_actions WHERE match_id=? ORDER BY seq", (m["id"],))
        order = {r: i for i, r in enumerate(ROLES)}
        mine = sorted([p for p in parts if p["team_id"] == team], key=lambda p: order.get(p["role"], 9))
        theirs = sorted([p for p in parts if p["team_id"] == opp], key=lambda p: order.get(p["role"], 9))
        gd = m["gold_diff_15"]
        out.append({"id": m["id"], "date": m["date"], "patch": m["patch"], "tournament": m["tournament"],
                    "series_id": m["series_id"], "game_number": m["game_number"], "side": side, "opponent": opp,
                    "win": m["winner"] == team, "duration_s": m["duration_s"],
                    "gold_diff_15": (gd if side == "blue" else -gd) if gd is not None else None,
                    "picks": [{"role": p["role"], "champion": p["champion"]} for p in mine],
                    "opp_picks": [{"role": p["role"], "champion": p["champion"]} for p in theirs],
                    "bans": [a["champion"] for a in draft if a["type"] == "ban" and a["team_id"] == team],
                    "opp_bans": [a["champion"] for a in draft if a["type"] == "ban" and a["team_id"] == opp]})
    return out


def build_report(idx: StatsIndex, team_id: str, vs: Optional[str] = None) -> dict:
    team = idx.teams.get(team_id)
    if not team:
        raise KeyError(team_id)
    summary = idx.team_summary(team_id)
    games = summary["games"] or 1
    players = []
    for role in ROLES:
        p = idx.player_for(team_id, role)
        if not p:
            continue
        pool = idx.player_pool(p["id"], limit=10)
        tot = idx.player_total.get(p["id"])
        players.append({"id": p["id"], "name": p["name"], "role": role, "games": tot.games if tot else 0,
                        "wr": tot.wr if tot else 0.0, "pool": pool, "unique_champions": len(idx.player_champ.get(p["id"], {}))})

    def table(d, n=10, with_wr=False):
        rows = []
        for c, v in _top(d, n):
            row = {"champion": c, "count": v, "rate": v / games}
            if with_wr:
                a = idx.team_pick[team_id][c]
                row.update(wins=a.wins, wr=a.wr)
            rows.append(row)
        return rows

    picks = {c: a.games for c, a in idx.team_pick.get(team_id, {}).items()}
    phase_n = idx.team_phase_n.get(team_id, {})
    first_roles = summary["first_pick_roles"]
    fr_total = sum(first_roles.values()) or 1
    report = {
        "team": {k: team.get(k) for k in ("id", "name", "tag", "color", "region")},
        "summary": summary,
        "players": players,
        "most_picked": table(picks, 12, with_wr=True),
        "most_banned_by": table(dict(idx.team_ban.get(team_id, {})), 10),
        "most_banned_against": table(dict(idx.banned_against.get(team_id, {})), 10),
        "first_picks": table(dict(phase_n.get("first", {})), 8),
        "phase1_bans": table(dict(phase_n.get("ban1", {})), 8),
        "phase2_bans": table(dict(phase_n.get("ban2", {})), 8),
        "first_pick_roles": [{"role": r, "count": n, "rate": n / fr_total} for r, n in _top(first_roles, 5)],
        "recent": recent_matches(team_id, 8),
    }
    report["insights"] = insights(idx, report)
    if vs:
        report["ban_plan"] = ban_plan(idx, report)
    return report


def ban_plan(idx: StatsIndex, report: dict, n: int = 5) -> List[dict]:
    """Target bans vs this opponent: comfort x meta, one per player at most twice."""
    cands = []
    for p in report["players"]:
        for e in p["pool"][:5]:
            if e["games"] < 2:
                continue
            value = e["comfort"] * (0.6 + 0.8 * idx.meta_score(e["champion"])) * (0.7 + 0.6 * e["wr"])
            cands.append({"champion": e["champion"], "player": p["name"], "role": p["role"], "games": e["games"],
                          "wr": e["wr"], "value": round(value, 3),
                          "reason": f"{p['name']} ({p['role']}): {e['games']}/{p['games']} games, {_pct(e['wr'])} WR"})
    cands.sort(key=lambda x: -x["value"])
    out, per_player = [], {}
    for c in cands:
        if per_player.get(c["player"], 0) >= 2:
            continue
        per_player[c["player"]] = per_player.get(c["player"], 0) + 1
        out.append(c)
        if len(out) >= n:
            break
    return out


def insights(idx: StatsIndex, r: dict) -> List[dict]:
    out = []
    s = r["summary"]
    # Win-condition player: highest comfort * games on a signature champion
    best = None
    for p in r["players"]:
        for e in p["pool"][:3]:
            if e["games"] >= 3:
                v = e["games"] * (0.5 + e["wr"])
                if not best or v > best[0]:
                    best = (v, p, e)
    if best:
        _, p, e = best
        out.append({"type": "threat", "text": f"{p['name']} ({p['role']}) is a key carry on {name_of(e['champion'])}: "
                                              f"{e['games']}/{p['games']} games, {_pct(e['wr'])} WR — prime ban target."})
    sides = s["sides"]
    if sides["blue"]["games"] >= 3 and sides["red"]["games"] >= 3:
        diff = sides["blue"]["wr"] - sides["red"]["wr"]
        if abs(diff) >= 0.12:
            better = "blue" if diff > 0 else "red"
            worse = "red" if better == "blue" else "blue"
            out.append({"type": "side", "text": f"Much stronger on {better} side ({_pct(sides[better]['wr'])}) than "
                                                f"{worse} ({_pct(sides[worse]['wr'])}). If we get side choice, force them {worse}."})
    obj = s["objectives"]
    fd = obj["first_dragon"]["rate"]
    if fd is not None:
        tone = "prioritise early dragon" if fd >= 0.55 else "concede early dragons" if fd <= 0.45 else "split early dragons"
        out.append({"type": "early", "text": f"They {tone}: first dragon in {_pct(fd)} of games; first herald {_pct(obj['first_herald']['rate'])}."})
    g = s["gold_diff_15"]
    if g["avg"] is not None:
        style = "an early-game team" if g["avg"] > 600 else "a scaling team" if g["avg"] < -400 else "even in the early game"
        out.append({"type": "early", "text": f"They are {style}: average gold diff @15 {int(round(g['avg'])):+,} "
                                             f"(ahead in {_pct(g['ahead_rate'])} of games)."})
    if r["first_pick_roles"]:
        fr = r["first_pick_roles"][0]
        fp = r["first_picks"][0] if r["first_picks"] else None
        txt = f"First-pick priority goes to {fr['role']} ({_pct(fr['rate'])} of first picks)"
        if fp:
            txt += f"; most common first pick {name_of(fp['champion'])} ({fp['count']}×)."
        out.append({"type": "draft", "text": txt})
    narrow = [p for p in r["players"] if p["games"] >= 6 and p["unique_champions"] <= 6]
    for p in narrow[:1]:
        out.append({"type": "pool", "text": f"{p['name']} has a narrow pool ({p['unique_champions']} champions in {p['games']} games) — fearless games 2-3 will stretch them."})
    return out


def to_markdown(r: dict) -> str:
    t, s = r["team"], r["summary"]
    L = [f"# Scouting Report — {t['name']} ({t['tag']})", "",
         f"Record: **{s['wins']}-{s['games'] - s['wins']}** ({_pct(s['wr'])} WR) · "
         f"Blue {s['sides']['blue']['wins']}/{s['sides']['blue']['games']} ({_pct(s['sides']['blue']['wr'])}) · "
         f"Red {s['sides']['red']['wins']}/{s['sides']['red']['games']} ({_pct(s['sides']['red']['wr'])})", ""]
    L += ["## Key insights", ""] + [f"- {i['text']}" for i in r["insights"]] + [""]
    if r.get("ban_plan"):
        L += ["## Suggested ban plan", "", "| # | Champion | Target | Evidence |", "|---|---|---|---|"]
        L += [f"| {i + 1} | {name_of(b['champion'])} | {b['player']} ({b['role']}) | {b['reason']} |" for i, b in enumerate(r["ban_plan"])]
        L.append("")
    L += ["## Early game", "", "| Objective | Rate |", "|---|---|"]
    for k, lab in (("first_blood", "First blood"), ("first_dragon", "First dragon"), ("first_herald", "First herald"),
                   ("first_tower", "First tower")):
        L.append(f"| {lab} | {_pct(s['objectives'][k]['rate'])} |")
    g = s["gold_diff_15"]
    gold_txt = "n/a" if g["avg"] is None else "{:+,}".format(int(round(g["avg"])))
    L.append(f"| Avg gold diff @15 | {gold_txt} |")
    L.append("")
    L += ["## Player champion pools", ""]
    for p in r["players"]:
        L.append(f"### {p['name']} — {p['role']} ({p['games']} games, {_pct(p['wr'])} WR)")
        L += ["", "| Champion | Games | WR | Comfort |", "|---|---|---|---|"]
        L += [f"| {name_of(e['champion'])} | {e['games']} | {_pct(e['wr'])} | {round(100 * e['comfort'])} |" for e in p["pool"][:6]]
        L.append("")
    for key, title in (("most_picked", "Most picked"), ("most_banned_by", "Most banned by them"),
                       ("most_banned_against", "Most banned against them"), ("first_picks", "First-pick priorities")):
        L += [f"## {title}", "", "| Champion | Count | Rate |", "|---|---|---|"]
        L += [f"| {name_of(x['champion'])} | {x['count']} | {_pct(x['rate'])} |" for x in r[key]]
        L.append("")
    L += ["## Recent matches", "", "| Date | Opponent | Side | Result | Picks |", "|---|---|---|---|---|"]
    for m in r["recent"]:
        L.append(f"| {m['date'][:10]} | {m['opponent']} | {m['side']} | {'W' if m['win'] else 'L'} | "
                 f"{', '.join(name_of(p['champion']) for p in m['picks'])} |")
    L += ["", "_Generated by DraftMind AI._"]
    return "\n".join(L)
