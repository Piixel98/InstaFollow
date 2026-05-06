APP_STYLE = """
QMainWindow {
    background: #1E1E1E;
}

QWidget {
    color: #EAEAEA;
    font-family: "Segoe UI";
    font-size: 13px;
}

QFrame#shell {
    background: #242424;
    border: 1px solid #3A3A3A;
    border-radius: 18px;
}

QLabel#title {
    color: #F5F5F5;
    font-size: 22px;
    font-weight: 700;
}

QLabel#sectionTitle {
    color: #CFCFCF;
    font-size: 13px;
    font-weight: 600;
}

QFrame#browserPanel,
QFrame#outputPanel,
QFrame#statsPanel,
QFrame#sessionForm {
    background: #2A2A2A;
    border: 1px solid #3A3A3A;
    border-radius: 14px;
}

QFrame#credentialCard {
    background: #202020;
    border: 1px solid #383838;
    border-radius: 10px;
}

QFrame#credentialCard[locked="true"] {
    border: 1px solid #4CAF50;
    background: #1E2A21;
}

QFrame#credentialCard[warning="true"] {
    border: 1px solid #6A521D;
    background: #282419;
}

QFrame#browserViewport {
    background: #171717;
    border: none;
    border-radius: 0px;
    margin: 0px;
    padding: 0px;
}

QTextEdit#output,
QTextEdit#logs {
    background: #181818;
    border: 1px solid #333333;
    border-radius: 10px;
    color: #EAEAEA;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 10px;
}

QPushButton {
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-weight: 600;
}

QPushButton#menuButton {
    background: transparent;
    color: #BDBDBD;
    font-size: 20px;
    padding: 4px 10px;
}

QPushButton#menuButton:hover {
    background: #303030;
}

QPushButton#startButton {
    background: #4CAF50;
    color: white;
}

QPushButton#startButton:hover {
    background: #5CBD60;
}

QPushButton#startButton:disabled {
    background: #365E38;
    color: #A7A7A7;
}

QPushButton#stopButton {
    background: #F44336;
    color: white;
}

QPushButton#stopButton:hover {
    background: #FF584D;
}

QPushButton#stopButton:disabled {
    background: #65312D;
    color: #A7A7A7;
}

QPushButton#logsButton,
QPushButton#secondaryButton,
QPushButton#toggleButton,
QPushButton#ghostButton {
    background: #333333;
    color: #EAEAEA;
}

QPushButton#logsButton:hover,
QPushButton#secondaryButton:hover,
QPushButton#toggleButton:hover,
QPushButton#ghostButton:hover {
    background: #3E3E3E;
}

QPushButton#iconButton {
    background: #2D2D2D;
    color: #EAEAEA;
    border-radius: 8px;
    padding: 8px 10px;
    min-width: 32px;
}

QPushButton#iconButton:hover {
    background: #3A3A3A;
}

QLineEdit {
    background: #181818;
    border: 1px solid #333333;
    border-radius: 8px;
    color: #EAEAEA;
    padding: 9px 10px;
}

QLineEdit:disabled {
    color: #A7A7A7;
    background: #202020;
}

QLabel#statusPill {
    border-radius: 10px;
    padding: 6px 10px;
    background: #333333;
    color: #DADADA;
    font-weight: 600;
}

QLabel#statValue {
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 700;
}

QLabel#statLabel {
    color: #AFAFAF;
    font-size: 11px;
}

QLabel#sessionBadge {
    border-radius: 10px;
    padding: 6px 10px;
    background: #333333;
    color: #DADADA;
    font-weight: 600;
}

QProgressBar {
    height: 8px;
    background: #1D1D1D;
    border: 1px solid #333333;
    border-radius: 4px;
    text-align: center;
}

QProgressBar::chunk {
    background: #3B82F6;
    border-radius: 4px;
}
"""
