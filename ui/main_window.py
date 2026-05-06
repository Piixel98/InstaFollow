import html
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QSize, QSettings, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
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
        self.cookies_available = has_valid_cookies()
        self.credentials_locked = False

        setup_logging()
        self._install_log_handler()
        self._build_ui()
        self.apply_language()
        self._restore_window()

    def _build_ui(self):
        self.setWindowTitle("InstaFollow")
        self.setWindowIcon(QIcon(resource_path("assets/instafollow.ico")))
        self.setMinimumSize(1100, 760)
        self.setStyleSheet(APP_STYLE)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)

        shell = QFrame()
        shell.setObjectName("shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(22, 18, 22, 18)
        shell_layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("InstaFollow")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusPill")
        header.addWidget(self.status_label)

        menu_button = QPushButton("...")
        menu_button.setObjectName("menuButton")
        menu_button.clicked.connect(self._open_menu)
        header.addWidget(menu_button)
        shell_layout.addLayout(header)

        self.browser_panel = self._build_browser_panel()
        shell_layout.addWidget(self.browser_panel, stretch=7)

        self.stats_panel = self._build_stats_panel()
        shell_layout.addWidget(self.stats_panel)

        self.output_panel = self._build_output_panel()
        shell_layout.addWidget(self.output_panel, stretch=3)

        footer = QHBoxLayout()
        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #AFAFAF;")
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
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(14, 12, 14, 8)
        header.setSpacing(10)
        self.browser_title = QLabel("")
        label = self.browser_title
        label.setObjectName("sectionTitle")
        header.addWidget(label)
        header.addStretch()
        self.browser_toggle_button = QPushButton("")
        self.browser_toggle_button.setObjectName("toggleButton")
        self.browser_toggle_button.clicked.connect(self.toggle_browser_visibility)
        header.addWidget(self.browser_toggle_button)
        layout.addLayout(header)

        self.session_form = self._build_session_form()
        layout.addWidget(self.session_form, stretch=1)

        self.browser_container = BrowserContainer()
        self.browser_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.browser_container.setVisible(False)
        self.browser_container.setStyleSheet("QFrame#browserViewport { margin: 0px; border: none; border-radius: 0px; }")
        layout.addWidget(self.browser_container, stretch=1)
        return panel

    def _build_session_form(self):
        form = QFrame()
        form.setObjectName("sessionForm")
        layout = QVBoxLayout(form)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.session_heading = QLabel("")
        self.session_heading.setObjectName("sectionTitle")
        self.session_heading.setVisible(False)
        self.session_badge = QLabel("")
        self.session_badge.setObjectName("sessionBadge")
        header.addWidget(self.session_heading)
        header.addStretch()
        header.addWidget(self.session_badge)
        layout.addLayout(header)

        self.credential_card = QFrame()
        self.credential_card.setObjectName("credentialCard")
        card_layout = QGridLayout(self.credential_card)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setHorizontalSpacing(10)
        card_layout.setVerticalSpacing(8)

        self.username_label = QLabel("")
        self.password_label = QLabel("")
        for label in (self.username_label, self.password_label):
            label.setObjectName("statLabel")

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_visibility_button = QPushButton("")
        self.password_visibility_button.setObjectName("iconButton")
        self.password_visibility_button.setCheckable(True)
        self.password_visibility_button.setIcon(self._eye_icon(False))
        self.password_visibility_button.setIconSize(QSize(18, 18))
        self.password_visibility_button.clicked.connect(self.toggle_password_visibility)

        self.session_status = QLabel("")
        self.session_status.setStyleSheet("color: #AFAFAF;")

        self.save_credentials_button = QPushButton("")
        self.save_credentials_button.setObjectName("startButton")
        self.save_credentials_button.clicked.connect(self.save_session_form)

        self.edit_credentials_button = QPushButton("")
        self.edit_credentials_button.setObjectName("ghostButton")
        self.edit_credentials_button.clicked.connect(self.edit_credentials)

        self.change_account_button = QPushButton("")
        self.change_account_button.setObjectName("secondaryButton")
        self.change_account_button.clicked.connect(self.change_account)

        card_layout.addWidget(self.username_label, 0, 0)
        card_layout.addWidget(self.username_input, 1, 0)
        card_layout.addWidget(self.password_label, 0, 1)
        password_layout = QHBoxLayout()
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(6)
        password_layout.addWidget(self.password_input)
        password_layout.addWidget(self.password_visibility_button)
        card_layout.addLayout(password_layout, 1, 1)
        card_layout.setColumnStretch(0, 1)
        card_layout.setColumnStretch(1, 1)
        layout.addWidget(self.credential_card)

        actions = QHBoxLayout()
        actions.addWidget(self.save_credentials_button)
        actions.addWidget(self.edit_credentials_button)
        actions.addWidget(self.change_account_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.session_status)
        self.apply_cookie_lock()
        return form

    def _build_stats_panel(self):
        panel = QFrame()
        panel.setObjectName("statsPanel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setHorizontalSpacing(28)

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
        layout.addWidget(self.progress, 0, 4, 2, 1)
        layout.setColumnStretch(4, 1)
        return panel

    def _stat_block(self, layout, column, value, label):
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        text_label = QLabel(label)
        text_label.setObjectName("statLabel")
        if not hasattr(self, "stat_labels"):
            self.stat_labels = []
        self.stat_labels.append(text_label)
        layout.addWidget(value_label, 0, column)
        layout.addWidget(text_label, 1, column)
        return value_label

    def _build_output_panel(self):
        panel = QFrame()
        panel.setObjectName("outputPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
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

    def _install_log_handler(self):
        logger = logging.getLogger("InstaFollow")
        self.qt_log_handler = QtLogHandler()
        self.qt_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.qt_log_handler.emitter.message.connect(self.append_log)
        logger.addHandler(self.qt_log_handler)

    def start_automation(self):
        if self.worker and self.worker.isRunning():
            return

        self.cookies_available = has_valid_cookies()
        self.apply_cookie_lock()
        if not self._has_ready_session():
            self.session_status.setText(self.t("credentials_not_ready"))
            self.show_toast(self.t("credentials_not_ready"))
            return

        self.output.clear()
        self.full_log_lines.clear()
        self.progress.setValue(0)
        self.update_counts(0, 0, 0)
        self.set_status("running")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.change_account_button.setEnabled(False)
        self.show_toast(self.t("automation_started"))

        self.worker = AutomationWorker(self, credentials=self.saved_credentials)
        self.worker.output.connect(self.append_log)
        self.worker.status_changed.connect(self.set_status)
        self.worker.browser_ready.connect(self.embed_browser)
        self.worker.credentials_required.connect(self.handle_credentials_required)
        self.worker.security_code_required.connect(self.handle_security_code_required)
        self.worker.login_failed.connect(self.handle_login_failed)
        self.worker.progress_changed.connect(self.progress.setValue)
        self.worker.counts_changed.connect(self.update_counts)
        self.worker.unfollow_selection_prompt.connect(self.handle_unfollow_selection_prompt)
        self.worker.finished_ok.connect(lambda: self.show_toast(self.t("automation_finished")))
        self.worker.failed.connect(self.handle_worker_failed)
        self.worker.stopped_by_user.connect(self.handle_worker_stopped_by_user)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.start()

    def stop_automation(self):
        if self.worker and self.worker.isRunning():
            self.show_toast(self.t("stopping"))
            self.set_status("stopping")
            self.worker.stop()

    def handle_worker_finished(self):
        self.browser_container.release()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.awaiting_security_code = False
        self.cookies_available = has_valid_cookies()
        self.apply_cookie_lock()
        self._refresh_start_button_state()

    def handle_worker_failed(self):
        self.set_status("error")
        self.show_toast(self.t("automation_failed"))

    def handle_worker_stopped_by_user(self):
        self.set_status("stopped")
        self.append_log("warning", self.t("stopped_by_user"))
        self.show_toast(self.t("stopped_by_user"))

    def embed_browser(self):
        self.session_form.setVisible(False)
        self.browser_container.setVisible(True)
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

        dialog = SecurityCodeDialog(self.t, self)
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() == QDialog.Accepted:
            code = dialog.get_security_code()
            if code and self.worker:
                self.append_log("info", "Security code submitted, verifying...")
                self.worker.set_security_code(code)
            else:
                self.append_log("warning", "No security code entered")
        else:
            self.append_log("error", "2FA cancelled by user")
            if self.worker:
                self.worker.stop()

    def handle_login_failed(self):
        credentials = self.saved_credentials or {}
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

    def append_log(self, level, message):
        self.full_log_lines.append(message)
        color = {
            "success": "#4CAF50",
            "info": "#EAEAEA",
            "warning": "#F6C343",
            "error": "#F44336",
            "debug": "#9CA3AF",
        }.get(level, "#EAEAEA")

        escaped = html.escape(message)
        self.output.append(f'<span style="color:{color};">{escaped}</span>')
        self.output.moveCursor(QTextCursor.End)

    def update_counts(self, followers, following, non_followers):
        self.followers_value.setText(str(followers))
        self.following_value.setText(str(following))
        self.non_followers_value.setText(str(non_followers))

    def set_status(self, status):
        normalized = str(status).lower()
        self.current_status = normalized
        self.status_label.setText(self.t(f"status_{normalized}", status))
        color = {
            "running": "#1F5130",
            "idle": "#333333",
            "stopped": "#65312D",
            "stopping": "#6A521D",
            "error": "#65312D",
        }.get(normalized, "#333333")
        self.status_label.setStyleSheet(f"background: {color};")

    def show_toast(self, message):
        self.toast.setText(message)
        QTimer.singleShot(3500, lambda: self.toast.setText(""))

    def open_logs_dialog(self):
        dialog = LogsDialog(self.t, self)
        dialog.exec()

    def toggle_browser_visibility(self):
        visible = not self.browser_container.isVisible()
        self.session_form.setVisible(not visible)
        self.browser_container.setVisible(visible)
        self._refresh_browser_panel_state()
        if visible:
            self.browser_container.resize_embedded()

    def toggle_password_visibility(self):
        if self.password_visibility_button.isChecked():
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.password_visibility_button.setIcon(self._eye_icon(True))
            return
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_visibility_button.setIcon(self._eye_icon(False))

    def save_session_form(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self.session_status.setText(self.t("credentials_required"))
            return

        self.saved_credentials = {"username": username, "password": password}
        self.username_input.setText("****")
        self.password_input.setText("****")
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
        path = Path("non_followers.txt").resolve()
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
        open_logs = QAction(self.t("open_logs"), self)
        open_logs.triggered.connect(self.open_logs_dialog)
        menu.addAction(open_logs)

        clear_output = QAction(self.t("clear_output"), self)
        clear_output.triggered.connect(self.clear_output)
        menu.addAction(clear_output)

        language_menu = menu.addMenu(self.t("language"))
        spanish = QAction(self.t("spanish"), self)
        spanish.triggered.connect(lambda: self.set_language("es"))
        language_menu.addAction(spanish)

        english = QAction(self.t("english"), self)
        english.triggered.connect(lambda: self.set_language("en"))
        language_menu.addAction(english)

        menu.exec(self.mapToGlobal(self.rect().topRight()))

    def t(self, key, default=None):
        return TRANSLATIONS.get(self.language, TRANSLATIONS["en"]).get(key, default or key)

    def set_language(self, language):
        self.language = language
        self.settings.setValue("language", language)
        self.apply_language()

    def clear_output(self):
        self.output.clear()
        self.progress.setValue(0)

    def apply_language(self):
        self._refresh_browser_panel_state()
        self.session_heading.setText("")
        self.username_label.setText(self.t("username"))
        self.password_label.setText(self.t("password"))
        self.save_credentials_button.setText(self.t("save_credentials"))
        self.edit_credentials_button.setText(self.t("edit_credentials"))
        self.change_account_button.setText(self.t("change_account"))
        self.password_visibility_button.setToolTip(self.t("show_password"))
        self.output_title.setText(self.t("user_output"))
        self.start_button.setText(self.t("start"))
        self.stop_button.setText(self.t("stop"))
        self.export_button.setText(self.t("export"))
        self.stat_labels[0].setText(self.t("followers"))
        self.stat_labels[1].setText(self.t("following"))
        self.stat_labels[2].setText(self.t("non_followers"))
        self.apply_cookie_lock()
        self.set_status(self.current_status)

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
            self.username_input.setText("****")
            self.password_input.setText("****")
            self.credentials_locked = True
            self.session_status.setText(self.t("locked_session"))
        elif not self.saved_credentials:
            self.session_status.setText(self.t("credentials_required"))

        self._refresh_session_visual_state()
        self._refresh_start_button_state()

    def _has_ready_session(self):
        return self.cookies_available or (self.credentials_locked and bool(self.saved_credentials))

    def _refresh_start_button_state(self):
        if not hasattr(self, "start_button"):
            return
        running = bool(self.worker and self.worker.isRunning())
        self.start_button.setEnabled((not running) and self._has_ready_session())

    def _browser_toggle_text(self):
        key = "hide_browser" if self.browser_container.isVisible() else "show_browser"
        return self.t(key)

    def _refresh_browser_panel_state(self):
        visible = self.browser_container.isVisible()
        self.browser_title.setText(self.t("browser") if visible else self.t("session"))
        self.browser_toggle_button.setText(self._browser_toggle_text())
        self.browser_toggle_button.setIcon(self._eye_icon(visible))
        self.browser_toggle_button.setIconSize(QSize(18, 18))

    def _eye_icon(self, active=False):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor("#EAEAEA" if active else "#BDBDBD")
        painter.setPen(QPen(color, 1.8))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(3, 6, 14, 8)
        painter.setBrush(color)
        painter.drawEllipse(8, 8, 4, 4)
        if active:
            painter.setPen(QPen(QColor("#4CAF50"), 2.0))
            painter.drawLine(15, 4, 18, 7)
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
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("language", self.language)
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)

        for username in users:
            checkbox = QCheckBox(f"@{username}")
            checkbox.setChecked(True)
            checkbox.setProperty("username", username)
            self.checkboxes.append(checkbox)
            content_layout.addWidget(checkbox)

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
        save_button = buttons.addButton(self.translate("save_selection"), QDialogButtonBox.AcceptRole)
        save_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_users(self):
        return [checkbox.property("username") for checkbox in self.checkboxes if checkbox.isChecked()]

    def _set_all(self, checked):
        for checkbox in self.checkboxes:
            checkbox.setChecked(checked)


class SecurityCodeDialog(QDialog):
    def __init__(self, translate, parent=None):
        super().__init__(parent)
        self.translate = translate
        self.security_code = None
        self.setWindowTitle(self.translate("security_code_required"))
        self.setMinimumSize(420, 280)
        self.setMaximumWidth(520)
        self.setModal(True)
        
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
        
        # Code input
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
        layout.addWidget(self.code_input)
        
        # Visibility toggle
        visibility_layout = QHBoxLayout()
        self.visibility_button = QPushButton(self.translate("show"))
        self.visibility_button.setObjectName("ghostButton")
        self.visibility_button.setCheckable(True)
        self.visibility_button.setMaximumWidth(60)
        self.visibility_button.clicked.connect(self.toggle_visibility)
        visibility_layout.addStretch()
        visibility_layout.addWidget(self.visibility_button)
        layout.addLayout(visibility_layout)
        
        layout.addStretch()
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        submit_button = buttons.addButton(self.translate("save"), QDialogButtonBox.AcceptRole)
        submit_button.clicked.connect(self.submit_code)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Set focus to input
        self.code_input.setFocus()
        self.code_input.returnPressed.connect(self.submit_code)
    
    def toggle_visibility(self):
        if self.visibility_button.isChecked():
            self.code_input.setEchoMode(QLineEdit.Normal)
            self.visibility_button.setText(self.translate("hide"))
        else:
            self.code_input.setEchoMode(QLineEdit.Password)
            self.visibility_button.setText(self.translate("show"))
    
    def submit_code(self):
        code = self.code_input.text().strip()
        if code:
            self.security_code = code
            self.accept()
    
    def get_security_code(self):
        return self.security_code


class LogsDialog(QDialog):
    def __init__(self, translate, parent=None):
        super().__init__(parent)
        self.translate = translate
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
        path = latest_log_file()
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
