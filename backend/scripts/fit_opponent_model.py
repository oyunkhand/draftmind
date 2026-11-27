"""Fit the opponent-prediction weights on real games (conditional logit).

Protocol (chronological, no leakage):
  games [0, 60%)    -> statistics the model reads (StatsIndex)
  games [60%, 75%)  -> fitting set, walk-forward: each game is predicted, then added to the index
  games [75%, 100%) -> untouched; evaluated afterwards by run_backtest (the numbers the app shows)

At every draft action the model scores each legal champion with its factors; the fitted weights
maximise the probability of the champion the team actually picked or banned (softmax over the legal
candidates, L2-regularised). The weights are written to app/engine/model_weights.json.

Usage (from backend/):  python -m scripts.fit_opponent_model
"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from app.adapters import load_dataset
from app.engine import scoring
from app.engine.backtest import run_backtest
from app.engine.draft import DraftError, DraftState, SeriesGame, fearless_locks
from app.engine.stats import StatsIndex

TRAIN_FRAC, FIT_END = 0.60, 0.75
OUT = Path(__file__).resolve().parents[1] / "app" / "engine" / "model_weights.json"


def collect(matches, teams):
    """Feature tensors per action type: list of (X [candidates x features], index of the actual choice)."""
    matches = sorted(matches, key=lambda m: m["date"])
    a, b = int(len(matches) * TRAIN_FRAC), int(len(matches) * FIT_END)
    idx = StatsIndex(matches[:a], teams, {})
    keys = {"pick": list(scoring.PREDICT_PICK), "ban": list(scoring.PREDICT_BAN)}
    data = {"pick": [], "ban": []}
    for m in matches[a:b]:
        draft = sorted(m["draft"], key=lambda x: x["seq"])
        if len(draft) == 20:
            prev = [g for g in matches if g["series_id"] == m["series_id"] and g["game_number"] < m["game_number"]]
            locks = fearless_locks([SeriesGame(g["blue_team"], g["red_team"],
                                               [x["champion"] for x in g["draft"] if x["type"] == "pick" and x["side"] == "blue"],
                                               [x["champion"] for x in g["draft"] if x["type"] == "pick" and x["side"] == "red"])
                                    for g in prev], m["blue_team"], m["red_team"], "hard")
            state = DraftState(m["blue_team"], m["red_team"], fearless_mode="hard", locked=locks, first_side=draft[0]["side"])
            for step, act in zip(state.order, draft):
                preds = scoring.predict_opponent(idx, state, step.side, step=step, top=1000)["predictions"]
                names = [p["champion"] for p in preds]
                if act["champion"] in names:
                    X = np.array([[next(f["value"] for f in p["factors"] if f["key"] == k) for k in keys[step.type]]
                                  for p in preds], dtype=float)
                    data[step.type].append((X, names.index(act["champion"])))
                try:
                    state.apply(act["champion"])
                except DraftError:
                    break
        idx._add_match(m)
    return data, keys, (a, b)


def fit(rows, n_feat, l2=0.01, iters=600, lr=0.05):
    """Conditional logit by Adam on the mean negative log-likelihood."""
    w = np.zeros(n_feat)
    m1, m2 = np.zeros(n_feat), np.zeros(n_feat)
    for t in range(1, iters + 1):
        grad, nll = np.zeros(n_feat), 0.0
        for X, y in rows:
            s = X @ w
            s -= s.max()
            p = np.exp(s)
            p /= p.sum()
            nll -= np.log(p[y] + 1e-12)
            grad += X.T @ p - X[y]
        grad = grad / len(rows) + l2 * w
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad ** 2
        w -= lr * (m1 / (1 - 0.9 ** t)) / (np.sqrt(m2 / (1 - 0.999 ** t)) + 1e-8)
        if t % 100 == 0:
            print(f"  iter {t}: nll {nll / len(rows):.4f}", file=sys.stderr)
    return w


def calibrate(rows, w):
    """Temperature T (on the fitting rows) so the mean top-1 probability equals the top-1 hit rate."""
    acc = np.mean([int(np.argmax(X @ w) == y) for X, y in rows])

    def conf(t):
        out = []
        for X, _ in rows:
            s = X @ w / t
            p = np.exp(s - s.max())
            out.append(p.max() / p.sum())
        return float(np.mean(out))
    lo, hi = 0.5, 4.0
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if conf(mid) > acc else (lo, mid)
    return round((lo + hi) / 2, 3), float(acc)


def main():
    data_, info = load_dataset()
    if data_.get("source") != "grid":
        sys.exit("needs the real GRID data (set STL_DATA_DIR); refusing to fit on the sample dataset")
    matches, teams = data_["matches"], data_["teams"]
    before = run_backtest(matches, teams, {})
    feats, keys, (a, b) = collect(matches, teams)
    out = {"temperature": {"pick": 1.0, "ban": 1.0}}
    for typ in ("pick", "ban"):
        print(f"fitting {typ}: {len(feats[typ])} actions", file=sys.stderr)
        w = fit(feats[typ], len(keys[typ]))
        out[typ] = {k: round(float(v), 3) for k, v in zip(keys[typ], w)}
        out["temperature"][typ], acc = calibrate(feats[typ], w)
        print(f"  {typ}: top-1 on fitting set {acc:.3f}, temperature {out['temperature'][typ]}", file=sys.stderr)
    out.update({"source": "fitted", "fitted_on": f"games {a}-{b} of {len(matches)} (chronological, walk-forward)",
                "fitted_at": dt.date.today().isoformat(), "dataset": info.get("name")})
    existing = json.loads(OUT.read_text()) if OUT.is_file() else {}
    keep = {k: v for k, v in existing.items() if k == "winprob"}  # written by fit_winprob.py
    OUT.write_text(json.dumps({**out, **keep}, indent=2) + "\n")
    # reload the module-level weights and evaluate on the untouched last 25%
    scoring.PREDICT_PICK.update(out["pick"]); scoring.PREDICT_BAN.update(out["ban"])
    scoring.TEMPERATURE.update(out["temperature"])
    after = run_backtest(matches, teams, {})
    print(json.dumps({"weights": out, "test_before": {k: before[k] for k in ("pick", "ban")},
                      "test_after": {k: after[k] for k in ("pick", "ban")}}, indent=2))


if __name__ == "__main__":
    main()
