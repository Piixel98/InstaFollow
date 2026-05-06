import logging
import sys
import ctypes
from ctypes import WINFUNCTYPE, c_int, c_long, c_longlong, create_unicode_buffer
from ctypes.wintypes import BOOL, DWORD, HWND, LPARAM

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QVBoxLayout

from browser import get_last_browser_identity

logger = logging.getLogger("InstaFollow")


class BrowserContainer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserViewport")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, False)
        self._embedded_hwnd = None
        self._embedder = WindowsChromeEmbedder(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    def try_embed(self, browser_pid=None, window_marker=None):
        if browser_pid is None and window_marker is None:
            browser_pid, window_marker = get_last_browser_identity()
        self._embedded_hwnd = self._embedder.embed(browser_pid, window_marker)
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

    def hide_unembedded(self):
        self._embedder.hide_unembedded()


class WindowsChromeEmbedder:
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_CHILD = 0x40000000
    WS_CLIPSIBLINGS = 0x04000000
    WS_CLIPCHILDREN = 0x02000000
    WS_POPUP = 0x80000000
    WS_VISIBLE = 0x10000000
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040
    SWP_HIDEWINDOW = 0x0080
    WS_EX_DLGMODALFRAME = 0x00000001
    WS_EX_CLIENTEDGE = 0x00000200
    WS_EX_WINDOWEDGE = 0x00000100
    WS_EX_APPWINDOW = 0x00040000

    def __init__(self, host):
        self.host = host
        self._original_parent = None
        self._original_style = None
        self._original_exstyle = None
        self.user32 = getattr(ctypes, "windll", None).user32 if hasattr(ctypes, "windll") else None
        if self.user32 is not None:
            self._configure_winapi()

    def embed(self, browser_pid=None, window_marker=None):
        if not sys.platform.startswith("win"):
            logger.info("Chrome embedding is only available on Windows", extra={"user_visible": False})
            return None
        if self.user32 is None:
            logger.warning("Windows API is not available for Chrome embedding", extra={"user_visible": False})
            return None

        hwnd = self._find_chrome_window(browser_pid, window_marker)
        if not hwnd:
            logger.warning(
                "Could not find Playwright Chrome window to embed",
                extra={"user_visible": False},
            )
            return None

        parent_hwnd = int(self.host.winId())
        self._original_parent = self.user32.GetParent(HWND(hwnd))
        self._original_style = self._get_window_long(hwnd)
        self._original_exstyle = self._get_window_long(hwnd, self.GWL_EXSTYLE)

        style = self._original_style
        style &= ~(self.WS_CAPTION | self.WS_THICKFRAME | self.WS_POPUP)
        style |= self.WS_CHILD | self.WS_VISIBLE | self.WS_CLIPSIBLINGS | self.WS_CLIPCHILDREN
        self._set_window_long(hwnd, style)

        exstyle = self._original_exstyle
        exstyle &= ~(self.WS_EX_APPWINDOW | self.WS_EX_WINDOWEDGE | self.WS_EX_CLIENTEDGE | self.WS_EX_DLGMODALFRAME)
        self._set_window_long(hwnd, exstyle, self.GWL_EXSTYLE)

        self.user32.SetParent(HWND(hwnd), HWND(parent_hwnd))
        self._apply_frame_change(hwnd)
        self.resize(hwnd)
        logger.info("Chrome window embedded in the application", extra={"user_visible": False})
        return hwnd

    def resize(self, hwnd):
        if not sys.platform.startswith("win"):
            return

        try:
            width = max(1, self.host.width())
            height = max(1, self.host.height())
            self.user32.MoveWindow(HWND(hwnd), 0, 0, width, height, True)
            self._apply_frame_change(hwnd)
        except Exception as exc:
            logger.debug("Could not resize embedded Chrome: %s", exc, exc_info=True, extra={"user_visible": False})

    def release(self, hwnd):
        if not sys.platform.startswith("win"):
            return

        try:
            if self._original_parent is not None:
                self.user32.SetParent(HWND(hwnd), HWND(self._original_parent))
            if self._original_style is not None:
                self._set_window_long(hwnd, self._original_style)
            if self._original_exstyle is not None:
                self._set_window_long(hwnd, self._original_exstyle, self.GWL_EXSTYLE)
            if self._original_style is not None or self._original_exstyle is not None:
                self._apply_frame_change(hwnd)
        except Exception as exc:
            logger.debug("Could not release embedded Chrome: %s", exc, exc_info=True, extra={"user_visible": False})

    def hide_unembedded(self):
        if not sys.platform.startswith("win") or self.user32 is None:
            return

        browser_pid, window_marker = get_last_browser_identity()
        hwnd = self._find_chrome_window(browser_pid, window_marker)
        if hwnd:
            self.user32.SetWindowPos(
                HWND(hwnd),
                HWND(0),
                -32000,
                -32000,
                1,
                1,
                self.SWP_NOZORDER | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED | self.SWP_HIDEWINDOW,
            )

    def _find_chrome_window(self, browser_pid=None, window_marker=None):
        candidates = []

        def callback(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd):
                return True

            length = self.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buffer = create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if not title:
                return True

            window_pid = self._get_window_pid(hwnd)
            if browser_pid is not None and window_pid != browser_pid:
                return True

            if window_marker and window_marker in title:
                candidates.insert(0, hwnd)
                return True

            if browser_pid is not None and window_pid == browser_pid:
                candidates.append(hwnd)
            return True

        enum_proc = WINFUNCTYPE(BOOL, HWND, LPARAM)(callback)
        self.user32.EnumWindows(enum_proc, 0)
        return candidates[0] if candidates else None

    def _get_window_pid(self, hwnd):
        pid = DWORD()
        self.user32.GetWindowThreadProcessId(HWND(hwnd), ctypes.byref(pid))
        return int(pid.value)

    def _apply_frame_change(self, hwnd):
        self.user32.SetWindowPos(
            HWND(hwnd),
            HWND(0),
            0,
            0,
            max(1, self.host.width()),
            max(1, self.host.height()),
            self.SWP_NOZORDER | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED | self.SWP_SHOWWINDOW,
        )

    def _get_window_long(self, hwnd, index=None):
        index = self.GWL_STYLE if index is None else index
        if sys.maxsize > 2**32:
            return self.user32.GetWindowLongPtrW(HWND(hwnd), index)
        return self.user32.GetWindowLongW(HWND(hwnd), index)

    def _set_window_long(self, hwnd, style, index=None):
        index = self.GWL_STYLE if index is None else index
        if sys.maxsize > 2**32:
            return self.user32.SetWindowLongPtrW(HWND(hwnd), index, c_longlong(style))
        return self.user32.SetWindowLongW(HWND(hwnd), index, c_long(style))

    def _configure_winapi(self):
        self.user32.GetParent.argtypes = [HWND]
        self.user32.GetParent.restype = HWND
        self.user32.SetParent.argtypes = [HWND, HWND]
        self.user32.SetParent.restype = HWND
        self.user32.IsWindowVisible.argtypes = [HWND]
        self.user32.IsWindowVisible.restype = BOOL
        self.user32.GetWindowTextLengthW.argtypes = [HWND]
        self.user32.GetWindowTextLengthW.restype = c_int
        self.user32.GetWindowTextW.argtypes = [HWND, ctypes.c_wchar_p, c_int]
        self.user32.GetWindowTextW.restype = c_int
        self.user32.MoveWindow.argtypes = [HWND, c_int, c_int, c_int, c_int, BOOL]
        self.user32.MoveWindow.restype = BOOL
        self.user32.SetWindowPos.argtypes = [HWND, HWND, c_int, c_int, c_int, c_int, c_int]
        self.user32.SetWindowPos.restype = BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(DWORD)]
        self.user32.GetWindowThreadProcessId.restype = DWORD
        if sys.maxsize > 2**32:
            self.user32.GetWindowLongPtrW.argtypes = [HWND, c_int]
            self.user32.GetWindowLongPtrW.restype = c_longlong
            self.user32.SetWindowLongPtrW.argtypes = [HWND, c_int, c_longlong]
            self.user32.SetWindowLongPtrW.restype = c_longlong
        else:
            self.user32.GetWindowLongW.argtypes = [HWND, c_int]
            self.user32.GetWindowLongW.restype = c_long
            self.user32.SetWindowLongW.argtypes = [HWND, c_int, c_long]
            self.user32.SetWindowLongW.restype = c_long
