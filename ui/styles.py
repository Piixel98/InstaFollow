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
QFrame#statsPanel {
    background: #2A2A2A;
    border: 1px solid #3A3A3A;
    border-radius: 14px;
}

QFrame#browserViewport {
    background: #171717;
    border: 1px solid #343434;
    border-radius: 12px;
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
QPushButton#secondaryButton {
    background: #333333;
    color: #EAEAEA;
}

QPushButton#logsButton:hover,
QPushButton#secondaryButton:hover {
    background: #3E3E3E;
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
