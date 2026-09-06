"""
PolyQuest — Overlay de tradução para jogadores
Pressione a hotkey configurada para traduzir tudo que está na tela.
"""

import json
import sys
import traceback
from pathlib import Path


def _base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


# Log de crash — ativo antes de qualquer outro import
from src.crash_log import setup as _setup_crash_log
_setup_crash_log(_base_path() / "crash.log")


import keyboard
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.about_dialog import AboutDialog
from src.capture import capture_screen, capture_region, resolve_monitor
from src.glossary_dialog import GlossaryDialog
from src import i18n
from src.i18n import t
from src.license import is_premium
from src.ocr import check_ocr_language, extract_blocks
from src.overlay import OverlayWindow, find_screen_for_monitor
from src.region_selector import RegionSelector
from src.settings_dialog import SettingsDialog
from src.translator import (
    translate_blocks, get_cache_stats, get_last_failures, init_cache,
)
from src.update_checker import check_for_update


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


def _config_path() -> Path:
    return _base_path() / "config.json"


def load_full_config() -> dict:
    """Carrega config.json, migrando formato flat para perfis se necessário."""
    with open(_config_path(), "r", encoding="utf-8") as f:
        raw = json.load(f)

    if "profiles" not in raw:
        name = t("profile_default")
        profile = {k: v for k, v in raw.items()}
        if "glossary" not in profile:
            profile["glossary"] = []
        full = {"activeProfile": name, "profiles": {name: profile}}
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(full, f, indent=4, ensure_ascii=False)
        return full
    return raw


def active_config(full: dict) -> dict:
    """Retorna o dict flat do perfil ativo."""
    name = full.get("activeProfile", "")
    profiles = full.get("profiles", {})
    if name in profiles:
        return profiles[name]
    first = next(iter(profiles), None)
    return profiles[first] if first else _DEFAULT_PROFILE.copy()


def load_config() -> dict:
    """Conveniência: retorna o config flat do perfil ativo."""
    return active_config(load_full_config())


def _load_icon(name: str) -> QIcon:
    path = _base_path() / name
    if path.exists():
        return QIcon(str(path))
    return _build_tray_icon_fallback()


def _build_tray_icon_fallback() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 120, 215))
    painter.setPen(QColor(0, 120, 215))
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor(255, 255, 255))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x84, "T")
    painter.end()
    return QIcon(pixmap)


class TranslationWorker(QThread):
    finished = pyqtSignal(list, dict, int)   # blocks, mss_monitor, falhas de rede
    error = pyqtSignal(str)

    def __init__(self, config: dict, region: dict | None = None, ai: dict | None = None):
        super().__init__()
        self._config = config
        # region = {"bbox": mss dict absoluto, "monitor": mss dict do monitor}
        self._region = region
        # ai = {"provider": ..., "api_key": ...} quando o Modo IA está ativo
        self._ai = ai

    def run(self):
        try:
            if self._region:
                bbox = self._region["bbox"]
                monitor = self._region["monitor"]
                image = capture_region(bbox)
            else:
                image, monitor = capture_screen(
                    monitor_index=self._config.get("monitor"),
                    source_resolution=self._config.get("source_resolution"),
                )
            blocks = extract_blocks(
                image,
                lang=self._config.get("source_language", "en"),
            )

            if self._region and blocks:
                # Blocos vêm relativos à área capturada; reposiciona no monitor
                dx = bbox["left"] - monitor["left"]
                dy = bbox["top"] - monitor["top"]
                for b in blocks:
                    b.x += dx
                    b.y += dy

            if not blocks:
                self.finished.emit([], monitor, 0)
                return

            translate_blocks(
                blocks,
                source=self._config.get("source_language", "en"),
                target=self._config.get("target_language", "pt"),
                mode=self._config.get("translation_mode", "balanced"),
                glossary=self._config.get("glossary"),
                ai=self._ai,
            )
            self.finished.emit(blocks, monitor, get_last_failures())

        except Exception:
            self.error.emit(traceback.format_exc())


class PolyQuest(QObject):
    _trigger = pyqtSignal()
    _trigger_region = pyqtSignal()

    def __init__(self, full_config: dict, config_path: Path):
        super().__init__()
        self._full_config = full_config
        self._config = active_config(full_config)
        self._config_path = config_path
        self._overlay: OverlayWindow | None = None
        self._worker: TranslationWorker | None = None
        self._working = False
        self._ocr_ready = True

        # Sessão de tradução (região selecionada + modo contínuo)
        self._region_selector: RegionSelector | None = None
        self._session_region: dict | None = None
        self._continuous = False
        self._notified_fail = False
        self._cont_timer = QTimer()
        self._cont_timer.setSingleShot(True)
        self._cont_timer.timeout.connect(self._on_continuous_tick)

        self._icon_main = _load_icon("icon.ico")
        self._icon_settings = _load_icon("icon_settings.ico")

        self._trigger.connect(self._on_trigger)
        self._trigger_region.connect(self._on_region_trigger)
        self._tray = self._setup_tray()

    def _setup_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._icon_main)
        tray.setToolTip(t("tray_tooltip_ready"))
        tray.setContextMenu(self._build_tray_menu())
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()
        hotkey = self._config.get("hotkey", "*").upper()

        self._action_translate = menu.addAction(t("tray_action_translate", hotkey=hotkey))
        self._action_translate.triggered.connect(self._trigger.emit)

        region_key = self._config.get("region_hotkey")
        suffix = f"  [{region_key.upper()}]" if region_key else ""
        self._action_region = menu.addAction(t("tray_action_translate_region", hotkey=suffix))
        self._action_region.triggered.connect(self._trigger_region.emit)
        menu.addSeparator()
        action_settings = menu.addAction(t("tray_action_settings"))
        action_settings.triggered.connect(self._open_settings)
        action_glossary = menu.addAction(t("tray_action_glossary"))
        action_glossary.triggered.connect(self._open_glossary)
        action_about = menu.addAction(t("tray_action_about"))
        action_about.triggered.connect(self._open_about)
        menu.addSeparator()
        action_quit = menu.addAction(t("tray_action_quit"))
        action_quit.triggered.connect(QApplication.quit)
        return menu

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_settings()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._trigger.emit()

    def _reload_config(self):
        self._full_config = load_full_config()
        self._config = active_config(self._full_config)

    def _open_glossary(self):
        if not is_premium():
            self._tray.showMessage(
                "PolyQuest",
                t("license_hint_beta"),
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            return
        dlg = GlossaryDialog(self._full_config, self._config_path)
        dlg.exec()
        self._reload_config()

    def _open_about(self):
        dlg = AboutDialog()
        dlg.exec()

    def _open_settings(self):
        self._tray.setIcon(self._icon_settings)
        self._tray.setToolTip(t("tray_tooltip_settings"))
        dlg = SettingsDialog(self._full_config, self._config_path)
        result = dlg.exec()
        self._tray.setIcon(self._icon_main)
        self._tray.setToolTip(t("tray_tooltip_ready"))
        if result:
            old_hotkey = self._config.get("hotkey", "*")
            old_region = self._config.get("region_hotkey")
            self._stop_session()
            self._reload_config()

            # Atualiza idioma da interface se mudou
            i18n.setup(self._config.get("ui_language", "pt"))

            for key in (old_hotkey, old_region):
                if not key:
                    continue
                try:
                    keyboard.remove_hotkey(key)
                except Exception:
                    pass
            keyboard.add_hotkey(self._config.get("hotkey", "*"), self._trigger.emit)
            new_region = self._config.get("region_hotkey")
            if new_region:
                keyboard.add_hotkey(new_region, self._trigger_region.emit)

            # Reconstrói o menu com os textos no novo idioma
            self._tray.setContextMenu(self._build_tray_menu())
            self._tray.showMessage(
                "PolyQuest",
                t("tray_msg_settings_saved"),
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def register_hotkey(self):
        hotkey = self._config.get("hotkey", "*")
        keyboard.add_hotkey(hotkey, self._trigger.emit)
        region_key = self._config.get("region_hotkey")
        if region_key:
            keyboard.add_hotkey(region_key, self._trigger_region.emit)
        self._tray.showMessage(
            "PolyQuest",
            t("tray_msg_ready", hotkey=hotkey.upper()),
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    # -- Sessão de tradução -------------------------------------------------
    def _session_active(self) -> bool:
        return bool(
            (self._overlay and self._overlay.isVisible())
            or self._cont_timer.isActive()
        )

    def _stop_session(self):
        self._cont_timer.stop()
        self._session_region = None
        self._continuous = False
        if self._overlay:
            self._overlay.close()
            self._overlay = None

    def _start_session(self, region: dict | None = None):
        self._session_region = region
        self._continuous = bool(self._config.get("continuous_mode")) and is_premium()
        self._notified_fail = False
        self._run_worker()

    def _ai_config(self) -> dict | None:
        """Config do Modo IA (global, fora dos perfis) quando ativo e premium."""
        ai = self._full_config.get("ai") or {}
        if ai.get("enabled") and ai.get("api_key") and is_premium():
            return {"provider": ai.get("provider", "claude"), "api_key": ai["api_key"]}
        return None

    def _run_worker(self):
        self._working = True
        self._tray.setToolTip(t("tray_tooltip_translating"))
        self._worker = TranslationWorker(
            self._config, region=self._session_region, ai=self._ai_config()
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_trigger(self):
        if not self._ocr_ready:
            self._tray.showMessage(
                "PolyQuest",
                t("tray_msg_still_loading"),
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )
            return

        if self._session_active():
            self._stop_session()
            return

        if self._working:
            return

        self._start_session(region=None)

    def _on_region_trigger(self):
        if not self._ocr_ready:
            return

        if self._session_active():
            self._stop_session()
            return

        if self._working:
            return

        if self._region_selector:
            self._region_selector.close()
            return

        monitor = resolve_monitor(self._config.get("monitor"))
        screen = find_screen_for_monitor(monitor)
        selector = RegionSelector(screen)
        self._region_selector = selector
        selector.region_selected.connect(
            lambda bbox: self._on_region_chosen(bbox, monitor)
        )
        selector.cancelled.connect(self._on_region_cancelled)
        selector.open()

    def _on_region_chosen(self, bbox: dict, monitor: dict):
        self._region_selector = None
        self._start_session(region={"bbox": bbox, "monitor": monitor})

    def _on_region_cancelled(self):
        self._region_selector = None

    def _on_continuous_tick(self):
        if self._working:
            self._cont_timer.start(500)
            return
        # Sem suporte a excluir o overlay da captura: esconde antes de capturar
        if (self._overlay and self._overlay.isVisible()
                and not self._overlay.capture_excluded):
            self._overlay.hide()
            QTimer.singleShot(80, self._run_worker)
            return
        self._run_worker()

    def _on_finished(self, blocks, monitor, failures):
        self._working = False
        self._tray.setToolTip(t("tray_tooltip_ready"))

        stats = get_cache_stats()
        print(f"[PolyQuest] Cache: {stats['hits']} hits, {stats['misses']} misses ({stats['ratio']}), {stats['size']} entries, {stats['disk']} no disco")

        if failures and not self._notified_fail:
            self._notified_fail = True
            self._tray.showMessage(
                "PolyQuest",
                t("tray_msg_translate_failed"),
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )

        # Substitui o overlay anterior (modo contínuo re-renderiza a cada ciclo)
        if self._overlay:
            self._overlay.close()
            self._overlay = None

        if blocks:
            screen = find_screen_for_monitor(monitor)
            self._overlay = OverlayWindow(blocks, self._config, screen)
            self._overlay.show()
        elif not self._continuous:
            self._tray.showMessage(
                "PolyQuest",
                t("tray_msg_no_text"),
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )
            return

        if self._continuous:
            interval = max(1, int(self._config.get("continuous_interval", 3)))
            self._cont_timer.start(interval * 1000)

    def _on_error(self, message):
        self._working = False
        self._cont_timer.stop()
        self._tray.setToolTip(t("tray_tooltip_ready"))
        self._tray.showMessage(
            "PolyQuest",
            t("tray_msg_error"),
            QSystemTrayIcon.MessageIcon.Critical,
            3000,
        )
        stats = get_cache_stats()
        print(f"[PolyQuest] Cache: {stats['hits']} hits, {stats['misses']} misses ({stats['ratio']}), {stats['size']} entries, {stats['disk']} no disco")
        print(f"[PolyQuest] Erro:\n{message}")


def main():
    full_config = load_full_config()
    config = active_config(full_config)

    # Cache persistente de traduções (mesma pasta gravável do config.json)
    init_cache(_base_path() / "translation_cache.db")

    # Inicializa o idioma da interface antes de qualquer texto ser exibido
    i18n.setup(config.get("ui_language", "pt"))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    try:
        check_ocr_language(config.get("source_language", "en"))
    except RuntimeError:
        from PyQt6.QtWidgets import QMessageBox
        import subprocess

        source_lang = config.get("source_language", "en")
        if source_lang == "auto":
            # Sem OCR nos idiomas do perfil do Windows — não há pacote "auto"
            QMessageBox.critical(None, "PolyQuest", t("ocr_install_failed"))
            sys.exit(1)
        tag = {"en": "en-US", "pt": "pt-BR", "es": "es-ES", "fr": "fr-FR",
               "de": "de-DE", "it": "it-IT", "nl": "nl-NL", "pl": "pl-PL",
               "ru": "ru-RU", "tr": "tr-TR", "ja": "ja-JP", "zh": "zh-CN",
               "ko": "ko-KR", "ar": "ar-SA", "vi": "vi-VN"}.get(source_lang, source_lang)

        box = QMessageBox()
        box.setWindowTitle(t("ocr_req_title"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(t("ocr_install_prompt", tag=tag))
        btn_install = box.addButton(t("ocr_install_btn"), QMessageBox.ButtonRole.AcceptRole)
        btn_quit = box.addButton(t("ocr_install_btn_quit"), QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() == btn_install:
            cmd = (
                f'Add-WindowsCapability -Online '
                f'-Name "Language.OCR~~~{tag}~0.0.1.0"'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "Start-Process", "powershell",
                 "-ArgumentList", f"'-NoProfile -ExecutionPolicy Bypass -Command \"{cmd}\"'",
                 "-Verb", "RunAs", "-Wait"],
                capture_output=True,
            )
            # Verifica se o OCR foi instalado com sucesso
            try:
                check_ocr_language(source_lang)
                QMessageBox.information(None, "PolyQuest", t("ocr_install_success"))
            except RuntimeError:
                QMessageBox.critical(None, "PolyQuest", t("ocr_install_failed"))
                sys.exit(1)
        else:
            sys.exit(1)

    translator = PolyQuest(full_config, _config_path())
    translator.register_hotkey()

    from PyQt6.QtCore import QTimer

    def _check_update():
        update = check_for_update()
        if update and update.get("version"):
            import webbrowser
            box = QMessageBox()
            box.setWindowTitle(t("update_available_title"))
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(t("update_available_msg",
                          version=update["version"],
                          message=update.get("message", "")))
            btn_dl = box.addButton(t("update_btn_download"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(t("update_btn_later"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == btn_dl and update.get("url"):
                webbrowser.open(update["url"])

    def _startup():
        _check_update()
        translator._open_settings()

    QTimer.singleShot(500, _startup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
