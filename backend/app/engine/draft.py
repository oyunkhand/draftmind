"""Pro draft state machine + fearless series tracking + role assignment.

Draft order (tournament draft, 20 actions):
  Ban phase 1 : B1 R1 B2 R2 B3 R3
  Pick phase 1: B1 R1 R2 B2 B3 R3
  Ban phase 2 : R4 B4 R5 B5
  Pick phase 2: R4 B4 B5 R5

First Selection (2026): the team with the selection picks a side OR the first draft turn, so the red
side can draft first. `draft_order("red")` mirrors the order above (R1 ban, R1 pick, ...).

Fearless modes:
  off  - classic draft
  hard - any champion PICKED in an earlier game of the series is unavailable to both teams
  soft - a team cannot re-pick champions it picked itself earlier in the series
"""
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import permutations, product
from typing import Dict, Iterable, List, Optional, Sequence, Set

from ..champions import ROLES, roles_of

SIDES = ("blue", "red")
FEARLESS_MODES = ("off", "hard", "soft")


@dataclass(frozen=True)
class Step:
    index: int
    side: str
    type: str  # "ban" | "pick"
    phase: str  # ban1 | pick1 | ban2 | pick2
    label: str  # e.g. "B1 ban", "R3 pick"


def _build_order(first: str = "blue") -> List[Step]:
    seq = (
        [("blue", "ban"), ("red", "ban")] * 3
        + [("blue", "pick"), ("red", "pick"), ("red", "pick"), ("blue", "pick"), ("blue", "pick"), ("red", "pick")]
        + [("red", "ban"), ("blue", "ban")] * 2
        + [("red", "pick"), ("blue", "pick"), ("blue", "pick"), ("red", "pick")]
    )
    if first == "red":
        seq = [(other(side), typ) for side, typ in seq]
    out, counters = [], {(s, t): 0 for s in SIDES for t in ("ban", "pick")}
    for i, (side, typ) in enumerate(seq):
        counters[(side, typ)] += 1
        phase = "ban1" if i < 6 else "pick1" if i < 12 else "ban2" if i < 16 else "pick2"
        out.append(Step(i, side, typ, phase, f"{side[0].upper()}{counters[(side, typ)]} {typ}"))
    return out


def other(side: str) -> str:
    return "red" if side == "blue" else "blue"


DRAFT_ORDER: List[Step] = _build_order("blue")
_ORDERS = {"blue": DRAFT_ORDER, "red": _build_order("red")}


def draft_order(first_side: str = "blue") -> List[Step]:
    """The 20-step order when `first_side` drafts first (blue is the classic order)."""
    if first_side not in _ORDERS:
        raise DraftError(f"first_side must be blue or red, not {first_side}")
    return _ORDERS[first_side]


# ---------------------------------------------------------------------------- roles
_ROLE_WEIGHT = [1.0, 0.8, 0.6]
OFF_ROLE = -2.0


@lru_cache(maxsize=None)
def role_fit(cid: str, role: str) -> float:
    rs = roles_of(cid)
    if role in rs:
        return _ROLE_WEIGHT[min(rs.index(role), 2)]
    return OFF_ROLE


def _feasible(champs: Sequence[str]) -> Optional[Dict[str, str]]:
    """Best assignment where every champion plays one of its listed roles, or None."""
    best, best_score = None, -1e9
    for combo in product(*[roles_of(c) or list(ROLES) for c in champs]):
        if len(set(combo)) != len(combo):
            continue
        s = sum(role_fit(c, r) for c, r in zip(champs, combo))
        if s > best_score:
            best, best_score = combo, s
    return {r: c for c, r in zip(champs, best)} if best else None


def assign_roles(champs: Sequence[str]) -> Dict[str, str]:
    """Best role -> champion assignment for up to 5 champions (falls back to off-role if unavoidable)."""
    champs = [c for c in champs if c][:5]
    if not champs:
        return {}
    a = _feasible(champs)
    if a is not None:
        return a
    best, best_score = None, -1e9
    for roles in permutations(ROLES, len(champs)):
        s = sum(role_fit(c, r) for c, r in zip(champs, roles))
        if s > best_score:
            best, best_score = roles, s
    return {r: c for c, r in zip(champs, best)}


def assignment_score(champs: Sequence[str]) -> float:
    a = assign_roles(champs)
    return sum(role_fit(c, r) for r, c in a.items())


def fits_open_role(existing: Sequence[str], cid: str) -> Optional[str]:
    """Role the new champion would take if it can join without forcing anyone off-role, else None."""
    existing = [c for c in existing if c]
    if len(existing) >= 5:
        return None
    a = _feasible(existing + [cid])
    if a is None:
        return None
    return next((r for r, c in a.items() if c == cid), None)


# ---------------------------------------------------------------------------- state
class DraftError(ValueError):
    pass


@dataclass
class DraftState:
    blue_team: str
    red_team: str
    actions: List[str] = field(default_factory=list)  # champion ids, in self.order
    fearless_mode: str = "off"
    locked: Dict[str, List[str]] = field(default_factory=lambda: {"blue": [], "red": []})
    first_side: str = "blue"  # which side drafts first (First Selection)

    @property
    def order(self) -> List[Step]:
        return draft_order(self.first_side)

    # -- queries ------------------------------------------------------------
    @property
    def index(self) -> int:
        return len(self.actions)

    @property
    def complete(self) -> bool:
        return self.index >= len(self.order)

    @property
    def current(self) -> Optional[Step]:
        return None if self.complete else self.order[self.index]

    def team_of(self, side: str) -> str:
        return self.blue_team if side == "blue" else self.red_team

    def side_of(self, team: str) -> str:
        if team == self.blue_team:
            return "blue"
        if team == self.red_team:
            return "red"
        raise DraftError(f"team {team} is not in this draft")

    def _of(self, side: str, typ: str) -> List[str]:
        return [c for step, c in zip(self.order, self.actions) if step.side == side and step.type == typ]

    def picks(self, side: str) -> List[str]:
        return self._of(side, "pick")

    def bans(self, side: str) -> List[str]:
        return self._of(side, "ban")

    def taken(self) -> Set[str]:
        return set(self.actions)

    def roles(self, side: str) -> Dict[str, str]:
        return assign_roles(self.picks(side))

    def open_roles(self, side: str) -> List[str]:
        filled = self.roles(side)
        return [r for r in ROLES if r not in filled]

    def next_step_for(self, side: str, typ: Optional[str] = None) -> Optional[Step]:
        for step in self.order[self.index:]:
            if step.side == side and (typ is None or step.type == typ):
                return step
        return None

    def unavailable_reason(self, cid: str, side: str, typ: str) -> Optional[str]:
        if cid in self.taken():
            return "already picked or banned"
        if typ == "pick" and cid in self.locked.get(side, []):
            return "fearless: used earlier in the series"
        if typ == "ban" and all(cid in self.locked.get(s, []) for s in SIDES):
            return "fearless: already locked for both teams"
        return None

    def is_available(self, cid: str, side: str, typ: str) -> bool:
        return self.unavailable_reason(cid, side, typ) is None

    # -- transitions -------------------------------------------------------------
    def apply(self, cid: str) -> Step:
        step = self.current
        if step is None:
            raise DraftError("draft is complete")
        if not roles_of(cid):
            raise DraftError(f"unknown champion {cid}")
        reason = self.unavailable_reason(cid, step.side, step.type)
        if reason:
            raise DraftError(f"{cid} unavailable: {reason}")
        self.actions.append(cid)
        return step

    def undo(self) -> Optional[str]:
        return self.actions.pop() if self.actions else None

    # -- serialization -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"blue_team": self.blue_team, "red_team": self.red_team, "actions": list(self.actions),
                "fearless_mode": self.fearless_mode, "locked": {s: list(v) for s, v in self.locked.items()},
                "first_side": self.first_side}

    @classmethod
    def from_dict(cls, d: dict) -> "DraftState":
        return cls(d["blue_team"], d["red_team"], list(d.get("actions", [])), d.get("fearless_mode", "off"),
                   {s: list(d.get("locked", {}).get(s, [])) for s in SIDES}, d.get("first_side", "blue"))

    def timeline(self) -> List[dict]:
        out = []
        for step in self.order:
            c = self.actions[step.index] if step.index < len(self.actions) else None
            out.append({"index": step.index, "side": step.side, "type": step.type, "phase": step.phase,
                        "label": step.label, "team": self.team_of(step.side), "champion": c,
                        "current": step.index == self.index})
        return out


# ---------------------------------------------------------------------------- fearless
@dataclass
class SeriesGame:
    blue_team: str
    red_team: str
    blue_picks: List[str]
    red_picks: List[str]


def fearless_locks(previous: Iterable[SeriesGame], blue_team: str, red_team: str, mode: str) -> Dict[str, List[str]]:
    """Champions each side of the upcoming game may not pick."""
    if mode not in FEARLESS_MODES:
        raise DraftError(f"unknown fearless mode {mode}")
    locked: Dict[str, List[str]] = {"blue": [], "red": []}
    if mode == "off":
        return locked
    by_team: Dict[str, List[str]] = {}
    everything: List[str] = []
    for g in previous:
        for team, picks in ((g.blue_team, g.blue_picks), (g.red_team, g.red_picks)):
            by_team.setdefault(team, []).extend(picks)
            everything.extend(picks)
    for side, team in (("blue", blue_team), ("red", red_team)):
        pool = everything if mode == "hard" else by_team.get(team, [])
        locked[side] = sorted(set(pool))
    return locked
