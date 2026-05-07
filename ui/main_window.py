import html
import logging
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QSize, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cookies import delete_saved_cookies, has_valid_cookies
from ui.browser_embed import BrowserContainer
from ui.logging_handler import QtLogHandler
from ui.styles import APP_STYLE
from ui.translations import TRANSLATIONS
from ui.worker import AutomationWorker
from utils import latest_log_file, setup_logging


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.full_log_lines = []
        self.settings = QSettings("InstaFollow", "InstaFollow")
        self.language = self.settings.value("language", "es")
        self.current_status = "idle"
        self.saved_credentials = None
        self.awaiting_security_code = False
        self.security_code_dialog = None
        self.cookies_available = has_valid_cookies()
        self.credentials_locked = False
        self.selected_process_mode = "no_followers"
        self.target_username = self.settings.value("target_username", "")
        self.export_file_path = self.settings.value("export_file_path", "non_followers.txt")
        self.logs_dir = self.settings.value("logs_dir", "logs")
        self.followers_count = 0
        self.following_count = 0
        self.non_followers_count = self._read_non_followers_count()
        self.cookie_watch_timer = QTimer(self)
        self.cookie_watch_timer.setInterval(1000)
        self.cookie_watch_timer.timeout.connect(self._sync_cookie_credentials_state)

        setup_logging(self.logs_dir)
        self._install_log_handler()
        self._build_ui()
        self._refresh_count_labels()
        self.apply_language()
        self._apply_responsive_layout()
        self._restore_window()

    def _build_ui(self):
        self.setWindowTitle("InstaFollow")
        self.setWindowIcon(QIcon(resource_path("assets/instafollow.ico")))
        self.setMinimumSize(540, 640)
        self.setStyleSheet(APP_STYLE)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)

        shell = QFrame()
        shell.setObjectName("shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 18, 20, 18)
        shell_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        title_group = QVBoxLayout()
        title_group.setContentsMargins(0, 0, 0, 0)
        title_group.setSpacing(1)
        title = QLabel("InstaFollow")
        title.setObjectName("title")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("statLabel")
        title_group.addWidget(title)
        title_group.addWidget(self.subtitle_label)
        header.addLayout(title_group)
        header.addStretch()

        self.process_switch = QFrame()
        self.process_switch.setObjectName("processSwitch")
        process_layout = QHBoxLayout(self.process_switch)
        process_layout.setContentsMargins(3, 3, 3, 3)
        process_layout.setSpacing(3)

        self.no_followers_button = QPushButton("")
        self.no_followers_button.setObjectName("processButton")
        self.no_followers_button.setCheckable(True)
        self.no_followers_button.setMinimumWidth(132)
        self.no_followers_button.clicked.connect(lambda: self.select_process_mode("no_followers"))
        process_layout.addWidget(self.no_followers_button)

        self.unfollow_process_button = QPushButton("")
        self.unfollow_process_button.setObjectName("processButton")
        self.unfollow_process_button.setCheckable(True)
        self.unfollow_process_button.setMinimumWidth(132)
        self.unfollow_process_button.clicked.connect(lambda: self.select_process_mode("unfollow"))
        process_layout.addWidget(self.unfollow_process_button)
        header.addWidget(self.process_switch)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusPill")
        header.addWidget(self.status_label)

        self.menu_button = QPushButton("")
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setIcon(self._menu_icon())
        self.menu_button.setIconSize(QSize(18, 18))
        self.menu_button.setToolTip(self.t("more_options"))
        self.menu_button.clicked.connect(self._open_menu)
        header.addWidget(self.menu_button)
        shell_layout.addLayout(header)

        self.browser_panel = self._build_browser_panel()
        shell_layout.addWidget(self.browser_panel, stretch=7)

        self.stats_panel = self._build_stats_panel()
        shell_layout.addWidget(self.stats_panel)

        self.output_panel = self._build_output_panel()
        shell_layout.addWidget(self.output_panel, stretch=3)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.toast = QLabel("")
        self.toast.setObjectName("toast")
        footer.addWidget(self.toast)
        footer.addStretch()

        self.stop_button = QPushButton("")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_automation)
        footer.addWidget(self.stop_button)

        self.start_button = QPushButton("")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_automation)
        footer.addWidget(self.start_button)

        shell_layout.addLayout(footer)
        root_layout.addWidget(shell)
        self.setCentralWidget(root)

    def _build_browser_panel(self):
        panel = QFrame()
        panel.setObjectName("browserPanel")
        panel.setFrameShape(QFrame.NoFrame)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(16, 14, 16, 10)
        header.setSpacing(10)
        self.browser_title = QLabel("")
        label = self.browser_title
        label.setObjectName("sectionTitle")
        header.addWidget(label)
        header.addStretch()
        self.browser_toggle_button = QPushButton("")
        self.browser_toggle_button.setObjectName("toggleButton")
        self.browser_toggle_button.setCheckable(True)
        self.browser_toggle_button.clicked.connect(self.toggle_browser_visibility)
        header.addWidget(self.browser_toggle_button)
        layout.addLayout(header)

        self.session_form = self._build_session_form()
        self.session_scroll = QScrollArea()
        self.session_scroll.setObjectName("sessionScroll")
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setFrameShape(QFrame.NoFrame)
        self.session_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.session_scroll.setWidget(self.session_form)
        layout.addWidget(self.session_scroll, stretch=1)

        self.browser_container = BrowserContainer()
        self.browser_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.browser_container.setVisible(False)
        self.browser_container.setStyleSheet(
            "QFrame#browserViewport { margin: 0px; padding: 0px; border: none; border-radius: 0px; }"
        )
        layout.addWidget(self.browser_container, stretch=1)
        return panel

    def _build_session_form(self):
        form = QFrame()
        form.setObjectName("sessionForm")
        layout = QVBoxLayout(form)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.session_heading = QLabel("")
        self.session_heading.setObjectName("sectionTitle")
        self.session_heading.setVisible(False)
        self.session_badge = QLabel("")
        self.session_badge.setObjectName("sessionBadge")
        self.session_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        header.addWidget(self.session_heading)
        header.addStretch()
        header.addWidget(self.session_badge)
        layout.addLayout(header)

        self.credential_card = QFrame()
        self.credential_card.setObjectName("credentialCard")
        self.credentials_layout = QGridLayout(self.credential_card)
        self.credentials_layout.setContentsMargins(16, 14, 16, 16)
        self.credentials_layout.setHorizontalSpacing(12)
        self.credentials_layout.setVerticalSpacing(9)

        self.username_label = QLabel("")
        self.password_label = QLabel("")
        self.target_username_label = QLabel("")
        for label in (self.target_username_label, self.username_label, self.password_label):
            label.setObjectName("statLabel")
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.target_username_input = QLineEdit()
        self.target_username_input.setText(self.target_username)
        self.target_username_input.setMinimumWidth(0)
        self.target_username_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.target_username_input.editingFinished.connect(self.save_target_username)
        self.target_username_input.textChanged.connect(lambda: self._refresh_start_button_state())

        self.username_input = QLineEdit()
        self.username_input.setMinimumWidth(0)
        self.username_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.password_input = QLineEdit()
        self.password_input.setMinimumWidth(0)
        self.password_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_visibility_button = QPushButton("")
        self.password_visibility_button.setObjectName("iconButton")
        self.password_visibility_button.setCheckable(True)
        self.password_visibility_button.setIcon(self._eye_icon(False))
        self.password_visibility_button.setIconSize(QSize(18, 18))
        self.password_visibility_button.setFixedWidth(42)
        self.password_visibility_button.clicked.connect(self.toggle_password_visibility)

        self.session_status = QLabel("")
        self.session_status.setObjectName("sessionStatus")
        self.session_status.setWordWrap(True)

        self.save_credentials_button = QPushButton("")
        self.save_credentials_button.setObjectName("startButton")
        self.save_credentials_button.clicked.connect(self.save_session_form)

        self.edit_credentials_button = QPushButton("")
        self.edit_credentials_button.setObjectName("ghostButton")
        self.edit_credentials_button.clicked.connect(self.edit_credentials)

        self.change_account_button = QPushButton("")
        self.change_account_button.setObjectName("secondaryButton")
        self.change_account_button.clicked.connect(self.change_account)

        self.password_layout = QHBoxLayout()
        self.password_layout.setContentsMargins(0, 0, 0, 0)
        self.password_layout.setSpacing(6)
        self.password_layout.addWidget(self.password_input)
        self.password_layout.addWidget(self.password_visibility_button)
        self.credentials_layout.setColumnStretch(0, 1)
        self.credentials_layout.setColumnStretch(1, 1)
        self._credentials_layout_mode = None
        self._apply_responsive_layout()
        layout.addWidget(self.credential_card)

        for button in (self.save_credentials_button, self.edit_credentials_button, self.change_account_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.session_actions_layout = QGridLayout()
        self.session_actions_layout.setHorizontalSpacing(8)
        self.session_actions_layout.setVerticalSpacing(8)
        layout.addLayout(self.session_actions_layout)
        self._apply_session_actions_layout(self._credentials_layout_mode)
        layout.addWidget(self.session_status)
        self.apply_cookie_lock()
        return form

    def _build_stats_panel(self):
        panel = QFrame()
        panel.setObjectName("statsPanel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        self.followers_value = self._stat_block(layout, 0, "0", "")
        self.following_value = self._stat_block(layout, 1, "0", "")
        self.non_followers_value = self._stat_block(layout, 2, "0", "")

        self.export_button = QPushButton("")
        self.export_button.setObjectName("secondaryButton")
        self.export_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.export_button.clicked.connect(self.open_non_followers_file)
        layout.addWidget(self.export_button, 0, 3, 2, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)
        self.progress.setProperty("running", False)
        layout.addWidget(self.progress, 0, 4, 2, 1)
        layout.setColumnStretch(4, 1)
        return panel

    def _stat_block(self, layout, column, value, label):
        block = QFrame()
        block.setObjectName("statBlock")
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(14, 10, 14, 10)
        block_layout.setSpacing(1)

        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        text_label = QLabel(label)
        text_label.setObjectName("statLabel")
        if not hasattr(self, "stat_labels"):
            self.stat_labels = []
        self.stat_labels.append(text_label)
        block_layout.addWidget(value_label)
        block_layout.addWidget(text_label)
        layout.addWidget(block, 0, column, 2, 1)
        return value_label

    def _build_output_panel(self):
        panel = QFrame()
        panel.setObjectName("outputPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        self.output_title = QLabel("")
        label = self.output_title
        label.setObjectName("sectionTitle")
        layout.addWidget(label)

        self.output = QTextEdit()
        self.output.setObjectName("output")
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        return panel

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        if not hasattr(self, "credentials_layout"):
            return

        host_width = self.session_scroll.viewport().width() if hasattr(self, "session_scroll") else self.credential_card.width()
        mode = "wide"
        if host_width < 620:
            mode = "narrow"
        elif host_width < 860:
            mode = "compact"
        if getattr(self, "_credentials_layout_mode", None) == mode:
            return

        self._credentials_layout_mode = mode
        for widget in (
            self.target_username_label,
            self.target_username_input,
            self.username_label,
            self.username_input,
            self.password_label,
        ):
            self.credentials_layout.removeWidget(widget)
        self.credentials_layout.removeItem(self.password_layout)

        if mode in ("compact", "narrow"):
            self.credentials_layout.addWidget(self.target_username_label, 0, 0, 1, 1)
            self.credentials_layout.addWidget(self.target_username_input, 1, 0, 1, 1)
            self.credentials_layout.addWidget(self.username_label, 2, 0, 1, 1)
            self.credentials_layout.addWidget(self.username_input, 3, 0, 1, 1)
            self.credentials_layout.addWidget(self.password_label, 4, 0, 1, 1)
            self.credentials_layout.addLayout(self.password_layout, 5, 0, 1, 1)
            self.credentials_layout.setColumnStretch(0, 1)
            self.credentials_layout.setColumnStretch(1, 0)
            self._apply_session_actions_layout(mode)
            return

        self.credentials_layout.addWidget(self.target_username_label, 0, 0, 1, 2)
        self.credentials_layout.addWidget(self.target_username_input, 1, 0, 1, 2)
        self.credentials_layout.addWidget(self.username_label, 2, 0, 1, 1)
        self.credentials_layout.addWidget(self.username_input, 3, 0, 1, 1)
        self.credentials_layout.addWidget(self.password_label, 2, 1, 1, 1)
        self.credentials_layout.addLayout(self.password_layout, 3, 1, 1, 1)
        self.credentials_layout.setColumnStretch(0, 1)
        self.credentials_layout.setColumnStretch(1, 1)
        self._apply_session_actions_layout(mode)

    def _apply_session_actions_layout(self, mode):
        if not hasattr(self, "session_actions_layout"):
            return

        for widget in (self.save_credentials_button, self.edit_credentials_button, self.change_account_button):
            self.session_actions_layout.removeWidget(widget)

        if mode == "narrow":
            self.session_actions_layout.addWidget(self.save_credentials_button, 0, 0)
            self.session_actions_layout.addWidget(self.edit_credentials_button, 1, 0)
            self.session_actions_layout.addWidget(self.change_account_button, 2, 0)
            self.session_actions_layout.setColumnStretch(0, 1)
            self.session_actions_layout.setColumnStretch(1, 0)
            return

        if mode == "compact":
            self.session_actions_layout.addWidget(self.save_credentials_button, 0, 0, 1, 2)
            self.session_actions_layout.addWidget(self.edit_credentials_button, 1, 0)
            self.session_actions_layout.addWidget(self.change_account_button, 1, 1)
            self.session_actions_layout.setColumnStretch(0, 1)
            self.session_actions_layout.setColumnStretch(1, 1)
            return

        self.session_actions_layout.addWidget(self.save_credentials_button, 0, 0)
        self.session_actions_layout.addWidget(self.edit_credentials_button, 0, 1)
        self.session_actions_layout.addWidget(self.change_account_button, 0, 2)
        self.session_actions_layout.setColumnStretch(0, 0)
        self.session_actions_layout.setColumnStretch(1, 0)
        self.session_actions_layout.setColumnStretch(2, 0)

    def _install_log_handler(self):
        logger = logging.getLogger("InstaFollow")
        self.qt_log_handler = QtLogHandler()
        self.qt_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.qt_log_handler.emitter.message.connect(self.append_log)
        logger.addHandler(self.qt_log_handler)

    def start_automation(self, mode=None):
        if self.worker and self.worker.isRunning():
            return

        mode = mode or self.selected_process_mode
        target_username = self.save_target_username()
        if not target_username:
            self.session_status.setText(self.t("instagram_username_required"))
            self.show_toast(self.t("instagram_username_required"))
            return

        export_path = self._export_path()
        if mode == "unfollow" and not export_path.exists():
            QMessageBox.information(
                self,
                self.t("non_followers_missing_title"),
                self.t("non_followers_missing_text"),
            )
            return

        self.cookies_available = has_valid_cookies()
        self.apply_cookie_lock()
        if mode != "unfollow" and not self._has_ready_session():
            self.session_status.setText(self.t("credentials_not_ready"))
            self.show_toast(self.t("credentials_not_ready"))
            return

        self.output.clear()
        self.full_log_lines.clear()
        self.progress.setValue(0)
        self._set_progress_running(True)
        self._refresh_count_labels()
        self.set_status("running")
        self.start_button.setEnabled(False)
        self.no_followers_button.setEnabled(False)
        self.unfollow_process_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.change_account_button.setEnabled(False)
        self.show_toast(self.t("automation_started"))

        self.worker = AutomationWorker(
            self,
            credentials=self.saved_credentials,
            mode=mode,
            target_username=target_username,
            export_path=str(export_path),
        )
        self.worker.output.connect(self.append_log)
        self.worker.status_changed.connect(self.set_status)
        self.worker.browser_ready.connect(self.embed_browser)
        self.worker.credentials_required.connect(self.handle_credentials_required)
        self.worker.security_code_required.connect(self.handle_security_code_required)
        self.worker.login_failed.connect(self.handle_login_failed)
        self.worker.progress_changed.connect(self.progress.setValue)
        self.worker.counts_changed.connect(self.update_counts)
        self.worker.unfollow_selection_prompt.connect(self.handle_unfollow_selection_prompt)
        self.worker.unfollow_finished.connect(self.handle_unfollow_finished)
        self.worker.finished_ok.connect(lambda: self.show_toast(self.t("automation_finished")))
        self.worker.failed.connect(self.handle_worker_failed)
        self.worker.stopped_by_user.connect(self.handle_worker_stopped_by_user)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.start()
        self._start_cookie_watch()

    def stop_automation(self):
        if self.worker and self.worker.isRunning():
            self.show_toast(self.t("stopping"))
            self.set_status("stopping")
            self.worker.stop()

    def handle_worker_finished(self):
        self._stop_cookie_watch()
        self.browser_container.release()
        self.start_button.setEnabled(True)
        self.no_followers_button.setEnabled(True)
        self.unfollow_process_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_progress_running(False)
        self.awaiting_security_code = False
        self._close_security_code_dialog()
        self._sync_cookie_credentials_state()
        self.apply_cookie_lock()
        self._refresh_start_button_state()

    def handle_worker_failed(self):
        self._stop_cookie_watch()
        self.set_status("error")
        self.progress.setValue(0)
        self._set_progress_running(False)
        self._close_security_code_dialog()
        self.show_toast(self.t("automation_failed"))

    def handle_worker_stopped_by_user(self):
        self._stop_cookie_watch()
        self.set_status("stopped")
        self.progress.setValue(0)
        self._set_progress_running(False)
        self._close_security_code_dialog()
        self.append_log("warning", self.t("stopped_by_user"))
        self.show_toast(self.t("stopped_by_user"))

    def embed_browser(self):
        self._show_browser_panel()
        self._refresh_browser_panel_state()
        self._embed_attempts = 0
        QTimer.singleShot(250, self._try_embed_browser)

    def _try_embed_browser(self):
        if self.browser_container.try_embed():
            self.append_log("success", "Chrome embedded in the application.")
            for delay in (100, 400, 1000):
                QTimer.singleShot(delay, self.browser_container.resize_embedded)
        else:
            self._embed_attempts += 1
            if self._embed_attempts < 20:
                QTimer.singleShot(250, self._try_embed_browser)
                return
            self.browser_container.hide_unembedded()
            self.append_log("error", "Chrome could not be embedded in the application.")

    def handle_credentials_required(self):
        self.session_status.setText(self.t("credentials_required"))
        if not self.saved_credentials:
            self.cookies_available = False
            self.credentials_locked = False
            self.username_input.clear()
            self.password_input.clear()
            self.apply_cookie_lock()
        if self.worker and self.saved_credentials:
            self.worker.set_credentials(self.saved_credentials)

    def handle_security_code_required(self):
        self.session_status.setText(self.t("security_code_required"))
        self.session_status.setStyleSheet("color: #F6C343; font-weight: 600;")
        self.append_log("warning", "2FA Security code required. Please check Instagram and enter the code.")
        self.show_toast(self.t("security_code_required"))

        if self.security_code_dialog and self.security_code_dialog.isVisible():
            self.security_code_dialog.raise_()
            self.security_code_dialog.activateWindow()
            return

        self.awaiting_security_code = True
        dialog = SecurityCodeDialog(self.t, self)
        dialog.setWindowModality(Qt.NonModal)
        dialog.resend_requested.connect(self._request_security_code_resend)
        dialog.accepted.connect(lambda: self._submit_security_code_dialog(dialog))
        dialog.rejected.connect(lambda: self._cancel_security_code_dialog(dialog))
        dialog.finished.connect(lambda: self._forget_security_code_dialog(dialog))
        self.security_code_dialog = dialog
        dialog.show()
        QTimer.singleShot(0, dialog.raise_)
        QTimer.singleShot(0, dialog.activateWindow)

    def _submit_security_code_dialog(self, dialog):
        if dialog is not self.security_code_dialog:
            return

        code = dialog.get_security_code()
        self.awaiting_security_code = False
        if code and self.worker:
            self.append_log("info", "Security code submitted, verifying...")
            self.worker.set_security_code(code)
            return

        self.append_log("warning", "No security code entered")

    def _request_security_code_resend(self):
        self.append_log("info", "Requesting a new security code.")
        if self.worker:
            self.worker.request_security_code_resend()

    def _cancel_security_code_dialog(self, dialog):
        if dialog is not self.security_code_dialog or not self.awaiting_security_code:
            return

        self.awaiting_security_code = False
        self.append_log("error", "2FA cancelled by user")
        if self.worker:
            self.worker.stop()

    def _forget_security_code_dialog(self, dialog):
        if dialog is self.security_code_dialog:
            self.security_code_dialog = None

    def _close_security_code_dialog(self):
        dialog = self.security_code_dialog
        if not dialog:
            return
        self.awaiting_security_code = False
        self.security_code_dialog = None
        dialog.close()

    def handle_login_failed(self):
        credentials = self.saved_credentials or {}
        if has_valid_cookies():
            self.saved_credentials = None
        self.awaiting_security_code = False
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)
        self.username_input.setText(credentials.get("username", ""))
        self.password_input.setText(credentials.get("password", ""))
        self.save_credentials_button.setEnabled(True)
        self.edit_credentials_button.setEnabled(False)
        self.credentials_locked = False
        self._refresh_session_visual_state()
        self._refresh_start_button_state()
        self.session_status.setText(self.t("login_failed"))
        self.show_toast(self.t("login_failed"))

    def handle_unfollow_selection_prompt(self, users):
        dialog = UnfollowSelectionDialog(self.t, users, self)
        if dialog.exec() == QDialog.Accepted:
            self.worker.answer(dialog.selected_users())
            return
        self.worker.answer([])

    def handle_unfollow_finished(self, success, errors):
        message = self.t("unfollow_summary_text").format(
            success=len(success),
            errors=len(errors),
        )
        if errors:
            failed_users = "\n".join(
                f"@{item.get('username', '')}: {item.get('error', '')}"
                for item in errors
            )
            message = f"{message}\n\n{self.t('unfollow_errors')}:\n{failed_users}"
        QMessageBox.information(self, self.t("unfollow_summary_title"), message)

    def append_log(self, level, message):
        self.full_log_lines.append(message)
        color = {
            "success": "#5FAF86",
            "info": "#E8ECEF",
            "warning": "#D8B35A",
            "error": "#D76B63",
            "debug": "#9CA3AF",
        }.get(level, "#E8ECEF")

        escaped = html.escape(message)
        self.output.append(f'<span style="color:{color};">{escaped}</span>')
        self.output.moveCursor(QTextCursor.End)

    def update_counts(self, followers, following, non_followers):
        if followers >= 0:
            self.followers_count = followers
        if following >= 0:
            self.following_count = following
        if non_followers >= 0:
            self.non_followers_count = non_followers
        self._refresh_count_labels()

    def _refresh_count_labels(self):
        self.followers_value.setText(str(self.followers_count))
        self.following_value.setText(str(self.following_count))
        self.non_followers_value.setText(str(self.non_followers_count))

    def _read_non_followers_count(self):
        path = self._export_path()
        if not path.exists():
            return 0
        try:
            with path.open("r", encoding="utf-8") as file:
                return len({line.strip().lstrip("@") for line in file if line.strip()})
        except OSError:
            return 0

    def _export_path(self):
        return Path(self.export_file_path or "non_followers.txt")

    def set_status(self, status):
        normalized = str(status).lower()
        self.current_status = normalized
        self.status_label.setText(self.t(f"status_{normalized}", status))
        color = {
            "running": "#214D3B",
            "idle": "#262C32",
            "stopped": "#633B37",
            "stopping": "#5A4B2D",
            "error": "#633B37",
        }.get(normalized, "#262C32")
        self.status_label.setStyleSheet(
            "border-radius: 10px; padding: 6px 10px; color: #DDE6E1; "
            f"font-size: 11px; font-weight: 750; background: {color};"
        )

    def show_toast(self, message):
        self.toast.setText(message)
        QTimer.singleShot(3500, lambda: self.toast.setText(""))

    def open_logs_dialog(self):
        dialog = LogsDialog(self.t, self.logs_dir, self)
        dialog.exec()

    def open_config_dialog(self):
        dialog = ConfigDialog(self.t, self.export_file_path, self.logs_dir, self.language, self)
        if dialog.exec() != QDialog.Accepted:
            return

        export_file_path, logs_dir, language = dialog.values()
        self.export_file_path = export_file_path
        self.logs_dir = logs_dir
        self.settings.setValue("export_file_path", self.export_file_path)
        self.settings.setValue("logs_dir", self.logs_dir)
        if language != self.language:
            self.set_language(language)
        setup_logging(self.logs_dir)
        self.non_followers_count = self._read_non_followers_count()
        self._refresh_count_labels()
        self._refresh_start_button_state()
        self.show_toast(self.t("config_saved"))

    def toggle_browser_visibility(self):
        visible = not self.browser_container.isVisible()
        if visible:
            self._show_browser_panel()
        else:
            self.session_scroll.setVisible(True)
            self.browser_container.setVisible(False)
        self._refresh_browser_panel_state()
        if visible:
            self._schedule_browser_resizes()

    def _show_browser_panel(self):
        self.session_scroll.setVisible(False)
        self.browser_container.setVisible(True)
        self.browser_panel.layout().invalidate()
        self.browser_panel.updateGeometry()
        self._schedule_browser_resizes()

    def _schedule_browser_resizes(self):
        for delay in (0, 100, 300, 700):
            QTimer.singleShot(delay, self.browser_container.resize_embedded)

    def toggle_password_visibility(self):
        if self.password_visibility_button.isChecked():
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.password_visibility_button.setIcon(self._eye_icon(True))
            return
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_visibility_button.setIcon(self._eye_icon(False))

    def save_target_username(self):
        username = self.target_username_input.text().strip().lstrip("@").strip("/")
        self.target_username = username
        self.target_username_input.setText(username)
        self.settings.setValue("target_username", username)
        self._refresh_start_button_state()
        return username

    def save_session_form(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self.session_status.setText(self.t("credentials_required"))
            return

        self.saved_credentials = {"username": username, "password": password}
        self.username_input.setText("********")
        self.password_input.setText("********")
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.save_credentials_button.setEnabled(False)
        self.edit_credentials_button.setEnabled(True)
        self.credentials_locked = True
        self._refresh_session_visual_state()
        self._refresh_start_button_state()
        self.session_status.setText(self.t("credentials_memory_locked"))
        self.show_toast(self.t("credentials_saved"))
        if self.worker and self.worker.isRunning():
            self.worker.set_credentials(self.saved_credentials)

    def edit_credentials(self):
        if not self.saved_credentials:
            return
        credentials = self.saved_credentials
        self.credentials_locked = False
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)
        self.username_input.setText(credentials.get("username", ""))
        self.password_input.setText(credentials.get("password", ""))
        self.save_credentials_button.setEnabled(True)
        self.edit_credentials_button.setEnabled(False)
        self.username_input.setFocus()
        self._refresh_session_visual_state()
        self._refresh_start_button_state()

    def change_account(self):
        result = QMessageBox.warning(
            self,
            self.t("change_account_title"),
            self.t("change_account_text"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        delete_saved_cookies()
        self.cookies_available = False
        self.saved_credentials = None
        self.username_input.clear()
        self.password_input.clear()
        self.credentials_locked = False
        self.apply_cookie_lock()
        self._refresh_start_button_state()

    def open_non_followers_file(self):
        path = self._export_path().resolve()
        if not path.exists():
            QMessageBox.information(
                self,
                self.t("non_followers_missing_title"),
                self.t("non_followers_missing_text"),
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self,
                self.t("open_non_followers_failed_title"),
                self.t("open_non_followers_failed_text"),
            )

    def _open_menu(self):
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        config_action = QAction(self.t("config"), self)
        config_action.setIcon(self._settings_icon())
        config_action.setToolTip(self.t("config_tooltip"))
        config_action.triggered.connect(self.open_config_dialog)
        menu.addAction(config_action)

        open_logs = QAction(self.t("open_logs"), self)
        open_logs.setIcon(self._logs_icon())
        open_logs.setToolTip(self.t("open_logs_tooltip"))
        open_logs.triggered.connect(self.open_logs_dialog)
        menu.addAction(open_logs)

        menu.addSeparator()

        clear_output = QAction(self.t("clear_output"), self)
        clear_output.setIcon(self._clear_icon())
        clear_output.setToolTip(self.t("clear_output_tooltip"))
        clear_output.triggered.connect(self.clear_output)
        menu.addAction(clear_output)

        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def t(self, key, default=None):
        return TRANSLATIONS.get(self.language, TRANSLATIONS["en"]).get(key, default or key)

    def set_language(self, language):
        self.language = language
        self.settings.setValue("language", language)
        self.apply_language()

    def clear_output(self):
        self.output.clear()
        self.progress.setValue(0)

    def _set_progress_running(self, running):
        self.progress.setProperty("running", bool(running))
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)

    def _start_cookie_watch(self):
        self._sync_cookie_credentials_state()
        if not self.cookie_watch_timer.isActive():
            self.cookie_watch_timer.start()

    def _stop_cookie_watch(self):
        if self.cookie_watch_timer.isActive():
            self.cookie_watch_timer.stop()

    def _sync_cookie_credentials_state(self):
        self.cookies_available = has_valid_cookies()
        if not self.cookies_available:
            return

        if self.saved_credentials:
            self.saved_credentials = None
            self.username_input.setText("********")
            self.password_input.setText("********")
            self.append_log("success", self.t("cookies_detected_credentials_cleared"))

        self.credentials_locked = True
        self.apply_cookie_lock()

    def apply_language(self):
        self._refresh_browser_panel_state()
        self.subtitle_label.setText(self.t("app_subtitle"))
        self.session_heading.setText("")
        self.target_username_label.setText(self.t("instagram_username"))
        self.target_username_input.setPlaceholderText(self.t("instagram_username_placeholder"))
        self.username_label.setText(self.t("username"))
        self.password_label.setText(self.t("password"))
        self.save_credentials_button.setText(self.t("save_credentials"))
        self.edit_credentials_button.setText(self.t("edit_credentials"))
        self.change_account_button.setText(self.t("change_account"))
        self.password_visibility_button.setToolTip(self.t("show_password"))
        self.output_title.setText(self.t("user_output"))
        self.start_button.setText(self.t("start"))
        self.no_followers_button.setText(self.t("no_followers_process"))
        self.no_followers_button.setToolTip(self.t("no_followers_process_tooltip"))
        self.unfollow_process_button.setText(self.t("unfollow_process"))
        self.unfollow_process_button.setToolTip(self.t("unfollow_process_tooltip"))
        self.stop_button.setText(self.t("stop"))
        self.menu_button.setToolTip(self.t("more_options"))
        self.export_button.setText(self.t("export"))
        self.stat_labels[0].setText(self.t("followers"))
        self.stat_labels[1].setText(self.t("following"))
        self.stat_labels[2].setText(self.t("non_followers"))
        self._refresh_process_header()
        self.apply_cookie_lock()
        self.set_status(self.current_status)

    def select_process_mode(self, mode):
        self.selected_process_mode = mode
        self._refresh_process_header()
        self._refresh_start_button_state()

    def _refresh_process_header(self):
        if not hasattr(self, "no_followers_button"):
            return

        selected = {
            "no_followers": self.no_followers_button,
            "unfollow": self.unfollow_process_button,
        }
        for mode, button in selected.items():
            is_selected = mode == self.selected_process_mode
            button.setChecked(is_selected)
            button.setProperty("selected", is_selected)
            button.setAccessibleName(self.t(f"{mode}_process"))
            button.style().unpolish(button)
            button.style().polish(button)

    def apply_cookie_lock(self):
        if not hasattr(self, "username_input"):
            return

        locked = self.cookies_available
        if not locked and not self.saved_credentials:
            self.credentials_locked = False

        self.username_input.setEnabled(not locked)
        self.password_input.setEnabled(not locked)
        self.save_credentials_button.setEnabled(not locked and not self.credentials_locked)
        self.edit_credentials_button.setEnabled(not locked and self.credentials_locked)
        self.password_visibility_button.setEnabled(not locked)
        self.change_account_button.setEnabled(locked)
        if locked:
            self.username_input.setText("********")
            self.password_input.setText("********")
            self.credentials_locked = True
            self.session_status.setText(self.t("locked_session"))
        elif not self.saved_credentials:
            self.session_status.setText(self.t("credentials_required"))

        self._refresh_session_visual_state()
        self._refresh_start_button_state()

    def _has_ready_session(self):
        return self.cookies_available or (self.credentials_locked and bool(self.saved_credentials))

    def _has_target_username(self):
        if not hasattr(self, "target_username_input"):
            return bool(self.target_username)
        return bool(self.target_username_input.text().strip().lstrip("@").strip("/"))

    def _refresh_start_button_state(self):
        if not hasattr(self, "start_button"):
            return
        running = bool(self.worker and self.worker.isRunning())
        has_target = self._has_target_username()
        session_enabled = (not running) and has_target and self._has_ready_session()
        unfollow_enabled = (not running) and has_target and self._export_path().exists()
        start_enabled = unfollow_enabled if self.selected_process_mode == "unfollow" else session_enabled
        self.start_button.setEnabled(start_enabled)
        if hasattr(self, "no_followers_button"):
            self.no_followers_button.setEnabled(not running)
        if hasattr(self, "unfollow_process_button"):
            self.unfollow_process_button.setEnabled(not running)

    def _browser_toggle_text(self):
        key = "hide_browser" if self.browser_container.isVisible() else "show_browser"
        return self.t(key)

    def _refresh_browser_panel_state(self):
        visible = self.browser_container.isVisible()
        self.browser_title.setText(self.t("browser") if visible else self.t("session"))
        self.browser_toggle_button.setText(self._browser_toggle_text())
        self.browser_toggle_button.setIcon(self._eye_icon(visible))
        self.browser_toggle_button.setIconSize(QSize(18, 18))
        self.browser_toggle_button.setChecked(visible)
        self.browser_toggle_button.setProperty("active", visible)
        self.browser_toggle_button.setToolTip(self.t("hide_browser_tooltip" if visible else "show_browser_tooltip"))
        self.browser_toggle_button.style().unpolish(self.browser_toggle_button)
        self.browser_toggle_button.style().polish(self.browser_toggle_button)

    def _eye_icon(self, active=False):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor("#E8ECEF" if active else "#B9C2C8")
        painter.setPen(QPen(color, 1.8))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(3, 6, 14, 8)
        painter.setBrush(color)
        painter.drawEllipse(8, 8, 4, 4)
        if active:
            painter.setPen(QPen(QColor("#3C8B6D"), 2.0))
            painter.drawLine(15, 4, 18, 7)
        painter.end()
        return QIcon(pixmap)

    def _menu_icon(self):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#B9C2C8"))
        painter.setPen(Qt.NoPen)
        for x in (5, 10, 15):
            painter.drawEllipse(x - 1, 9, 2, 2)
        painter.end()
        return QIcon(pixmap)

    def _settings_icon(self):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#C9D0D5"), 1.8))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(5, 5, 10, 10)
        painter.drawLine(10, 1, 10, 4)
        painter.drawLine(10, 16, 10, 19)
        painter.drawLine(1, 10, 4, 10)
        painter.drawLine(16, 10, 19, 10)
        painter.setBrush(QColor("#5FAF86"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 4, 4)
        painter.end()
        return QIcon(pixmap)

    def _logs_icon(self):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#C9D0D5"), 1.7))
        painter.drawRoundedRect(4, 3, 12, 14, 2, 2)
        for y in (7, 10, 13):
            painter.drawLine(7, y, 13, y)
        painter.end()
        return QIcon(pixmap)

    def _clear_icon(self):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#D76B63"), 1.8))
        painter.drawLine(6, 6, 14, 14)
        painter.drawLine(14, 6, 6, 14)
        painter.end()
        return QIcon(pixmap)

    def _refresh_session_visual_state(self):
        if not hasattr(self, "credential_card"):
            return

        locked = self.cookies_available or self.credentials_locked
        warning = not locked and not self.saved_credentials
        self.credential_card.setProperty("locked", locked)
        self.credential_card.setProperty("warning", warning)
        self.credential_card.style().unpolish(self.credential_card)
        self.credential_card.style().polish(self.credential_card)

        if self.cookies_available:
            self.session_badge.setText("LOCKED")
        elif self.credentials_locked:
            self.session_badge.setText(self.t("session_ready"))
        else:
            self.session_badge.setText(self.t("status_idle"))

    def _restore_window(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.save_target_username()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("language", self.language)
        self.settings.setValue("export_file_path", self.export_file_path)
        self.settings.setValue("logs_dir", self.logs_dir)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        super().closeEvent(event)


class UnfollowSelectionDialog(QDialog):
    def __init__(self, translate, users, parent=None):
        super().__init__(parent)
        self.translate = translate
        self.checkboxes = []
        self.setWindowTitle(self.translate("unfollow_selection_title"))
        self.setMinimumSize(520, 520)
        self.resize(620, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        label = QLabel(self.translate("unfollow_selection_text"))
        label.setObjectName("sectionTitle")
        layout.addWidget(label)

        self.selection_count = QLabel("")
        self.selection_count.setObjectName("statLabel")
        layout.addWidget(self.selection_count)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)

        for username in users:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            checkbox = QCheckBox(f"@{username}")
            checkbox.setChecked(False)
            checkbox.setProperty("username", username)
            checkbox.stateChanged.connect(self._refresh_selection_state)
            self.checkboxes.append(checkbox)
            row.addWidget(checkbox, stretch=1)

            profile_button = QPushButton(self.translate("view_profile"))
            profile_button.setObjectName("ghostButton")
            profile_button.clicked.connect(lambda checked=False, user=username: self._open_profile(user))
            row.addWidget(profile_button)
            content_layout.addLayout(row)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        quick_actions = QHBoxLayout()
        select_all = QPushButton(self.translate("select_all"))
        select_all.setObjectName("secondaryButton")
        select_all.clicked.connect(lambda: self._set_all(True))
        select_none = QPushButton(self.translate("select_none"))
        select_none.setObjectName("secondaryButton")
        select_none.clicked.connect(lambda: self._set_all(False))
        quick_actions.addWidget(select_all)
        quick_actions.addWidget(select_none)
        quick_actions.addStretch()
        layout.addLayout(quick_actions)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.unfollow_button = buttons.addButton(self.translate("unfollow_selected"), QDialogButtonBox.AcceptRole)
        self.unfollow_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_selection_state()

    def selected_users(self):
        return [checkbox.property("username") for checkbox in self.checkboxes if checkbox.isChecked()]

    def _set_all(self, checked):
        for checkbox in self.checkboxes:
            checkbox.setChecked(checked)
        self._refresh_selection_state()

    def _refresh_selection_state(self):
        selected = len(self.selected_users())
        self.selection_count.setText(self.translate("selected_count").format(count=selected))
        self.unfollow_button.setEnabled(selected > 0)

    def _open_profile(self, username):
        QDesktopServices.openUrl(QUrl(f"https://www.instagram.com/{username}/"))


class SecurityCodeDialog(QDialog):
    resend_requested = Signal()
    RESEND_SECONDS = 60

    def __init__(self, translate, parent=None):
        super().__init__(parent)
        self.translate = translate
        self.security_code = None
        self._resend_seconds_remaining = self.RESEND_SECONDS
        self.setWindowTitle(self.translate("security_code_required"))
        self.setMinimumSize(440, 340)
        self.setMaximumWidth(520)
        self.setModal(False)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)
        
        # Title
        title = QLabel(self.translate("security_code_required"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)
        
        # Description
        description = QLabel(self.translate("enter_security_code"))
        description.setStyleSheet("color: #BDBDBD; font-size: 13px; line-height: 1.5;")
        description.setWordWrap(True)
        layout.addWidget(description)
        
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(self.translate("security_code_placeholder"))
        self.code_input.setEchoMode(QLineEdit.Password)
        self.code_input.setMinimumHeight(44)
        self.code_input.setStyleSheet("""
            QLineEdit {
                background: #202020;
                border: 1px solid #383838;
                border-radius: 8px;
                padding: 10px 14px;
                color: #EAEAEA;
            }
            QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)

        code_layout = QHBoxLayout()
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(6)
        code_layout.addWidget(self.code_input)

        self.visibility_button = QPushButton("")
        self.visibility_button.setObjectName("iconButton")
        self.visibility_button.setCheckable(True)
        self.visibility_button.setIcon(self._eye_icon(False))
        self.visibility_button.setIconSize(QSize(18, 18))
        self.visibility_button.setToolTip(self.translate("show"))
        self.visibility_button.clicked.connect(self.toggle_visibility)
        code_layout.addWidget(self.visibility_button)
        layout.addLayout(code_layout)

        self.resend_status = QLabel("")
        self.resend_status.setObjectName("sessionStatus")
        self.resend_status.setWordWrap(True)
        layout.addWidget(self.resend_status)

        self.resend_button = QPushButton("")
        self.resend_button.setObjectName("secondaryButton")
        self.resend_button.clicked.connect(self.request_new_code)
        layout.addWidget(self.resend_button)

        self.resend_timer = QTimer(self)
        self.resend_timer.setInterval(1000)
        self.resend_timer.timeout.connect(self._tick_resend_countdown)
        self._start_resend_countdown()

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        submit_button = buttons.addButton(self.translate("save"), QDialogButtonBox.AcceptRole)
        submit_button.clicked.connect(self.submit_code)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Set focus to input
        self.code_input.setFocus()
        self.code_input.returnPressed.connect(self.submit_code)

    def request_new_code(self):
        if not self.resend_button.isEnabled():
            return
        self.resend_requested.emit()
        self._start_resend_countdown()

    def _start_resend_countdown(self):
        self._resend_seconds_remaining = self.RESEND_SECONDS
        self.resend_button.setEnabled(False)
        self._refresh_resend_state()
        self.resend_timer.start()

    def _tick_resend_countdown(self):
        self._resend_seconds_remaining = max(0, self._resend_seconds_remaining - 1)
        self._refresh_resend_state()
        if self._resend_seconds_remaining == 0:
            self.resend_timer.stop()

    def _refresh_resend_state(self):
        if self._resend_seconds_remaining > 0:
            dots = "." * ((self.RESEND_SECONDS - self._resend_seconds_remaining) % 4)
            self.resend_status.setText(
                self.translate("resend_security_code_countdown").format(seconds=self._resend_seconds_remaining) + dots
            )
            self.resend_button.setVisible(False)
            self.resend_button.setEnabled(False)
            return

        self.resend_status.setText(self.translate("resend_security_code_ready"))
        self.resend_button.setText(self.translate("resend_security_code"))
        self.resend_button.setVisible(True)
        self.resend_button.setEnabled(True)
    
    def toggle_visibility(self):
        if self.visibility_button.isChecked():
            self.code_input.setEchoMode(QLineEdit.Normal)
            self.visibility_button.setIcon(self._eye_icon(True))
            self.visibility_button.setToolTip(self.translate("hide"))
        else:
            self.code_input.setEchoMode(QLineEdit.Password)
            self.visibility_button.setIcon(self._eye_icon(False))
            self.visibility_button.setToolTip(self.translate("show"))
    
    def submit_code(self):
        code = self.code_input.text().strip()
        if code:
            self.security_code = code
            self.accept()
    
    def get_security_code(self):
        return self.security_code

    def _eye_icon(self, active=False):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor("#E8ECEF" if active else "#B9C2C8")
        painter.setPen(QPen(color, 1.8))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(3, 6, 14, 8)
        painter.setBrush(color)
        painter.drawEllipse(8, 8, 4, 4)
        if active:
            painter.setPen(QPen(QColor("#3C8B6D"), 2.0))
            painter.drawLine(15, 4, 18, 7)
        painter.end()
        return QIcon(pixmap)

class ConfigDialog(QDialog):
    def __init__(self, translate, export_file_path, logs_dir, language, parent=None):
        super().__init__(parent)
        self.translate = translate
        self._current_language = language or "es"
        self.setWindowTitle(self.translate("config"))
        self.setMinimumSize(520, 300)
        self.resize(680, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(14)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(12)

        language_label = QLabel(self.translate("application_language"))
        language_label.setObjectName("statLabel")
        self.language_input = QComboBox()
        self.language_input.setObjectName("languageCombo")
        self.language_input.setIconSize(QSize(22, 15))
        self.language_input.addItem(QIcon(resource_path("assets/flag-es.svg")), self.translate("spanish"), "es")
        self.language_input.addItem(QIcon(resource_path("assets/flag-gb.svg")), self.translate("english"), "en")
        selected_language = max(0, self.language_input.findData(language or "es"))
        self.language_input.setCurrentIndex(selected_language)
        self.language_input.currentIndexChanged.connect(self._refresh_language_save_button)
        form.addWidget(language_label, 0, 0, 1, 2)
        form.addWidget(self.language_input, 1, 0, 1, 2)

        export_label = QLabel(self.translate("export_file"))
        export_label.setObjectName("statLabel")
        self.export_input = QLineEdit(str(export_file_path or "non_followers.txt"))
        export_button = QPushButton(self.translate("browse"))
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self.browse_export_file)
        form.addWidget(export_label, 2, 0, 1, 2)
        form.addWidget(self.export_input, 3, 0)
        form.addWidget(export_button, 3, 1)

        logs_label = QLabel(self.translate("logs_directory"))
        logs_label.setObjectName("statLabel")
        self.logs_input = QLineEdit(str(logs_dir or "logs"))
        logs_button = QPushButton(self.translate("browse"))
        logs_button.setObjectName("secondaryButton")
        logs_button.clicked.connect(self.browse_logs_dir)
        form.addWidget(logs_label, 4, 0, 1, 2)
        form.addWidget(self.logs_input, 5, 0)
        form.addWidget(logs_button, 5, 1)
        form.setColumnStretch(0, 1)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.save_button = buttons.addButton("", QDialogButtonBox.AcceptRole)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if self.cancel_button:
            self.cancel_button.setText(self._config_t("cancel"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_language_save_button()

    def _config_t(self, key):
        return TRANSLATIONS.get(self._current_language, TRANSLATIONS["en"]).get(key, key)

    def _refresh_language_save_button(self):
        self._current_language = self.language_input.currentData() or "es"
        self.save_button.setText(self._config_t("save"))

    def browse_export_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.translate("export_file"),
            self.export_input.text().strip() or "non_followers.txt",
            "Text files (*.txt);;All files (*)",
        )
        if path:
            self.export_input.setText(path)

    def browse_logs_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            self.translate("logs_directory"),
            self.logs_input.text().strip() or "logs",
        )
        if path:
            self.logs_input.setText(path)

    def values(self):
        export_file_path = self.export_input.text().strip() or "non_followers.txt"
        logs_dir = self.logs_input.text().strip() or "logs"
        language = self.language_input.currentData() or "es"
        return export_file_path, logs_dir, language


class LogsDialog(QDialog):
    def __init__(self, translate, logs_dir, parent=None):
        super().__init__(parent)
        self.translate = translate
        self.logs_dir = logs_dir
        self.setWindowTitle(self.translate("logs_title"))
        self.setMinimumSize(980, 640)
        self.resize(1120, 720)

        self.text = self._read_log_file()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        self.editor = QTextEdit()
        self.editor.setObjectName("logs")
        self.editor.setReadOnly(True)
        self.editor.setPlainText(self.text)
        layout.addWidget(self.editor, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton(self.translate("copy"), QDialogButtonBox.ActionRole)
        copy_button.clicked.connect(self.editor.selectAll)
        copy_button.clicked.connect(self.editor.copy)

        save_button = buttons.addButton(self.translate("export_logs"), QDialogButtonBox.ActionRole)
        save_button.clicked.connect(self.export_logs)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _read_log_file(self):
        path = latest_log_file(self.logs_dir)
        if path is None or not path.exists():
            return self.translate("no_logs")
        return path.read_text(encoding="utf-8", errors="replace")

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export logs", "instafollow-log.txt", "Text files (*.txt)")
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")


def resource_path(relative_path):
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return str(base_path / relative_path)
