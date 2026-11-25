"""Data adapter interface.

Every adapter returns a normalized `Dataset` dict which is ingested into SQLite. All analytics
read from SQLite, so the scoring engine never knows which provider the data came from.

Dataset shape:
{
  "source": "sample" | "grid",
  "teams":   [{id, name, tag, color, region, players: [{id, name, role}]}],
  "series":  [{id, tournament, date, best_of, fearless, team_a, team_b, winner, score: [a, b], games: [match ids]}],
  "matches": [{id, series_id, game_number, date, patch, tournament, blue_team, red_team, winner, duration_s,
               draft: [{seq, side, type: "ban"|"pick", team, champion}],        # champion = Data Dragon id
               participants: [{team, side, player, role, champion}],
               objectives: {first_blood, first_dragon, first_herald, first_tower: team id | None,
                            gold_diff_15: int (blue - red) | None}}],
  "priors":  {"matchups": [{a, b, wr_a, games}], "synergies": [{a, b, wr, games}]}   # optional
}
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

Dataset = Dict[str, Any]


class DataAdapter(ABC):
    name = "base"

    @abstractmethod
    def load(self) -> Dataset:
        """Fetch and normalize the full dataset."""

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name}
