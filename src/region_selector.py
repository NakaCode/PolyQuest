"""
Seletor de região: tela escurecida onde o usuário arrasta um retângulo
para traduzir só aquela área. ESC cancela.
"""

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QScreen
from PyQt6.QtWidgets import QLabel, QWidget

from src.i18n import t

_MIN_SIZE = 12  # px lógicos — abaixo disso trata como clique acidental


class RegionSelector(QWidget):
    # bbox mss em pixels físicos absolutos: {"left", "top", "width", "height"}
    region_selected = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, screen: QScreen):
        super().__init__()
        self._screen = screen
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._done = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

        hint = QLabel(t("region_selector_hint"), self)
        hint.setStyleSheet(
            "background-color: rgba(0, 120, 215, 230); color: white;"
            "padding: 6px 12px; font-size: 12px; font-weight: bold;"
            "border-radius: 4px;"
        )
        hint.adjustSize()
        hint.move((self.width() - hint.width()) // 2, 24)

    def open(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        dim = QColor(0, 0, 0, 110)
        if self._origin and self._current:
            sel = QRect(self._origin, self._current).normalized()
            # Escurece tudo, menos a área selecionada
            painter.fillRect(QRect(0, 0, self.width(), sel.top()), dim)
            painter.fillRect(QRect(0, sel.top(), sel.left(), sel.height()), dim)
            painter.fillRect(
                QRect(sel.right() + 1, sel.top(),
                      self.width() - sel.right() - 1, sel.height()), dim)
            painter.fillRect(
                QRect(0, sel.bottom() + 1,
                      self.width(), self.height() - sel.bottom() - 1), dim)
            pen = QPen(QColor(0, 229, 255))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(sel)
        else:
            painter.fillRect(self.rect(), dim)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        sel = QRect(self._origin, event.position().toPoint()).normalized()
        self._origin = self._current = None
        if sel.width() < _MIN_SIZE or sel.height() < _MIN_SIZE:
            self._finish(None)
            return

        dpr = self._screen.devicePixelRatio()
        geo = self._screen.geometry()
        bbox = {
            "left":   int((geo.x() + sel.x()) * dpr),
            "top":    int((geo.y() + sel.y()) * dpr),
            "width":  max(1, int(sel.width() * dpr)),
            "height": max(1, int(sel.height() * dpr)),
        }
        self._finish(bbox)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def closeEvent(self, event):
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(event)

    def _finish(self, bbox: dict | None):
        if self._done:
            return
        self._done = True
        self.close()
        if bbox:
            self.region_selected.emit(bbox)
        else:
            self.cancelled.emit()
