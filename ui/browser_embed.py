import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QVBoxLayout

logger = logging.getLogger("InstaFollow")


class BrowserContainer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserViewport")
        self._embedded_hwnd = None
        self._embedder = WindowsChromeEmbedder(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    def try_embed(self):
        self._embedded_hwnd = self._embedder.embed()
        if self._embedded_hwnd:
            QTimer.singleShot(100, self.resize_embedded)
            return True
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_embedded()

    def resize_embedded(self):
        if self._embedded_hwnd:
            self._embedder.resize(self._embedded_hwnd)

    def release(self):
        if self._embedded_hwnd:
            self._embedder.release(self._embedded_hwnd)
            self._embedded_hwnd = None


class WindowsChromeEmbedder:
    def __init__(self, host):
        self.host = host
        self._original_parent = None

    def embed(self):
        if not sys.platform.startswith("win"):
            logger.info("Chrome embedding is only available on Windows")
            return None

        try:
            import win32con
            import win32gui
        except ImportError:
            logger.warning("Install pywin32 to embed Chrome inside the Qt window")
            return None

        hwnd = self._find_chrome_window(win32gui)
        if not hwnd:
            logger.warning("Could not find Chrome window to embed")
            return None

        parent_hwnd = int(self.host.winId())
        self._original_parent = win32gui.GetParent(hwnd)

        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style = style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME
        style = style | win32con.WS_CHILD
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetParent(hwnd, parent_hwnd)
        self.resize(hwnd)
        logger.info("Chrome window embedded in the application")
        return hwnd

    def resize(self, hwnd):
        if not sys.platform.startswith("win"):
            return

        try:
            import win32gui

            rect = self.host.rect()
            win32gui.MoveWindow(hwnd, 0, 0, rect.width(), rect.height(), True)
        except Exception as exc:
            logger.debug("Could not resize embedded Chrome: %s", exc)

    def release(self, hwnd):
        if not sys.platform.startswith("win"):
            return

        try:
            import win32con
            import win32gui

            if self._original_parent is not None:
                win32gui.SetParent(hwnd, self._original_parent)
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            style = style | win32con.WS_CAPTION | win32con.WS_THICKFRAME
            style = style & ~win32con.WS_CHILD
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        except Exception as exc:
            logger.debug("Could not release embedded Chrome: %s", exc)

    def _find_chrome_window(self, win32gui):
        candidates = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return

            title = win32gui.GetWindowText(hwnd)
            if not title:
                return

            normalized = title.lower()
            if "instagram" in normalized or "chrome" in normalized or "chromium" in normalized:
                candidates.append(hwnd)

        win32gui.EnumWindows(callback, None)
        return candidates[-1] if candidates else None
