"""Persistence for last search results, enabling `rtw verify` without re-searching."""

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import ValidationError

from rtw.search.models import SearchResult

if TYPE_CHECKING:
    from rtw.search.models import ScoredCandidate

logger = logging.getLogger(__name__)

_DEFAULT_STATE_PATH = Path.home() / ".rtw" / "last_search.json"


class SearchState:
    """Saves and loads the most recent search result for verification."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = state_path or _DEFAULT_STATE_PATH

    def save(self, result: SearchResult) -> None:
        """Serialize SearchResult to JSON file."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = result.model_dump(mode="json")
        data["_saved_at"] = time.time()
        self.state_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        logger.info("Search state saved: %s", self.state_path)

    def load(self) -> Optional[SearchResult]:
        """Deserialize from file. Returns None if missing or corrupted."""
        if not self.state_path.exists():
            return None
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            # Remove our metadata key before validation
            raw.pop("_saved_at", None)
            return SearchResult.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            logger.warning("Failed to load search state: %s", exc)
            return None

    def get_option(self, option_id: int) -> Optional["ScoredCandidate"]:
        """Fetch a specific option by 1-based ID.

        Args:
            option_id: 1-based index (as shown in CLI output).

        Returns:
            ScoredCandidate or None if not found.
        """
        result = self.load()
        if result is None:
            return None
        idx = option_id - 1  # Convert to 0-based
        if 0 <= idx < len(result.options):
            return result.options[idx]
        return None

    def state_age_minutes(self) -> Optional[float]:
        """Return age of the state file in minutes, or None."""
        if not self.state_path.exists():
            return None
        mtime = self.state_path.stat().st_mtime
        return (time.time() - mtime) / 60

    @property
    def option_count(self) -> int:
        """Number of options in saved state, 0 if no state."""
        result = self.load()
        return len(result.options) if result else 0
