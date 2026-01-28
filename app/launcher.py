# app/launcher.py
# ============================================================================
# COOKSY - Recipe Management Software
# Copyright © 2026 - Tutti i diritti riservati
# Licenza Proprietaria - Vedi LICENSE.md e TERMS_AND_CONDITIONS.md
# ============================================================================
# AVVISO LEGALE: Questo software è fornito sotto licenza proprietaria.
# L'uso non autorizzato, la copia, modifica o distribuzione è vietato.
# ============================================================================

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, cast
from http.server import HTTPServer, SimpleHTTPRequestHandler

import webview

# Carica variabili d'ambiente da .env e .env.local
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    # Carica anche .env.local per overriding locale (es. Stripe keys)
    _env_local_path = Path(__file__).resolve().parents[1] / ".env.local"
    if _env_local_path.exists():
        load_dotenv(_env_local_path)
except ImportError:
    pass  # dotenv opzionale

# GUIType non è sempre esportato direttamente: fallback a Any per tenere typing leggero
try:
    from webview.guilib import GUIType  # type: ignore
except Exception:  # pragma: no cover
    from typing import Any as GUIType  # type: ignore

from backend.bridge import Bridge


def _sys_base() -> Path:
    """Determina la base del sistema (dove è l'EXE o lo script)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return _project_root()

# Progress lives in backend/progress.py in the original project.
# Some previous patches imported it from backend.bridge by mistake.
try:
    from backend.progress import Progress as _Progress  # type: ignore
except Exception:  # pragma: no cover
    _Progress = None  # type: ignore


def _project_root() -> Path:
    # .../app/launcher.py -> root progetto
    return Path(__file__).resolve().parents[1]


def _ui_path() -> Path:
    """Trova il percorso della directory ui/"""
    possible_paths = [
        _project_root() / "ui",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        possible_paths.append(exe_dir / "_internal" / "ui")
    possible_paths.append(Path.cwd() / "ui")
    
    for ui_dir in possible_paths:
        if (ui_dir / "index.html").exists():
            return ui_dir
    
    return _project_root() / "ui"


def _start_local_http_server(ui_path: Path, port: int = 35432) -> tuple[HTTPServer, threading.Thread]:
    """Avvia un HTTP server locale per servire la UI. Necessario per WebAuthn."""
    
    class UIHandler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            # Servire tutto da ui_path
            if path == "/" or path == "":
                path = "/index.html"
            return str(ui_path / path.lstrip("/"))
        
        def end_headers(self):
            # Aggiungi header per WebAuthn
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()
        
        def log_message(self, format, *args):
            # Silenzioso
            pass
    
    os.chdir(ui_path)
    server = HTTPServer(("127.0.0.1", port), UIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _ui_url() -> str:
    """Ritorna URL localhost per UI (WebAuthn richiede secure context)"""
    port = int(os.environ.get("RICETTEPDF_UI_PORT", "35432"))
    return f"http://127.0.0.1:{port}/"


def _is_first_install() -> bool:
    """Controlla se è il primo avvio da EXE compilato (fresh install)"""
    import sys
    if getattr(sys, 'frozen', False):
        # App compilata con PyInstaller
        marker_file = Path(_sys_base()) / ".first_run_completed"
        is_first = not marker_file.exists()
        if is_first:
            try:
                marker_file.touch()
            except Exception:
                pass
        return is_first
    return False


def _ui_url() -> str:
    """Ritorna URL localhost per UI (WebAuthn richiede secure context)"""
    port = int(os.environ.get("RICETTEPDF_UI_PORT", "35432"))
    return f"http://127.0.0.1:{port}/"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _make_progress() -> Any:
    """Create a Progress instance if available; otherwise return a light stub."""
    if _Progress is not None:
        try:
            return _Progress()
        except Exception:
            pass
    # Minimal stub compatible with most progress consumers
    return {"pct": 0, "stage": "idle", "msg": ""}


def _set_bridge_window(bridge: Bridge, window: Optional[webview.Window]) -> None:
    """Support multiple historical Bridge implementations."""
    if window is None:
        return
    if hasattr(bridge, "set_window"):
        try:
            bridge.set_window(window)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    try:
        setattr(bridge, "_window", window)
    except Exception:
        pass


def main() -> None:
    # Force debug=False in production (exe builds)
    import sys
    is_frozen = getattr(sys, 'frozen', False)
    debug = False if is_frozen else _env_bool("RICETTEPDF_DEBUG", default=False)

    # SAFE mode: avoids resize/fullscreen edge cases on some Windows setups.
    safe = _env_bool("RICETTEPDF_SAFE", default=False)

    # Optional GUI override: auto | edgechromium | cef | mshtml
    gui_raw = (os.environ.get("RICETTEPDF_GUI") or "").strip().lower()
    gui: Optional[GUIType] = None
    gui_choices = {"qt", "gtk", "cef", "mshtml", "edgechromium", "android"}
    if gui_raw in gui_choices:
        gui = cast(GUIType, gui_raw)
    # Prefer Edge (WebView2) in frozen builds for best compatibility
    if is_frozen and not gui:
        gui = cast(GUIType, "edgechromium")

    try:
        webview.settings["ALLOW_CONTEXT_MENU"] = True
    except Exception:
        pass

    progress = _make_progress()
    bridge = Bridge(progress=progress)
    
    # Avvia HTTP server per servire UI via localhost (richiesto per WebAuthn)
    ui_path = _ui_path()
    port = int(os.environ.get("RICETTEPDF_UI_PORT", "35432"))
    server, server_thread = _start_local_http_server(ui_path, port)
    time.sleep(0.5)  # Attendi che il server sia pronto
    
    # Imposta variabili d'ambiente per WebAuthn rpId/origin se non già presenti
    if "WEBAPP_RP_ID" not in os.environ:
        os.environ["WEBAPP_RP_ID"] = "localhost"
    if "WEBAPP_ORIGIN" not in os.environ:
        os.environ["WEBAPP_ORIGIN"] = f"http://127.0.0.1:{port}"
    
    # Rimosso: bypass automatico dei termini non più necessario

    url = _ui_url()

    window = webview.create_window(
        title="RicettePDF",
        url=url,
        js_api=bridge,
        width=1400 if not safe else 1200,
        height=900 if not safe else 800,
        resizable=(not safe),
        min_size=(1100, 700),
    )

    _set_bridge_window(bridge, window)

    # IMPORTANT: create_window must be called before start (otherwise pywebview raises).
    # Start with preferred GUI and gracefully fallback if not available
    try:
        if gui:
            webview.start(debug=debug, gui=gui)
        else:
            webview.start(debug=debug)
    except Exception as e:
        try:
            print(f"[WARN] Edge/WebView2 not available: {e}. Falling back to default engine.")
            webview.start(debug=debug)
        except Exception as e2:
            print(f"[FATAL] UI start failed: {e2}")
            raise


if __name__ == "__main__":
    # Verifica licenza all'avvio
    try:
        from backend.license_manager import check_or_create_license
        check_or_create_license()
    except Exception as e:
        print(f"[WARN] License check failed: {e}")
    
    main()
