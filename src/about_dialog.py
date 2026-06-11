import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from src.i18n import t

def _app_icon():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    icon_path = base / "icon.ico"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()

_STYLE = """
QDialog {
    background-color: #0a0e18;
}
QLabel {
    color: #d8f0ff;
}
QPushButton {
    background-color: #111c30;
    color: #d8f0ff;
    border: 1px solid #1e2d48;
    border-radius: 6px;
    padding: 6px 18px;
    font-size: 12px;
}
QPushButton:hover { background-color: #1e2d48; }
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(t("about_title"))
        self.setWindowIcon(_app_icon())
        self.setFixedSize(400, 270)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(30, 24, 30, 20)

        title = QLabel("PolyQuest")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff;")
        root.addWidget(title)

        version = QLabel(t("about_version"))
        version.setStyleSheet("font-size: 11px; color: #5a7a9a;")
        root.addWidget(version)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #1e2d48; margin: 4px 0;")
        root.addWidget(sep)

        desc = QLabel(t("about_desc"))
        desc.setStyleSheet("font-size: 12px; color: #d8f0ff; line-height: 1.4;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        credits_lbl = QLabel(t("about_developed_by"))
        credits_lbl.setStyleSheet("font-size: 11px; color: #5a7a9a; margin-top: 8px;")
        root.addWidget(credits_lbl)

        authors = QLabel(t("about_authors"))
        authors.setStyleSheet("font-size: 13px; font-weight: bold; color: #34d399;")
        root.addWidget(authors)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #111c30; margin: 6px 0;")
        root.addWidget(sep2)

        tech = QLabel(t("about_tech"))
        tech.setStyleSheet("font-size: 10px; color: #5a7a9a;")
        tech.setWordWrap(True)
        root.addWidget(tech)

        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(t("about_btn_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)
