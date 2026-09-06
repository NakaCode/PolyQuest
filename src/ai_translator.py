"""
Modo IA (BYOK): tradução via LLM com a API key do próprio usuário.
Suporta Claude (SDK oficial), Gemini e OpenAI (REST).

Contrato: translate_texts(...) retorna a lista de traduções na mesma ordem,
ou None em qualquer falha — o chamador cai no Google Translate.
"""

import json
import re
from typing import List

import requests

PROVIDERS = ["claude", "gemini", "openai"]

# Modelos rápidos/baratos por padrão: o usuário paga a própria key e traduz
# uma tela a cada poucos segundos — latência importa mais que teto de
# qualidade aqui. Para priorizar qualidade, troque p/ claude-opus-4-8 etc.
_CLAUDE_MODEL = "claude-haiku-4-5"
_GEMINI_MODEL = "gemini-2.5-flash"
_OPENAI_MODEL = "gpt-4o-mini"

_TIMEOUT = 25.0
_MAX_TEXTS_PER_CALL = 60

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def _system_prompt(source: str, target: str, glossary: list | None) -> str:
    src = "auto-detect the source language" if source == "auto" else f"from '{source}'"
    rules = [
        f"You translate text captured by OCR from a video game screen, {src} into '{target}'.",
        "The items belong to the same screen — use them as context for each other.",
        "Keep the tone and register of video games; keep UI terms short.",
        "Preserve numbers, symbols, placeholders and proper nouns.",
        "If an item is not translatable (numbers, codes), return it unchanged.",
        "Never add explanations or notes.",
    ]
    if glossary:
        fixed = "; ".join(
            f"'{e.get('original')}' -> '{e.get('translation')}'"
            for e in glossary
            if e.get("original") and e.get("translation")
        )
        if fixed:
            rules.append(f"Always use these fixed translations (any casing): {fixed}.")
    rules.append(
        'Respond ONLY with a JSON object {"translations": [...]} containing '
        "exactly one translated string per input item, in the same order."
    )
    return "\n".join(rules)


def _user_payload(texts: List[str]) -> str:
    return json.dumps({"items": texts}, ensure_ascii=False)


def _parse_translations(raw: str, expected: int) -> List[str] | None:
    """Extrai {"translations": [...]} da resposta, tolerando texto em volta."""
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except Exception:
        return None
    out = data.get("translations")
    if (
        isinstance(out, list)
        and len(out) == expected
        and all(isinstance(t, str) for t in out)
    ):
        return [t.strip() for t in out]
    return None


# ── Providers ───────────────────────────────────────────────────────

def _call_claude(system: str, payload: str, api_key: str, expected: int) -> List[str] | None:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=_TIMEOUT, max_retries=1)
        response = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": payload}],
            output_config={"format": {"type": "json_schema", "schema": _JSON_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        return _parse_translations(text, expected)
    except Exception:
        return None


def _call_gemini(system: str, payload: str, api_key: str, expected: int) -> List[str] | None:
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": payload}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_translations(text, expected)
    except Exception:
        return None


def _call_openai(system: str, payload: str, api_key: str, expected: int) -> List[str] | None:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": payload},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        text = resp.json()["choices"][0]["message"]["content"]
        return _parse_translations(text, expected)
    except Exception:
        return None


_CALLERS = {
    "claude": _call_claude,
    "gemini": _call_gemini,
    "openai": _call_openai,
}


def translate_texts(
    texts: List[str],
    source: str,
    target: str,
    provider: str,
    api_key: str,
    glossary: list | None = None,
) -> List[str] | None:
    """
    Traduz a lista inteira via LLM (em blocos de até 60 itens).
    Retorna None se QUALQUER bloco falhar — o chamador usa o fallback.
    """
    caller = _CALLERS.get(provider)
    if caller is None or not api_key or not texts:
        return None

    system = _system_prompt(source, target, glossary)
    results: List[str] = []
    for start in range(0, len(texts), _MAX_TEXTS_PER_CALL):
        chunk = texts[start:start + _MAX_TEXTS_PER_CALL]
        out = caller(system, _user_payload(chunk), api_key, len(chunk))
        if out is None:
            return None
        results.extend(out)
    return results
