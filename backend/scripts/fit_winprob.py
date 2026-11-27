"""Fit the live-draft win probability model (logistic regression) on real games.

Same chronological protocol as fit_opponent_model.py:
  games [0, 60%)   -> statistics (StatsIndex, Elo)
  games [60%, 75%) -> fitting rows, walk-forward: features are computed before the game is added
  games [75%, 100%)-> held-out evaluation, walk-forward
Rows are taken before the draft and after every pick, from both teams' points of view (mirrored), so the
model is symmetric and works at any point of the draft.

Usage (from backend/):  python -m scripts.fit_winprob
"""
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

from app.adapters import load_dataset
from app.engine import winprob
from app.engine.draft import DraftError, DraftState
from app.engine.stats import StatsIndex

OUT = Path(__file__).resolve().parents[1] / "app" / "engine" / "model_weights.json"
TRAIN_FRAC, FIT_END = 0.60, 0.75
CHECKPOINTS = (0, 6, 9, 12, 16, 18, 20)  # before draft, after bans 1, mid pick 1, after picks 1, ...


def rows_for(idx, m):
    draft = sorted(m["draft"], key=lambda a: a["seq"])
    if len(draft) != 20:
        return []
    st = DraftState(m["blue_team"], m["red_team"], first_side=draft[0]["side"])
    out = []
    for k in range(21):
        if k in CHECKPOINTS:
            for side in ("blue", "red"):
                f = winprob.features(idx, st, side)
                out.append((k, [f[x] for x in winprob.FEATURES], int(m["winner"] == st.team_of(side))))
        if k < 20:
            try:
                st.actions.append(draft[k]["champion"])
            except DraftError:
                return out
    return out


def collect(matches, teams, a, b, c):
    idx = StatsIndex(matches[:a], teams, {})
    fit_rows, test_rows = [], []
    for i, m in enumerate(matches[a:c], start=a):
        (fit_rows if i < b else test_rows).extend(rows_for(idx, m))
        idx._add_match(m)
    return fit_rows, test_rows


def fit(rows, cols, l2=0.01, iters=3000, lr=0.1):
    X = np.array([[1.0] + [r[1][i] for i in cols] for r in rows])
    y = np.array([r[2] for r in rows], dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]]
        w -= lr * g
    return w


def evaluate(rows, cols, w, k=None):
    sel = [r for r in rows if k is None or r[0] == k]
    X = np.array([[1.0] + [r[1][i] for i in cols] for r in sel])
    y = np.array([r[2] for r in sel], dtype=float)
    p = np.clip(1 / (1 + np.exp(-X @ w)), 1e-6, 1 - 1e-6)
    return {"rows": len(sel), "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4),
            "accuracy": round(float(np.mean((p > 0.5) == (y == 1))), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 4)}


def main():
    data, info = load_dataset()
    if data.get("source") != "grid":
        sys.exit("needs the real GRID data (set STL_DATA_DIR); refusing to fit on the sample dataset")
    matches = sorted(data["matches"], key=lambda m: m["date"])
    n = len(matches)
    a, b = int(n * TRAIN_FRAC), int(n * FIT_END)
    fit_rows, test_rows = collect(matches, data["teams"], a, b, n)
    full = list(range(len(winprob.FEATURES)))
    base = [winprob.FEATURES.index("elo"), winprob.FEATURES.index("blue")]
    w_full, w_base = fit(fit_rows, full), fit(fit_rows, base)
    report = {"held_out_games": n - b, "by_point": {}}
    for k in CHECKPOINTS:
        report["by_point"][f"after {k} actions"] = {"model": evaluate(test_rows, full, w_full, k),
                                                    "elo_and_side_only": evaluate(test_rows, base, w_base, k)}
    weights = {"intercept": round(float(w_full[0]), 4)}
    weights.update({f: round(float(v), 4) for f, v in zip(winprob.FEATURES, w_full[1:])})
    final = report["by_point"]["after 20 actions"]
    entry = {"weights": weights, "source": "fitted",
             "fitted_on": f"games {a}-{b} of {n} (chronological, walk-forward)", "fitted_at": dt.date.today().isoformat(),
             "held_out": {"games": n - b, "final_draft": final, "before_draft": report["by_point"]["after 0 actions"]}}
    existing = json.loads(OUT.read_text()) if OUT.is_file() else {}
    existing["winprob"] = entry
    OUT.write_text(json.dumps(existing, indent=2) + "\n")
    print(json.dumps({"weights": weights, "report": report}, indent=2))


if __name__ == "__main__":
    main()
