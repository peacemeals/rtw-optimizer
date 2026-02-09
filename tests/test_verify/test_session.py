"""Tests for ExpertFlyer session management."""

import json
import os
import time

import pytest

from rtw.verify.session import SessionManager


class TestSessionManager:
    def test_no_session(self, tmp_path):
        sm = SessionManager(session_path=tmp_path / "session.json")
        assert sm.has_session() is False
        assert sm.session_age_hours() is None
        assert sm.get_storage_state_path() is None

    def test_valid_session(self, tmp_path):
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"cookies": []}))
        sm = SessionManager(session_path=path, max_age_hours=24)
        assert sm.has_session() is True
        age = sm.session_age_hours()
        assert age is not None
        assert age < 1  # Just created
        assert sm.get_storage_state_path() == path

    def test_expired_session(self, tmp_path):
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"cookies": []}))
        # Set mtime to 25 hours ago
        old_time = time.time() - 25 * 3600
        os.utime(path, (old_time, old_time))
        sm = SessionManager(session_path=path, max_age_hours=24)
        assert sm.has_session() is False
        age = sm.session_age_hours()
        assert age is not None
        assert age > 24
        assert sm.get_storage_state_path() is None

    def test_clear_session(self, tmp_path):
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"cookies": []}))
        sm = SessionManager(session_path=path)
        assert path.exists()
        sm.clear_session()
        assert not path.exists()

    def test_clear_nonexistent(self, tmp_path):
        sm = SessionManager(session_path=tmp_path / "nope.json")
        sm.clear_session()  # Should not raise

    def test_custom_max_age(self, tmp_path):
        path = tmp_path / "session.json"
        path.write_text(json.dumps({"cookies": []}))
        # Set mtime to 2 hours ago
        old_time = time.time() - 2 * 3600
        os.utime(path, (old_time, old_time))
        # With 1-hour max age, should be expired
        sm = SessionManager(session_path=path, max_age_hours=1)
        assert sm.has_session() is False
        # With 4-hour max age, should be valid
        sm2 = SessionManager(session_path=path, max_age_hours=4)
        assert sm2.has_session() is True
