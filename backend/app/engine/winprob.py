"""Live draft win probability: P(our team wins | draft so far).

A logistic model over transparent "us minus them" features of the champions revealed so far:
  elo      log-odds of the Elo expectation (team strength going into the game)
  blue     +1 if we are on blue side, -1 on red
  meta     sum over picks of (champion win rate shrunk toward 50%, minus 50%), ours minus theirs
  comfort  sum over picks of how much better the assigned player does on it than on average, ours minus theirs
  lane     sum over lanes revealed on both sides of (our lane matchup win rate shrunk toward 50%, minus 50%)
  synergy  mean pair synergy lift of our picks minus theirs
Picks that are not revealed yet contribute nothing, so early in the draft the estimate rests on Elo and
side, and it sharpens as champions lock in. Weights are fitted on real games by scripts/fit_winprob.py.
"""
import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from ..champions import ROLES
from .draft import DraftState, other
from .stats import StatsIndex

FEATURES = ["elo", "blue", "meta", "comfort", "lane", "synergy"]
META_K, PLAYER_K, LANE_K = 30.0, 8.0, 20.0  # pseudo-games of shrinkage toward the prior
DEFAULT = {"intercept": 0.0, "elo": 1.0, "blue": 0.05, "meta": 1.0, "comfort": 0.3, "lane": 1.0, "synergy": 1.0}
LABELS = {"elo": "Team strength (Elo)", "blue": "Side", "meta": "Champion strength", "comfort": "Player comfort",
          "lane": "Lane matchups", "synergy": "Synergy"}

_FILE = Path(__file__).with_name("model_weights.json")
WEIGHTS: Dict[str, float] = dict(DEFAULT)
INFO: Dict[str, object] = {"source": "defaults"}
if _FILE.is_file():
    _w = json.loads(_FILE.read_text()).get("winprob")
    if _w:
        WEIGHTS.update(_w["weights"])
        INFO = {k: v for k, v in _w.items() if k != "weights"}


def _logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return math.log(p / (1 - p))


def _shrunk(wins: float, games: float, prior: float, k: float) -> float:
    return (wins + prior * k) / (games + k)


def _champ_strength(idx: StatsIndex, c: str) -> float:
    """Champion win rate shrunk hard toward 50% (pro samples per champion are small)."""
    a = idx.champ_pick.get(c)
    return _shrunk(a.ww, a.w, 0.5, META_K) - 0.5 if a else 0.0


def _player_edge(idx: StatsIndex, pid: Optional[str], c: str) -> float:
    """How much better the player does on c than on average (shrunk toward their own win rate)."""
    if not pid or pid not in idx.player_total:
        return 0.0
    tot = idx.player_total[pid]
    base = _shrunk(tot.wins, tot.games, 0.5, 10.0)
    a = idx.player_champ.get(pid, {}).get(c)
    return _shrunk(a.wins, a.games, base, PLAYER_K) - base if a else 0.0


def _side_terms(idx: StatsIndex, state: DraftState, side: str) -> Dict[str, float]:
    team = state.team_of(side)
    roles = state.roles(side)  # role -> champion
    meta = sum(_champ_strength(idx, c) for c in roles.values())
    comfort = 0.0
    for role, c in roles.items():
        p = idx.player_for(team, role)
        comfort += _player_edge(idx, p["id"] if p else None, c)
    champs = list(roles.values())
    pairs = [(a, b) for i, a in enumerate(champs) for b in champs[i + 1:]]
    syn = sum(idx.synergy(a, b)["wr"] - 0.5 for a, b in pairs) / 10.0
    return {"meta": meta, "comfort": comfort, "synergy": syn}


def features(idx: StatsIndex, state: DraftState, our_side: str) -> Dict[str, float]:
    opp_side = other(our_side)
    us, them = state.team_of(our_side), state.team_of(opp_side)
    a, b = _side_terms(idx, state, our_side), _side_terms(idx, state, opp_side)
    ours, theirs = state.roles(our_side), state.roles(opp_side)
    lane = 0.0
    for r in ROLES:
        if r in ours and r in theirs:
            n, w = idx.lane.get((ours[r], theirs[r]), [0, 0])
            lane += _shrunk(w, n, 0.5, LANE_K) - 0.5
    return {"elo": _logit(idx.elo_expect(us, them)), "blue": 1.0 if our_side == "blue" else -1.0,
            "meta": a["meta"] - b["meta"], "comfort": a["comfort"] - b["comfort"], "lane": lane,
            "synergy": a["synergy"] - b["synergy"]}


def predict(idx: StatsIndex, state: DraftState, our_side: str, weights: Optional[Dict[str, float]] = None) -> dict:
    w = weights or WEIGHTS
    f = features(idx, state, our_side)
    z = w.get("intercept", 0.0) + sum(w.get(k, 0.0) * v for k, v in f.items())
    contrib = [{"key": k, "label": LABELS[k], "value": round(v, 4), "logit": round(w.get(k, 0.0) * v, 4)} for k, v in f.items()]
    contrib.sort(key=lambda c: -abs(c["logit"]))
    return {"p": 1.0 / (1.0 + math.exp(-z)), "factors": contrib}


def curve(idx: StatsIndex, state: DraftState, our_side: str) -> List[dict]:
    """Win probability after each action so far (index 0 = before the first ban)."""
    out = []
    for k in range(len(state.actions) + 1):
        st = DraftState(state.blue_team, state.red_team, list(state.actions[:k]), state.fearless_mode,
                        state.locked, state.first_side)
        step = state.order[k - 1] if k else None
        out.append({"index": k, "p": round(predict(idx, st, our_side)["p"], 4),
                    "label": step.label if step else "start", "champion": state.actions[k - 1] if k else None})
    return out


def what_if(idx: StatsIndex, state: DraftState, our_side: str, champions: List[str]) -> Dict[str, float]:
    """Change in our win probability if the current pick is each of `champions` (picks only)."""
    step = state.current
    if not step or step.type != "pick":
        return {}
    base = predict(idx, state, our_side)["p"]
    out = {}
    for c in champions:
        st = DraftState(state.blue_team, state.red_team, list(state.actions) + [c], state.fearless_mode,
                        state.locked, state.first_side)
        out[c] = round(predict(idx, st, our_side)["p"] - base, 4)
    return out
