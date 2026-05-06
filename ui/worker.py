import logging
import threading

from PySide6.QtCore import QThread, Signal

from browser import get_browser_context
from cookies import load_cookies, save_cookies
from instagram import get_users, is_logged_in, login_with_credentials, restore_instagram_session, unfollow_selected_users

logger = logging.getLogger("InstaFollow")


class AutomationWorker(QThread):
    output = Signal(str, str)
    status_changed = Signal(str)
    browser_ready = Signal()
    progress_changed = Signal(int)
    counts_changed = Signal(int, int, int)
    credentials_required = Signal()
    security_code_required = Signal()
    login_failed = Signal()
    unfollow_selection_prompt = Signal(list)
    finished_ok = Signal()
    failed = Signal()
    stopped_by_user = Signal()

    def __init__(self, parent=None, credentials=None):
        super().__init__(parent)
        self.stop_event = threading.Event()
        self._answer_event = threading.Event()
        self._answer = None
        self._credentials_event = threading.Event()
        self._credentials = credentials
        self._security_code_event = threading.Event()
        self._security_code = None
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self._stopped_signal_sent = False

    def run(self):
        failed = False
        try:
            self._run_flow()
            self.finished_ok.emit()
        except StopRequested:
            logger.info("Automation stopped by user", extra={"user_visible": False})
            self._emit_stopped_by_user()
        except Exception:
            if self.stop_event.is_set():
                logger.info(
                    "Automation stopped while the browser was closing",
                    exc_info=True,
                    extra={"user_visible": False},
                )
                self._emit_stopped_by_user()
            else:
                failed = True
                logger.exception("Automation failed", extra={"user_visible": False})
                self.failed.emit()
        finally:
            self._close_browser()
            if not failed:
                self.status_changed.emit("Stopped")

    def stop(self):
        self.stop_event.set()
        self._answer = None
        self._answer_event.set()
        self._credentials_event.set()
        self._security_code_event.set()
        self._close_browser()

    def answer(self, value):
        self._answer = value
        self._answer_event.set()

    def set_credentials(self, credentials):
        self._credentials = credentials
        self._credentials_event.set()

    def set_security_code(self, code):
        self._security_code = code
        self._security_code_event.set()

    def _run_flow(self):
        self.status_changed.emit("Running")
        self.progress_changed.emit(5)
        self.output.emit("info", "Opening Chrome with Playwright.")

        self.pw, self.browser, self.context, self.page = get_browser_context()
        self._check_stop()
        self.browser_ready.emit()

        self.progress_changed.emit(12)
        if load_cookies(self.context):
            self.output.emit("success", "Saved session restored.")
            restore_instagram_session(self.page)
            self._check_stop()
            if not is_logged_in(self.page):
                self.output.emit("warning", "Saved session is not valid anymore. Login required.")
                self._perform_login()
                self._check_stop()
                save_cookies(self.context)
                self.output.emit("success", "Session saved.")
        else:
            self.output.emit("warning", "Login required. Using credentials from the session form.")
            self._perform_login()
            self._check_stop()
            save_cookies(self.context)
            self.output.emit("success", "Session saved.")

        self.progress_changed.emit(20)

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
            selected_users = self._ask_unfollow_selection(sorted(diff))
            if selected_users:
                self._check_stop()
                self.output.emit("info", f"Starting automatic unfollow for {len(selected_users)} selected users.")
                unfollow_selected_users(
                    self.page,
                    selected_users,
                    stop_checker=self._check_stop,
                    progress=self._unfollow_progress,
                )
                self._check_stop()
            else:
                logger.info("No users selected for unfollow")

        self._check_stop()
        self.progress_changed.emit(100)
        self.output.emit("success", "Automation finished.")

    def _perform_login(self):
        while True:
            credentials = self._wait_for_credentials()
            self._check_stop()
            if login_with_credentials(self.page, credentials, self._wait_for_security_code, self._check_stop):
                return
            self._credentials = None
            self._credentials_event.clear()
            self.login_failed.emit()

    def _wait_for_credentials(self):
        if self._credentials:
            return self._credentials

        self.credentials_required.emit()
        self._credentials_event.clear()
        while not self._credentials_event.wait(0.1):
            self._check_stop()
        if not self._credentials:
            raise StopRequested()
        return self._credentials

    def _wait_for_security_code(self):
        self._security_code = None
        self._security_code_event.clear()
        self.security_code_required.emit()
        while not self._security_code_event.wait(0.1):
            self._check_stop()
        if not self._security_code:
            raise StopRequested()
        return self._security_code

    def _ask_unfollow_selection(self, users):
        self._answer = []
        self._answer_event.clear()
        self.unfollow_selection_prompt.emit(users)
        while not self._answer_event.wait(0.1):
            self._check_stop()
        if self._answer is None:
            raise StopRequested()
        return list(self._answer)

    def _unfollow_progress(self, index, total, username):
        if total:
            self.progress_changed.emit(82 + int((index / total) * 18))
        self.output.emit("info", f"Reviewing {username} ({index}/{total}).")

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
        except Exception:
            logger.debug("Could not close Playwright cleanly", exc_info=True, extra={"user_visible": False})

    def _emit_stopped_by_user(self):
        if self._stopped_signal_sent:
            return
        self._stopped_signal_sent = True
        self.stopped_by_user.emit()


class StopRequested(Exception):
    pass
