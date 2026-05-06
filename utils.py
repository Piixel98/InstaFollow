import logging
import random
import sys
import threading
import time
from contextlib import contextmanager


class Spinner:
    def __init__(self, message, interval=0.12):
        self.message = message
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread:
            return

        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, final_message=None):
        if not self._thread:
            return

        self._stop_event.set()
        self._thread.join()
        self._thread = None
        sys.stdout.write("\r" + " " * (len(self.message) + 8) + "\r")
        if final_message:
            user_success(final_message)
        sys.stdout.flush()

    def _spin(self):
        frames = ("|", "/", "-", "\\")
        index = 0

        while not self._stop_event.is_set():
            sys.stdout.write(f"\r{frames[index % len(frames)]} {self.message}")
            sys.stdout.flush()
            index += 1
            time.sleep(self.interval)


def setup_logging():
    logger = logging.getLogger("InstaFollow")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    file_handler = logging.FileHandler("log.txt", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(logging.Formatter("Error: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def user_info(message):
    print(message)


def user_success(message):
    print(f"[OK] {message}")


def user_warning(message):
    print(f"[!] {message}")


def user_error(message):
    print(f"[ERROR] {message}")


@contextmanager
def loading(message, done_message=None):
    spinner = Spinner(message)
    spinner.start()
    try:
        yield
    except Exception:
        spinner.stop()
        raise
    else:
        spinner.stop(done_message)


def wait_with_spinner(seconds, message="Esperando antes de continuar"):
    with loading(message):
        time.sleep(seconds)


def human_sleep(a=0.7, b=1.8):
    time.sleep(random.uniform(a, b))


def long_pause(message="Esperando unos segundos antes de continuar"):
    wait_with_spinner(random.uniform(3, 6), message)


def handle_cookie_consent(page, timeout_ms=5000):
    logger = logging.getLogger("InstaFollow")
    button_labels = (
        "Rechazar cookies opcionales",
        "Permitir todas las cookies",
        "Reject optional cookies",
        "Decline optional cookies",
        "Allow all cookies",
        "Only allow essential cookies",
    )

    for index, label in enumerate(button_labels):
        wait_ms = timeout_ms if index == 0 else 700

        try:
            button = page.get_by_role("button", name=label).first
            button.wait_for(state="visible", timeout=wait_ms)
            button.click(timeout=2000)
            logger.info("Cookie dialog closed with button: %s", label)
            human_sleep(0.4, 1.0)
            return True
        except Exception:
            continue

    logger.debug("Cookie dialog not found")
    return False
