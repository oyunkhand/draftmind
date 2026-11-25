"""Explainable draft scoring.

Every candidate gets a list of *factors*. Each factor is a normalized value (0..1 or -1..1), a
weight, its contribution (value * weight) and a human-readable piece of evidence built from the
underlying stats. Totals are a plain weighted sum, so the "why" is exactly the math.

* predict_opponent  - opponent's likely next pick/ban: weighted score -> softmax probabilities.
* recommend         - our best next pick/ban with a coach-tunable weight vector.
"""
import math
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..champions import all_champions, name_of
from .draft import DraftState, Step, assign_roles, fits_open_role, other
from .stats import StatsIndex

PICK_FACTORS = ["meta", "counter", "synergy", "comfort", "deny", "coach"]
BAN_FACTORS = ["threat", "predicted", "meta", "counter", "protect", "coach"]

DEFAULT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "pick": {"meta": 1.0, "counter": 1.2, "synergy": 0.6, "comfort": 1.3, "deny": 0.7, "coach": 0.5},
    "ban": {"threat": 1.4, "predicted": 1.2, "meta": 0.9, "counter": 0.8, "protect": 0.8, "coach": 0.5},
}
FACTOR_LABELS = {
    "meta": "Meta strength", "counter": "Counter value", "synergy": "Synergy", "comfort": "Player comfort",
    "deny": "Denies opponent", "coach": "Coach history", "threat": "Opponent comfort",
    "predicted": "Likely enemy pick", "protect": "Keeps our comfort open", "team": "Team draft pattern",
    "target": "Targets our players",
}

# Opponent model weights (grid-searched on a chronological backtest, see backtest.py)
PREDICT_PICK = {"comfort": 1.6, "team": 2.0, "meta": 2.4, "counter": 0.5}
PREDICT_BAN = {"target": 1.7, "team": 0.6, "meta": 2.0, "counter": 0.4}
# Softmax temperatures calibrated by minimizing held-out log-loss (top-1 confidence ~ top-1 accuracy)
TEMPERATURE = {"pick": 0.9, "ban": 0.7}


def pct(x: float) -> str:
    return f"{round(100 * x)}%"


def clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def factor(key: str, value: float, weight: float, evidence: str, **stats) -> dict:
    return {"key": key, "label": FACTOR_LABELS.get(key, key), "value": round(value, 4), "weight": weight,
            "contribution": round(value * weight, 4), "evidence": evidence, "stats": stats}


def candidates() -> Iterable[str]:
    return all_champions().keys()


# ---------------------------------------------------------------------------- shared factor math
def counter_value(idx: StatsIndex, c: str, role: Optional[str], enemies: Dict[str, str]) -> Tuple[float, List[dict]]:
    """How well champion c does against the enemy's revealed picks (lane opponent weighted 1.0, others 0.3)."""
    if not enemies:
        return 0.0, []
    total_w, acc, details = 0.0, 0.0, []
    for erole, e in enemies.items():
        lw = 1.0 if erole == role else 0.3
        total_w += lw
        m = idx.matchup(c, e)
        if not m["evidence"]:
            continue
        acc += lw * (m["wr"] - 0.5)
        details.append({"enemy": e, "role": erole, "lane": erole == role, "wr": round(m["wr"], 4),
                        "pro_games": m["pro_games"], "prior_games": m["prior_games"]})
    details.sort(key=lambda d: -abs(d["wr"] - 0.5) * (1.0 if d["lane"] else 0.3))
    return clip((acc / total_w) / 0.07), details


def synergy_value(idx: StatsIndex, c: str, allies: Sequence[str]) -> Tuple[float, List[dict]]:
    if not allies:
        return 0.0, []
    acc, details = 0.0, []
    for a in allies:
        s = idx.synergy(c, a)
        if not s["evidence"]:
            continue
        acc += s["wr"] - 0.5
        details.append({"ally": a, "wr": round(s["wr"], 4), "pro_games": s["pro_games"], "prior_games": s["prior_games"]})
    details.sort(key=lambda d: -abs(d["wr"] - 0.5))
    return clip(acc / max(1, len(allies)) / 0.04), details


def _games_str(cf: dict) -> str:
    return f"{cf['games']}/{cf['total']} games, {pct(cf['wr'])} WR" if cf["games"] else "no recorded games"


def softmax(scores: List[float], temperature: float) -> List[float]:
    if not scores:
        return []
    mx = max(scores)
    ex = [math.exp((s - mx) / temperature) for s in scores]
    z = sum(ex)
    return [e / z for e in ex]


# ---------------------------------------------------------------------------- opponent prediction
def predict_opponent(idx: StatsIndex, state: DraftState, opp_side: str, step: Optional[Step] = None,
                     top: int = 5, exclude: Set[str] = frozenset()) -> dict:
    """Predict the opponent's action at `step` (default: their next action)."""
    step = step or state.next_step_for(opp_side)
    if step is None:
        return {"step": None, "predictions": []}
    team, our_side = state.team_of(opp_side), other(opp_side)
    our_team = state.team_of(our_side)
    opp_picks, our_picks = state.picks(opp_side), state.picks(our_side)
    our_roles, opp_roles = assign_roles(our_picks), assign_roles(opp_picks)
    scored = []
    for c in candidates():
        if c in exclude or not state.is_available(c, opp_side, step.type):
            continue
        if step.type == "pick":
            role = fits_open_role(opp_picks, c)
            if not role:
                continue
            p = idx.player_for(team, role)
            cf = idx.comfort(p["id"] if p else None, c)
            phase = "first" if not opp_picks else step.phase
            team_rate, n, g = idx.team_phase_rate(team, phase, c)
            if phase == "first":
                tr2 = idx.team_phase_rate(team, "pick1", c)[0]
                team_rate = 0.6 * team_rate + 0.4 * tr2
            meta = idx.meta_score(c)
            cv, cdet = counter_value(idx, c, role, our_roles)
            pname = p["name"] if p else role
            fs = [
                factor("comfort", cf["score"], PREDICT_PICK["comfort"], f"{pname} ({role}): {_games_str(cf)}",
                       player=pname, role=role, games=cf["games"], wins=cf["wins"], total=cf["total"]),
                factor("team", team_rate, PREDICT_PICK["team"],
                       f"{'First-picked' if phase == 'first' else 'Picked in ' + step.phase} {n}× in {g} games" if n
                       else f"Not a {phase} habit for this team", count=n, games=g, phase=phase),
                factor("meta", meta, PREDICT_PICK["meta"], _meta_evidence(idx, c)),
                factor("counter", cv, PREDICT_PICK["counter"], _counter_evidence(cdet) if cdet else "No revealed matchup data"),
            ]
        else:
            role = fits_open_role(our_picks, c)
            if not role and not fits_open_role(opp_picks, c):
                continue
            p = idx.player_for(our_team, role) if role else None
            cf = idx.comfort(p["id"] if p else None, c) if p else {"score": 0.0, "games": 0, "total": 0, "wr": 0, "wins": 0}
            team_rate, n, g = idx.team_phase_rate(team, step.phase, c)
            meta = idx.meta_score(c)
            cv, cdet = counter_value(idx, c, None, opp_roles)
            pname = p["name"] if p else "—"
            fs = [
                factor("target", cf["score"], PREDICT_BAN["target"],
                       f"Targets {pname} ({role}): {_games_str(cf)}" if p else "Not in our open roles",
                       player=pname, role=role, games=cf["games"]),
                factor("team", team_rate, PREDICT_BAN["team"],
                       f"Banned in {step.phase} {n}× in {g} games" if n else f"Rarely banned by them in {step.phase}",
                       count=n, games=g),
                factor("meta", meta, PREDICT_BAN["meta"], _meta_evidence(idx, c)),
                factor("counter", cv, PREDICT_BAN["counter"],
                       _counter_evidence(cdet, against_us=True) if cdet else "No threat data vs their picks"),
            ]
        score = sum(f["contribution"] for f in fs)
        scored.append((c, score, fs, role))
    probs = softmax([s for _, s, _, _ in scored], TEMPERATURE[step.type])
    ranked = sorted(zip(scored, probs), key=lambda x: -x[1])[:top]
    out = []
    for (c, score, fs, role), prob in ranked:
        fs_sorted = sorted(fs, key=lambda f: -f["contribution"])
        out.append({"champion": c, "name": name_of(c), "role": role, "probability": round(prob, 4),
                    "score": round(score, 4), "factors": fs_sorted,
                    "why": "; ".join(f["evidence"] for f in fs_sorted[:2])})
    return {"step": _step_dict(step), "team": team, "predictions": out}


# ---------------------------------------------------------------------------- our recommendations
def recommend(idx: StatsIndex, state: DraftState, our_side: str, weights: Optional[Dict[str, Dict[str, float]]] = None,
              coach_affinity: Optional[Dict[str, Dict[str, dict]]] = None, exclude: Set[str] = frozenset(),
              top: int = 8, step: Optional[Step] = None) -> dict:
    step = step or (state.current if state.current and state.current.side == our_side else state.next_step_for(our_side))
    if step is None:
        return {"step": None, "recommendations": []}
    w = merge_weights(weights)[step.type]
    aff = (coach_affinity or {}).get(step.type, {})
    opp_side = other(our_side)
    us, them = state.team_of(our_side), state.team_of(opp_side)
    our_picks, opp_picks = state.picks(our_side), state.picks(opp_side)
    our_roles, opp_roles = assign_roles(our_picks), assign_roles(opp_picks)
    results = []
    if step.type == "pick":
        for c in candidates():
            if c in exclude or not state.is_available(c, our_side, "pick"):
                continue
            role = fits_open_role(our_picks, c)
            if not role:
                continue
            p = idx.player_for(us, role)
            cf = idx.comfort(p["id"] if p else None, c)
            meta = idx.meta_score(c)
            cv, cdet = counter_value(idx, c, role, opp_roles)
            sv, sdet = synergy_value(idx, c, our_picks)
            opp_role = fits_open_role(opp_picks, c) if state.is_available(c, opp_side, "pick") else None
            op = idx.player_for(them, opp_role) if opp_role else None
            ocf = idx.comfort(op["id"] if op else None, c) if op else None
            ca = aff.get(c, {"value": 0.0, "accepted": 0, "rejected": 0})
            pname = p["name"] if p else role
            fs = [
                factor("meta", meta, w["meta"], _meta_evidence(idx, c)),
                factor("counter", cv, w["counter"], _counter_evidence(cdet) if cdet else
                       ("No enemy picks revealed yet" if not opp_picks else "No matchup data vs their picks"), details=cdet[:3]),
                factor("synergy", sv, w["synergy"], _synergy_evidence(sdet) if sdet else
                       ("First pick — no allies yet" if not our_picks else "No notable synergy data"), details=sdet[:3]),
                factor("comfort", cf["score"], w["comfort"], f"{pname} ({role}): {_games_str(cf)}",
                       player=pname, role=role, games=cf["games"], wins=cf["wins"], total=cf["total"]),
                factor("deny", ocf["score"] if ocf else 0.0, w["deny"],
                       f"Denies {op['name']} ({opp_role}): {_games_str(ocf)}" if ocf and ocf["games"]
                       else "Not in the opponent's pool", player=op["name"] if op else None),
                factor("coach", ca["value"], w["coach"], _coach_evidence(ca), **{k: ca[k] for k in ("accepted", "rejected")}),
            ]
            results.append(_package(c, role, fs, w, "pick"))
    else:
        pred = predict_opponent(idx, state, opp_side, step=state.next_step_for(opp_side, "pick"), top=40)
        pred_p = {x["champion"]: x["probability"] for x in pred["predictions"]}
        top_p = max(pred_p.values() or [1.0])
        for c in candidates():
            if c in exclude or not state.is_available(c, our_side, "ban"):
                continue
            opp_role = fits_open_role(opp_picks, c) if state.is_available(c, opp_side, "pick") else None
            if not opp_role:
                continue
            op = idx.player_for(them, opp_role)
            ocf = idx.comfort(op["id"] if op else None, c)
            meta = idx.meta_score(c)
            cv, cdet = counter_value(idx, c, None, our_roles)  # how well c does into OUR picks
            our_role = fits_open_role(our_picks, c) if state.is_available(c, our_side, "pick") else None
            p = idx.player_for(us, our_role) if our_role else None
            cf = idx.comfort(p["id"] if p else None, c) if p else None
            prob = pred_p.get(c, 0.0)
            ca = aff.get(c, {"value": 0.0, "accepted": 0, "rejected": 0})
            oname = op["name"] if op else opp_role
            fs = [
                factor("threat", ocf["score"], w["threat"], f"{oname} ({opp_role}): {_games_str(ocf)}",
                       player=oname, role=opp_role, games=ocf["games"], total=ocf["total"]),
                factor("predicted", prob / top_p if top_p else 0.0, w["predicted"],
                       f"{pct(prob)} chance they pick it next" if prob >= 0.01 else "Unlikely next enemy pick",
                       probability=prob),
                factor("meta", meta, w["meta"], _meta_evidence(idx, c)),
                factor("counter", max(0.0, cv), w["counter"],
                       _counter_evidence(cdet, against_us=True) if cdet and cv > 0 else "No threat to our picks",
                       details=cdet[:3]),
                factor("protect", -(cf["score"] if cf else 0.0), w["protect"],
                       f"We'd lose {p['name']}'s comfort ({_games_str(cf)})" if cf and cf["games"] else "Not one of our comfort picks"),
                factor("coach", ca["value"], w["coach"], _coach_evidence(ca), **{k: ca[k] for k in ("accepted", "rejected")}),
            ]
            results.append(_package(c, opp_role, fs, w, "ban"))
    results.sort(key=lambda r: -r["total"])
    for i, r in enumerate(results[:top]):
        r["rank"] = i + 1
    return {"step": _step_dict(step), "type": step.type, "weights": w, "recommendations": results[:top]}


def _package(c: str, role: Optional[str], fs: List[dict], w: Dict[str, float], typ: str) -> dict:
    total = sum(f["contribution"] for f in fs)
    max_total = sum(v for k, v in w.items() if k not in ("protect",) and v > 0) or 1.0
    fs_sorted = sorted(fs, key=lambda f: -f["contribution"])
    pros = [f for f in fs_sorted if f["contribution"] > 0.05][:3]
    cons = [f for f in sorted(fs, key=lambda f: f["contribution"]) if f["contribution"] < -0.05][:2]
    verb = "Pick" if typ == "pick" else "Ban"
    summary = f"{verb} {name_of(c)}" + (f" ({role})" if role else "")
    if pros:
        summary += " — " + "; ".join(f["evidence"] for f in pros[:2])
    return {"champion": c, "name": name_of(c), "role": role, "total": round(total, 4),
            "score": round(clip(100 * total / max_total, 0, 100)), "factors": fs_sorted,
            "summary": summary, "pros": [f["evidence"] for f in pros], "risks": [f["evidence"] for f in cons]}


def merge_weights(weights: Optional[Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, float]]:
    out = {k: dict(v) for k, v in DEFAULT_WEIGHTS.items()}
    for typ, d in (weights or {}).items():
        if typ in out:
            for k, v in d.items():
                if k in out[typ]:
                    out[typ][k] = float(max(0.0, min(5.0, v)))
    return out


def coach_affinity(decisions: Iterable[dict]) -> Dict[str, Dict[str, dict]]:
    """Turn the coach's Accept/Modify/Reject log into a per-champion preference in [-1, 1]."""
    raw: Dict[str, Dict[str, dict]] = {"pick": {}, "ban": {}}
    for d in decisions:
        typ = d.get("action_type")
        if typ not in raw:
            continue
        def bump(c, v, key):
            if not c:
                return
            e = raw[typ].setdefault(c, {"sum": 0.0, "accepted": 0, "rejected": 0})
            e["sum"] += v
            e[key] += 1
        if d["decision"] == "accept":
            bump(d["suggested_champion"], 1.0, "accepted")
        elif d["decision"] == "reject":
            bump(d["suggested_champion"], -1.0, "rejected")
        elif d["decision"] == "modify":
            bump(d["suggested_champion"], -0.4, "rejected")
            bump(d.get("final_champion"), 1.0, "accepted")
    return {typ: {c: {"value": round(math.tanh(e["sum"] / 2.0), 4), "accepted": e["accepted"], "rejected": e["rejected"]}
                  for c, e in d.items()} for typ, d in raw.items()}


# ---------------------------------------------------------------------------- evidence text
def _meta_evidence(idx: StatsIndex, c: str) -> str:
    p, b, pres = idx.presence(c)
    a = idx.champ_pick.get(c)
    if not a or (a.games == 0 and pres == 0):
        return "No recent pro presence"
    return f"{pct(pres)} pro presence ({pct(p)} pick / {pct(b)} ban), {pct(a.wr) if a.games else 'n/a'} WR in {a.games} games"


def _counter_evidence(details: List[dict], against_us: bool = False) -> str:
    d = details[0]
    src = f"{d['pro_games']} pro games" + (f" + {d['prior_games']:,} SoloQ" if d["prior_games"] else "")
    if against_us:
        return f"{pct(d['wr'])} WR into our {name_of(d['enemy'])} ({src})"
    verb = "Counters" if d["wr"] >= 0.5 else "Weak into"
    return f"{verb} {name_of(d['enemy'])}{' in lane' if d['lane'] else ''}: {pct(d['wr'])} WR ({src})"


def _synergy_evidence(details: List[dict]) -> str:
    d = details[0]
    src = f"{d['pro_games']} pro games" + (f" + {d['prior_games']:,} SoloQ" if d["prior_games"] else "")
    verb = "Pairs with" if d["wr"] >= 0.5 else "Awkward with"
    return f"{verb} {name_of(d['ally'])}: {pct(d['wr'])} WR together ({src})"


def _coach_evidence(ca: dict) -> str:
    if not ca["accepted"] and not ca["rejected"]:
        return "No previous coach decisions"
    return f"Coach accepted {ca['accepted']}×, rejected {ca['rejected']}× in past drafts"


def _step_dict(step: Step) -> dict:
    return {"index": step.index, "side": step.side, "type": step.type, "phase": step.phase, "label": step.label}
