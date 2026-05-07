APP_STYLE = """
QMainWindow {
    background: #101214;
}

QWidget {
    color: #E8ECEF;
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #3C8B6D;
    selection-color: #F4F7F5;
}

QFrame#shell {
    background: #171A1D;
    border: 1px solid #282E33;
    border-radius: 16px;
}

QLabel#title {
    color: #F1F5F2;
    font-size: 24px;
    font-weight: 750;
}

QLabel#sectionTitle {
    color: #C9D0D5;
    font-size: 12px;
    font-weight: 700;
}

QFrame#browserPanel,
QFrame#outputPanel,
QFrame#statsPanel,
QFrame#sessionForm {
    background: #1D2125;
    border: 1px solid #30363C;
    border-radius: 12px;
}

QFrame#credentialCard {
    background: #15181B;
    border: 1px solid #2B3238;
    border-radius: 10px;
}

QFrame#credentialCard[locked="true"] {
    background: #18231E;
    border: 1px solid #3E765B;
}

QFrame#credentialCard[warning="true"] {
    background: #211F18;
    border: 1px solid #7A6540;
}

QFrame#statBlock {
    background: #15181B;
    border: 1px solid #2A3036;
    border-radius: 10px;
}

QFrame#browserViewport {
    background: #0D0F11;
    border: none;
    border-radius: 0px;
    margin: 0px;
    padding: 0px;
}

QTextEdit#output,
QTextEdit#logs {
    background: #111417;
    border: 1px solid #2B3238;
    border-radius: 10px;
    color: #E4E8EB;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 10px;
}

QTextEdit#output:focus,
QTextEdit#logs:focus {
    border: 1px solid #3E765B;
}

QPushButton {
    background: #2A3036;
    color: #EEF2F0;
    border: 1px solid #394149;
    border-radius: 9px;
    padding: 9px 15px;
    font-weight: 650;
    min-height: 18px;
    min-width: 0px;
}

QPushButton:hover {
    background: #333A42;
    border-color: #48525C;
}

QPushButton:pressed {
    background: #23292F;
    border-color: #3E765B;
}

QPushButton:focus {
    border: 1px solid #5FAF86;
}

QPushButton:disabled {
    background: #20252A;
    border-color: #2B3137;
    color: #77818A;
}

QPushButton#menuButton {
    background: #20252A;
    color: #B9C2C8;
    border: 1px solid #303841;
    border-radius: 10px;
    padding: 7px 9px;
    min-width: 36px;
    min-height: 24px;
}

QPushButton#menuButton:hover {
    background: #2B3238;
    border-color: #48525C;
}

QPushButton#menuButton:pressed {
    background: #18231E;
    border-color: #5FAF86;
}

QFrame#processSwitch {
    background: #111417;
    border: 1px solid #303840;
    border-radius: 11px;
}

QPushButton#processButton {
    background: transparent;
    color: #AEB8BF;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 13px;
    font-weight: 700;
    min-height: 20px;
}

QPushButton#processButton:hover {
    background: #20262B;
    color: #E8ECEF;
    border-color: #2F3840;
}

QPushButton#processButton:focus {
    border: 1px solid #5FAF86;
}

QPushButton#processButton[selected="true"] {
    background: #2A4338;
    color: #F4F7F5;
    border: 1px solid #4EA37F;
}

QPushButton#processButton[selected="true"]:hover {
    background: #315143;
    border-color: #5FAF86;
}

QPushButton#processButton:disabled {
    background: transparent;
    color: #69737B;
    border-color: transparent;
}

QPushButton#startButton {
    background: #3C8B6D;
    border: 1px solid #4EA37F;
    color: #F4F7F5;
}

QPushButton#startButton:hover {
    background: #459A79;
}

QPushButton#startButton:pressed {
    background: #33785E;
}

QPushButton#startButton:disabled {
    background: #23352E;
    border-color: #2F4D40;
    color: #82948B;
}

QPushButton#stopButton {
    background: #7E3F3A;
    border: 1px solid #9E514A;
    color: #F7ECEB;
}

QPushButton#stopButton:hover {
    background: #914943;
}

QPushButton#stopButton:pressed {
    background: #6D3632;
}

QPushButton#logsButton,
QPushButton#secondaryButton,
QPushButton#toggleButton,
QPushButton#ghostButton {
    background: #23292F;
    color: #E4E9E7;
    border: 1px solid #343C44;
}

QPushButton#toggleButton {
    border-radius: 999px;
    padding: 8px 13px;
}

QPushButton#toggleButton[active="true"] {
    background: #18231E;
    color: #F4F7F5;
    border: 1px solid #4EA37F;
}

QPushButton#toggleButton[active="true"]:hover {
    background: #20382F;
    border-color: #5FAF86;
}

QPushButton#logsButton:hover,
QPushButton#secondaryButton:hover,
QPushButton#toggleButton:hover,
QPushButton#ghostButton:hover {
    background: #2C333A;
    border-color: #454F59;
}

QPushButton#ghostButton {
    background: transparent;
}

QPushButton#iconButton {
    background: #20252A;
    color: #E8ECEF;
    border: 1px solid #323A42;
    border-radius: 8px;
    padding: 8px 10px;
    min-width: 32px;
}

QPushButton#iconButton:hover {
    background: #2B3238;
}

QLineEdit {
    background: #111417;
    border: 1px solid #303840;
    border-radius: 8px;
    color: #EEF2F0;
    padding: 9px 11px;
    min-width: 0px;
}

QLineEdit:hover {
    border-color: #3F4851;
}

QLineEdit:focus {
    border: 1px solid #5FAF86;
    background: #12171A;
}

QLineEdit:disabled {
    color: #8C969E;
    background: #1A1E22;
    border-color: #2B3238;
}

QComboBox {
    background: #111417;
    border: 1px solid #303840;
    border-radius: 8px;
    color: #EEF2F0;
    padding: 8px 11px;
    min-height: 20px;
}

QComboBox:hover {
    border-color: #3F4851;
}

QComboBox:focus {
    border: 1px solid #5FAF86;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox QAbstractItemView {
    background: #1B1F23;
    border: 1px solid #343C44;
    border-radius: 8px;
    color: #E8ECEF;
    selection-background-color: #28342F;
    selection-color: #F4F7F5;
    padding: 4px;
}

QLabel#statusPill,
QLabel#sessionBadge {
    border-radius: 10px;
    padding: 6px 10px;
    background: #262C32;
    color: #D8E0DD;
    font-size: 11px;
    font-weight: 750;
}

QLabel#statValue {
    color: #F3F6F4;
    font-size: 22px;
    font-weight: 760;
}

QLabel#statLabel {
    color: #9EA9B1;
    font-size: 11px;
    font-weight: 600;
}

QLabel#toast {
    color: #AAB4BA;
    font-size: 12px;
}

QLabel#sessionStatus {
    color: #AAB4BA;
    font-size: 12px;
}

QProgressBar {
    height: 10px;
    background: #111417;
    border: 1px solid #2B3238;
    border-radius: 5px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background: #3C8B6D;
    border-radius: 5px;
}

QProgressBar[running="true"] {
    background: #101614;
    border: 1px solid #3E765B;
}

QProgressBar[running="true"]::chunk {
    background: #5FE0A2;
    border-radius: 5px;
}

QMenu {
    background: #1B1F23;
    border: 1px solid #343C44;
    border-radius: 10px;
    padding: 7px;
}

QMenu::item {
    color: #E8ECEF;
    padding: 9px 28px 9px 10px;
    border-radius: 7px;
}

QMenu::icon {
    padding-left: 6px;
}

QMenu::separator {
    height: 1px;
    background: #303840;
    margin: 6px 8px;
}

QMenu::item:selected {
    background: #24342E;
    color: #F4F7F5;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea#sessionScroll {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    background: #15181B;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #3B444D;
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #4A555F;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QCheckBox {
    color: #DDE3E0;
    spacing: 9px;
    padding: 7px 8px;
    border-radius: 7px;
}

QCheckBox:hover {
    background: #20262B;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #46515B;
    background: #111417;
}

QCheckBox::indicator:checked {
    background: #3C8B6D;
    border: 1px solid #5FAF86;
}

QCheckBox::indicator:checked:hover {
    background: #459A79;
}
"""
