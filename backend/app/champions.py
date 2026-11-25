"""Champion metadata from the bundled Riot Data Dragon snapshot (data/champions.json)."""
import json
from functools import lru_cache
from typing import Dict, List

from . import config

ROLES = ["top", "jungle", "mid", "bot", "support"]


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(config.DATA_DIR / "champions.json") as f:
        return json.load(f)


def ddragon_version() -> str:
    return _load()["version"]


@lru_cache(maxsize=1)
def all_champions() -> Dict[str, dict]:
    return {c["id"]: c for c in _load()["champions"]}


def roles_of(cid: str) -> List[str]:
    c = all_champions().get(cid)
    return list(c["roles"]) if c else []


def name_of(cid: str) -> str:
    c = all_champions().get(cid)
    return c["name"] if c else cid


@lru_cache(maxsize=1)
def _name_index() -> Dict[str, str]:
    idx = {}
    for cid, c in all_champions().items():
        for k in (cid, c["name"], str(c["key"])):
            idx[normalize(k)] = cid
    return idx


def normalize(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def resolve(name_or_id: str) -> str:
    """Map a display name / numeric key / id (e.g. "Kai'Sa", "145", "Kaisa") to the Data Dragon id."""
    return _name_index().get(normalize(str(name_or_id)), str(name_or_id))
