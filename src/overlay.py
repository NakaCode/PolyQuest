import ctypes
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QScreen
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from src.i18n import t
from src.ocr import TextBlock

GWL_EXSTYLE = -20

THEMES = {
    "dark": {
        "bg_rgb": (10, 10, 10),
        "fg": "#FFFFFF",
        "bar_bg": "rgba(0, 120, 215, 220)",
        "bar_fg": "white",
    },
    "light": {
        "bg_rgb": (240, 240, 240),
        "fg": "#111111",
        "bar_bg": "rgba(0, 90, 180, 220)",
        "bar_fg": "white",
    },
    "green": {
        "bg_rgb": (0, 15, 0),
        "fg": "#00FF41",
        "bar_bg": "rgba(0, 80, 0, 220)",
        "bar_fg": "#00FF41",
    },
    "amber": {
        "bg_rgb": (20, 10, 0),
        "fg": "#FFB300",
        "bar_bg": "rgba(120, 60, 0, 220)",
        "bar_fg": "#FFB300",
    },
}


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def resolve_theme(config: dict) -> dict:
    if config.get("theme") == "custom":
        cc = config.get("customColors", {})
        bg = cc.get("background", "#000000")
        fg = cc.get("text", "#FFFFFF")
        r, g, b = _hex_to_rgb(bg)
        return {
            "bg_rgb": (r, g, b),
            "fg": fg,
            "bar_bg": f"rgba({r}, {g}, {b}, 220)",
            "bar_fg": fg,
            "_custom_opacity": cc.get("opacity", 70),
        }
    return THEMES.get(config.get("theme", "dark"), THEMES["dark"])
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000


def find_screen_for_monitor(mss_monitor: dict) -> QScreen:
    """
    Encontra o QScreen que corresponde ao monitor mss capturado.
    Compara as dimensões físicas para tolerar diferenças de DPI entre monitores.
    """
    best = QApplication.primaryScreen()
    best_score = float("inf")

    for screen in QApplication.screens():
        dpr = screen.devicePixelRatio()
        geo = screen.geometry()

        phys_w = geo.width() * dpr
        phys_h = geo.height() * dpr
        phys_x = geo.x() * dpr
        phys_y = geo.y() * dpr

        score = (abs(phys_w - mss_monitor["width"]) +
                 abs(phys_h - mss_monitor["height"]) +
                 abs(phys_x - mss_monitor["left"]) * 0.1 +
                 abs(phys_y - mss_monitor["top"]) * 0.1)

        if score < best_score:
            best_score = score
            best = screen

    return best


class OverlayWindow(QWidget):
    def __init__(self, blocks: List[TextBlock], config: dict, screen: Optional[QScreen] = None):
        super().__init__()
        self._config = config
        self._screen = screen or QApplication.primaryScreen()
        self._setup_window()
        self._render_blocks(blocks)
        self._render_status_bar(config["hotkey"])
        self._make_click_through()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._dpr = self._screen.devicePixelRatio()
        self._logical_dpi = self._screen.logicalDotsPerInch()
        self.setGeometry(self._screen.geometry())

    def _font_size_pt(self, line_h_physical: int) -> int:
        logical_h = line_h_physical / self._dpr
        pt = int(logical_h * 72 / self._logical_dpi * 0.72)
        offset = self._config.get("font_size", 0)
        return max(7, pt + offset)

    def _render_blocks(self, blocks: List[TextBlock]):
        theme = resolve_theme(self._config)
        if "_custom_opacity" in theme:
            opacity = int(theme["_custom_opacity"] * 255 / 100)
        else:
            opacity = self._config.get("background_opacity", 210)
        r, g, b = theme["bg_rgb"]

        for block in blocks:
            if not block.translated:
                continue

            x = int(block.x / self._dpr)
            y = int(block.y / self._dpr)

            font_pt = self._font_size_pt(block.line_h)
            font = QFont()
            font.setPointSize(font_pt)

            label = QLabel(block.translated, self)
            label.setFont(font)
            label.setWordWrap(False)
            label.setStyleSheet(
                f"""
                QLabel {{
                    background-color: rgba({r}, {g}, {b}, {opacity});
                    color: {theme["fg"]};
                    padding: 1px 4px;
                    border-radius: 3px;
                }}
                """
            )
            label.adjustSize()
            label.move(x, y)

    def _render_status_bar(self, hotkey: str):
        theme = resolve_theme(self._config)
        bar = QLabel(t("overlay_hint", hotkey=hotkey), self)
        bar.setStyleSheet(
            f"""
            QLabel {{
                background-color: {theme["bar_bg"]};
                color: {theme["bar_fg"]};
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            """
        )
        bar.adjustSize()
        bar.move(0, 0)

    def _make_click_through(self):
        try:
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            )
        except Exception as e:
            print(f"[Overlay] click-through: {e}")
