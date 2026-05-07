import logging
from pathlib import Path
import threading

from PySide6.QtCore import QThread, Signal

from browser import get_browser_context
from cookies import load_cookies, save_cookies
from instagram import (
    get_users,
    is_logged_in,
    login_with_credentials,
    resend_security_code,
    restore_instagram_session,
    unfollow_selected_users,
)

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
    unfollow_finished = Signal(list, list)
    finished_ok = Signal()
    failed = Signal()
    stopped_by_user = Signal()

    def __init__(self, parent=None, credentials=None, mode="no_followers", target_username="", export_path="non_followers.txt"):
        super().__init__(parent)
        self.mode = mode
        self.target_username = target_username.strip().lstrip("@")
        self.export_path = Path(export_path or "non_followers.txt")
        self.stop_event = threading.Event()
        self._answer_event = threading.Event()
        self._answer = None
        self._credentials_event = threading.Event()
        self._credentials = credentials
        self._security_code_event = threading.Event()
        self._resend_security_code_event = threading.Event()
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
        self._resend_security_code_event.set()
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

    def request_security_code_resend(self):
        self._resend_security_code_event.set()

    def _run_flow(self):
        self.status_changed.emit("Running")
        self.progress_changed.emit(5)

        selected_unfollow_users = None
        if self.mode == "unfollow":
            selected_unfollow_users = self._prepare_unfollow_selection()
            if not selected_unfollow_users:
                self.progress_changed.emit(100)
                self.output.emit("info", "No users selected for unfollow.")
                return

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

        if self.mode == "unfollow":
            self._run_unfollow_flow(selected_unfollow_users)
            return

        self._run_no_followers_flow()

    def _run_no_followers_flow(self):
        self.progress_changed.emit(35)
        self.output.emit("info", "Collecting followers.")
        followers = get_users(self.page, "followers", self.target_username)
        self.output.emit("success", f"Followers found: {len(followers)}")
        self.counts_changed.emit(len(followers), -1, -1)
        self._check_stop()

        self.progress_changed.emit(60)
        self.output.emit("info", "Collecting following accounts.")
        following = get_users(self.page, "following", self.target_username)
        self.output.emit("success", f"Following accounts found: {len(following)}")
        self.counts_changed.emit(-1, len(following), -1)
        self._check_stop()

        diff = following - followers
        self.counts_changed.emit(-1, -1, len(diff))
        self.progress_changed.emit(82)
        self.output.emit("info", f"Non-followers detected: {len(diff)}")

        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        with self.export_path.open("w", encoding="utf-8") as file:
            for username in sorted(diff):
                file.write(username + "\n")
        self.output.emit("success", f"{self.export_path.name} generated.")

        self._check_stop()
        self.progress_changed.emit(100)
        self.output.emit("success", "NoFollowers finished.")

    def _prepare_unfollow_selection(self):
        users = self._load_non_followers_file()
        self.counts_changed.emit(-1, -1, len(users))
        self.progress_changed.emit(8)
        self.output.emit("info", f"{self.export_path.name} loaded: {len(users)} users.")

        if not users:
            self.output.emit("warning", "No users available for unfollow.")
            return []

        selected_users = self._ask_unfollow_selection(users)
        if not selected_users:
            logger.info("No users selected for unfollow")
        return selected_users

    def _run_unfollow_flow(self, selected_users):
        self.progress_changed.emit(35)

        if selected_users:
            self._check_stop()
            self.output.emit("info", f"Starting automatic unfollow for {len(selected_users)} selected users.")
            result = unfollow_selected_users(
                self.page,
                selected_users,
                self.target_username,
                stop_checker=self._check_stop,
                progress=self._unfollow_progress,
                success_callback=lambda username: self._remove_from_non_followers_file(username),
            )
            self.unfollow_finished.emit(result.get("success", []), result.get("errors", []))
            self._check_stop()
        else:
            logger.info("No users selected for unfollow")
            self.output.emit("info", "No users selected for unfollow.")

        self._check_stop()
        self.progress_changed.emit(100)
        self.output.emit("success", "Unfollow finished.")

    def _load_non_followers_file(self):
        path = self.export_path
        if not path.exists():
            self.output.emit("warning", f"{path.name} was not found. Run NoFollowers first.")
            return []
        with path.open("r", encoding="utf-8") as file:
            return sorted({line.strip().lstrip("@") for line in file if line.strip()})

    def _perform_login(self):
        while True:
            credentials = self._wait_for_credentials()
            self._check_stop()
            if login_with_credentials(self.page, credentials, self._wait_for_security_code, self._check_stop):
                return
            self.output.emit("error", "Login failed or security code rejected. Restarting login flow.")
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
        self._resend_security_code_event.clear()
        self.security_code_required.emit()
        while not self._security_code_event.wait(0.1):
            self._check_stop()
            if self._resend_security_code_event.is_set():
                self._resend_security_code_event.clear()
                self._resend_security_code()
        if not self._security_code:
            raise StopRequested()
        return self._security_code

    def _resend_security_code(self):
        if self.page is None:
            self.output.emit("warning", "Browser is not ready to request a new security code.")
            return

        self.output.emit("info", "Requesting a new security code in Instagram.")
        try:
            if resend_security_code(self.page, self._check_stop):
                self.output.emit("success", "New security code requested.")
            else:
                self.output.emit("warning", "Could not find the button to request a new security code.")
        except StopRequested:
            raise
        except Exception as exc:
            logger.debug("Could not request a new security code", exc_info=True, extra={"user_visible": False})
            self.output.emit("warning", f"Could not request a new security code: {exc}")

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

    def _remove_from_non_followers_file(self, username):
        try:
            path = self.export_path
            with path.open("r", encoding="utf-8") as file:
                users = [line.strip() for line in file if line.strip()]
            normalized = username.strip().lower()
            remaining = [user for user in users if user.strip().lower() != normalized]
            with path.open("w", encoding="utf-8") as file:
                for user in remaining:
                    file.write(user + "\n")
            self.counts_changed.emit(-1, -1, len(remaining))
            self.output.emit("success", f"Removed @{username} from {path.name}.")
        except Exception as exc:
            self.output.emit("warning", f"Could not update {self.export_path.name} for @{username}: {exc}")

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
