import ctypes
from typing import List, Optional, Tuple

import mss
from PIL import Image


def _foreground_monitor(sct) -> dict:
    """
    Retorna o monitor mss que contém a janela em foco (ex: o jogo).
    Fallback: monitor primário.
    """
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return sct.monitors[1]

    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.GetWindowRect(hwnd, rect)
    win_cx = (rect[0] + rect[2]) // 2
    win_cy = (rect[1] + rect[3]) // 2

    for m in sct.monitors[1:]:  # ignora monitors[0] (todos os monitores juntos)
        if (m["left"] <= win_cx < m["left"] + m["width"] and
                m["top"] <= win_cy < m["top"] + m["height"]):
            return m

    return sct.monitors[1]


def list_monitors() -> List[dict]:
    """Retorna lista de monitores disponíveis (índice 1-based)."""
    with mss.mss() as sct:
        return list(sct.monitors[1:])


def resolve_monitor(monitor_index: Optional[int] = None) -> dict:
    """Resolve o monitor alvo (configurado ou o da janela em foco)."""
    with mss.mss() as sct:
        if monitor_index is not None:
            idx = max(1, min(monitor_index, len(sct.monitors) - 1))
            return dict(sct.monitors[idx])
        return dict(_foreground_monitor(sct))


def capture_region(bbox: dict) -> Image.Image:
    """Captura uma área arbitrária (coordenadas físicas absolutas)."""
    with mss.mss() as sct:
        screenshot = sct.grab(bbox)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")


def capture_screen(
    monitor_index: Optional[int] = None,
    source_resolution: Optional[list] = None,
) -> Tuple[Image.Image, dict]:
    """
    Captura o monitor selecionado ou o que contém a janela em foco.

    monitor_index : 1-based (None = automático pela janela ativa)
    source_resolution : [largura, altura] para restringir a área capturada
                        (None = resolução nativa do monitor)
    """
    with mss.mss() as sct:
        if monitor_index is not None:
            idx = max(1, min(monitor_index, len(sct.monitors) - 1))
            monitor = dict(sct.monitors[idx])
        else:
            monitor = dict(_foreground_monitor(sct))

        if source_resolution and len(source_resolution) == 2:
            w, h = int(source_resolution[0]), int(source_resolution[1])
            if w > 0 and h > 0:
                monitor["width"] = min(w, monitor["width"])
                monitor["height"] = min(h, monitor["height"])

        screenshot = sct.grab(monitor)
        image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    return image, monitor
