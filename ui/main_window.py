import html
import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.browser_embed import BrowserContainer
from ui.logging_handler import QtLogHandler
from ui.styles import APP_STYLE
from ui.worker import AutomationWorker
from utils import setup_logging


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.full_log_lines = []
        self.settings = QSettings("InstaFollow", "InstaFollow")

        setup_logging()
        self._install_log_handler()
        self._build_ui()
        self._restore_window()

    def _build_ui(self):
        self.setWindowTitle("InstaFollow")
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

        self.status_label = QLabel("Idle")
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

        self.logs_button = QPushButton("Open Logs")
        self.logs_button.setObjectName("logsButton")
        self.logs_button.clicked.connect(self.open_logs_dialog)
        footer.addWidget(self.logs_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_automation)
        footer.addWidget(self.stop_button)

        self.start_button = QPushButton("Start")
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
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        label = QLabel("Browser")
        label.setObjectName("sectionTitle")
        header.addWidget(label)
        header.addStretch()
        hint = QLabel("Playwright + Chrome")
        hint.setStyleSheet("color: #8D8D8D;")
        header.addWidget(hint)
        layout.addLayout(header)

        self.browser_container = BrowserContainer()
        self.browser_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.browser_container)
        return panel

    def _build_stats_panel(self):
        panel = QFrame()
        panel.setObjectName("statsPanel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setHorizontalSpacing(28)

        self.followers_value = self._stat_block(layout, 0, "0", "followers")
        self.following_value = self._stat_block(layout, 1, "0", "following")
        self.non_followers_value = self._stat_block(layout, 2, "0", "non-followers")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress, 0, 3, 2, 1)
        layout.setColumnStretch(3, 1)
        return panel

    def _stat_block(self, layout, column, value, label):
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        text_label = QLabel(label)
        text_label.setObjectName("statLabel")
        layout.addWidget(value_label, 0, column)
        layout.addWidget(text_label, 1, column)
        return value_label

    def _build_output_panel(self):
        panel = QFrame()
        panel.setObjectName("outputPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        label = QLabel("User Output")
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

        self.output.clear()
        self.full_log_lines.clear()
        self.progress.setValue(0)
        self.update_counts(0, 0, 0)
        self.set_status("Running")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.show_toast("Automation started")

        self.worker = AutomationWorker(self)
        self.worker.output.connect(self.append_log)
        self.worker.status_changed.connect(self.set_status)
        self.worker.browser_ready.connect(self.embed_browser)
        self.worker.progress_changed.connect(self.progress.setValue)
        self.worker.counts_changed.connect(self.update_counts)
        self.worker.login_required.connect(self.handle_login_required)
        self.worker.unfollow_prompt.connect(self.handle_unfollow_prompt)
        self.worker.cookie_cleanup_prompt.connect(self.handle_cookie_cleanup_prompt)
        self.worker.finished_ok.connect(lambda: self.show_toast("Automation finished"))
        self.worker.failed.connect(self.handle_worker_failed)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.start()

    def stop_automation(self):
        if self.worker and self.worker.isRunning():
            self.show_toast("Stopping automation")
            self.set_status("Stopping")
            self.worker.stop()

    def handle_worker_finished(self):
        self.browser_container.release()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def handle_worker_failed(self, message):
        self.append_log("error", f"Automation failed: {message}")
        self.show_toast("Automation failed")

    def embed_browser(self):
        QTimer.singleShot(900, self._try_embed_browser)

    def _try_embed_browser(self):
        if self.browser_container.try_embed():
            self.append_log("success", "Chrome embedded in the application.")
        else:
            self.append_log("warning", "Chrome could not be embedded. It will remain in its own window.")

    def handle_login_required(self):
        result = QMessageBox.information(
            self,
            "Login required",
            "Log in to Instagram in the Chrome view/window, complete 2FA if needed, then press OK.",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        self.worker.answer(result == QMessageBox.Ok)

    def handle_unfollow_prompt(self, username, index, total):
        result = QMessageBox.question(
            self,
            "Confirm unfollow",
            f"[{index}/{total}] Do you want to unfollow @{username}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        self.worker.answer(result == QMessageBox.Yes)

    def handle_cookie_cleanup_prompt(self):
        result = QMessageBox.warning(
            self,
            "Saved cookies",
            "Keeping cookies lets InstaFollow restore your Instagram session later.\n\n"
            "Security note: cookies can grant access to your session on this computer. "
            "Delete them on shared or untrusted devices.\n\n"
            "Delete saved Instagram cookies now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        self.worker.answer(result == QMessageBox.Yes)

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
        self.status_label.setText(status)
        color = {
            "Running": "#1F5130",
            "Idle": "#333333",
            "Stopped": "#65312D",
            "Stopping": "#6A521D",
        }.get(status, "#333333")
        self.status_label.setStyleSheet(f"background: {color};")

    def show_toast(self, message):
        self.toast.setText(message)
        QTimer.singleShot(3500, lambda: self.toast.setText(""))

    def open_logs_dialog(self):
        dialog = LogsDialog("\n".join(self.full_log_lines), self)
        dialog.exec()

    def _open_menu(self):
        menu = QMenu(self)
        open_logs = QAction("Open logs", self)
        open_logs.triggered.connect(self.open_logs_dialog)
        menu.addAction(open_logs)

        clear_output = QAction("Clear output", self)
        clear_output.triggered.connect(self.output.clear)
        menu.addAction(clear_output)

        menu.exec(self.mapToGlobal(self.rect().topRight()))

    def _restore_window(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        super().closeEvent(event)


class LogsDialog(QMessageBox):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detailed Logs")
        self.setIcon(QMessageBox.NoIcon)
        self.setStandardButtons(QMessageBox.Close)
        self.setMinimumSize(760, 520)

        self.text = text or self._read_log_file()
        self.editor = QTextEdit()
        self.editor.setObjectName("logs")
        self.editor.setReadOnly(True)
        self.editor.setPlainText(self.text)
        self.layout().addWidget(self.editor, 1, 0, 1, self.layout().columnCount())

        copy_button = self.addButton("Copy", QMessageBox.ActionRole)
        copy_button.clicked.connect(self.editor.selectAll)
        copy_button.clicked.connect(self.editor.copy)

        save_button = self.addButton("Export", QMessageBox.ActionRole)
        save_button.clicked.connect(self.export_logs)

    def _read_log_file(self):
        path = Path("log.txt")
        if not path.exists():
            return "No log file found."
        return path.read_text(encoding="utf-8", errors="replace")

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export logs", "instafollow-log.txt", "Text files (*.txt)")
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
