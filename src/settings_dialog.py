import json
from pathlib import Path
from threading import Thread

import keyboard
import mss
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIntValidator
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from src.i18n import t, UI_LANGUAGES
from src.license import is_premium, activate, deactivate, get_license_info

def _app_icon():
    """Retorna o QIcon do app a partir de icon.ico."""
    import sys
    from PyQt6.QtGui import QIcon
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
    font-weight: bold;
    letter-spacing: 1px;
}
QLineEdit:disabled {
    color: #1e2d48;
    background-color: #070c15;
    border-color: #111c30;
}
QComboBox {
    background-color: #111c30;
    color: #d8f0ff;
    border: 1px solid #1e2d48;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #111c30;
    color: #d8f0ff;
    selection-background-color: #9b30ff;
    outline: none;
}
QCheckBox {
    color: #d8f0ff;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #1e2d48;
    border-radius: 3px;
    background-color: #111c30;
}
QCheckBox::indicator:checked {
    background-color: #9b30ff;
    border-color: #9b30ff;
}
QPushButton {
    background-color: #111c30;
    color: #d8f0ff;
    border: 1px solid #1e2d48;
    border-radius: 6px;
    padding: 6px 18px;
    font-size: 12px;
}
QPushButton:hover  { background-color: #1e2d48; }
QPushButton:disabled { color: #5a7a9a; }
QPushButton#save_btn {
    background-color: #9b30ff;
    border-color: #9b30ff;
    color: #ffffff;
}
QPushButton#save_btn:hover { background-color: #7a18e0; }
QPushButton#delete_btn:hover { background-color: #f87171; color: #0a0e18; }
QSpinBox {
    background-color: #111c30;
    color: #d8f0ff;
    border: 1px solid #1e2d48;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
}
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: #1e2d48; border-radius: 3px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #2a3a5c; }
QSlider::groove:horizontal {
    height: 6px;
    background: #111c30;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -4px 0;
    background: #9b30ff;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #7a18e0; }
QTabWidget::pane {
    border: 1px solid #1e2d48;
    border-radius: 6px;
    background: transparent;
    top: -1px;
}
QTabBar::tab {
    background: #111c30;
    color: #5a7a9a;
    padding: 7px 20px;
    border: 1px solid #1e2d48;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: bold;
}
QTabBar::tab:selected { background: #1e2d48; color: #00e5ff; }
QTabBar::tab:!selected:hover { color: #d8f0ff; }
"""

_SOURCE_LANGUAGES = [
    "auto",
    "en", "pt", "es", "fr", "de", "it",
    "nl", "pl", "ru", "tr", "ja", "zh", "ko", "ar", "vi",
]

_TARGET_LANGUAGES = [
    "pt", "en", "es", "fr", "de", "it",
    "nl", "pl", "ru", "tr", "ja", "zh", "ko", "ar", "vi",
]

_THEMES = ["dark", "light", "green", "amber", "custom"]

_MODES = ["fast", "balanced", "precise"]

_DEFAULT_PROFILE = {
    "hotkey": "*",
    "region_hotkey": None,
    "source_language": "en",
    "target_language": "pt",
    "translation_mode": "balanced",
    "font_size": 0,
    "background_opacity": 210,
    "theme": "dark",
    "monitor": None,
    "source_resolution": None,
    "continuous_mode": False,
    "continuous_interval": 3,
    "glossary": [],
}


def _section_label(text: str, premium: bool = False) -> QLabel:
    display = f"{text}   ★ PRO" if premium else text
    color = "#00e5ff"
    extra = ""
    if premium:
        extra = (
            "QLabel { font-size: 10px; font-weight: bold; margin-top: 4px; }"
        )
    lbl = QLabel(display)
    lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {color}; margin-top: 4px;")
    return lbl


def _premium_tag() -> QLabel:
    """Cria uma tag 'PRO' pequena para colocar ao lado de widgets."""
    lbl = QLabel("PRO")
    lbl.setFixedWidth(32)
    lbl.setStyleSheet(
        "font-size: 9px; font-weight: 900; color: #9b30ff; "
        "background: rgba(155, 48, 255, 0.15); border: 1px solid rgba(155, 48, 255, 0.3); "
        "border-radius: 3px; padding: 1px 4px; letter-spacing: .05em;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("color: #111c30;")
    return sep


class SettingsDialog(QDialog):
    _HEIGHT_BASE = 700
    _HEIGHT_CUSTOM = 700
    _license_result = pyqtSignal(dict)

    def __init__(self, full_config: dict, config_path: Path, parent=None):
        super().__init__(parent)
        self._full_config = full_config
        self._config_path = config_path
        self._profiles = full_config.get("profiles", {})
        self._active_name = full_config.get("activeProfile", "")
        self._config = dict(self._profiles.get(self._active_name, _DEFAULT_PROFILE))
        self._new_hotkey = self._config.get("hotkey", "*")
        self._new_region_hotkey = self._config.get("region_hotkey")
        self._captured_key: str | None = None
        self._capture_target = "main"  # qual hotkey está sendo capturada

        self._capture_timer = QTimer()
        self._capture_timer.timeout.connect(self._check_capture)

        self._license_result.connect(self._on_license_result)

        self._loading = False
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        self.setWindowTitle(t("settings_title"))
        self.setWindowIcon(_app_icon())
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_STYLE)

        # Abas: todos os campos visíveis sem rolagem, janela compacta
        self.setFixedWidth(480)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 8)
        outer.setSpacing(6)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        def _make_tab(title_key: str) -> QVBoxLayout:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setSpacing(7)
            lay.setContentsMargins(16, 14, 16, 12)
            self._tabs.addTab(page, t(title_key))
            return lay

        tab_general = _make_tab("settings_tab_general")
        tab_capture = _make_tab("settings_tab_translation")
        tab_appear = _make_tab("settings_tab_appearance")

        root = tab_general

        # ── Seção: Licença ────────────────────────────────────────────
        root.addWidget(_section_label(t("license_section")))

        self._premium = is_premium()

        row_lic_status = QHBoxLayout()
        row_lic_status.setSpacing(8)
        lbl_lic = QLabel(t("license_status_label"))
        lbl_lic.setFixedWidth(148)
        row_lic_status.addWidget(lbl_lic)

        self._lic_status = QLabel()
        self._update_license_status()
        row_lic_status.addWidget(self._lic_status, 1)
        root.addLayout(row_lic_status)

        row_lic_key = QHBoxLayout()
        row_lic_key.setSpacing(8)
        lbl_key_lic = QLabel(t("license_key_label"))
        lbl_key_lic.setFixedWidth(148)
        row_lic_key.addWidget(lbl_key_lic)

        self._lic_input = QLineEdit()
        self._lic_input.setPlaceholderText(t("license_key_placeholder"))
        row_lic_key.addWidget(self._lic_input, 1)

        self._lic_btn = QPushButton()
        self._lic_btn.setFixedWidth(85)
        self._lic_btn.clicked.connect(self._on_license_action)
        row_lic_key.addWidget(self._lic_btn)
        root.addLayout(row_lic_key)

        self._lic_msg = QLabel("")
        self._lic_msg.setStyleSheet("font-size: 11px; color: #5a7a9a;")
        self._lic_msg.setWordWrap(True)
        root.addWidget(self._lic_msg)

        self._update_license_ui()

        root.addWidget(_separator())

        # ── Seção: Perfil do Jogo ─────────────────────────────────────
        root.addWidget(_section_label(t("profile_section"), premium=True))

        row_profile = QHBoxLayout()
        row_profile.setSpacing(6)
        lbl_profile = QLabel(t("profile_label"))
        lbl_profile.setFixedWidth(148)
        row_profile.addWidget(lbl_profile)

        self._profile_combo = QComboBox()
        for name in self._profiles:
            self._profile_combo.addItem(name, name)
        idx = self._profile_combo.findData(self._active_name)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        row_profile.addWidget(self._profile_combo, 1)

        self._new_profile_btn = QPushButton(f"  {t('profile_new')}  ")
        self._new_profile_btn.clicked.connect(self._new_profile)
        row_profile.addWidget(self._new_profile_btn)

        self._del_btn = QPushButton(f"  {t('profile_delete')}  ")
        self._del_btn.setObjectName("delete_btn")
        self._del_btn.setEnabled(len(self._profiles) > 1)
        self._del_btn.clicked.connect(self._delete_profile)
        row_profile.addWidget(self._del_btn)

        root.addLayout(row_profile)

        # ═══ Aba: Tradução ═══
        root = tab_capture

        # ── Seção: Tecla de atalho ────────────────────────────────────
        root.addWidget(_section_label(t("settings_section_hotkey")))

        row_key = QHBoxLayout()
        row_key.setSpacing(8)
        lbl_key = QLabel(t("settings_hotkey_label"))
        lbl_key.setFixedWidth(148)
        row_key.addWidget(lbl_key)

        self._display = QLineEdit(self._new_hotkey)
        self._display.setReadOnly(True)
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setMinimumWidth(90)
        row_key.addWidget(self._display, 1)

        self._capture_btn = QPushButton(t("settings_hotkey_change"))
        self._capture_btn.setFixedWidth(70)
        self._capture_btn.setStyleSheet("padding: 6px 6px;")
        self._capture_btn.clicked.connect(lambda: self._start_capture("main"))
        row_key.addWidget(self._capture_btn)
        root.addLayout(row_key)

        # Hotkey da tradução por região
        row_region = QHBoxLayout()
        row_region.setSpacing(8)
        lbl_region = QLabel(t("settings_region_hotkey_label"))
        lbl_region.setFixedWidth(148)
        lbl_region.setToolTip(t("settings_region_hotkey_tip"))
        row_region.addWidget(lbl_region)

        self._region_display = QLineEdit(self._new_region_hotkey or "—")
        self._region_display.setReadOnly(True)
        self._region_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._region_display.setMinimumWidth(90)
        self._region_display.setToolTip(t("settings_region_hotkey_tip"))
        row_region.addWidget(self._region_display, 1)

        self._region_capture_btn = QPushButton(t("settings_hotkey_change"))
        self._region_capture_btn.setFixedWidth(70)
        self._region_capture_btn.setStyleSheet("padding: 6px 6px;")
        self._region_capture_btn.clicked.connect(lambda: self._start_capture("region"))
        row_region.addWidget(self._region_capture_btn)

        self._region_clear_btn = QPushButton(t("settings_btn_clear"))
        self._region_clear_btn.setFixedWidth(64)
        self._region_clear_btn.setStyleSheet("padding: 6px 6px;")
        self._region_clear_btn.clicked.connect(self._clear_region_hotkey)
        row_region.addWidget(self._region_clear_btn)
        root.addLayout(row_region)

        self._info = QLabel(t("settings_hotkey_hint"))
        self._info.setStyleSheet("color: #5a7a9a; font-size: 11px;")
        root.addWidget(self._info)

        root.addWidget(_separator())

        # ── Seção: Captura ────────────────────────────────────────────
        root.addWidget(_section_label(t("settings_section_capture")))

        row_mon = QHBoxLayout()
        row_mon.setSpacing(8)
        lbl_mon = QLabel(t("settings_monitor_label"))
        lbl_mon.setFixedWidth(148)
        row_mon.addWidget(lbl_mon)

        self._monitor_combo = QComboBox()
        self._monitor_combo.addItem(t("settings_monitor_auto"), None)
        try:
            with mss.mss() as sct:
                for i, m in enumerate(sct.monitors[1:], start=1):
                    self._monitor_combo.addItem(
                        t("settings_monitor_item", i=i, w=m["width"], h=m["height"]), i
                    )
        except Exception:
            pass

        row_mon.addWidget(self._monitor_combo, 1)
        root.addLayout(row_mon)

        row_res = QHBoxLayout()
        row_res.setSpacing(8)

        self._res_manual_check = QCheckBox(t("settings_resolution_label"))
        self._res_manual_check.setFixedWidth(148)
        row_res.addWidget(self._res_manual_check)

        self._res_w = QLineEdit("1920")
        self._res_w.setFixedWidth(68)
        self._res_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._res_w.setValidator(QIntValidator(1, 9999, self))
        row_res.addWidget(self._res_w)

        lbl_x = QLabel("×")
        lbl_x.setStyleSheet("color: #5a7a9a; font-size: 14px;")
        lbl_x.setFixedWidth(12)
        lbl_x.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_res.addWidget(lbl_x)

        self._res_h = QLineEdit("1080")
        self._res_h.setFixedWidth(68)
        self._res_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._res_h.setValidator(QIntValidator(1, 9999, self))
        row_res.addWidget(self._res_h)

        row_res.addStretch()
        root.addLayout(row_res)

        self._res_manual_check.toggled.connect(self._res_w.setEnabled)
        self._res_manual_check.toggled.connect(self._res_h.setEnabled)

        # Modo contínuo (PRO)
        row_cont = QHBoxLayout()
        row_cont.setSpacing(8)

        self._cont_check = QCheckBox(t("settings_continuous_check"))
        self._cont_check.setFixedWidth(148)
        self._cont_check.setToolTip(t("settings_continuous_tip"))
        row_cont.addWidget(self._cont_check)

        self._cont_interval = QSpinBox()
        self._cont_interval.setRange(1, 15)
        self._cont_interval.setSuffix(" s")
        self._cont_interval.setFixedWidth(68)
        self._cont_interval.setToolTip(t("settings_continuous_tip"))
        row_cont.addWidget(self._cont_interval)

        self._cont_pro_tag = _premium_tag()
        row_cont.addWidget(self._cont_pro_tag)
        row_cont.addStretch()
        root.addLayout(row_cont)

        self._cont_check.toggled.connect(self._cont_interval.setEnabled)

        root.addWidget(_separator())

        # ── Seção: Idiomas ────────────────────────────────────────────
        root.addWidget(_section_label(t("settings_section_languages")))

        row_src = QHBoxLayout()
        row_src.setSpacing(8)
        lbl_src = QLabel(t("settings_source_lang"))
        lbl_src.setFixedWidth(148)
        row_src.addWidget(lbl_src)
        self._src_lang_combo = QComboBox()
        for code in _SOURCE_LANGUAGES:
            self._src_lang_combo.addItem(t(f"lang_{code}"), code)
        row_src.addWidget(self._src_lang_combo, 1)
        root.addLayout(row_src)

        row_tgt = QHBoxLayout()
        row_tgt.setSpacing(8)
        lbl_tgt = QLabel(t("settings_target_lang"))
        lbl_tgt.setFixedWidth(148)
        row_tgt.addWidget(lbl_tgt)
        self._tgt_lang_combo = QComboBox()
        for code in _TARGET_LANGUAGES:
            self._tgt_lang_combo.addItem(t(f"lang_{code}"), code)
        row_tgt.addWidget(self._tgt_lang_combo, 1)
        root.addLayout(row_tgt)

        # ═══ Aba: Aparência ═══
        root = tab_appear

        # ── Seção: Aparência ──────────────────────────────────────────
        root.addWidget(_section_label(t("settings_section_appearance")))

        row_theme = QHBoxLayout()
        row_theme.setSpacing(8)
        lbl_theme = QLabel(t("settings_theme_label"))
        lbl_theme.setFixedWidth(148)
        row_theme.addWidget(lbl_theme)
        self._theme_combo = QComboBox()
        for code in _THEMES:
            self._theme_combo.addItem(t(f"theme_{code}"), code)
        row_theme.addWidget(self._theme_combo, 1)
        root.addLayout(row_theme)

        # ── Seção personalizar (colapsável) ──────────────────────────
        self._custom_section = QWidget()
        custom_lay = QVBoxLayout(self._custom_section)
        custom_lay.setContentsMargins(0, 4, 0, 4)
        custom_lay.setSpacing(6)

        self._custom_bg = "#000000"
        self._custom_fg = "#FFFFFF"
        self._custom_opacity = 70

        # Cor do fundo
        row_bg = QHBoxLayout()
        row_bg.setSpacing(8)
        lbl_bg = QLabel(t("custom_bg_color"))
        lbl_bg.setFixedWidth(148)
        row_bg.addWidget(lbl_bg)

        self._bg_swatch = QPushButton()
        self._bg_swatch.setFixedSize(28, 28)
        self._bg_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_swatch.clicked.connect(self._pick_bg_color)
        row_bg.addWidget(self._bg_swatch)

        self._bg_hex = QLineEdit(self._custom_bg)
        self._bg_hex.setFixedWidth(80)
        self._bg_hex.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg_hex.textChanged.connect(self._on_bg_hex_changed)
        row_bg.addWidget(self._bg_hex)
        row_bg.addStretch()
        custom_lay.addLayout(row_bg)

        # Cor do texto
        row_fg = QHBoxLayout()
        row_fg.setSpacing(8)
        lbl_fg = QLabel(t("custom_text_color"))
        lbl_fg.setFixedWidth(148)
        row_fg.addWidget(lbl_fg)

        self._fg_swatch = QPushButton()
        self._fg_swatch.setFixedSize(28, 28)
        self._fg_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fg_swatch.clicked.connect(self._pick_fg_color)
        row_fg.addWidget(self._fg_swatch)

        self._fg_hex = QLineEdit(self._custom_fg)
        self._fg_hex.setFixedWidth(80)
        self._fg_hex.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fg_hex.textChanged.connect(self._on_fg_hex_changed)
        row_fg.addWidget(self._fg_hex)
        row_fg.addStretch()
        custom_lay.addLayout(row_fg)

        # Opacidade
        row_opa = QHBoxLayout()
        row_opa.setSpacing(8)
        lbl_opa = QLabel(t("custom_opacity"))
        lbl_opa.setFixedWidth(148)
        row_opa.addWidget(lbl_opa)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.valueChanged.connect(self._update_custom_preview)
        row_opa.addWidget(self._opacity_slider, 1)

        self._opacity_label = QLabel("70%")
        self._opacity_label.setFixedWidth(36)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_opa.addWidget(self._opacity_label)
        custom_lay.addLayout(row_opa)

        # Prévia
        self._preview_label = QLabel(t("custom_preview"))
        self._preview_label.setFixedHeight(36)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("border-radius: 4px; font-size: 13px; font-weight: bold;")
        custom_lay.addWidget(self._preview_label)

        root.addWidget(self._custom_section)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        row_font = QHBoxLayout()
        row_font.setSpacing(8)
        lbl_font = QLabel(t("settings_font_size_label"))
        lbl_font.setFixedWidth(148)
        row_font.addWidget(lbl_font)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(-5, 15)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setFixedWidth(80)
        self._font_size_spin.valueChanged.connect(self._update_custom_preview)
        row_font.addWidget(self._font_size_spin)
        self._font_pro_tag = _premium_tag()
        row_font.addWidget(self._font_pro_tag)
        row_font.addStretch()
        root.addLayout(row_font)

        lbl_font_hint = QLabel(t("settings_font_size_hint"))
        lbl_font_hint.setStyleSheet("color: #5a7a9a; font-size: 11px;")
        root.addWidget(lbl_font_hint)

        row_mode = QHBoxLayout()
        row_mode.setSpacing(8)
        lbl_mode = QLabel(t("settings_mode_label"))
        lbl_mode.setFixedWidth(148)
        row_mode.addWidget(lbl_mode)
        self._mode_combo = QComboBox()
        for code in _MODES:
            self._mode_combo.addItem(t(f"mode_{code}"), code)
        row_mode.addWidget(self._mode_combo, 1)
        # Modo de tradução pertence à aba Tradução (após os idiomas)
        tab_capture.addLayout(row_mode)

        # ── Seção: Modo IA (PRO, BYOK — key global, fora dos perfis) ──
        tab_capture.addWidget(_separator())
        tab_capture.addWidget(_section_label(t("ai_section"), premium=True))

        ai_cfg = self._full_config.get("ai") or {}

        row_ai_check = QHBoxLayout()
        row_ai_check.setSpacing(8)
        self._ai_check = QCheckBox(t("ai_enable"))
        self._ai_check.setFixedWidth(148)
        row_ai_check.addWidget(self._ai_check)
        self._ai_pro_tag = _premium_tag()
        row_ai_check.addWidget(self._ai_pro_tag)
        row_ai_check.addStretch()
        tab_capture.addLayout(row_ai_check)

        row_ai_provider = QHBoxLayout()
        row_ai_provider.setSpacing(8)
        lbl_ai_provider = QLabel(t("ai_provider_label"))
        lbl_ai_provider.setFixedWidth(148)
        row_ai_provider.addWidget(lbl_ai_provider)
        self._ai_provider_combo = QComboBox()
        self._ai_provider_combo.addItem("Claude (Anthropic)", "claude")
        self._ai_provider_combo.addItem("Gemini (Google)", "gemini")
        self._ai_provider_combo.addItem("OpenAI", "openai")
        row_ai_provider.addWidget(self._ai_provider_combo, 1)
        tab_capture.addLayout(row_ai_provider)

        row_ai_key = QHBoxLayout()
        row_ai_key.setSpacing(8)
        lbl_ai_key = QLabel(t("ai_key_label"))
        lbl_ai_key.setFixedWidth(148)
        row_ai_key.addWidget(lbl_ai_key)
        self._ai_key_input = QLineEdit()
        self._ai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_key_input.setPlaceholderText(t("ai_key_placeholder"))
        row_ai_key.addWidget(self._ai_key_input, 1)
        tab_capture.addLayout(row_ai_key)

        lbl_ai_hint = QLabel(t("ai_hint"))
        lbl_ai_hint.setStyleSheet("color: #5a7a9a; font-size: 11px;")
        lbl_ai_hint.setWordWrap(True)
        tab_capture.addWidget(lbl_ai_hint)

        self._ai_check.setChecked(bool(ai_cfg.get("enabled", False)))
        idx = self._ai_provider_combo.findData(ai_cfg.get("provider", "claude"))
        if idx >= 0:
            self._ai_provider_combo.setCurrentIndex(idx)
        self._ai_key_input.setText(ai_cfg.get("api_key", ""))
        self._ai_check.toggled.connect(self._ai_provider_combo.setEnabled)
        self._ai_check.toggled.connect(self._ai_key_input.setEnabled)

        # ═══ De volta à aba Geral: idioma da interface ═══
        root = tab_general
        root.addWidget(_separator())

        # ── Seção: Interface ──────────────────────────────────────────
        root.addWidget(_section_label(t("settings_section_interface")))

        row_lang = QHBoxLayout()
        row_lang.setSpacing(8)
        lbl_lang = QLabel(t("settings_ui_language_label"))
        lbl_lang.setFixedWidth(148)
        row_lang.addWidget(lbl_lang)
        self._ui_lang_combo = QComboBox()
        for code, key in UI_LANGUAGES:
            self._ui_lang_combo.addItem(t(key), code)
        row_lang.addWidget(self._ui_lang_combo, 1)
        root.addLayout(row_lang)

        tab_general.addStretch()
        tab_capture.addStretch()
        tab_appear.addStretch()

        # ── Botões (fixos abaixo das abas) ────────────────────────────
        bottom = QVBoxLayout()
        bottom.setContentsMargins(24, 8, 24, 10)
        bottom.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel = QPushButton(t("settings_btn_cancel"))
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton(t("settings_btn_save"))
        save.setObjectName("save_btn")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btn_row.addWidget(save)

        bottom.addLayout(btn_row)

        # ── Créditos ──────────────────────────────────────────────────
        footer_sep = QFrame()
        footer_sep.setFrameShape(QFrame.Shape.HLine)
        footer_sep.setStyleSheet("color: #111c30; margin-top: 4px;")
        bottom.addWidget(footer_sep)

        footer = QLabel("PolyQuest  ·  Lucas Silva & Claude")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #1e2d48;")
        bottom.addWidget(footer)

        outer.addLayout(bottom)

        # ── Carrega valores do perfil ativo nos widgets ───────────────
        self._load_profile_into_ui(self._config)

    def _apply_height(self, is_custom: bool):
        """Altura desejada limitada ao espaço disponível na tela (com scroll)."""
        desired = self._HEIGHT_CUSTOM if is_custom else self._HEIGHT_BASE
        try:
            avail = self.screen().availableGeometry().height() - 60
        except Exception:
            avail = 800
        self.resize(self.width(), min(desired, max(480, avail)))

        # ── Aplica gates Premium ─────────────────────────────────────
        self._apply_premium_gates()

    # -- License management ------------------------------------------------
    def _update_license_status(self):
        if self._premium:
            self._lic_status.setText(t("license_status_premium"))
            self._lic_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #34d399;")
        else:
            self._lic_status.setText(t("license_status_beta"))
            self._lic_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #f9e2af;")

    def _update_license_ui(self):
        if self._premium:
            info = get_license_info()
            key = info.get("key", "") if info else ""
            self._lic_input.setText(key)
            self._lic_input.setReadOnly(True)
            self._lic_btn.setText(t("license_btn_deactivate"))
            self._lic_msg.setText("")
        else:
            self._lic_input.setText("")
            self._lic_input.setReadOnly(False)
            self._lic_btn.setText(t("license_btn_activate"))
            self._lic_msg.setText(t("license_hint_beta"))
            self._lic_msg.setStyleSheet("font-size: 11px; color: #f9e2af;")

    def _on_license_action(self):
        if self._premium:
            deactivate()
            self._premium = False
            self._update_license_status()
            self._update_license_ui()
            self._apply_premium_gates()
            self._lic_msg.setText(t("license_deactivated"))
            self._lic_msg.setStyleSheet("font-size: 11px; color: #f9e2af;")
            return

        key = self._lic_input.text().strip()
        if not key:
            return

        self._lic_btn.setEnabled(False)
        self._lic_input.setReadOnly(True)
        self._lic_msg.setText(t("license_activating"))
        self._lic_msg.setStyleSheet("font-size: 11px; color: #00e5ff;")

        # Ativa em thread separada para não travar a UI
        def _do_activate():
            result = activate(key)
            self._license_result.emit(result)

        Thread(target=_do_activate, daemon=True).start()

    def _on_license_result(self, result: dict):
        """Callback chamado na UI thread quando a ativação termina."""
        self._lic_btn.setEnabled(True)
        self._lic_input.setReadOnly(False)
        if result.get("ok"):
            self._premium = True
            self._update_license_status()
            self._update_license_ui()
            self._apply_premium_gates()
            self._lic_msg.setText(t("license_activated"))
            self._lic_msg.setStyleSheet("font-size: 11px; color: #34d399;")
        else:
            self._lic_msg.setText(t("license_error", error=result.get("error", "")))
            self._lic_msg.setStyleSheet("font-size: 11px; color: #f87171;")

    def _apply_premium_gates(self):
        """Habilita/desabilita widgets que são exclusivos Premium."""
        p = self._premium

        # Perfis: novo/excluir
        self._profile_combo.setEnabled(p)
        if hasattr(self, '_new_profile_btn'):
            self._new_profile_btn.setEnabled(p)
        self._del_btn.setEnabled(p and len(self._profiles) > 1)

        # Font size
        self._font_size_spin.setEnabled(p)
        if hasattr(self, '_font_pro_tag'):
            self._font_pro_tag.setVisible(not p)

        # Modo contínuo
        self._cont_check.setEnabled(p)
        self._cont_interval.setEnabled(p and self._cont_check.isChecked())
        if hasattr(self, '_cont_pro_tag'):
            self._cont_pro_tag.setVisible(not p)

        # Modo IA
        self._ai_check.setEnabled(p)
        self._ai_provider_combo.setEnabled(p and self._ai_check.isChecked())
        self._ai_key_input.setEnabled(p and self._ai_check.isChecked())
        if hasattr(self, '_ai_pro_tag'):
            self._ai_pro_tag.setVisible(not p)

        # Tema "Personalizar" — mostra/esconde "🔒" no dropdown
        self._loading = True
        custom_idx = self._theme_combo.findData("custom")
        if custom_idx >= 0:
            base_name = t("theme_custom")
            if p:
                self._theme_combo.setItemText(custom_idx, base_name)
            else:
                self._theme_combo.setItemText(custom_idx, f"{base_name}  ★ PRO")
                # Se o tema atual é custom e não é premium, volta para dark
                if self._theme_combo.currentData() == "custom":
                    dark_idx = self._theme_combo.findData("dark")
                    if dark_idx >= 0:
                        self._theme_combo.setCurrentIndex(dark_idx)
                    self._custom_section.setVisible(False)
                    self._apply_height(False)
        self._loading = False

    # -- Profile management ------------------------------------------------
    def _on_profile_changed(self):
        if self._loading:
            return
        name = self._profile_combo.currentData()
        if name and name in self._profiles:
            self._active_name = name
            self._config = dict(self._profiles[name])
            self._new_hotkey = self._config.get("hotkey", "*")
            self._load_profile_into_ui(self._config)
        self._del_btn.setEnabled(len(self._profiles) > 1)

    def _new_profile(self):
        name, ok = QInputDialog.getText(
            self, t("profile_new_title"), t("profile_new_prompt"),
        )
        name = name.strip()
        if not ok or not name or name in self._profiles:
            return
        self._profiles[name] = dict(_DEFAULT_PROFILE)
        self._active_name = name
        self._config = dict(self._profiles[name])
        self._new_hotkey = self._config.get("hotkey", "*")

        self._loading = True
        self._profile_combo.addItem(name, name)
        self._profile_combo.setCurrentIndex(self._profile_combo.count() - 1)
        self._loading = False

        self._load_profile_into_ui(self._config)
        self._del_btn.setEnabled(len(self._profiles) > 1)

    def _delete_profile(self):
        if len(self._profiles) <= 1:
            return
        name = self._active_name
        reply = QMessageBox.question(
            self,
            t("profile_delete"),
            t("profile_delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        del self._profiles[name]

        self._loading = True
        idx = self._profile_combo.findData(name)
        if idx >= 0:
            self._profile_combo.removeItem(idx)
        self._loading = False

        # Troca para o primeiro perfil restante
        first_name = self._profile_combo.currentData()
        self._active_name = first_name
        self._config = dict(self._profiles.get(first_name, _DEFAULT_PROFILE))
        self._new_hotkey = self._config.get("hotkey", "*")
        self._load_profile_into_ui(self._config)
        self._del_btn.setEnabled(len(self._profiles) > 1)

    def _load_profile_into_ui(self, cfg: dict):
        """Popula todos os widgets com os valores do perfil."""
        self._loading = True

        # Hotkey
        self._new_hotkey = cfg.get("hotkey", "*")
        self._display.setText(self._new_hotkey)
        self._new_region_hotkey = cfg.get("region_hotkey")
        self._region_display.setText(self._new_region_hotkey or "—")
        self._info.setText(t("settings_hotkey_hint"))
        self._info.setStyleSheet("color: #5a7a9a; font-size: 11px;")

        # Monitor
        mon = cfg.get("monitor")
        idx = self._monitor_combo.findData(mon)
        self._monitor_combo.setCurrentIndex(idx if idx >= 0 else 0)

        # Resolução
        res = cfg.get("source_resolution")
        self._res_manual_check.setChecked(res is not None)
        self._res_w.setText(str(res[0]) if res else "1920")
        self._res_h.setText(str(res[1]) if res else "1080")
        self._res_w.setEnabled(res is not None)
        self._res_h.setEnabled(res is not None)

        # Modo contínuo
        self._cont_check.setChecked(bool(cfg.get("continuous_mode", False)))
        self._cont_interval.setValue(int(cfg.get("continuous_interval", 3)))
        self._cont_interval.setEnabled(self._premium and self._cont_check.isChecked())

        # Idiomas
        idx = self._src_lang_combo.findData(cfg.get("source_language", "en"))
        if idx >= 0:
            self._src_lang_combo.setCurrentIndex(idx)
        idx = self._tgt_lang_combo.findData(cfg.get("target_language", "pt"))
        if idx >= 0:
            self._tgt_lang_combo.setCurrentIndex(idx)

        # Tema
        idx = self._theme_combo.findData(cfg.get("theme", "dark"))
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

        # Custom colors
        cc = cfg.get("customColors", {})
        self._custom_bg = cc.get("background", "#000000")
        self._custom_fg = cc.get("text", "#FFFFFF")
        self._custom_opacity = cc.get("opacity", 70)
        self._bg_hex.setText(self._custom_bg)
        self._fg_hex.setText(self._custom_fg)
        self._opacity_slider.setValue(self._custom_opacity)
        self._update_swatches()

        is_custom = cfg.get("theme") == "custom"
        self._custom_section.setVisible(is_custom)
        self._apply_height(is_custom)

        # Fonte / modo
        self._font_size_spin.setValue(cfg.get("font_size", 0))
        idx = self._mode_combo.findData(cfg.get("translation_mode", "balanced"))
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

        # Interface
        idx = self._ui_lang_combo.findData(cfg.get("ui_language", "pt"))
        if idx >= 0:
            self._ui_lang_combo.setCurrentIndex(idx)

        self._loading = False
        self._update_custom_preview()

    # ------------------------------------------------------------------
    def _start_capture(self, target: str = "main"):
        self._captured_key = None
        self._capture_target = target
        self._capture_btn.setEnabled(False)
        self._region_capture_btn.setEnabled(False)
        display = self._display if target == "main" else self._region_display
        display.setText("...")
        self._info.setText(t("settings_hotkey_waiting"))
        self._info.setStyleSheet("color: #f9e2af; font-size: 11px;")

        def _on_key(event):
            if self._captured_key is None:
                self._captured_key = event.name

        keyboard.on_press(_on_key, suppress=False)
        self._capture_timer.start(50)

    def _check_capture(self):
        if self._captured_key is None:
            return

        self._capture_timer.stop()
        keyboard.unhook_all()

        key = self._captured_key
        self._captured_key = None
        if self._capture_target == "region":
            self._new_region_hotkey = key
            self._region_display.setText(key)
        else:
            self._new_hotkey = key
            self._display.setText(key)
        self._capture_btn.setEnabled(True)
        self._region_capture_btn.setEnabled(True)
        self._info.setText(t("settings_hotkey_selected", key=key))
        self._info.setStyleSheet("color: #34d399; font-size: 11px;")

    def _clear_region_hotkey(self):
        self._new_region_hotkey = None
        self._region_display.setText("—")

    # -- Custom theme helpers ------------------------------------------------
    def _on_theme_changed(self):
        if self._loading:
            return
        is_custom = self._theme_combo.currentData() == "custom"
        # Tema custom requer Premium
        if is_custom and not self._premium:
            self._loading = True
            dark_idx = self._theme_combo.findData("dark")
            if dark_idx >= 0:
                self._theme_combo.setCurrentIndex(dark_idx)
            self._loading = False
            # Feedback visual na seção de licença
            self._lic_msg.setText(t("license_hint_beta"))
            self._lic_msg.setStyleSheet("font-size: 11px; color: #f9e2af;")
            return
        self._custom_section.setVisible(is_custom)
        self._apply_height(is_custom)

    def _is_valid_hex(self, text: str) -> bool:
        if len(text) != 7 or text[0] != "#":
            return False
        try:
            int(text[1:], 16)
            return True
        except ValueError:
            return False

    def _update_swatches(self):
        for btn, color in [(self._bg_swatch, self._custom_bg), (self._fg_swatch, self._custom_fg)]:
            btn.setStyleSheet(
                f"background-color: {color}; border: 1px solid #1e2d48; border-radius: 4px;"
            )

    def _update_custom_preview(self):
        if self._loading:
            return
        opa = self._opacity_slider.value()
        self._custom_opacity = opa
        self._opacity_label.setText(f"{opa}%")
        r, g, b = self._hex_to_rgb(self._custom_bg)
        alpha = int(opa * 255 / 100)
        font_pt = 13 + (self._font_size_spin.value() if hasattr(self, '_font_size_spin') else 0)
        self._preview_label.setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {alpha}); "
            f"color: {self._custom_fg}; border-radius: 4px; "
            f"font-size: {font_pt}px; font-weight: bold;"
        )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        h = hex_color.lstrip("#")
        try:
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return (0, 0, 0)

    def _pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self._custom_bg), self)
        if color.isValid():
            self._custom_bg = color.name()
            self._bg_hex.setText(self._custom_bg)
            self._update_swatches()
            self._update_custom_preview()

    def _pick_fg_color(self):
        color = QColorDialog.getColor(QColor(self._custom_fg), self)
        if color.isValid():
            self._custom_fg = color.name()
            self._fg_hex.setText(self._custom_fg)
            self._update_swatches()
            self._update_custom_preview()

    def _on_bg_hex_changed(self, text: str):
        if self._is_valid_hex(text):
            self._custom_bg = text
            self._update_swatches()
            self._update_custom_preview()

    def _on_fg_hex_changed(self, text: str):
        if self._is_valid_hex(text):
            self._custom_fg = text
            self._update_swatches()
            self._update_custom_preview()

    # -- Save ----------------------------------------------------------------
    def _save(self):
        profile = {}
        profile["hotkey"] = self._new_hotkey
        profile["region_hotkey"] = (
            self._new_region_hotkey
            if self._new_region_hotkey != self._new_hotkey else None
        )

        # Captura
        profile["monitor"] = self._monitor_combo.currentData()
        profile["continuous_mode"] = bool(self._premium and self._cont_check.isChecked())
        profile["continuous_interval"] = self._cont_interval.value()
        if self._res_manual_check.isChecked():
            try:
                w = int(self._res_w.text())
                h = int(self._res_h.text())
                profile["source_resolution"] = [w, h] if w > 0 and h > 0 else None
            except ValueError:
                profile["source_resolution"] = None
        else:
            profile["source_resolution"] = None

        # Idiomas
        profile["source_language"] = self._src_lang_combo.currentData()
        profile["target_language"] = self._tgt_lang_combo.currentData()

        # Aparência
        profile["theme"] = self._theme_combo.currentData()
        if profile["theme"] == "custom":
            profile["customColors"] = {
                "background": self._custom_bg,
                "text": self._custom_fg,
                "opacity": self._opacity_slider.value(),
            }
        profile["font_size"] = self._font_size_spin.value()
        profile["background_opacity"] = self._config.get("background_opacity", 210)
        profile["translation_mode"] = self._mode_combo.currentData()

        # Interface
        profile["ui_language"] = self._ui_lang_combo.currentData()

        # Preserva glossário existente
        profile["glossary"] = self._config.get("glossary", [])

        # Preserva customColors se existiam e tema não é custom
        if profile["theme"] != "custom" and "customColors" in self._config:
            profile["customColors"] = self._config["customColors"]

        # Salva no perfil ativo
        self._profiles[self._active_name] = profile

        self._full_config["activeProfile"] = self._active_name
        self._full_config["profiles"] = self._profiles

        # Modo IA é global (fora dos perfis); key fica gravada mesmo desativado
        self._full_config["ai"] = {
            "enabled": bool(self._premium and self._ai_check.isChecked()),
            "provider": self._ai_provider_combo.currentData(),
            "api_key": self._ai_key_input.text().strip(),
        }

        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._full_config, f, indent=4, ensure_ascii=False)
        self.accept()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._capture_timer.stop()
        keyboard.unhook_all()
        super().closeEvent(event)

    def reject(self):
        self._capture_timer.stop()
        keyboard.unhook_all()
        super().reject()
