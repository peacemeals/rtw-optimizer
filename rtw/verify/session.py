"""ExpertFlyer session management via Playwright storage_state."""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_PATH = Path.home() / ".rtw" / "expertflyer_session.json"
_SESSION_MAX_AGE_HOURS = 24
_LOGIN_POLL_INTERVAL = 2  # seconds
_EXPERTFLYER_BASE = "https://www.expertflyer.com"


class SessionManager:
    """Manages ExpertFlyer browser session persistence.

    Uses Playwright's storage_state to save/restore cookies and
    localStorage after a manual login in a headed browser.
    """

    def __init__(
        self,
        session_path: Optional[Path] = None,
        max_age_hours: float = _SESSION_MAX_AGE_HOURS,
    ) -> None:
        self.session_path = session_path or _DEFAULT_SESSION_PATH
        self.max_age_hours = max_age_hours

    def has_session(self) -> bool:
        """Check if a valid (non-expired) session file exists."""
        if not self.session_path.exists():
            return False
        age = self.session_age_hours()
        if age is None:
            return False
        return age < self.max_age_hours

    def session_age_hours(self) -> Optional[float]:
        """Return session file age in hours, or None if no file."""
        if not self.session_path.exists():
            return None
        mtime = self.session_path.stat().st_mtime
        age_seconds = time.time() - mtime
        return age_seconds / 3600

    def get_storage_state_path(self) -> Optional[Path]:
        """Return session path if valid, None if expired or missing."""
        if self.has_session():
            return self.session_path
        return None

    def clear_session(self) -> None:
        """Delete the session file."""
        if self.session_path.exists():
            self.session_path.unlink()
            logger.info("Session cleared: %s", self.session_path)

    def login_interactive(self, timeout_seconds: int = 120) -> bool:
        """Launch a headed browser for manual ExpertFlyer login.

        Opens a Chromium window, navigates to ExpertFlyer, and waits
        for the user to log in. Once login is detected (URL change from
        auth.expertflyer.com back to www.expertflyer.com), the session
        cookies are saved.

        Returns True if login succeeded, False on timeout.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return False

        # Ensure parent directory exists
        self.session_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1200, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            logger.info("Navigating to ExpertFlyer...")
            page.goto(_EXPERTFLYER_BASE, timeout=30000)
            time.sleep(2)

            # Wait for user to complete login
            deadline = time.time() + timeout_seconds
            logged_in = False

            try:
                while time.time() < deadline:
                    time.sleep(_LOGIN_POLL_INTERVAL)
                    try:
                        url = page.url
                        # Login detected: URL is on www.expertflyer.com (not auth.)
                        # and page has session cookies
                        if (
                            "www.expertflyer.com" in url
                            and "auth.expertflyer.com" not in url
                            and "/login" not in url
                        ):
                            # Check for authenticated cookies
                            # ExpertFlyer uses __txn_* tokens on www
                            # and auth0 cookies on auth subdomain
                            cookies = context.cookies()
                            auth_cookies = [
                                c
                                for c in cookies
                                if (
                                    c["name"].startswith("__txn_")
                                    or c["name"] == "auth0"
                                )
                                and "expertflyer.com" in c.get("domain", "")
                            ]
                            if auth_cookies:
                                logged_in = True
                                break
                    except Exception:
                        # Page might be navigating
                        continue
            except KeyboardInterrupt:
                logger.info("Login cancelled by user")

            if logged_in:
                # Save session
                context.storage_state(path=str(self.session_path))
                # Set restrictive permissions
                try:
                    os.chmod(self.session_path, 0o600)
                except OSError:
                    pass
                logger.info("Session saved: %s", self.session_path)

            try:
                browser.close()
            except Exception:
                pass

            return logged_in
