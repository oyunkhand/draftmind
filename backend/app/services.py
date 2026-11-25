"""Coach workflow: series, draft sessions, human-in-the-loop decisions."""
import datetime as dt
import json
import uuid
from typing import List, Optional

from . import db
from .champions import name_of, resolve
from .engine import scoring
from .engine.draft import (DRAFT_ORDER, FEARLESS_MODES, DraftError, DraftState, SeriesGame, fearless_locks, other)
from .engine.stats import StatsIndex

DECISIONS = ("accept", "modify", "reject")


class NotFound(KeyError):
    pass


def _now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------- weights
def get_weights() -> dict:
    return scoring.merge_weights(db.get_setting("weights"))


def set_weights(w: dict) -> dict:
    merged = scoring.merge_weights(w)
    db.set_setting("weights", merged)
    return merged


def reset_weights() -> dict:
    db.set_setting("weights", scoring.DEFAULT_WEIGHTS)
    return scoring.merge_weights(None)


# ---------------------------------------------------------------------------- series
def create_series(our_team: str, opponent: str, best_of: int = 3, fearless_mode: str = "hard",
                  title: Optional[str] = None) -> dict:
    if our_team == opponent:
        raise DraftError("pick two different teams")
    if fearless_mode not in FEARLESS_MODES:
        raise DraftError(f"fearless_mode must be one of {FEARLESS_MODES}")
    if not db.one("SELECT id FROM teams WHERE id=?", (our_team,)) or not db.one("SELECT id FROM teams WHERE id=?", (opponent,)):
        raise DraftError("unknown team")
    sid = _id("ser")
    with db.tx() as c:
        c.execute("INSERT INTO coach_series VALUES (?,?,?,?,?,?,?)",
                  (sid, our_team, opponent, int(best_of), fearless_mode, title, _now()))
    return get_series(sid)


def list_series() -> List[dict]:
    out = []
    for s in db.rows("SELECT * FROM coach_series ORDER BY created_at DESC"):
        games = db.rows("SELECT id, game_number, our_side, result, state FROM draft_sessions WHERE series_id=? ORDER BY game_number", (s["id"],))
        s["games"] = [{"id": g["id"], "game_number": g["game_number"], "our_side": g["our_side"], "result": g["result"],
                       "complete": len(json.loads(g["state"])["actions"]) >= 20} for g in games]
        s["score"] = [sum(g["result"] == "win" for g in games), sum(g["result"] == "loss" for g in games)]
        s["decisions"] = db.one("SELECT COUNT(*) n FROM decisions WHERE series_id=?", (s["id"],))["n"]
        out.append(s)
    return out


def get_series(sid: str) -> dict:
    s = db.one("SELECT * FROM coach_series WHERE id=?", (sid,))
    if not s:
        raise NotFound(sid)
    games = []
    for g in db.rows("SELECT * FROM draft_sessions WHERE series_id=? ORDER BY game_number", (sid,)):
        state = DraftState.from_dict(json.loads(g["state"]))
        decisions = db.rows("SELECT * FROM decisions WHERE session_id=? ORDER BY id", (g["id"],))
        for d in decisions:
            d["top_suggestions"] = json.loads(d["top_suggestions"] or "[]")
        games.append({"id": g["id"], "game_number": g["game_number"], "our_side": g["our_side"], "result": g["result"],
                      "complete": state.complete, "timeline": state.timeline(), "locked": state.locked,
                      "blue_team": state.blue_team, "red_team": state.red_team, "decisions": decisions,
                      "created_at": g["created_at"]})
    s["games"] = games
    s["score"] = [sum(g["result"] == "win" for g in games), sum(g["result"] == "loss" for g in games)]
    s["fearless_pool"] = _series_used(sid)
    return s


def delete_series(sid: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM decisions WHERE series_id=?", (sid,))
        c.execute("DELETE FROM draft_sessions WHERE series_id=?", (sid,))
        c.execute("DELETE FROM coach_series WHERE id=?", (sid,))


def _series_used(sid: str) -> List[dict]:
    used = []
    for g in db.rows("SELECT * FROM draft_sessions WHERE series_id=? ORDER BY game_number", (sid,)):
        st = DraftState.from_dict(json.loads(g["state"]))
        for side in ("blue", "red"):
            for c in st.picks(side):
                used.append({"champion": c, "team": st.team_of(side), "game": g["game_number"]})
    return used


def _previous_games(sid: str, before: int) -> List[SeriesGame]:
    out = []
    for g in db.rows("SELECT state FROM draft_sessions WHERE series_id=? AND game_number<? ORDER BY game_number", (sid, before)):
        st = DraftState.from_dict(json.loads(g["state"]))
        out.append(SeriesGame(st.blue_team, st.red_team, st.picks("blue"), st.picks("red")))
    return out


def create_game(sid: str, our_side: str = "blue") -> dict:
    s = db.one("SELECT * FROM coach_series WHERE id=?", (sid,))
    if not s:
        raise NotFound(sid)
    if our_side not in ("blue", "red"):
        raise DraftError("our_side must be blue or red")
    n = db.one("SELECT COUNT(*) n FROM draft_sessions WHERE series_id=?", (sid,))["n"]
    if n >= s["best_of"]:
        raise DraftError(f"series is best of {s['best_of']}; all games already created")
    blue, red = (s["our_team"], s["opponent"]) if our_side == "blue" else (s["opponent"], s["our_team"])
    locks = fearless_locks(_previous_games(sid, n + 1), blue, red, s["fearless_mode"])
    state = DraftState(blue, red, fearless_mode=s["fearless_mode"], locked=locks)
    gid = _id("drf")
    with db.tx() as c:
        c.execute("INSERT INTO draft_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (gid, sid, n + 1, s["our_team"], s["opponent"], our_side, json.dumps(state.to_dict()), None, _now(), _now()))
    return {"id": gid, "series_id": sid, "game_number": n + 1}


def quick_draft(our_team: str, opponent: str, our_side: str = "blue", fearless_mode: str = "off") -> dict:
    s = create_series(our_team, opponent, best_of=1 if fearless_mode == "off" else 3, fearless_mode=fearless_mode,
                      title="Quick draft")
    return create_game(s["id"], our_side)


# ---------------------------------------------------------------------------- sessions
def _load(gid: str):
    g = db.one("SELECT * FROM draft_sessions WHERE id=?", (gid,))
    if not g:
        raise NotFound(gid)
    return g, DraftState.from_dict(json.loads(g["state"]))


def _save(gid: str, state: DraftState) -> None:
    with db.tx() as c:
        c.execute("UPDATE draft_sessions SET state=?, updated_at=? WHERE id=?", (json.dumps(state.to_dict()), _now(), gid))


def _rejected_now(gid: str, step: int) -> set:
    return {r["suggested_champion"] for r in
            db.rows("SELECT suggested_champion FROM decisions WHERE session_id=? AND step=? AND decision='reject'", (gid, step))}


def analysis(idx: StatsIndex, gid: str) -> dict:
    g, state = _load(gid)
    our_side, opp_side = g["our_side"], other(g["our_side"])
    affinity = scoring.coach_affinity(db.rows("SELECT * FROM decisions WHERE our_team=?", (g["our_team"],)))
    excluded = _rejected_now(gid, state.index) if state.current and state.current.side == our_side else set()
    rec = scoring.recommend(idx, state, our_side, get_weights(), affinity, exclude=excluded)
    pred = scoring.predict_opponent(idx, state, opp_side)
    series = db.one("SELECT * FROM coach_series WHERE id=?", (g["series_id"],))
    return {
        "id": gid, "series_id": g["series_id"], "game_number": g["game_number"], "best_of": series["best_of"] if series else 1,
        "our_team": g["our_team"], "opponent": g["opponent"], "our_side": our_side, "result": g["result"],
        "fearless_mode": state.fearless_mode, "locked": state.locked,
        "state": {"index": state.index, "complete": state.complete,
                  "current": state.current and {"index": state.current.index, "side": state.current.side,
                                                "type": state.current.type, "phase": state.current.phase,
                                                "label": state.current.label, "team": state.team_of(state.current.side),
                                                "ours": state.current.side == our_side},
                  "timeline": state.timeline(), "roles": {s: state.roles(s) for s in ("blue", "red")}},
        "recommendations": rec, "prediction": pred, "rejected_this_step": sorted(excluded),
        "decisions": db.rows("SELECT id, step, action_type, suggested_champion, decision, final_champion, note, created_at "
                             "FROM decisions WHERE session_id=? ORDER BY id", (gid,)),
    }


def apply_action(idx: StatsIndex, gid: str, champion: str) -> dict:
    g, state = _load(gid)
    c = resolve(champion)
    step = state.current
    if step and step.side == g["our_side"]:
        # A direct grid click on our turn is logged as a manual call (useful in Series History).
        rec = scoring.recommend(idx, state, g["our_side"], get_weights(), exclude=_rejected_now(gid, state.index), top=5)
        _log_decision(g, state, rec, c if rec["recommendations"] and rec["recommendations"][0]["champion"] == c else None,
                      "manual", c, None)
    state.apply(c)
    _save(gid, state)
    return analysis(idx, gid)


def undo(idx: StatsIndex, gid: str) -> dict:
    g, state = _load(gid)
    removed = state.undo()
    if removed is not None:
        with db.tx() as conn:
            conn.execute("DELETE FROM decisions WHERE session_id=? AND step>=? AND decision!='reject'", (gid, state.index))
        _save(gid, state)
    return analysis(idx, gid)


def _log_decision(g: dict, state: DraftState, rec: dict, suggested: Optional[str], decision: str,
                  final: Optional[str], note: Optional[str]) -> None:
    recs = rec.get("recommendations", [])
    hit = next((r for r in recs if r["champion"] == suggested), None)
    top = [{"champion": r["champion"], "score": r["score"]} for r in recs[:5]]
    with db.tx() as c:
        c.execute("INSERT INTO decisions (session_id, series_id, our_team, opponent, step, action_type, suggested_champion, "
                  "suggested_rank, suggested_score, decision, final_champion, note, top_suggestions, created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (g["id"], g["series_id"], g["our_team"], g["opponent"], state.index, state.current.type,
                   suggested, hit["rank"] if hit else None, hit["score"] if hit else None, decision, final, note,
                   json.dumps(top), _now()))


def decide(idx: StatsIndex, gid: str, champion: str, decision: str, final_champion: Optional[str] = None,
           note: Optional[str] = None) -> dict:
    if decision not in DECISIONS:
        raise DraftError(f"decision must be one of {DECISIONS}")
    g, state = _load(gid)
    step = state.current
    if step is None:
        raise DraftError("draft is complete")
    if step.side != g["our_side"]:
        raise DraftError("it is not our turn")
    suggested = resolve(champion)
    final = resolve(final_champion) if final_champion else None
    if decision == "modify" and not final:
        raise DraftError("modify needs final_champion")
    rec = scoring.recommend(idx, state, g["our_side"], get_weights(), exclude=_rejected_now(gid, state.index), top=8)
    chosen = suggested if decision == "accept" else final
    if chosen:
        reason = state.unavailable_reason(chosen, step.side, step.type)
        if reason:
            raise DraftError(f"{name_of(chosen)} unavailable: {reason}")
    _log_decision(g, state, rec, suggested, decision, chosen, note)
    if chosen:
        state.apply(chosen)
        _save(gid, state)
    return analysis(idx, gid)


def set_result(idx: StatsIndex, gid: str, result: Optional[str]) -> dict:
    if result not in ("win", "loss", None):
        raise DraftError("result must be win, loss or null")
    _load(gid)
    with db.tx() as c:
        c.execute("UPDATE draft_sessions SET result=?, updated_at=? WHERE id=?", (result, _now(), gid))
    return analysis(idx, gid)


def decision_log(our_team: Optional[str] = None, limit: int = 200) -> List[dict]:
    q, p = "SELECT * FROM decisions", ()
    if our_team:
        q, p = q + " WHERE our_team=?", (our_team,)
    out = db.rows(q + " ORDER BY id DESC LIMIT ?", p + (limit,))
    for d in out:
        d["top_suggestions"] = json.loads(d["top_suggestions"] or "[]")
    return out


__all__ = ["DRAFT_ORDER"]
