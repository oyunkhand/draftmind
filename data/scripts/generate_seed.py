"""Deterministic generator for the DraftMind sample dataset.

Simulates two round-robin stages of fearless Bo3 series between 8 fictional pro teams.
Every game has a full 20-action pro draft (ban 3 / pick 3 / ban 2 / pick 2), role
assignments, early-game objectives and gold@15. Drafting agents follow hidden "ground truth"
(player comfort pools, team first-pick tendencies, ban styles, patch meta, lane matchups,
synergies) so the analytics in DraftMind surface real, discoverable patterns.

Also emits "solo-queue priors" (lane matchup + synergy win rates) the way a coach would pull
them from a stats site. All names and numbers are synthetic.

Run:  python3 data/scripts/generate_seed.py
"""
import datetime as dt
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..")
SEED = 20261124
rng = random.Random(SEED)

ROLES = ["top", "jungle", "mid", "bot", "support"]

# Pro draft order: (side, type). Indexes 0-19.
DRAFT_ORDER = (
    [("blue", "ban"), ("red", "ban")] * 3
    + [("blue", "pick"), ("red", "pick"), ("red", "pick"), ("blue", "pick"), ("blue", "pick"), ("red", "pick")]
    + [("red", "ban"), ("blue", "ban")] * 2
    + [("red", "pick"), ("blue", "pick"), ("blue", "pick"), ("red", "pick")]
)
assert len(DRAFT_ORDER) == 20

S_TIER = ["Azir", "Orianna", "Rumble", "KSante", "Vi", "XinZhao", "Kaisa", "Varus", "Rell", "Rakan",
          "Corki", "Sejuani", "Ambessa", "Taliyah", "Kalista", "Alistar", "Yone", "Jayce", "Skarner",
          "Aurora", "Ezreal", "Nautilus"]
A_TIER = ["Gnar", "Renekton", "Jax", "Aatrox", "Ornn", "Sion", "Gwen", "Camille", "Viego", "LeeSin",
          "MonkeyKing", "Nidalee", "JarvanIV", "Pantheon", "Poppy", "Ahri", "Sylas", "Syndra", "Viktor",
          "Tristana", "Galio", "Hwei", "Ryze", "Akali", "Xayah", "Zeri", "Jhin", "Ashe", "Lucian",
          "Smolder", "Braum", "Renata", "Leona", "Lulu", "Neeko", "Karma", "Bard", "Thresh", "Maokai",
          "Nocturne", "Kennen", "Gragas", "Lillia", "Aphelios", "Caitlyn", "Wukong"]

HARD_COUNTERS = [  # (counter, countered, strength)
    ("Renekton", "Gwen", 0.35), ("Jayce", "KSante", 0.25), ("Poppy", "Kalista", 0.2),
    ("Galio", "Akali", 0.3), ("Galio", "Ahri", 0.2), ("Syndra", "Azir", 0.2), ("Taliyah", "Orianna", 0.15),
    ("Corki", "Viktor", 0.15), ("Leona", "Ezreal", 0.2), ("Braum", "Kalista", 0.25), ("Nautilus", "Lulu", 0.15),
    ("Rumble", "Sion", 0.2), ("Gnar", "Aatrox", 0.15), ("Lillia", "Sejuani", 0.15), ("Nidalee", "Sejuani", 0.2),
    ("Viego", "Vi", 0.1), ("Varus", "Kaisa", 0.12), ("Lucian", "Jhin", 0.2), ("Kennen", "Jax", 0.2),
    ("Ryze", "Sylas", 0.15), ("Zeri", "Ashe", -0.15), ("Alistar", "Rakan", 0.1), ("Rell", "Ezreal", 0.15),
]
SYNERGIES = [
    ("Xayah", "Rakan", 0.35), ("Kalista", "Renata", 0.2), ("Kalista", "Rell", 0.15), ("Orianna", "JarvanIV", 0.25),
    ("Orianna", "XinZhao", 0.15), ("Yone", "Rell", 0.2), ("Yasuo", "Rell", 0.25), ("Lucian", "Nami", 0.3),
    ("Lucian", "Braum", 0.15), ("Zeri", "Lulu", 0.3), ("Zeri", "Yuumi", 0.2), ("Jinx", "Lulu", 0.2),
    ("Kaisa", "Nautilus", 0.2), ("Kaisa", "Rell", 0.15), ("Ezreal", "Karma", 0.15), ("Aphelios", "Thresh", 0.15),
    ("Senna", "TahmKench", 0.2), ("Galio", "Camille", 0.15), ("Azir", "Sejuani", 0.15), ("Sylas", "Vi", 0.1),
    ("Varus", "Ashe", 0.15), ("Corki", "Skarner", 0.1), ("Taliyah", "Ambessa", 0.12), ("Twitch", "Lulu", 0.2),
    ("Jhin", "Bard", 0.12), ("Rumble", "Sejuani", 0.15), ("Ivern", "Draven", 0.15), ("Aurora", "Vi", 0.1),
]

TEAMS = [
    # id, name, tag, color, strength, aggression, first-pick role priority, ban style, blue-side edge
    ("NMB", "Nimbus Esports", "NMB", "#38bdf8", 0.64, 0.58, ["jungle", "mid"], "target", 0.04),
    ("IWF", "Iron Wolves", "IWF", "#f59e0b", 0.60, 0.70, ["mid", "bot"], "target", 0.10),
    ("CRC", "Crimson Comet", "CRC", "#ef4444", 0.56, 0.62, ["bot", "support"], "meta", -0.02),
    ("PVX", "Polar Vortex", "PVX", "#a78bfa", 0.53, 0.40, ["top", "jungle"], "meta", 0.02),
    ("SFG", "Solar Flare Gaming", "SFG", "#fb923c", 0.50, 0.55, ["mid", "jungle"], "target", 0.06),
    ("NSP", "Neon Serpents", "NSP", "#22c55e", 0.47, 0.66, ["jungle", "top"], "meta", 0.00),
    ("GRG", "Granite Giants", "GRG", "#94a3b8", 0.44, 0.35, ["support", "bot"], "target", 0.08),
    ("EVK", "Echo Valkyries", "EVK", "#f472b6", 0.41, 0.48, ["mid", "support"], "meta", -0.04),
]
PLAYER_NAMES = {
    "NMB": ["Stratos", "Cirrus", "Halcyon", "Aether", "Zephyr"],
    "IWF": ["Fang", "Howl", "Vesper", "Grim", "Talon"],
    "CRC": ["Blaze", "Ember", "Nova", "Pyre", "Cinder"],
    "PVX": ["Glacier", "Frost", "Rime", "Tundra", "Floe"],
    "SFG": ["Corona", "Helios", "Sunspot", "Flux", "Dawn"],
    "NSP": ["Viper", "Venom", "Coil", "Mamba", "Scale"],
    "GRG": ["Basalt", "Quarry", "Obsidian", "Slate", "Pebble"],
    "EVK": ["Rune", "Saga", "Skald", "Valk", "Hymn"],
}
PATCHES = ["16.16", "16.17", "16.18", "16.19", "16.20", "16.21", "16.22"]


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def load_champions():
    with open(os.path.join(DATA, "champions.json")) as f:
        champs = json.load(f)["champions"]
    return {c["id"]: c for c in champs if c["curated"]}


CHAMPS = load_champions()
BY_ROLE = {r: sorted(c for c, d in CHAMPS.items() if r in d["roles"]) for r in ROLES}

# ---------------------------------------------------------------- hidden ground truth
BASE_META = {}
DRIFT = {}
for cid in sorted(CHAMPS):
    if cid in S_TIER:
        BASE_META[cid] = 0.30 + rng.uniform(-0.05, 0.05)
    elif cid in A_TIER:
        BASE_META[cid] = 0.15 + rng.uniform(-0.05, 0.05)
    else:
        BASE_META[cid] = rng.gauss(-0.05, 0.07)
    DRIFT[cid] = rng.gauss(0, 0.025)


def meta(cid, patch_idx):
    return BASE_META[cid] + DRIFT[cid] * (patch_idx - 3)


MATCHUP = {}  # (a, b) -> advantage of a over b in lane (antisymmetric)
for r in ROLES:
    pool = BY_ROLE[r]
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if (a, b) in MATCHUP:
                continue
            v = max(-0.25, min(0.25, rng.gauss(0, 0.08)))
            MATCHUP[(a, b)] = v
            MATCHUP[(b, a)] = -v
for a, b, v in HARD_COUNTERS:
    if a in CHAMPS and b in CHAMPS:
        MATCHUP[(a, b)] = v
        MATCHUP[(b, a)] = -v
SYN = {}
for a, b, v in SYNERGIES:
    if a in CHAMPS and b in CHAMPS:
        SYN[(a, b)] = v
        SYN[(b, a)] = v


def matchup(a, b):
    return MATCHUP.get((a, b), 0.0)


def synergy(a, b):
    return SYN.get((a, b), 0.0)


# ---------------------------------------------------------------- teams & players
def build_pool(role):
    candidates = BY_ROLE[role]
    weights = [3.0 if c in S_TIER else 2.0 if c in A_TIER else 0.6 for c in candidates]
    pool = {}
    size = min(len(candidates), rng.randint(9, 11))
    while len(pool) < size:
        c = rng.choices(candidates, weights)[0]
        if c in pool:
            continue
        pool[c] = None
    names = list(pool)
    rng.shuffle(names)
    out = {}
    for i, c in enumerate(names):
        if i < 2:
            out[c] = round(rng.uniform(0.88, 1.0), 3)  # signature picks
        elif i < 5:
            out[c] = round(rng.uniform(0.65, 0.85), 3)
        else:
            out[c] = round(rng.uniform(0.35, 0.65), 3)
    return out


teams = []
players = {}  # team -> role -> player dict
for tid, name, tag, color, strength, aggr, prio, ban_style, blue_edge in TEAMS:
    roster = {}
    for role, pname in zip(ROLES, PLAYER_NAMES[tid]):
        roster[role] = {"id": f"{tid}-{role}", "name": pname, "role": role, "pool": build_pool(role)}
    players[tid] = roster
    teams.append({
        "id": tid, "name": name, "tag": tag, "color": color, "region": "Sample League",
        "players": [{"id": p["id"], "name": p["name"], "role": p["role"]} for p in roster.values()],
        "_truth": {"strength": strength, "aggression": aggr, "priority": prio, "ban_style": ban_style,
                   "blue_edge": blue_edge},
    })
TEAM = {t["id"]: t for t in teams}

# Make sure the headline demo story exists: IWF mid is an Azir specialist.
players["IWF"]["mid"]["pool"]["Azir"] = 0.99
players["NMB"]["jungle"]["pool"]["Vi"] = 0.97


def comfort(tid, role, cid):
    return players[tid][role]["pool"].get(cid, 0.12)


# ---------------------------------------------------------------- draft simulation
def assign_roles(picks, roles_open):
    """Return role for a new champion given currently open roles (first matching role)."""
    for r in CHAMPS[picks]["roles"]:
        if r in roles_open:
            return r
    return None


def gumbel():
    return -math.log(-math.log(rng.random() + 1e-12) + 1e-12)


def simulate_draft(blue, red, patch_idx, unavailable):
    side_team = {"blue": blue, "red": red}
    picks = {"blue": {}, "red": {}}  # role -> champ
    bans = {"blue": [], "red": []}
    taken = set(unavailable)
    actions = []
    pick_count = {"blue": 0, "red": 0}
    for seq, (side, typ) in enumerate(DRAFT_ORDER):
        me, opp_side = side_team[side], ("red" if side == "blue" else "blue")
        opp = side_team[opp_side]
        truth = TEAM[me]["_truth"]
        my_open = [r for r in ROLES if r not in picks[side]]
        opp_open = [r for r in ROLES if r not in picks[opp_side]]
        best, best_score, best_role = None, -1e9, None
        if typ == "ban":
            w_comf, w_meta = (1.4, 0.9) if truth["ban_style"] == "target" else (0.7, 1.6)
            for cid in CHAMPS:
                if cid in taken:
                    continue
                roles = [r for r in CHAMPS[cid]["roles"] if r in opp_open]
                if not roles:
                    continue
                c = max(comfort(opp, r, cid) for r in roles)
                threat = sum(matchup(cid, p) for p in picks[side].values())
                s = w_comf * c + w_meta * meta(cid, patch_idx) * 2 + 0.6 * threat + 0.22 * gumbel()
                if s > best_score:
                    best, best_score = cid, s
            bans[side].append(best)
        else:
            first_rotation = pick_count[side] < 2
            for r in my_open:
                for cid in BY_ROLE[r]:
                    if cid in taken:
                        continue
                    s = 1.5 * comfort(me, r, cid) + 1.1 * meta(cid, patch_idx) * 2
                    s += 1.0 * sum(matchup(cid, p) for rr, p in picks[opp_side].items() if rr == r)
                    s += 0.4 * sum(matchup(cid, p) for rr, p in picks[opp_side].items() if rr != r)
                    s += 0.9 * sum(synergy(cid, p) for p in picks[side].values())
                    if first_rotation and r in truth["priority"]:
                        s += 0.35
                    if first_rotation and len(CHAMPS[cid]["roles"]) > 1:
                        s += 0.08
                    s += 0.25 * gumbel()
                    if s > best_score:
                        best, best_score, best_role = cid, s, r
            picks[side][best_role] = best
            pick_count[side] += 1
        taken.add(best)
        actions.append({"seq": seq, "side": side, "type": typ, "team": me, "champion": best})
    return actions, picks


def simulate_outcome(blue, red, picks, patch_idx):
    tb, tr = TEAM[blue]["_truth"], TEAM[red]["_truth"]
    x = 2.2 * (tb["strength"] - tr["strength"]) + 0.22 + tb["blue_edge"] - tr["blue_edge"] * 0.5
    for r in ROLES:
        cb, cr = picks["blue"][r], picks["red"][r]
        x += 0.45 * (meta(cb, patch_idx) - meta(cr, patch_idx))
        x += 0.7 * (comfort(blue, r, cb) - comfort(red, r, cr))
        x += 0.9 * matchup(cb, cr)
    for side, sign in (("blue", 1), ("red", -1)):
        ch = list(picks[side].values())
        x += sign * 0.8 * sum(synergy(a, b) for i, a in enumerate(ch) for b in ch[i + 1:])
    p_blue = sigmoid(x * 1.6)
    blue_win = rng.random() < p_blue
    w = 1 if blue_win else -1
    aggr = tb["aggression"] - tr["aggression"]
    early_lane = sum(matchup(picks["blue"][r], picks["red"][r]) for r in ("top", "mid", "bot"))
    gold15 = int(round(900 * w + 4200 * aggr + 3000 * early_lane + rng.gauss(0, 1500), -1))
    def first(p):
        return blue if rng.random() < p else red
    obj = {
        "first_blood": first(sigmoid(2.5 * aggr + 0.3 * w)),
        "first_dragon": first(sigmoid(3.0 * aggr + 0.5 * w + 0.0002 * gold15)),
        "first_herald": first(sigmoid(2.0 * aggr + 0.4 * w + (0.4 if "top" in tb["priority"] else 0)
                                      - (0.4 if "top" in tr["priority"] else 0))),
        "first_tower": first(sigmoid(0.00035 * gold15 + 0.4 * w)),
        "gold_diff_15": gold15,
    }
    duration = int(rng.gauss(31.5, 4) * 60 - abs(gold15) * 0.12)
    return (blue if blue_win else red), obj, max(1260, duration)


# ---------------------------------------------------------------- schedule
def main():
    team_ids = [t["id"] for t in teams]
    pairs = [(a, b) for i, a in enumerate(team_ids) for b in team_ids[i + 1:]]
    series_out, matches_out = [], []
    start = dt.datetime(2026, 7, 4, 17, 0)
    stages = [("Sample League Summer — Stage 1", 0), ("Sample League Summer — Stage 2", 1)]
    s_no = 0
    for stage_name, stage_idx in stages:
        order = pairs[:]
        rng.shuffle(order)
        for k, (a, b) in enumerate(order):
            s_no += 1
            day = start + dt.timedelta(days=stage_idx * 63 + (k // 4) * 3 + (k % 4) * 0.08)
            patch_idx = min(len(PATCHES) - 1, int((day - start).days / 18))
            sid = f"S{s_no:03d}"
            if rng.random() < 0.5:
                a, b = b, a
            blue, red = a, b
            wins = {a: 0, b: 0}
            used = set()
            game_ids = []
            g = 0
            while max(wins.values()) < 2:
                g += 1
                actions, picks = simulate_draft(blue, red, patch_idx, used)
                winner, obj, duration = simulate_outcome(blue, red, picks, patch_idx)
                wins[winner] += 1
                mid = f"{sid}-G{g}"
                participants = []
                for side, team in (("blue", blue), ("red", red)):
                    for r in ROLES:
                        participants.append({"team": team, "side": side, "player": players[team][r]["id"],
                                             "role": r, "champion": picks[side][r]})
                matches_out.append({
                    "id": mid, "series_id": sid, "game_number": g,
                    "date": (day + dt.timedelta(minutes=50 * (g - 1))).isoformat(),
                    "patch": PATCHES[patch_idx], "tournament": stage_name,
                    "blue_team": blue, "red_team": red, "winner": winner, "duration_s": duration,
                    "draft": actions, "participants": participants, "objectives": obj,
                })
                game_ids.append(mid)
                used |= {c for side in picks.values() for c in side.values()}  # fearless
                loser = red if winner == blue else blue
                other = blue if loser == red else red
                if rng.random() < 0.8:
                    blue, red = loser, other
                else:
                    blue, red = other, loser
            series_out.append({
                "id": sid, "tournament": stage_name, "date": day.isoformat(), "best_of": 3, "fearless": True,
                "team_a": a, "team_b": b, "winner": max(wins, key=wins.get), "score": [wins[a], wins[b]],
                "games": game_ids,
            })

    # Solo-queue style priors (what a coach would pull from a stats site): noisy view of the truth.
    matchup_priors = []
    for (a, b), v in sorted(MATCHUP.items()):
        if a < b:
            n = rng.randint(400, 6000)
            wr = 0.5 + 0.22 * v + rng.gauss(0, 0.006)
            matchup_priors.append({"a": a, "b": b, "wr_a": round(wr, 4), "games": n})
    synergy_priors = []
    for (a, b), v in sorted(SYN.items()):
        if a < b:
            synergy_priors.append({"a": a, "b": b, "wr": round(0.5 + 0.18 * v + rng.gauss(0, 0.005), 4),
                                   "games": rng.randint(800, 9000)})

    public_teams = [{k: v for k, v in t.items() if not k.startswith("_")} for t in teams]
    out = {
        "meta": {"name": "DraftMind sample dataset (synthetic)", "seed": SEED,
                 "generated_for": "offline demo / judging", "patches": PATCHES},
        "teams": public_teams, "series": series_out, "matches": matches_out,
        "priors": {"matchups": matchup_priors, "synergies": synergy_priors},
    }
    os.makedirs(os.path.join(DATA, "seed"), exist_ok=True)
    path = os.path.join(DATA, "seed", "dataset.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    # quick summary
    tw = {t: [0, 0] for t in team_ids}
    for m in matches_out:
        for t in (m["blue_team"], m["red_team"]):
            tw[t][1] += 1
        tw[m["winner"]][0] += 1
    blue_wr = sum(m["winner"] == m["blue_team"] for m in matches_out) / len(matches_out)
    print(f"{len(series_out)} series, {len(matches_out)} games, blue WR {blue_wr:.2f}")
    for t, (w, n) in tw.items():
        print(f"  {t}: {w}/{n} ({w / n:.0%})")
    print(f"-> {os.path.relpath(path)} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
