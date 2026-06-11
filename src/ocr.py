import asyncio
import io
from dataclasses import dataclass
from typing import List

from PIL import Image
from src.i18n import t
from winsdk.windows.globalization import Language
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

# Normaliza códigos curtos (ex: "en") para BCP-47 (ex: "en-US")
_LANG_MAP = {
    "en": "en-US", "pt": "pt-BR", "es": "es-ES", "fr": "fr-FR",
    "de": "de-DE", "it": "it-IT", "nl": "nl-NL", "pl": "pl-PL",
    "ru": "ru-RU", "tr": "tr-TR", "ja": "ja-JP", "zh": "zh-CN",
    "ko": "ko-KR", "ar": "ar-SA", "vi": "vi-VN",
}

# Cache de engines por idioma
_engine_cache: dict = {}


def check_ocr_language(lang: str = "en") -> None:
    """
    Verifica se o pacote de idioma está instalado no Windows OCR.
    Lança RuntimeError com instruções claras se não estiver.
    """
    tag = _LANG_MAP.get(lang, lang)
    if OcrEngine.try_create_from_language(Language(tag)) is None:
        raise RuntimeError(t("ocr_missing_lang", tag=tag))


def _get_engine(lang: str = "en") -> OcrEngine:
    global _engine_cache
    tag = _LANG_MAP.get(lang, lang)
    if tag not in _engine_cache:
        engine = OcrEngine.try_create_from_language(Language(tag))
        if engine is None:
            raise RuntimeError(t("ocr_unavailable", tag=tag))
        _engine_cache[tag] = engine
    return _engine_cache[tag]


@dataclass
class TextBlock:
    original: str
    translated: str
    x: int
    y: int
    w: int
    h: int
    line_h: int


async def _recognize(image: Image.Image, lang: str = "en"):
    # Converte PIL → BMP em memória (sem I/O de disco)
    buf = io.BytesIO()
    image.save(buf, format="BMP")
    bmp_data = buf.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(bmp_data)
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    stream.close()

    result = await _get_engine(lang).recognize_async(bitmap)
    return list(result.lines)


def extract_blocks(
    image: Image.Image,
    confidence_threshold: int = 35,
    lang: str = "en",
) -> List[TextBlock]:
    lines = asyncio.run(_recognize(image, lang))

    blocks = []
    for line in lines:
        words = list(line.words)
        if not words:
            continue

        text = " ".join(w.text for w in words).strip()
        if not text or not any(c.isalpha() for c in text):
            continue

        rects  = [w.bounding_rect for w in words]
        x      = int(min(r.x for r in rects))
        y      = int(min(r.y for r in rects))
        x2     = int(max(r.x + r.width  for r in rects))
        y2     = int(max(r.y + r.height for r in rects))
        w_px   = x2 - x
        h_px   = y2 - y
        line_h = int(rects[0].height) if rects else h_px

        blocks.append(TextBlock(
            original=text, translated="",
            x=x, y=y, w=w_px, h=h_px, line_h=line_h,
        ))

    blocks.sort(key=lambda b: (b.y, b.x))
    return blocks


def init_reader(lang: str = "en"):
    """Pré-aquece o engine do Windows OCR para o idioma especificado."""
    _get_engine(lang)
