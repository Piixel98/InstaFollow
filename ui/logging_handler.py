import logging

from PySide6.QtCore import QObject, Signal


class QtLogEmitter(QObject):
    message = Signal(str, str)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.emitter = QtLogEmitter()

    def emit(self, record):
        try:
            if getattr(record, "user_visible", True) is False:
                return
            message = self.format(record)
            self.emitter.message.emit(record.levelname.lower(), message)
        except Exception:
            self.handleError(record)
