"""Offline adapter: the seeded synthetic dataset in data/seed/dataset.json."""
import json
from pathlib import Path
from typing import Optional

from .. import config
from .base import DataAdapter, Dataset


class SampleAdapter(DataAdapter):
    name = "sample"

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or config.DATA_DIR / "seed" / "dataset.json")

    def load(self) -> Dataset:
        with open(self.path) as f:
            data = json.load(f)
        data["source"] = self.name
        return data

    def describe(self):
        return {"name": self.name, "path": str(self.path),
                "note": "Synthetic dataset (fictional teams) so the app runs fully offline."}
