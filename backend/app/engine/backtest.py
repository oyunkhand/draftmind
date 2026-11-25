"""Chronological backtest of the opponent-prediction model.

Train a StatsIndex on the earliest (1 - test_frac) of matches, then replay every draft action of
the held-out matches: before each action, predict what the acting team does and record where the
real champion ranked. Compared against a meta-only baseline (rank by pro presence).
"""
import math
from typing import Dict, List

from ..champions import all_champions
from .draft import DRAFT_ORDER, DraftState, SeriesGame, fearless_locks, fits_open_role
from .scoring import predict_opponent
from .stats import StatsIndex


def _baseline_rank(idx: StatsIndex, state: DraftState, side: str, typ: str, actual: str) -> int:
    cands = []
    for c in all_champions():
        if not state.is_available(c, side, typ):
            continue
        if typ == "pick" and not fits_open_role(state.picks(side), c):
            continue
        cands.append((idx.presence(c)[2], c))
    cands.sort(reverse=True)
    return next((i + 1 for i, (_, c) in enumerate(cands) if c == actual), 999)


def run_backtest(matches: List[dict], teams: List[dict], priors: dict, test_frac: float = 0.25,
                 fearless: bool = True) -> Dict:
    matches = sorted(matches, key=lambda m: m["date"])
    cut = int(len(matches) * (1 - test_frac))
    train, test = matches[:cut], matches[cut:]
    idx = StatsIndex(train, teams, priors)
    res = {k: {"n": 0, "top1": 0, "top3": 0, "top5": 0, "base_top1": 0, "base_top5": 0, "ll": 0.0, "conf": 0.0}
           for k in ("pick", "ban")}
    for m in test:
        draft = sorted(m["draft"], key=lambda a: a["seq"])
        if len(draft) != 20:
            continue
        prev = [g for g in matches if g.get("series_id") and g.get("series_id") == m.get("series_id")
                and (g.get("game_number") or 0) < (m.get("game_number") or 0)]
        locks = fearless_locks([SeriesGame(g["blue_team"], g["red_team"],
                                           [a["champion"] for a in g["draft"] if a["type"] == "pick" and a["side"] == "blue"],
                                           [a["champion"] for a in g["draft"] if a["type"] == "pick" and a["side"] == "red"])
                                for g in prev], m["blue_team"], m["red_team"], "hard" if fearless else "off")
        state = DraftState(m["blue_team"], m["red_team"], fearless_mode="hard" if fearless else "off", locked=locks)
        for step, a in zip(DRAFT_ORDER, draft):
            preds = predict_opponent(idx, state, step.side, step=step, top=400)["predictions"]
            names = [p["champion"] for p in preds[:5]]
            r = res[step.type]
            r["n"] += 1
            prob = next((p["probability"] for p in preds if p["champion"] == a["champion"]), 0.0)
            r["ll"] += -math.log(max(prob, 1e-4))
            r["conf"] += preds[0]["probability"] if preds else 0.0
            if names[:1] == [a["champion"]]:
                r["top1"] += 1
            if a["champion"] in names[:3]:
                r["top3"] += 1
            if a["champion"] in names[:5]:
                r["top5"] += 1
            b = _baseline_rank(idx, state, step.side, step.type, a["champion"])
            r["base_top1"] += int(b == 1)
            r["base_top5"] += int(b <= 5)
            try:
                state.apply(a["champion"])
            except Exception:
                break
    out = {"train_games": len(train), "test_games": len(test)}
    for k, r in res.items():
        n = r["n"] or 1
        out[k] = {"actions": r["n"], "top1": r["top1"] / n, "top3": r["top3"] / n, "top5": r["top5"] / n,
                  "baseline_top1": r["base_top1"] / n, "baseline_top5": r["base_top5"] / n,
                  "log_loss": r["ll"] / n, "avg_top1_confidence": r["conf"] / n}
    return out
