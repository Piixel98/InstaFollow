import logging
import threading

from PySide6.QtCore import QThread, Signal

from browser import get_browser_context
from config import INSTAGRAM
from cookies import delete_saved_cookies, load_cookies, save_cookies
from instagram import get_users
from unfollow import unfollow_users_with_confirmation
from utils import handle_cookie_consent

logger = logging.getLogger("InstaFollow")


class AutomationWorker(QThread):
    output = Signal(str, str)
    status_changed = Signal(str)
    browser_ready = Signal()
    progress_changed = Signal(int)
    counts_changed = Signal(int, int, int)
    login_required = Signal()
    unfollow_prompt = Signal(str, int, int)
    cookie_cleanup_prompt = Signal()
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop_event = threading.Event()
        self._answer_event = threading.Event()
        self._answer = None
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None

    def run(self):
        try:
            self._run_flow()
            self.finished_ok.emit()
        except StopRequested:
            self.output.emit("warning", "Automation stopped by user.")
        except Exception as exc:
            logger.exception("Automation failed")
            self.failed.emit(str(exc))
        finally:
            self._ask_cookie_cleanup()
            self._close_browser()
            self.status_changed.emit("Stopped")

    def stop(self):
        self.stop_event.set()
        self._answer = False
        self._answer_event.set()
        self._close_browser()

    def answer(self, value):
        self._answer = value
        self._answer_event.set()

    def _run_flow(self):
        self.status_changed.emit("Running")
        self.progress_changed.emit(5)
        self.output.emit("info", "Opening Chrome with Playwright.")

        self.pw, self.browser, self.context, self.page = get_browser_context()
        self._check_stop()
        self.browser_ready.emit()

        self.progress_changed.emit(12)
        self.output.emit("info", "Loading Instagram.")
        self.page.goto(INSTAGRAM)
        handle_cookie_consent(self.page)
        self._check_stop()

        self.progress_changed.emit(20)
        cookies_loaded = load_cookies(self.context)
        if cookies_loaded:
            self.output.emit("success", "Saved session restored.")
            self.page.goto(INSTAGRAM)
            handle_cookie_consent(self.page)
        else:
            self.output.emit("warning", "Login required. Complete it in Chrome.")
            self.login_required.emit()
            if not self._wait_for_answer():
                raise StopRequested()
            self._check_stop()
            save_cookies(self.context)
            self.output.emit("success", "Session saved.")

        self.progress_changed.emit(35)
        self.output.emit("info", "Collecting followers.")
        followers = get_users(self.page, "followers")
        self.output.emit("success", f"Followers found: {len(followers)}")
        self.counts_changed.emit(len(followers), 0, 0)
        self._check_stop()

        self.progress_changed.emit(60)
        self.output.emit("info", "Collecting following accounts.")
        following = get_users(self.page, "following")
        self.output.emit("success", f"Following accounts found: {len(following)}")
        self._check_stop()

        diff = following - followers
        self.counts_changed.emit(len(followers), len(following), len(diff))
        self.progress_changed.emit(82)
        self.output.emit("info", f"Non-followers detected: {len(diff)}")

        with open("non_followers.txt", "w", encoding="utf-8") as file:
            for username in sorted(diff):
                file.write(username + "\n")
        self.output.emit("success", "non_followers.txt generated.")

        if diff:
            self.output.emit("info", "Starting optional unfollow review.")
            unfollow_users_with_confirmation(
                self.page,
                sorted(diff),
                should_unfollow=self._ask_unfollow,
                stop_event=self.stop_event,
                progress=self._unfollow_progress,
            )

        self.progress_changed.emit(100)
        self.output.emit("success", "Automation finished.")

    def _ask_unfollow(self, username, index, total):
        self.unfollow_prompt.emit(username, index, total)
        return self._wait_for_answer()

    def _ask_cookie_cleanup(self):
        if self.context is None or self.stop_event.is_set():
            return

        self.cookie_cleanup_prompt.emit()
        if self._wait_for_answer(default=False):
            deleted = delete_saved_cookies(self.context)
            if deleted:
                self.output.emit("success", "Saved cookies deleted.")
            else:
                self.output.emit("info", "No saved cookie file found.")
        else:
            self.output.emit("warning", "Saved cookies kept on this computer.")

    def _unfollow_progress(self, index, total, username):
        if total:
            self.progress_changed.emit(82 + int((index / total) * 18))
        self.output.emit("info", f"Reviewing {username} ({index}/{total}).")

    def _wait_for_answer(self, default=False):
        self._answer = default
        self._answer_event.clear()
        while not self._answer_event.wait(0.1):
            if self.stop_event.is_set():
                return False
        return bool(self._answer)

    def _check_stop(self):
        if self.stop_event.is_set():
            raise StopRequested()

    def _close_browser(self):
        try:
            if self.browser is not None:
                self.browser.close()
                self.browser = None
            if self.pw is not None:
                self.pw.stop()
                self.pw = None
        except Exception as exc:
            logger.debug("Could not close Playwright cleanly: %s", exc)


class StopRequested(Exception):
    pass
