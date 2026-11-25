import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="draftmind-test-")
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["DATA_SOURCE"] = "sample"
os.environ["LLM_PROVIDER"] = "none"

from app.champions import ROLES  # noqa: E402

TEAMS = [
    {"id": "AAA", "name": "Alpha", "players": [{"id": f"AAA-{r}", "name": f"A{r}", "role": r} for r in ROLES]},
    {"id": "BBB", "name": "Bravo", "players": [{"id": f"BBB-{r}", "name": f"B{r}", "role": r} for r in ROLES]},
]
ORDER = (["blue", "red"] * 3, ["blue", "red", "red", "blue", "blue", "red"], ["red", "blue"] * 2, ["red", "blue", "blue", "red"])


def make_match(mid, date, blue_comp, red_comp, winner="AAA", blue="AAA", red="BBB", bans=None):
    """Build a normalized match. *_comp are role->champion dicts; bans is a list of 10 champions."""
    bans = bans or ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu", "Zilean", "Sona", "Yuumi", "Soraka"]
    sides_ban = ORDER[0] + ORDER[2]
    sides_pick = ORDER[1] + ORDER[3]
    picks = {"blue": list(blue_comp.values()), "red": list(red_comp.values())}
    seq_types = ["ban"] * 6 + ["pick"] * 6 + ["ban"] * 4 + ["pick"] * 4
    side_seq = ORDER[0] + ORDER[1] + ORDER[2] + ORDER[3]
    draft, bi, pi = [], 0, {"blue": 0, "red": 0}
    for seq, (typ, side) in enumerate(zip(seq_types, side_seq)):
        team = blue if side == "blue" else red
        if typ == "ban":
            champ = bans[bi]
            bi += 1
        else:
            champ = picks[side][pi[side]]
            pi[side] += 1
        draft.append({"seq": seq, "side": side, "type": typ, "team": team, "champion": champ})
    parts = [{"team": blue, "side": "blue", "player": f"{blue}-{r}", "role": r, "champion": c} for r, c in blue_comp.items()]
    parts += [{"team": red, "side": "red", "player": f"{red}-{r}", "role": r, "champion": c} for r, c in red_comp.items()]
    return {"id": mid, "series_id": None, "game_number": 1, "date": date, "patch": "16.20", "blue_team": blue,
            "red_team": red, "winner": winner, "duration_s": 1800, "draft": draft, "participants": parts,
            "objectives": {"first_blood": blue, "first_dragon": blue, "first_herald": red, "first_tower": blue,
                           "gold_diff_15": 1000}}


A_COMP = {"top": "Gnar", "jungle": "Vi", "mid": "Azir", "bot": "Varus", "support": "Rakan"}
B_COMP = {"top": "Renekton", "jungle": "Sejuani", "mid": "Orianna", "bot": "Kaisa", "support": "Nautilus"}


@pytest.fixture
def mini_index():
    from app.engine.stats import StatsIndex
    ms = [make_match(f"m{i}", f"2026-09-{i + 1:02d}T12:00:00", A_COMP, B_COMP, winner="AAA" if i % 3 else "BBB")
          for i in range(9)]
    priors = {"matchups": [{"a": "Jayce", "b": "Renekton", "wr_a": 0.62, "games": 3000}],
              "synergies": [{"a": "Xayah", "b": "Rakan", "wr": 0.58, "games": 4000}]}
    return StatsIndex(ms, TEAMS, priors)


@pytest.fixture(scope="session")
def sample_index():
    import json
    from app import config
    from app.engine.stats import StatsIndex
    d = json.load(open(config.DATA_DIR / "seed" / "dataset.json"))
    return StatsIndex(d["matches"], d["teams"], d["priors"])


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
