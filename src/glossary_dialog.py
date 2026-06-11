import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
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
    font-size: 13px;
}
QLineEdit {
    background-color: #111c30;
    color: #d8f0ff;
    border: 1px solid #1e2d48;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
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
QPushButton#add_btn {
    background-color: #9b30ff;
    border-color: #9b30ff;
    color: #ffffff;
}
QPushButton#add_btn:hover { background-color: #7a18e0; }
QPushButton#remove_btn {
    background-color: #1e2d48;
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
}
QPushButton#remove_btn:hover { background-color: #f87171; color: #0a0e18; }
QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #070c15;
    border: none;
}
QScrollArea {
    border: 1px solid #111c30;
    border-radius: 6px;
}
QScrollBar:vertical {
    background: #070c15;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #1e2d48;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


class GlossaryDialog(QDialog):
    def __init__(self, full_config: dict, config_path: Path, parent=None):
        super().__init__(parent)
        self._full_config = full_config
        self._config_path = config_path

        self._active_name = full_config.get("activeProfile", "")
        profiles = full_config.get("profiles", {})
        self._profile = profiles.get(self._active_name, {})
        self._glossary: list = list(self._profile.get("glossary", []))

        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        self.setWindowTitle(t("glossary_title"))
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(460, 420)
        self.resize(460, 520)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setSpacing(7)
        root.setContentsMargins(24, 20, 24, 18)

        # Titulo com nome do perfil
        title = QLabel(t("glossary_heading"))
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #00e5ff;")
        root.addWidget(title)

        if self._active_name:
            profile_hint = QLabel(self._active_name)
            profile_hint.setStyleSheet("font-size: 11px; color: #5a7a9a;")
            root.addWidget(profile_hint)

        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.Shape.HLine)
        sep_top.setStyleSheet("color: #1e2d48; margin-bottom: 2px;")
        root.addWidget(sep_top)

        # Formulario inline
        form_row = QHBoxLayout()
        form_row.setSpacing(6)

        self._input_original = QLineEdit()
        self._input_original.setPlaceholderText(t("glossary_original"))
        form_row.addWidget(self._input_original, 1)

        self._input_translation = QLineEdit()
        self._input_translation.setPlaceholderText(t("glossary_translation"))
        form_row.addWidget(self._input_translation, 1)

        add_btn = QPushButton(t("glossary_add"))
        add_btn.setObjectName("add_btn")
        add_btn.setMinimumWidth(90)
        add_btn.clicked.connect(self._add_term)
        form_row.addWidget(add_btn)

        root.addLayout(form_row)

        # Busca
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("glossary_search"))
        self._search.textChanged.connect(self._refresh_list)
        root.addWidget(self._search)

        # Header da lista
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 8, 0)
        lbl_orig = QLabel(t("glossary_original"))
        lbl_orig.setStyleSheet("font-size: 10px; font-weight: bold; color: #00e5ff;")
        header.addWidget(lbl_orig, 1)
        lbl_trad = QLabel(t("glossary_translation"))
        lbl_trad.setStyleSheet("font-size: 10px; font-weight: bold; color: #00e5ff;")
        header.addWidget(lbl_trad, 1)
        header.addSpacing(68)
        root.addLayout(header)

        # Lista com scroll
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_widget = QWidget()
        self._list_widget.setObjectName("list_inner")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setSpacing(3)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_widget)

        root.addWidget(self._scroll, 1)

        # Footer: contador + botao fechar
        footer_row = QHBoxLayout()
        self._count_label = QLabel()
        self._count_label.setStyleSheet("font-size: 11px; color: #5a7a9a;")
        footer_row.addWidget(self._count_label)
        footer_row.addStretch()

        close_btn = QPushButton(t("glossary_btn_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        footer_row.addWidget(close_btn)

        root.addLayout(footer_row)

    def _add_term(self):
        original = self._input_original.text().strip()
        translation = self._input_translation.text().strip()
        if not original or not translation:
            return
        self._glossary.append({"original": original, "translation": translation})
        self._input_original.clear()
        self._input_translation.clear()
        self._input_original.setFocus()
        self._save()
        self._refresh_list()

    def _remove_term(self, index: int):
        if 0 <= index < len(self._glossary):
            self._glossary.pop(index)
            self._save()
            self._refresh_list()

    def _save(self):
        self._profile["glossary"] = self._glossary
        profiles = self._full_config.get("profiles", {})
        profiles[self._active_name] = self._profile
        self._full_config["profiles"] = profiles
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._full_config, f, indent=4, ensure_ascii=False)

    def _refresh_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().strip().lower()

        for i, entry in enumerate(self._glossary):
            orig = entry.get("original", "")
            trad = entry.get("translation", "")

            if query and query not in orig.lower() and query not in trad.lower():
                continue

            row = QWidget()
            row.setStyleSheet(
                "QWidget { background-color: #111c30; border-radius: 4px; }"
            )
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 4, 8, 4)
            row_lay.setSpacing(6)

            lbl_o = QLabel(orig)
            lbl_o.setStyleSheet("color: #d8f0ff; font-size: 12px;")
            lbl_o.setWordWrap(True)
            row_lay.addWidget(lbl_o, 1)

            lbl_t = QLabel(trad)
            lbl_t.setStyleSheet("color: #34d399; font-size: 12px; font-weight: bold;")
            lbl_t.setWordWrap(True)
            row_lay.addWidget(lbl_t, 1)

            rm_btn = QPushButton(t("glossary_remove"))
            rm_btn.setObjectName("remove_btn")
            rm_btn.setFixedWidth(68)
            rm_btn.clicked.connect(lambda _, idx=i: self._remove_term(idx))
            row_lay.addWidget(rm_btn)

            self._list_layout.addWidget(row)

        self._count_label.setText(t("glossary_count", count=len(self._glossary)))
