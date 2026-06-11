"""
Sistema de licenciamento do PolyQuest.
Valida chave de licença via Supabase e vincula ao hardware da máquina.
"""

import hashlib
import json
import platform
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

# ── Supabase config ──────────────────────────────────────────────────
# TODO: substituir pelos valores reais do seu projeto Supabase
SUPABASE_URL = "https://mckcypgoimtjsxngkelh.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ja2N5cGdvaW10anN4bmdrZWxoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3NjY5NDMsImV4cCI6MjA5MTM0Mjk0M30.5wHrlq0PrDTkxTURa2hSqPHPQS0vvrswz-lRkCQozGM"

_ACTIVATE_URL = f"{SUPABASE_URL}/functions/v1/activate"
_CHECK_URL = f"{SUPABASE_URL}/functions/v1/check-license"

_LICENSE_FILE = ".polyquest_license"


def _base_path() -> Path:
    """Retorna o diretório do executável ou do script."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _license_path() -> Path:
    return _base_path() / _LICENSE_FILE


# ── Hardware ID ──────────────────────────────────────────────────────

def get_hardware_id() -> str:
    """
    Gera um ID único da máquina baseado em:
    - Nome do computador
    - Identificador do volume C:
    - Processador
    Resultado: hash SHA-256 truncado (32 chars).
    """
    parts = []

    # Nome do computador
    parts.append(platform.node())

    # Processador
    parts.append(platform.processor())

    # UUID da máquina (Windows) — tenta PowerShell primeiro, depois wmic
    try:
        output = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"],
            text=True, timeout=5, creationflags=0x08000000,
        )
        uuid = output.strip()
        if uuid:
            parts.append(uuid)
    except Exception:
        try:
            output = subprocess.check_output(
                "wmic csproduct get uuid",
                shell=True, text=True, timeout=5,
            )
            uuid = output.strip().split("\n")[-1].strip()
            if uuid and uuid != "UUID":
                parts.append(uuid)
        except Exception:
            pass

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Armazenamento local ─────────────────────────────────────────────

def _save_local(data: dict) -> None:
    """Salva dados de licença localmente (ofuscado em base64)."""
    import base64
    payload = json.dumps(data, ensure_ascii=False)
    encoded = base64.b64encode(payload.encode()).decode()
    _license_path().write_text(encoded, encoding="utf-8")


def _load_local() -> dict | None:
    """Carrega dados de licença local."""
    import base64
    path = _license_path()
    if not path.exists():
        return None
    try:
        encoded = path.read_text(encoding="utf-8").strip()
        payload = base64.b64decode(encoded).decode()
        return json.loads(payload)
    except Exception:
        return None


def _clear_local() -> None:
    """Remove o arquivo de licença local."""
    path = _license_path()
    if path.exists():
        path.unlink()


# ── API calls ────────────────────────────────────────────────────────

def _api_call(url: str, data: dict) -> dict:
    """Faz uma chamada POST para a API do Supabase."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "apikey": SUPABASE_ANON_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return {"ok": False, "error": body.get("error", str(e))}
        except Exception:
            return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Funções públicas ─────────────────────────────────────────────────

def activate(license_key: str) -> dict:
    """
    Tenta ativar uma chave de licença.
    Retorna: {"ok": True} ou {"ok": False, "error": "mensagem"}
    """
    key = license_key.strip().upper()
    hwid = get_hardware_id()

    result = _api_call(_ACTIVATE_URL, {
        "key": key,
        "hwid": hwid,
    })

    if result.get("ok"):
        _save_local({
            "key": key,
            "hwid": hwid,
            "activated_at": result.get("activated_at", ""),
        })
        return {"ok": True}

    return {"ok": False, "error": result.get("error", "Erro desconhecido")}


def deactivate() -> None:
    """Remove a licença local."""
    _clear_local()


def is_premium() -> bool:
    """
    Verifica se o app está ativado como Premium.
    Checa: arquivo local existe e hwid bate com a máquina atual.
    """
    data = _load_local()
    if not data:
        return False

    # Verifica se o hwid salvo bate com o da máquina
    if data.get("hwid") != get_hardware_id():
        _clear_local()
        return False

    return True


def validate_online() -> dict:
    """
    Valida a licença online (chamada opcional, ex: a cada X dias).
    Retorna: {"ok": True, "premium": True/False} ou {"ok": False, "error": ...}
    """
    data = _load_local()
    if not data:
        return {"ok": True, "premium": False}

    result = _api_call(_CHECK_URL, {
        "key": data.get("key", ""),
        "hwid": data.get("hwid", ""),
    })

    if result.get("ok") and result.get("valid"):
        return {"ok": True, "premium": True}

    # Licença inválida no servidor — remove local
    if result.get("ok") and not result.get("valid"):
        _clear_local()
        return {"ok": True, "premium": False}

    # Sem internet — mantém o estado local
    return {"ok": False, "error": result.get("error", ""), "premium": True}


def get_license_info() -> dict | None:
    """Retorna info da licença local ou None se não ativada."""
    return _load_local()
