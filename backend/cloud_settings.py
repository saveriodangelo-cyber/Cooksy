from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    """Percorso del file configurazione Cloud AI.

    Lo teniamo in data/config per essere portabile e facile da backuppare.
    """
    root = _project_root()
    p = root / "data" / "config" / "cloud_ai.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_env_file(env_file: str = ".env.local") -> None:
    """Carica variabili da .env.local se esiste (per sviluppo)."""
    root = _project_root()
    env_path = root / env_file
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass


def _default_settings() -> Dict[str, Any]:
    return {
        "enabled": False,
        "provider": "auto",  # auto | openai | gemini | offline
        "openai": {"api_key": "", "model": "gpt-4.1-mini"},
        "gemini": {"api_key": "", "model": "gemini-1.5-flash"},
    }


def load_settings() -> Dict[str, Any]:
    # Carica variabili d'ambiente da .env.local (se esiste)
    _load_env_file(".env.local")
    
    p = config_path()
    if not p.exists():
        s = _default_settings()
        save_settings(s)
        return s

    try:
        raw = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    base = _default_settings()
    # merge shallow
    for k, v in data.items():
        if k in ("enabled", "provider"):
            base[k] = v
        elif k in ("openai", "gemini") and isinstance(v, dict):
            base[k].update(v)

    # normalizza tipi
    base["enabled"] = bool(base.get("enabled"))
    prov = str(base.get("provider") or "auto").lower().strip()
    if prov not in {"auto", "openai", "gemini", "offline"}:
        prov = "auto"
    base["provider"] = prov

    base.setdefault("openai", {})
    base.setdefault("gemini", {})
    
    # Carica chiave API da variabile d'ambiente se disponibile (SECURE)
    # Fallback a file config per retrocompatibilita'
    openai_key = os.environ.get("RICETTEPDF_OPENAI_KEY", "").strip()
    if not openai_key:
        openai_key = str(base.get("openai", {}).get("api_key") or "").strip()
    base["openai"]["api_key"] = openai_key
    
    base["openai"].setdefault("model", "gpt-4.1-mini")
    base["gemini"].setdefault("api_key", "")
    base["gemini"].setdefault("model", "gemini-1.5-flash")

    return base


def save_settings(settings: Dict[str, Any]) -> None:
    p = config_path()
    try:
        p.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # non far crashare
        return


def masked_settings_for_ui(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ritorna un dict adatto alla UI: non espone le chiavi in chiaro."""
    s = settings if isinstance(settings, dict) else load_settings()

    def mask(k: str) -> str:
        if not k:
            return ""
        ks = str(k)
        if len(ks) <= 8:
            return "****"
        return ("*" * (len(ks) - 4)) + ks[-4:]

    out = {
        "enabled": bool(s.get("enabled")),
        "provider": str(s.get("provider") or "auto"),
        "openai": {
            "has_key": bool((s.get("openai") or {}).get("api_key")),
            "api_key_masked": mask((s.get("openai") or {}).get("api_key") or ""),
            "model": str((s.get("openai") or {}).get("model") or "gpt-4.1-mini"),
        },
        "gemini": {
            "has_key": bool((s.get("gemini") or {}).get("api_key")),
            "api_key_masked": mask((s.get("gemini") or {}).get("api_key") or ""),
            "model": str((s.get("gemini") or {}).get("model") or "gemini-1.5-flash"),
        },
    }
    return out


def update_settings_from_ui(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna settings con i valori forniti dalla UI.

    Regola: se api_key è stringa vuota, non sovrascrive quella esistente.
    """
    current = load_settings()
    if not isinstance(payload, dict):
        return current

    if "enabled" in payload:
        current["enabled"] = bool(payload.get("enabled"))

    if "provider" in payload:
        prov = str(payload.get("provider") or "auto").lower().strip()
        if prov in {"auto", "openai", "gemini", "offline"}:
            current["provider"] = prov

    for prov_key in ("openai", "gemini"):
        block = payload.get(prov_key)
        if not isinstance(block, dict):
            continue
        cur_block = current.setdefault(prov_key, {})

        # model
        if "model" in block and str(block.get("model") or "").strip():
            cur_block["model"] = str(block.get("model")).strip()

        # api key: aggiorna solo se non vuota
        if "api_key" in block:
            newk = str(block.get("api_key") or "").strip()
            if newk:
                cur_block["api_key"] = newk

    save_settings(current)
    return current
