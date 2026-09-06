import hashlib
import re
import sqlite3
import threading
import time
import unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import requests
from deep_translator import GoogleTranslator

from src.ocr import TextBlock

_NOISE_PATTERN = re.compile(r'^[\W\d_]+$')
_CONTROL_CHARS = re.compile(r'[\x00-\x1F\x7F]')

# ── Cache de traduções: LRU em memória + SQLite persistente ────────
_CACHE_MAX = 2048
_DISK_CACHE_MAX = 20000
_cache: OrderedDict[str, str] = OrderedDict()
_cache_hits = 0
_cache_misses = 0

_db: sqlite3.Connection | None = None
_db_lock = threading.Lock()
_pending_disk: list[tuple[str, str]] = []

# Textos que falharam por rede/API na última chamada de translate_blocks
# (permite ao app avisar o usuário em vez de falhar em silêncio)
_last_failures = 0


def get_last_failures() -> int:
    return _last_failures


def init_cache(path: Path | str) -> None:
    """Abre (ou cria) o cache persistente. Chamado uma vez no startup.
    Se o disco falhar, o app segue funcionando só com o cache em memória."""
    global _db
    try:
        db = sqlite3.connect(str(path), check_same_thread=False)
        db.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            " key TEXT PRIMARY KEY,"
            " translated TEXT NOT NULL,"
            " last_used INTEGER NOT NULL)"
        )
        count = db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        if count > _DISK_CACHE_MAX:
            db.execute(
                "DELETE FROM cache WHERE key IN ("
                " SELECT key FROM cache ORDER BY last_used ASC LIMIT ?)",
                (count - _DISK_CACHE_MAX,),
            )
        db.commit()
        _db = db
    except Exception:
        _db = None


def _cache_key(text: str, source: str, target: str) -> str:
    raw = f"{source}:{target}:{text}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _mem_put(key: str, translated: str) -> None:
    _cache[key] = translated
    _cache.move_to_end(key)
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _cache_get(text: str, source: str, target: str) -> str | None:
    global _cache_hits
    key = _cache_key(text, source, target)
    if key in _cache:
        _cache.move_to_end(key)
        _cache_hits += 1
        return _cache[key]
    if _db is not None:
        row = None
        try:
            with _db_lock:
                row = _db.execute(
                    "SELECT translated FROM cache WHERE key = ?", (key,)
                ).fetchone()
                if row:
                    _db.execute(
                        "UPDATE cache SET last_used = ? WHERE key = ?",
                        (int(time.time()), key),
                    )
        except Exception:
            row = None
        if row:
            _mem_put(key, row[0])
            _cache_hits += 1
            return row[0]
    return None


def _cache_put(text: str, source: str, target: str, translated: str) -> None:
    global _cache_misses
    key = _cache_key(text, source, target)
    _mem_put(key, translated)
    _cache_misses += 1
    with _db_lock:
        _pending_disk.append((key, translated))


def _flush_disk() -> None:
    """Grava as traduções novas no SQLite numa transação só (fim do ciclo)."""
    global _pending_disk
    if _db is None:
        with _db_lock:
            _pending_disk = []
        return
    try:
        with _db_lock:
            if not _pending_disk:
                _db.commit()  # persiste os updates de last_used das leituras
                return
            now = int(time.time())
            _db.executemany(
                "INSERT OR REPLACE INTO cache (key, translated, last_used)"
                " VALUES (?, ?, ?)",
                [(k, v, now) for k, v in _pending_disk],
            )
            _db.commit()
            _pending_disk = []
    except Exception:
        with _db_lock:
            _pending_disk = []


def get_cache_stats() -> dict:
    total = _cache_hits + _cache_misses
    disk = 0
    if _db is not None:
        try:
            with _db_lock:
                disk = _db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        except Exception:
            disk = 0
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "ratio": f"{(_cache_hits / total * 100):.0f}%" if total else "0%",
        "size": len(_cache),
        "disk": disk,
    }

# Presets de velocidade vs precisão
_MODES: dict = {
    "fast":     {"max_workers": 15, "min_letter_ratio": 0.6, "min_length": 3},
    "balanced": {"max_workers": 10, "min_letter_ratio": 0.4, "min_length": 2},
    "precise":  {"max_workers": 15, "min_letter_ratio": 0.25, "min_length": 1},
}

# ── Engine em lote (endpoint translate_a/t, um q por bloco) ────────
_BATCH_URL = "https://translate.googleapis.com/translate_a/t"
_BATCH_URL_ALT = "https://clients5.google.com/translate_a/t"
_BATCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
}
_CHUNK_MAX_CHARS = 3500
_CHUNK_WORKERS = 4


def _is_translatable(text: str, min_letter_ratio: float = 0.4, min_length: int = 2) -> bool:
    text = text.strip()
    if len(text) < min_length:
        return False
    letters = sum(1 for c in text if c.isalpha())
    if letters / len(text) < min_letter_ratio:
        return False
    if _NOISE_PATTERN.match(text):
        return False
    return True


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS.sub("", text).strip()


def _looks_valid(translated: str) -> bool:
    """
    Usa unicodedata para validar o resultado.
    Aceita letras de qualquer idioma (incluindo acentos do português),
    números, pontuação e espaços. Rejeita símbolos e caracteres de controle.
    """
    if not translated or not translated.strip():
        return False

    weird = 0
    for c in translated:
        cat = unicodedata.category(c)
        # L=letra, N=número, P=pontuação, Z=espaço, M=acento/marca
        if not cat.startswith(("L", "N", "P", "Z", "M")):
            weird += 1

    return (weird / len(translated)) <= 0.15


# Placeholders com ⟦n⟧: tradutores automáticos não mexem nesses colchetes
# matemáticos (os antigos __GL0__ eram traduzidos/deformados pelo Google).
_PH_PATTERN = re.compile(r"⟦\s*(\d+)\s*⟧")


def _apply_glossary(text: str, glossary: list) -> tuple[str, dict]:
    """
    Substitui termos do glossário por placeholders antes da tradução.
    Retorna o texto modificado e um mapa índice→tradução fixa.
    """
    placeholders = {}
    for i, entry in enumerate(glossary):
        orig = entry.get("original", "")
        if not orig:
            continue
        if re.search(re.escape(orig), text, re.IGNORECASE):
            text = re.sub(re.escape(orig), f"⟦{i}⟧", text, flags=re.IGNORECASE)
            placeholders[str(i)] = entry.get("translation", orig)
    return text, placeholders


def _restore_glossary(text: str, placeholders: dict) -> str:
    """Restore tolerante: aceita espaços que o tradutor insira dentro do ⟦n⟧."""
    return _PH_PATTERN.sub(
        lambda m: placeholders.get(m.group(1), m.group(0)), text
    )


def _translate_chunk_gtx(lines: List[str], source: str, target: str) -> list | None:
    """
    Traduz várias linhas numa única chamada HTTP: o endpoint translate_a/t
    aceita um parâmetro q por linha e devolve um array com uma tradução por q.
    Retorna None se falhar (rede, rate-limit, contagem divergente), para o
    chamador cair no fallback por bloco.
    """
    for url in (_BATCH_URL, _BATCH_URL_ALT):
        try:
            resp = requests.post(
                url,
                params={"client": "dict-chrome-ex", "sl": source, "tl": target},
                data=[("q", line) for line in lines],
                headers=_BATCH_HEADERS,
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if isinstance(data, str):
                data = [data]
            # Com sl=auto cada item vira [tradução, idioma]; normaliza
            out = [item[0] if isinstance(item, list) else item for item in data]
            if len(out) != len(lines) or not all(isinstance(o, str) for o in out):
                continue
            return [o.strip() for o in out]
        except Exception:
            continue
    return None


def _translate_one_text(text: str, source: str, target: str) -> str | None:
    """Fallback: traduz um texto isolado pelo engine antigo (deep_translator)."""
    try:
        result = GoogleTranslator(source=source, target=target).translate(text)
        return result.strip() if result else None
    except Exception:
        return None


def _make_chunks(texts: List[str], max_chars: int = _CHUNK_MAX_CHARS) -> List[List[str]]:
    chunks: List[List[str]] = []
    current: List[str] = []
    size = 0
    for text in texts:
        if current and size + len(text) + 1 > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(text)
        size += len(text) + 1
    if current:
        chunks.append(current)
    return chunks


def translate_blocks(
    blocks: List[TextBlock],
    source: str = "en",
    target: str = "pt",
    mode: str = "balanced",
    glossary: list | None = None,
) -> List[TextBlock]:
    global _last_failures
    _last_failures = 0
    if not blocks:
        return blocks

    preset = _MODES.get(mode, _MODES["balanced"])
    min_ratio = preset["min_letter_ratio"]
    min_len = preset["min_length"]

    # Fase 1: filtra, aplica glossário e resolve pelo cache.
    # O cache guarda a tradução ANTES do restore do glossário, com a chave
    # calculada sobre o texto já com placeholders — assim editar o glossário
    # nunca serve tradução velha do cache persistente.
    pending: list[tuple[TextBlock, str, dict]] = []
    for block in blocks:
        if not _is_translatable(block.original, min_ratio, min_len):
            block.translated = block.original
            continue
        clean = _sanitize(block.original)
        if glossary:
            gtext, placeholders = _apply_glossary(clean, glossary)
        else:
            gtext, placeholders = clean, {}
        cached = _cache_get(gtext, source, target)
        if cached is not None:
            block.translated = _restore_glossary(cached, placeholders) if placeholders else cached
            continue
        pending.append((block, gtext, placeholders))

    if not pending:
        _flush_disk()
        return blocks

    # Fase 2: dedupe (telas de jogo repetem muito texto) e tradução em lote.
    unique: dict[str, list] = {}
    for item in pending:
        unique.setdefault(item[1], []).append(item)

    chunks = _make_chunks(list(unique.keys()))
    results: dict[str, str | None] = {}
    failed: List[str] = []

    with ThreadPoolExecutor(max_workers=min(_CHUNK_WORKERS, len(chunks))) as executor:
        futures = {
            executor.submit(_translate_chunk_gtx, chunk, source, target): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk = futures[future]
            out = future.result()
            if out is None:
                failed.extend(chunk)
            else:
                for text, translated in zip(chunk, out):
                    results[text] = translated

    # Fase 3: fallback por bloco (engine antigo) para o que o lote não resolveu.
    if failed:
        with ThreadPoolExecutor(max_workers=min(preset["max_workers"], len(failed))) as executor:
            futures = {
                executor.submit(_translate_one_text, text, source, target): text
                for text in failed
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()

    # Fase 4: valida, preenche os blocos e persiste o cache.
    _last_failures = sum(1 for gtext in unique if results.get(gtext) is None)
    for gtext, items in unique.items():
        translated = results.get(gtext)
        if translated and _looks_valid(translated):
            _cache_put(gtext, source, target, translated)
            for block, _, placeholders in items:
                block.translated = _restore_glossary(translated, placeholders) if placeholders else translated
        else:
            for block, _, _ in items:
                block.translated = block.original

    _flush_disk()
    return blocks
