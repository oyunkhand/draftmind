"""First Selection advice (2026 rule): with the selection, a team chooses EITHER its side OR its draft turn
(first or second); the opponent then chooses the other. Which choice gives us the best expected win rate?

Expected win rate for (our side, our draft turn):
    league rate for that (side, turn) combination, from First Selection era games (side and turn decoupled)
  + our team's side and turn tendencies minus the opponent's, shrunk toward 0 for small samples
  + half the gap in overall form between the two teams

Each choice is scored assuming the opponent then makes the reply that is worst for us (minimax), so the
advice holds even against a well-prepared opponent. Every number is returned with its sample size.
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

SIDES = ("blue", "red")
TURNS = ("first", "second")
SHRINK_K = 15.0  # games at which a team's own tendency counts for half


def _first_side(m: dict) -> str:
    d = sorted(m["draft"], key=lambda a: a["seq"])
    return d[0]["side"] if d else "blue"


def _event(m: dict) -> str:
    return (m.get("tournament") or "").split(" — ")[0]


def _shrink(delta: float, n: int) -> float:
    return delta * n / (n + SHRINK_K)


class _Rate:
    __slots__ = ("g", "w")

    def __init__(self):
        self.g, self.w = 0, 0

    def add(self, win: bool):
        self.g += 1
        self.w += int(win)

    @property
    def wr(self) -> Optional[float]:
        return self.w / self.g if self.g else None

    def as_dict(self) -> dict:
        return {"games": self.g, "wins": self.w, "wr": round(self.wr, 4) if self.g else None}


def first_selection_advice(matches: List[dict], our: str, opp: str) -> dict:
    # Events where red ever drafted first are First Selection events: side and turn are independent there.
    fs_events = {_event(m) for m in matches if _first_side(m) == "red"}
    fs = [m for m in matches if _event(m) in fs_events]

    league: Dict[Tuple[str, str], _Rate] = defaultdict(_Rate)
    team_side: Dict[str, Dict[str, _Rate]] = defaultdict(lambda: defaultdict(_Rate))
    team_turn: Dict[str, Dict[str, _Rate]] = defaultdict(lambda: defaultdict(_Rate))
    team_all: Dict[str, _Rate] = defaultdict(_Rate)
    team_fs: Dict[str, _Rate] = defaultdict(_Rate)
    for m in matches:
        for side, team in (("blue", m["blue_team"]), ("red", m["red_team"])):
            win = m["winner"] == team
            team_side[team][side].add(win)
            team_all[team].add(win)
    for m in fs:
        first = _first_side(m)
        for side, team in (("blue", m["blue_team"]), ("red", m["red_team"])):
            win, turn = m["winner"] == team, "first" if side == first else "second"
            league[(side, turn)].add(win)
            team_turn[team][turn].add(win)
            team_fs[team].add(win)

    if not fs:
        return {"available": False, "reason": "No First Selection era games in the dataset (red never drafted first)."}

    def side_delta(team: str, side: str) -> Tuple[float, dict]:
        r, base = team_side[team][side], team_all[team].wr or 0.5
        return (_shrink((r.wr or base) - base, r.g), r.as_dict())

    def turn_delta(team: str, turn: str) -> Tuple[float, dict]:
        r, base = team_turn[team][turn], team_fs[team].wr or 0.5
        return (_shrink((r.wr or base) - base, r.g), r.as_dict())

    form = 0.5 * (_shrink((team_all[our].wr or 0.5) - 0.5, team_all[our].g)
                  - _shrink((team_all[opp].wr or 0.5) - 0.5, team_all[opp].g))

    def expected(side: str, turn: str) -> dict:
        other_side = "red" if side == "blue" else "blue"
        other_turn = "second" if turn == "first" else "first"
        base = league[(side, turn)].wr or 0.5
        our_s, _ = side_delta(our, side)
        opp_s, _ = side_delta(opp, other_side)
        our_t, _ = turn_delta(our, turn)
        opp_t, _ = turn_delta(opp, other_turn)
        p = base + 0.5 * (our_s - opp_s) + 0.5 * (our_t - opp_t) + form
        return {"side": side, "turn": turn, "wr": round(min(0.95, max(0.05, p)), 4),
                "parts": {"league": round(base, 4), "side": round(0.5 * (our_s - opp_s), 4),
                          "turn": round(0.5 * (our_t - opp_t), 4), "form": round(form, 4)}}

    grid = {(s, t): expected(s, t) for s in SIDES for t in TURNS}
    choices = []
    for s in SIDES:  # we take a side, they pick the turn that is worst for us
        reply = min(TURNS, key=lambda t: grid[(s, t)]["wr"])
        theirs = "first" if reply == "second" else "second"
        choices.append({"choice": f"{s} side", "kind": "side", "value": s,
                        "opponent_reply": f"they draft {theirs}, so we draft {reply}",
                        "wr": grid[(s, reply)]["wr"], "outcome": grid[(s, reply)]})
    for t in TURNS:  # we take a turn, they pick the side that is worst for us
        reply = min(SIDES, key=lambda s: grid[(s, t)]["wr"])
        theirs = "red" if reply == "blue" else "blue"
        choices.append({"choice": f"draft {t}", "kind": "turn", "value": t,
                        "opponent_reply": f"they take {theirs} side, so we play {reply}",
                        "wr": grid[(reply, t)]["wr"], "outcome": grid[(reply, t)]})
    choices.sort(key=lambda c: -c["wr"])
    best = choices[0]

    return {
        "available": True,
        "recommendation": best["choice"],
        "summary": (f"Take {best['choice']}: about {round(100 * best['wr'])}% expected win rate even after "
                    f"the opponent's best reply ({best['opponent_reply']})."),
        "choices": choices,
        "grid": [grid[(s, t)] for s in SIDES for t in TURNS],
        "league": {"events": sorted(fs_events), "games": len(fs),
                   "combos": [{"side": s, "turn": t, **league[(s, t)].as_dict()} for s in SIDES for t in TURNS],
                   "blue_wr": round(sum(league[("blue", t)].w for t in TURNS) / max(1, sum(league[("blue", t)].g for t in TURNS)), 4),
                   "first_wr": round(sum(league[(s, "first")].w for s in SIDES) / max(1, sum(league[(s, "first")].g for s in SIDES)), 4)},
        "teams": {team: {"overall": team_all[team].as_dict(),
                         "sides": {s: team_side[team][s].as_dict() for s in SIDES},
                         "turns_fs_era": {t: team_turn[team][t].as_dict() for t in TURNS}}
                  for team in (our, opp)},
        "method": "League (side, turn) rates from First Selection era games, plus each team's side/turn tendencies "
                  f"shrunk toward 0 (half weight at {int(SHRINK_K)} games) and half the form gap; minimax over the "
                  "opponent's reply.",
    }
