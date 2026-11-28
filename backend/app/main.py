"""DraftMind AI — FastAPI application."""
import base64
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from . import config, db, scouting, services
from .adapters import load_dataset
from .champions import all_champions, ddragon_version, name_of
from .engine import stats as stats_mod
from .engine.backtest import run_backtest
from .engine.scoring import MODEL_INFO, PREDICT_BAN, PREDICT_PICK
from .engine.draft import DraftError, draft_order
from .engine.explain import explain
from .engine.selection import first_selection_advice
from .engine.scoring import DEFAULT_WEIGHTS, FACTOR_LABELS
from .ingest import ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("draftmind")


def bootstrap() -> dict:
    data, info = load_dataset()
    meta = ingest(db.get_conn(), data, info)
    stats_mod.invalidate()
    log.info("dataset ready: %s (%s matches)", meta.get("source"), meta.get("matches"))
    return meta


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="DraftMind AI", version="1.0.0", lifespan=lifespan,
              description="AI draft & scouting assistant for League of Legends coaches.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

_AUTH_EXEMPT = {"/api/health"}  # the host's health check must work without credentials


def _authorized(header: Optional[str]) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).partition(b":")
    except ValueError:
        return False
    # compare bytes: compare_digest raises TypeError on non-ASCII str (e.g. a password typed on a Cyrillic layout)
    return secrets.compare_digest(user, config.DEMO_USER.encode()) & secrets.compare_digest(pw, config.DEMO_PASSWORD.encode())


@app.middleware("http")
async def demo_auth(request: Request, call_next):
    """Password-protect the whole site when DEMO_PASSWORD is set (judges-only demo of licensed data)."""
    if config.DEMO_PASSWORD and request.method != "OPTIONS" and request.url.path not in _AUTH_EXEMPT \
            and not _authorized(request.headers.get("authorization")):
        return Response(status_code=401, content="Authentication required",
                        headers={"WWW-Authenticate": 'Basic realm="DraftMind demo", charset="UTF-8"'})
    response = await call_next(request)
    if config.DEMO_PASSWORD:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.exception_handler(DraftError)
async def _draft_error(_: Request, e: DraftError):
    return JSONResponse(status_code=400, content={"detail": str(e)})


@app.exception_handler(services.NotFound)
async def _not_found(_: Request, e: services.NotFound):
    return JSONResponse(status_code=404, content={"detail": f"not found: {e.args[0]}"})


def idx():
    return stats_mod.get_index()


# ---------------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    ds = db.get_setting("dataset", {})
    return {"status": "ok", "data_source": ds.get("source"), "dataset": ds, "llm_provider": config.llm_provider(),
            "ddragon_version": ddragon_version()}


@app.get("/api/champions")
def champions():
    return {"version": ddragon_version(), "champions": list(all_champions().values())}


@app.get("/api/draft-order")
def get_draft_order(first_side: str = "blue"):
    return [{"index": s.index, "side": s.side, "type": s.type, "phase": s.phase, "label": s.label}
            for s in draft_order(first_side)]


@app.post("/api/admin/reload")
def reload_data():
    return bootstrap()


# ---------------------------------------------------------------------------- teams & matches
@app.get("/api/teams")
def teams():
    i = idx()
    out = []
    for t in db.rows("SELECT * FROM teams ORDER BY name"):
        s = i.team_games.get(t["id"])
        t["players"] = db.rows("SELECT id, name, role FROM players WHERE team_id=?", (t["id"],))
        t["games"], t["wins"] = (s.games, s.wins) if s else (0, 0)
        out.append(t)
    return out


@app.get("/api/teams/{team_id}")
def team(team_id: str):
    t = db.one("SELECT * FROM teams WHERE id=?", (team_id,))
    if not t:
        raise HTTPException(404, "team not found")
    t["players"] = db.rows("SELECT id, name, role FROM players WHERE team_id=?", (team_id,))
    t["summary"] = idx().team_summary(team_id)
    return t


@app.get("/api/matches")
def matches(team: Optional[str] = None, opponent: Optional[str] = None, limit: int = Query(20, le=200)):
    if team:
        return scouting.recent_matches(team, limit, opponent)
    return db.rows("SELECT * FROM matches ORDER BY date DESC LIMIT ?", (limit,))


@app.get("/api/h2h")
def head_to_head(a: str, b: str):
    ms = scouting.recent_matches(a, 50, b)
    return {"a": a, "b": b, "games": len(ms), "a_wins": sum(m["win"] for m in ms), "matches": ms[:10]}


@app.get("/api/dashboard")
def dashboard(our: str, opp: str):
    i = idx()
    h = head_to_head(our, opp)
    rep = scouting.build_report(i, opp, vs=our)
    return {"our": i.team_summary(our), "opp": i.team_summary(opp), "h2h": h,
            "our_recent": scouting.recent_matches(our, 6), "opp_recent": scouting.recent_matches(opp, 6),
            "insights": rep["insights"], "ban_plan": rep.get("ban_plan", [])}


@app.get("/api/first-selection")
def first_selection(our: str, opp: str):
    """First Selection advice: take a side or a draft turn? (minimax over the opponent's reply)"""
    return first_selection_advice(idx().matches, our, opp)


# ---------------------------------------------------------------------------- scouting
@app.get("/api/teams/{team_id}/scouting")
def scouting_report(team_id: str, vs: Optional[str] = None):
    try:
        return scouting.build_report(idx(), team_id, vs)
    except KeyError:
        raise HTTPException(404, "team not found")


@app.get("/api/teams/{team_id}/scouting.md", response_class=PlainTextResponse)
def scouting_markdown(team_id: str, vs: Optional[str] = None):
    try:
        md = scouting.to_markdown(scouting.build_report(idx(), team_id, vs))
    except KeyError:
        raise HTTPException(404, "team not found")
    return PlainTextResponse(md, headers={"Content-Disposition": f'attachment; filename="scouting-{team_id}.md"'})


# ---------------------------------------------------------------------------- settings
class WeightsIn(BaseModel):
    pick: Dict[str, float] = Field(default_factory=dict)
    ban: Dict[str, float] = Field(default_factory=dict)


@app.get("/api/settings/weights")
def get_weights():
    return {"weights": services.get_weights(), "defaults": DEFAULT_WEIGHTS, "labels": FACTOR_LABELS}


@app.put("/api/settings/weights")
def put_weights(w: WeightsIn):
    return {"weights": services.set_weights(w.model_dump()), "defaults": DEFAULT_WEIGHTS, "labels": FACTOR_LABELS}


@app.post("/api/settings/weights/reset")
def reset_weights():
    return {"weights": services.reset_weights(), "defaults": DEFAULT_WEIGHTS, "labels": FACTOR_LABELS}


# ---------------------------------------------------------------------------- series & drafts
class SeriesIn(BaseModel):
    our_team: str
    opponent: str
    best_of: int = Field(3, ge=1, le=5)
    fearless_mode: str = "hard"
    title: Optional[str] = None


class GameIn(BaseModel):
    our_side: str = "blue"
    first_side: str = "blue"  # First Selection: which side drafts first


class QuickDraftIn(BaseModel):
    our_team: str
    opponent: str
    our_side: str = "blue"
    fearless_mode: str = "off"
    first_side: str = "blue"


class ActionIn(BaseModel):
    champion: str


class DecisionIn(BaseModel):
    champion: str
    decision: str
    final_champion: Optional[str] = None
    note: Optional[str] = None


class ResultIn(BaseModel):
    result: Optional[str] = None


class ExplainIn(BaseModel):
    champion: str
    kind: str = "recommendation"  # recommendation | prediction


@app.get("/api/series")
def list_series():
    return services.list_series()


@app.post("/api/series")
def create_series(body: SeriesIn):
    return services.create_series(body.our_team, body.opponent, body.best_of, body.fearless_mode, body.title)


@app.get("/api/series/{sid}")
def get_series(sid: str):
    return services.get_series(sid)


@app.delete("/api/series/{sid}")
def delete_series(sid: str):
    services.delete_series(sid)
    return {"ok": True}


@app.post("/api/series/{sid}/games")
def create_game(sid: str, body: GameIn):
    return services.create_game(sid, body.our_side, body.first_side)


@app.post("/api/drafts")
def quick_draft(body: QuickDraftIn):
    return services.quick_draft(body.our_team, body.opponent, body.our_side, body.fearless_mode, body.first_side)


@app.get("/api/drafts/{gid}")
def get_draft(gid: str):
    return services.analysis(idx(), gid)


@app.post("/api/drafts/{gid}/actions")
def draft_action(gid: str, body: ActionIn):
    return services.apply_action(idx(), gid, body.champion)


@app.post("/api/drafts/{gid}/undo")
def draft_undo(gid: str):
    return services.undo(idx(), gid)


@app.post("/api/drafts/{gid}/decisions")
def draft_decision(gid: str, body: DecisionIn):
    return services.decide(idx(), gid, body.champion, body.decision, body.final_champion, body.note)


@app.post("/api/drafts/{gid}/result")
def draft_result(gid: str, body: ResultIn):
    return services.set_result(idx(), gid, body.result)


@app.post("/api/drafts/{gid}/explain")
def draft_explain(gid: str, body: ExplainIn):
    a = services.analysis(idx(), gid)
    pool = a["prediction"]["predictions"] if body.kind == "prediction" else a["recommendations"]["recommendations"]
    rec = next((r for r in pool if r["champion"] == body.champion), None)
    if not rec:
        raise HTTPException(404, "champion is not in the current list")
    tl = [f"{s['label']}: {name_of(s['champion'])}" for s in a["state"]["timeline"] if s["champion"]]
    step = a["recommendations"]["step"] if body.kind != "prediction" else a["prediction"]["step"]
    ctx = {"our_team": a["our_team"], "opponent": a["opponent"], "action": (step or {}).get("type", "pick"),
           "draft_so_far": ", ".join(tl) or "start of draft"}
    return explain(rec, ctx, body.kind)


@app.get("/api/decisions")
def decisions(team: Optional[str] = None):
    return services.decision_log(team)


# ---------------------------------------------------------------------------- model quality
_bt_lock = threading.Lock()
_bt_cache: Dict[str, dict] = {}


@app.get("/api/model/backtest")
def backtest():
    ds = db.get_setting("dataset", {})
    key = ds.get("fingerprint", "x")
    with _bt_lock:
        if key not in _bt_cache:
            i = idx()
            pri = {"matchups": [{"a": a, "b": b, "wr_a": v[0], "games": v[1]} for (a, b), v in i.prior_matchup.items() if a < b],
                   "synergies": [{"a": k[0], "b": k[1], "wr": v[0], "games": v[1]} for k, v in i.prior_synergy.items()]}
            _bt_cache[key] = run_backtest(i.matches, list(i.teams.values()), pri)
            _bt_cache[key]["model"] = {**MODEL_INFO, "pick": PREDICT_PICK, "ban": PREDICT_BAN}
        return _bt_cache[key]


# ---------------------------------------------------------------------------- frontend (single origin)
# Registered last so every /api route above wins. Unknown non-API paths return index.html (SPA routing).
if (config.FRONTEND_DIST / "index.html").is_file():
    _dist = config.FRONTEND_DIST.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = (_dist / path).resolve()
        if path and f.is_file() and _dist in f.parents:
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
