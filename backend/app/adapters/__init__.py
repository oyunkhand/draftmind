import logging
from typing import Tuple

from .. import config
from .base import DataAdapter, Dataset
from .sample import SampleAdapter

log = logging.getLogger("draftmind.adapters")


def load_dataset() -> Tuple[Dataset, dict]:
    """Pick the adapter from DATA_SOURCE / GRID_API_KEY. GRID failures fall back to the sample data."""
    src = config.DATA_SOURCE
    if src == "grid-files" or (src == "auto" and not config.GRID_API_KEY):
        from . import grid_files
        if grid_files.available():
            try:
                adapter = grid_files.GridFilesAdapter()
                return adapter.load(), adapter.describe()
            except Exception as e:  # noqa: BLE001 - surface + fall back, the app must keep working
                log.warning("GRID files adapter failed (%s); falling back to sample dataset", e)
        elif src == "grid-files":
            log.warning("STL_DATA_DIR %s not found; falling back to sample dataset", config.STL_DATA_DIR)
    if src == "grid" or (src == "auto" and config.GRID_API_KEY):
        try:
            from .grid import GridAdapter
            adapter = GridAdapter()
            data = adapter.load()
            return data, adapter.describe()
        except Exception as e:  # noqa: BLE001 - surface + fall back, the app must keep working
            log.warning("GRID adapter failed (%s); falling back to sample dataset", e)
            adapter = SampleAdapter()
            info = adapter.describe()
            info["fallback_reason"] = str(e)
            return adapter.load(), info
    adapter = SampleAdapter()
    return adapter.load(), adapter.describe()


__all__ = ["DataAdapter", "Dataset", "SampleAdapter", "load_dataset"]
