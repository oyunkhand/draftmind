"""GRID esports adapter (Central Data API + Series State API, GraphQL).

Reads GRID_API_KEY from the environment. Pulls recent League of Legends esports series from
Central Data, then each series' state (games, teams, players, champions, draft actions) from the
Series State API, and normalizes it to the DraftMind Dataset shape.

GRID does not label player positions, so roles are inferred from the champions each team drafted
(same assignment solver the draft engine uses) and rosters take each player's most frequent role.
Objective timings / gold@15 are not part of Series State, so those fields stay null and the UI
shows "n/a" for them.
"""
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

import httpx

from .. import config
from ..champions import resolve
from ..engine.draft import assign_roles
from .base import DataAdapter, Dataset

log = logging.getLogger("draftmind.grid")

LOL_TITLE_ID = "3"

SERIES_QUERY = """
query Series($first: Int, $after: Cursor) {
  allSeries(first: $first, after: $after,
            filter: { titleId: 3, types: ESPORTS },
            orderBy: StartTimeScheduled, orderDirection: DESC) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      id startTimeScheduled
      format { nameShortened }
      tournament { name }
      teams { baseInfo { id name nameShortened colorPrimary } }
    } }
  }
}
"""

STATE_QUERY = """
query State($id: ID!) {
  seriesState(id: $id) {
    id finished startedAt
    teams { id name won score }
    games {
      id sequenceNumber finished
      draftActions { id type sequenceNumber drafter { id type } draftable { id type name } }
      teams { id name side won players { id name character { id name } } }
    }
  }
}
"""


class GridAdapter(DataAdapter):
    name = "grid"

    def __init__(self, api_key: Optional[str] = None, max_series: Optional[int] = None,
                 client: Optional[httpx.Client] = None):
        self.api_key = api_key or config.GRID_API_KEY
        if not self.api_key:
            raise ValueError("GRID_API_KEY is not set")
        self.max_series = max_series or config.GRID_MAX_SERIES
        self.client = client or httpx.Client(timeout=30.0, headers={"x-api-key": self.api_key})

    # ------------------------------------------------------------------ transport
    def _gql(self, url: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        r = self.client.post(url, json={"query": query, "variables": variables})
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"GRID GraphQL error: {body['errors'][0].get('message')}")
        return body["data"]

    def _list_series(self) -> List[dict]:
        out, after = [], None
        while len(out) < self.max_series:
            data = self._gql(config.GRID_CENTRAL_URL, SERIES_QUERY, {"first": 50, "after": after})
            conn = data["allSeries"]
            out.extend(e["node"] for e in conn["edges"])
            if not conn["pageInfo"]["hasNextPage"]:
                break
            after = conn["pageInfo"]["endCursor"]
        return out[: self.max_series]

    # ------------------------------------------------------------------ normalize
    def load(self) -> Dataset:
        teams: Dict[str, dict] = {}
        player_roles: Dict[str, Counter] = defaultdict(Counter)
        player_names: Dict[str, str] = {}
        player_team: Dict[str, str] = {}
        series_out, matches_out = [], []

        for node in self._list_series():
            for t in node.get("teams") or []:
                b = t["baseInfo"]
                teams.setdefault(b["id"], {"id": b["id"], "name": b["name"], "tag": b.get("nameShortened") or b["name"][:3],
                                           "color": b.get("colorPrimary") or "#64748b", "region": "GRID"})
            try:
                state = self._gql(config.GRID_SERIES_STATE_URL, STATE_QUERY, {"id": node["id"]})["seriesState"]
            except Exception as e:  # one bad series should not sink the import
                log.warning("series %s skipped: %s", node["id"], e)
                continue
            if not state or not state.get("games"):
                continue
            fmt = (node.get("format") or {}).get("nameShortened") or "Bo1"
            best_of = int("".join(ch for ch in fmt if ch.isdigit()) or 1)
            s_teams = [t["id"] for t in state["teams"]]
            game_ids = []
            for g in sorted(state["games"], key=lambda g: g["sequenceNumber"]):
                if not g.get("finished") or len(g.get("teams") or []) != 2:
                    continue
                m = self._normalize_game(node, state, g, player_roles, player_names, player_team)
                if m:
                    matches_out.append(m)
                    game_ids.append(m["id"])
            if not game_ids or len(s_teams) != 2:
                continue
            score = [next((t.get("score") or 0) for t in state["teams"] if t["id"] == tid) for tid in s_teams]
            winner = next((t["id"] for t in state["teams"] if t.get("won")), None)
            series_out.append({"id": node["id"], "tournament": (node.get("tournament") or {}).get("name"),
                               "date": node.get("startTimeScheduled"), "best_of": best_of, "fearless": False,
                               "team_a": s_teams[0], "team_b": s_teams[1], "winner": winner, "score": score,
                               "games": game_ids})

        for t in teams.values():
            t["players"] = []
        for pid, roles in player_roles.items():
            tid = player_team.get(pid)
            if tid in teams:
                teams[tid]["players"].append({"id": pid, "name": player_names[pid], "role": roles.most_common(1)[0][0]})
        if not matches_out:
            raise RuntimeError("GRID returned no finished LoL games with drafts")
        return {"source": self.name, "teams": list(teams.values()), "series": series_out,
                "matches": matches_out, "priors": {"matchups": [], "synergies": []}}

    def _normalize_game(self, node, state, g, player_roles, player_names, player_team) -> Optional[dict]:
        sides = {t["side"]: t for t in g["teams"]}
        if "blue" not in sides or "red" not in sides:
            return None
        participants = []
        for side, t in sides.items():
            champs = {}
            for p in t.get("players") or []:
                if p.get("character"):
                    champs[p["id"]] = resolve(p["character"]["name"])
                    player_names[p["id"]] = p["name"]
                    player_team[p["id"]] = t["id"]
            assignment = assign_roles(list(champs.values()))  # role -> champion
            by_champ = {c: r for r, c in assignment.items()}
            for pid, c in champs.items():
                role = by_champ.get(c, "flex")
                player_roles[pid][role] += 1
                participants.append({"team": t["id"], "side": side, "player": pid, "role": role, "champion": c})
        draft = []
        for a in sorted(g.get("draftActions") or [], key=lambda a: int(a["sequenceNumber"])):
            team_id = (a.get("drafter") or {}).get("id")
            side = next((s for s, t in sides.items() if t["id"] == team_id), None)
            draft.append({"seq": len(draft), "side": side, "type": a["type"].lower(), "team": team_id,
                          "champion": resolve(a["draftable"]["name"])})
        winner = next((t["id"] for t in g["teams"] if t.get("won")), None)
        return {"id": g["id"], "series_id": node["id"], "game_number": g["sequenceNumber"],
                "date": state.get("startedAt") or node.get("startTimeScheduled"), "patch": None,
                "tournament": (node.get("tournament") or {}).get("name"),
                "blue_team": sides["blue"]["id"], "red_team": sides["red"]["id"], "winner": winner,
                "duration_s": None, "draft": draft, "participants": participants,
                "objectives": {"first_blood": None, "first_dragon": None, "first_herald": None,
                               "first_tower": None, "gold_diff_15": None}}

    def describe(self):
        return {"name": self.name, "central": config.GRID_CENTRAL_URL, "series_state": config.GRID_SERIES_STATE_URL,
                "max_series": self.max_series}
