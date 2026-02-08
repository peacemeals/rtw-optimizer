"""Tests for ScrapeCache - JSON file cache with TTL expiry."""

import time


from rtw.scraper.cache import ScrapeCache


class TestScrapeCache:
    """Test ScrapeCache set/get/expire/clear operations."""

    def test_set_and_get(self, tmp_path):
        """Cache stores and retrieves data correctly."""
        cache = ScrapeCache(cache_dir=tmp_path)
        cache.set("test_key", {"price": 1234.56, "carrier": "QF"})

        result = cache.get("test_key")
        assert result is not None
        assert result["price"] == 1234.56
        assert result["carrier"] == "QF"

    def test_get_missing_key(self, tmp_path):
        """Returns None for keys that were never set."""
        cache = ScrapeCache(cache_dir=tmp_path)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, tmp_path):
        """Expired entries return None."""
        cache = ScrapeCache(cache_dir=tmp_path)
        # Set with a very short TTL (fraction of a second in hours)
        cache.set("expiring", {"data": "old"}, ttl_hours=0.0001)  # ~0.36 seconds

        # Immediately should still be valid
        assert cache.get("expiring") is not None

        # Wait for expiry
        time.sleep(0.5)
        assert cache.get("expiring") is None

    def test_clear(self, tmp_path):
        """Clear removes all cached files."""
        cache = ScrapeCache(cache_dir=tmp_path)
        cache.set("key1", {"a": 1})
        cache.set("key2", {"b": 2})
        cache.set("key3", {"c": 3})

        assert cache.get("key1") is not None
        assert cache.get("key2") is not None

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_overwrite(self, tmp_path):
        """Setting the same key overwrites the previous value."""
        cache = ScrapeCache(cache_dir=tmp_path)
        cache.set("key", {"version": 1})
        cache.set("key", {"version": 2})

        result = cache.get("key")
        assert result is not None
        assert result["version"] == 2

    def test_key_sanitization(self, tmp_path):
        """Keys with special characters are handled safely."""
        cache = ScrapeCache(cache_dir=tmp_path)
        # Key with spaces, slashes, colons, etc.
        weird_key = "LAX/NRT:2025-06-15 business class (JL)"
        cache.set(weird_key, {"price": 999})

        result = cache.get(weird_key)
        assert result is not None
        assert result["price"] == 999

    def test_different_keys_dont_collide(self, tmp_path):
        """Different keys produce different cache entries."""
        cache = ScrapeCache(cache_dir=tmp_path)
        cache.set("key_a", {"origin": "LHR"})
        cache.set("key_b", {"origin": "NRT"})

        assert cache.get("key_a")["origin"] == "LHR"
        assert cache.get("key_b")["origin"] == "NRT"

    def test_custom_default_ttl(self, tmp_path):
        """Custom default TTL is used when ttl_hours not specified."""
        cache = ScrapeCache(cache_dir=tmp_path, default_ttl_hours=48)
        cache.set("long_ttl", {"data": "persistent"})

        # Should still be valid (48 hours haven't passed)
        assert cache.get("long_ttl") is not None

    def test_stores_various_types(self, tmp_path):
        """Cache handles various JSON-serializable data types."""
        cache = ScrapeCache(cache_dir=tmp_path)

        cache.set("string", "hello")
        assert cache.get("string") == "hello"

        cache.set("number", 42)
        assert cache.get("number") == 42

        cache.set("list", [1, 2, 3])
        assert cache.get("list") == [1, 2, 3]

        cache.set("null", None)
        assert (
            cache.get("null") is None
        )  # None data stored, get returns the data field which is None

    def test_cache_dir_created_automatically(self, tmp_path):
        """Cache directory is created if it doesn't exist."""
        new_dir = tmp_path / "sub" / "dir" / "cache"
        cache = ScrapeCache(cache_dir=new_dir)
        cache.set("test", {"ok": True})
        assert cache.get("test") == {"ok": True}

    def test_corrupted_file_returns_none(self, tmp_path):
        """Corrupted cache files return None instead of crashing."""
        cache = ScrapeCache(cache_dir=tmp_path)
        cache.set("corrupt", {"valid": True})

        # Corrupt the file
        path = cache._path_for("corrupt")
        path.write_text("not valid json{{{", encoding="utf-8")

        assert cache.get("corrupt") is None
