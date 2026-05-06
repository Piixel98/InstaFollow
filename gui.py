import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def resource_path(relative_path):
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base_path / relative_path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("InstaFollow")
    app.setOrganizationName("InstaFollow")
    app.setWindowIcon(QIcon(resource_path("assets/instafollow.ico")))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
