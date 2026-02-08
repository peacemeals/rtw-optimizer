"""JSON file-based scrape cache with TTL expiry.

Stores scrape results at ~/.rtw/cache/ to avoid redundant requests.
Each cache entry is a JSON file with data + timestamp for TTL checks.
"""

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional


_DEFAULT_CACHE_DIR = Path.home() / ".rtw" / "cache"
_DEFAULT_TTL_HOURS = 24


class ScrapeCache:
    """Simple JSON file cache with TTL-based expiry."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl_hours: float = _DEFAULT_TTL_HOURS,
    ) -> None:
        self.cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self.default_ttl_hours = default_ttl_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Convert an arbitrary key string into a filesystem-safe filename."""
        # Replace non-alphanumeric chars with underscores, then hash for uniqueness
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
        # Add a short hash to avoid collisions from different keys that sanitize the same
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:12]
        return f"{safe[:80]}_{key_hash}.json"

    def _path_for(self, key: str) -> Path:
        """Return the file path for a cache key."""
        return self.cache_dir / self._sanitize_key(key)

    def set(self, key: str, data: Any, ttl_hours: Optional[float] = None) -> None:
        """Store data in the cache with a TTL.

        Args:
            key: Cache key (will be sanitized for filesystem safety).
            data: JSON-serializable data to cache.
            ttl_hours: Time-to-live in hours. Defaults to instance default (24h).
        """
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        entry = {
            "key": key,
            "data": data,
            "timestamp": time.time(),
            "ttl_seconds": ttl * 3600,
        }
        path = self._path_for(key)
        path.write_text(json.dumps(entry, default=str), encoding="utf-8")

    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached data if it exists and hasn't expired.

        Returns:
            The cached data, or None if missing or expired.
        """
        path = self._path_for(key)
        if not path.exists():
            return None

        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # Check TTL
        age = time.time() - entry.get("timestamp", 0)
        if age > entry.get("ttl_seconds", 0):
            # Expired - clean up
            try:
                path.unlink()
            except OSError:
                pass
            return None

        return entry.get("data")

    def clear(self) -> None:
        """Remove all cached files."""
        if not self.cache_dir.exists():
            return
        for path in self.cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass
