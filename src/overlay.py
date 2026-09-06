import ctypes
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics, QScreen
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from src.i18n import t
from src.ocr import TextBlock

GWL_EXSTYLE = -20
WDA_EXCLUDEFROMCAPTURE = 0x00000011

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
        # True quando o Windows aceitou excluir a janela da captura de tela
        # (modo contínuo depende disso para não "ler" o próprio overlay)
        self.capture_excluded = False
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
        self.setGeometry(self._screen.geometry())

    # Padding do QLabel (1px 4px no stylesheet) + borda
    _LABEL_PAD_W = 10
    # O balão pode passar até 25% da largura original antes de encolher a
    # fonte — manter o tamanho visual do texto importa mais que a caixa exata
    _WIDTH_TOLERANCE = 1.25

    def _fit_font(self, text: str, avail_w: int, avail_h: int) -> tuple:
        """
        Fonte (em pixels) do mesmo tamanho do texto original (ajustada à
        altura da caixa). Só encolhe se a tradução estourar a largura além
        da tolerância, e nunca abaixo de 80% — legível vale mais que exato.
        """
        font = QFont()
        # 1) maior fonte que respeita a ALTURA original
        px = max(8, avail_h)
        while px > 7:
            font.setPixelSize(px)
            if QFontMetrics(font).height() <= avail_h:
                break
            px -= 1
        # 2) encolhe (pouco) só se estourar a largura além da tolerância
        allowed_w = max(int(avail_w * self._WIDTH_TOLERANCE), 8)
        floor = max(7, int(px * 0.8))
        while px > floor:
            font.setPixelSize(px)
            if QFontMetrics(font).horizontalAdvance(text) <= allowed_w:
                break
            px -= 1
        # ajuste manual do usuário (config "font_size")
        px = max(7, px + self._config.get("font_size", 0))
        font.setPixelSize(px)
        return font, QFontMetrics(font)

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
            max_w = max(8, int(block.w / self._dpr))
            max_h = max(8, int(block.h / self._dpr))

            font, fm = self._fit_font(
                block.translated, max_w - self._LABEL_PAD_W, max_h - 2
            )

            label = QLabel(block.translated, self)
            label.setFont(font)
            label.setWordWrap(False)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
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
            # A caixa cobre exatamente o texto original; só cresce se nem a
            # fonte no piso de legibilidade couber
            w = max(max_w, fm.horizontalAdvance(block.translated) + self._LABEL_PAD_W)
            h = max(max_h, fm.height() + 2)
            label.setFixedSize(w, h)
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
            # Exclui o overlay da captura de tela (Windows 10 2004+)
            self.capture_excluded = bool(
                ctypes.windll.user32.SetWindowDisplayAffinity(
                    hwnd, WDA_EXCLUDEFROMCAPTURE
                )
            )
        except Exception as e:
            print(f"[Overlay] click-through: {e}")
