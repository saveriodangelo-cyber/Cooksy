from __future__ import annotations

import os
import time
import re
import sys
import json
import shutil
import subprocess
import threading
import hashlib
from threading import Lock
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from backend.app_logging import get_logger, log_event, truncate_text
from backend.subscription_manager import SubscriptionManager
from backend.user_manager import UserManager
from backend.utils import project_root
try:
    from backend.stripe_manager import StripeManager
    _stripe_available = True
except ImportError:
    _stripe_available = False
    StripeManager = None  # type: ignore
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

def _snapshot_from_progress_obj(progress_obj: Any) -> Dict[str, Any]:
    try:
        if progress_obj is None:
            return {"pct": 0, "stage": "idle", "msg": ""}

        if isinstance(progress_obj, dict):
            return {
                "pct": int(progress_obj.get("pct", 0) or 0),
                "stage": str(progress_obj.get("stage", "idle") or "idle"),
                "msg": str(progress_obj.get("msg", "") or ""),
            }

        if hasattr(progress_obj, "snapshot"):
            try:
                snap = progress_obj.snapshot()
                if hasattr(snap, "to_dict"):
                    sd = snap.to_dict()
                    if isinstance(sd, dict):
                        return {
                            "pct": int(sd.get("pct", 0) or 0),
                            "stage": str(sd.get("stage", "idle") or "idle"),
                            "msg": str(sd.get("msg", sd.get("message", "")) or ""),
                        }
            except Exception:
                pass

        if hasattr(progress_obj, "pct") or hasattr(progress_obj, "stage") or hasattr(progress_obj, "msg"):
            return {
                "pct": int(getattr(progress_obj, "pct", 0) or 0),
                "stage": str(getattr(progress_obj, "stage", "idle") or "idle"),
                "msg": str(getattr(progress_obj, "msg", "") or ""),
            }

        if hasattr(progress_obj, "get"):
            snap = progress_obj.get()
            if isinstance(snap, dict):
                return {
                    "pct": int(snap.get("pct", 0) or 0),
                    "stage": str(snap.get("stage", "idle") or "idle"),
                    "msg": str(snap.get("msg", "") or ""),
                }
    except Exception:
        pass

    return {"pct": 0, "stage": "idle", "msg": ""}


def _kind_from_path(path: str) -> str:
    ext = (Path(path).suffix or "").lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx", ".doc"}:
        return "word"
    if ext in {".txt", ".log"}:
        return "txt"
    return "file"


def _file_hash(filepath: Path) -> str:
    """Calcola MD5 hash di un file per identificarlo univocamente.
    Usa memory-mapping per file >1MB per migliori performance.
    """
    try:
        md5 = hashlib.md5()
        file_size = filepath.stat().st_size
        
        # Per file grandi usa mmap (più veloce)
        if file_size > 1_048_576:  # >1MB
            import mmap
            with open(filepath, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    md5.update(mm)
        else:
            # File piccoli: lettura normale
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return ""


def _load_processed_cache(cache_path: Path) -> Dict[str, Any]:
    """Carica la cache dei file già processati."""
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_processed_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    """Salva la cache dei file processati."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def _is_file_processed(filepath: Path, cache: Dict[str, Any], method: str = "hash") -> bool:
    """Verifica se un file è già stato processato.
    
    Args:
        filepath: Percorso del file
        cache: Dizionario cache dei file processati
        method: "hash" (confronto MD5) o "name" (confronto per nome)
    """
    if method == "name":
        # Confronto per nome: il file è processato se esiste un entry con lo stesso nome
        return filepath.name in cache
    
    # Metodo default: confronto per hash
    file_key = filepath.name
    if file_key not in cache:
        return False
    entry = cache[file_key]
    if not isinstance(entry, dict):
        return False
    cached_hash = entry.get('hash', '')
    if not cached_hash:
        return False
    current_hash = _file_hash(filepath)
    return current_hash == cached_hash and current_hash != ""


def _mark_file_processed(filepath: Path, cache: Dict[str, Any], title: str = "") -> None:
    """Marca un file come processato nella cache."""
    from datetime import datetime
    file_hash = _file_hash(filepath)
    if not file_hash:
        return
    cache[filepath.name] = {
        'hash': file_hash,
        'processed_at': datetime.now().isoformat(timespec='seconds'),
        'title': title,
        'path': str(filepath.absolute())
    }


def _open_path(path: str) -> None:
    if not path:
        return

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
        return

    subprocess.Popen(["xdg-open", path])


def _default_output_dir() -> str:
    try:
        if sys.platform.startswith("win"):
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                ) as k:
                    desktop, _ = winreg.QueryValueEx(k, "Desktop")
                if desktop:
                    desktop = os.path.expandvars(str(desktop))
                    return str((Path(desktop) / "Elaborate").resolve())
            except Exception:
                pass

        user_home = os.environ.get("USERPROFILE") or str(Path.home())
        home = Path(user_home)
        desktop = home / "Desktop"
        base = desktop if desktop.exists() else home
        return str((base / "Elaborate").resolve())
    except Exception:
        return str((Path(".") / "Elaborate").resolve())


def _ensure_elaborate_dir(path: Optional[str]) -> str:
    try:
        raw = str(path or "").strip()
        if not raw:
            return _default_output_dir()
        p = Path(raw)
        if p.name.lower() == "elaborate":
            return str(p.resolve())
        return str((p / "Elaborate").resolve())
    except Exception:
        return _default_output_dir()


def _safe_filename(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "ricetta"
    n = n.replace("-", " ").replace("_", " ")
    n = re.sub(r"[\/:*?\"<>|]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n[:120] if len(n) > 120 else n


def _natural_sort_key(s: str) -> List[Any]:
    """Chiave di ordinamento naturale (file1, file2, file10)."""
    try:
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]
    except Exception:
        return [str(s).lower()]


class Bridge:
    def __init__(self, *args: Any, progress: Any = None, **kwargs: Any) -> None:
        self._window: Any = None
        self._progress: Any = progress
        self._selected_paths: List[str] = []
        self._output_dir: Optional[str] = _ensure_elaborate_dir(_default_output_dir())
        self._terms_bypass_fresh_install: bool = False

        # Subscription manager
        self._subscription_mgr = SubscriptionManager()
        self._user_mgr = UserManager()
        self._current_user_id = "default_user"  # default finché non esegui login
        self._session_token: Optional[str] = None
        self._analysis_usage_recorded: bool = False
        
        # Stripe manager (opzionale)
        self._stripe_mgr = StripeManager() if _stripe_available else None

        # Analisi asincrona (per progresso reale in UI)
        self._analysis_lock = Lock()
        self._analysis_thread: Optional[threading.Thread] = None
        self._analysis_running: bool = False
        self._analysis_result: Optional[Dict[str, Any]] = None
        self._analysis_error: Optional[str] = None

        # Batch cartella (analisi in serie + export)
        self._input_dir: Optional[str] = None
        self._batch_lock = Lock()
        self._batch_thread: Optional[threading.Thread] = None
        self._batch_running: bool = False
        self._batch_abort: bool = False
        self._batch_state: Dict[str, Any] = {
            "input_dir": None,
            "output_dir": None,
            "template": None,
            "total": 0,
            "done": 0,
            "errors": 0,
            "items": [],
            "current_file": None,
            "current_path": None,
            "timeout_pending": False,
            "timeout_file": None,
            "timeout_started_at": None,
            "timeout_decision": None,
            "started_at": None,
            "finished_at": None,
        }
        self._batch_error: Optional[str] = None

        self._run_id: str = str(uuid.uuid4())
        self._logger = get_logger(self._run_id)

        # Archivio ricette (SQLite)
        self._archive_db: Any = None
        
        # Inject Stripe integration methods
        from backend.stripe_bridge_integration import inject_stripe_methods
        inject_stripe_methods(self)

    def _get_archive_db(self) -> Any:
        if self._archive_db is None:
            from backend.archive_db import ArchiveDB
            self._archive_db = ArchiveDB.default()
        return self._archive_db

    # ===== SECURITY: CSRF Token Validation =====
    def _validate_csrf(self, payload: Dict[str, Any]) -> bool:
        """
        Valida il token CSRF dalla richiesta.
        Il token deve essere un esadecimale di 64 caratteri (256-bit hex).
        In un'app PyWebView locale, il token viene generato dal frontend 
        e memorizzato in sessionStorage. Questo è principalmente una protezione
        per quando l'app potrebbe essere accessibile via network.
        """
        try:
            csrf_token = payload.get('_csrf')
            if not csrf_token:
                return False
            # Token deve essere esadecimale a 64 caratteri (256-bit)
            if not isinstance(csrf_token, str) or len(csrf_token) != 64:
                return False
            # Verifica che sia valido esadecimale
            int(csrf_token, 16)
            return True
        except (ValueError, TypeError):
            return False

    def set_window(self, window: Any) -> None:
        self._window = window

    def exit_app(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Chiude l'applicazione. Usato quando l'utente rifiuta i Termini e Condizioni."""
        try:
            if self._window:
                self._window.destroy()
            else:
                # Fallback: usa sys.exit
                sys.exit(0)
            return {"ok": True}
        except Exception as e:
            print(f"[ERROR] exit_app failed: {e}", file=sys.stderr)
            sys.exit(1)
            return {"ok": False, "error": str(e)}

    def get_progress(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return _snapshot_from_progress_obj(self._progress)

    def get_default_output_dir(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            path = _ensure_elaborate_dir(self._output_dir or _default_output_dir())
            self._output_dir = path
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _record_ai_usage(self, recipe: Dict[str, Any]) -> None:
        try:
            if not isinstance(recipe, dict):
                return
            provider = None
            ai_meta = recipe.get("ai_completion")
            if isinstance(ai_meta, dict):
                provider = ai_meta.get("provider")
            if not provider:
                cloud_meta = recipe.get("cloud_ai")
                if isinstance(cloud_meta, dict):
                    provider = cloud_meta.get("provider") or cloud_meta.get("name") or cloud_meta.get("id")
            if not provider:
                return
            user_id = getattr(self, "_current_user_id", None) or "default_user"
            if user_id == "default_user":
                return
            self._subscription_mgr.record_api_call(user_id)
        except Exception:
            # uso best-effort: non blocca il flusso principale
            pass

    # ============ AUTH (LOCAL) ============

    def auth_register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Registra un nuovo utente locale.
        payload: { email, password, username }
        """
        try:
            # SECURITY: Validate CSRF token
            if not self._validate_csrf(payload):
                return {"ok": False, "error": "CSRF token invalid or missing"}

            email = str(payload.get("email", "") or "").strip()
            password = str(payload.get("password", "") or "")
            username = payload.get("username")
            out = self._user_mgr.register(email, password, username=username)
            return out
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def auth_login(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Esegue login, crea sessione, imposta utente corrente."""
        try:
            # SECURITY: Validate CSRF token
            if not self._validate_csrf(payload):
                return {"ok": False, "error": "CSRF token invalid or missing"}

            email = str(payload.get("email", "") or "").strip()
            password = str(payload.get("password", "") or "")
            auth = self._user_mgr.authenticate(email, password)
            if not auth.get("ok"):
                return auth
            self._current_user_id = str(auth.get("user_id"))
            self._session_token = str(auth.get("token"))
            return {"ok": True, "user_id": self._current_user_id, "token": self._session_token}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def auth_me(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ritorna info utente corrente (validando token se presente)."""
        try:
            token = payload.get("token") or self._session_token
            if token:
                valid = self._user_mgr.validate_session(str(token))
                if valid.get("ok"):
                    self._current_user_id = str(valid.get("user_id"))
                    if valid.get("rotated"):
                        self._session_token = valid.get("token") or self._session_token
                else:
                    return valid
            user = self._user_mgr.get_user(self._current_user_id)
            if not user:
                return {"ok": False, "error": "Utente non trovato"}
            quota = self._subscription_mgr.check_quota(self._current_user_id)
            return {
                "ok": True,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                },
                "quota": quota,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def auth_logout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            token = str(payload.get("token") or self._session_token or "")
            if not token:
                return {"ok": True}
            self._user_mgr.logout(token)
            self._session_token = None
            self._current_user_id = "default_user"
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ============ 2FA EMAIL/SMS OTP ============
    def otp_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Genera e invia OTP via email o SMS.
        payload: { email, purpose: 'registration' | 'login', method: 'email' | 'sms' }
        """
        try:
            email = str(payload.get("email", "")).strip().lower()
            purpose = str(payload.get("purpose", "registration"))
            method = str(payload.get("method", "email")).lower()
            
            if not email:
                return {"ok": False, "error": "Email richiesta"}
            
            if method not in ("email", "sms"):
                method = "email"
            
            otp_code = self._user_mgr.generate_email_otp(email, purpose=purpose)
            result = self._user_mgr.send_otp(email, otp_code, method=method)
            
            if not result.get("ok"):
                return result

            return {"ok": True, "message": f"OTP inviato via {method}", "method": method}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def otp_verify(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica l'OTP inviato.
        payload: { email, otp_code, purpose }
        """
        try:
            email = str(payload.get("email", "")).strip().lower()
            otp_code = str(payload.get("otp_code", "")).strip()
            purpose = str(payload.get("purpose", "registration"))
            
            if not email or not otp_code:
                return {"ok": False, "error": "Email e OTP richiesti"}
            
            return self._user_mgr.verify_email_otp(email, otp_code, purpose=purpose)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ============ PASSKEY / WEBAUTHN ============

    def passkey_start_registration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_id = str(payload.get("user_id", "")).strip()
            email = str(payload.get("email", "")).strip().lower()
            username = str(payload.get("username", "")).strip() or None
            if not user_id or not email:
                return {"ok": False, "error": "User id ed email richiesti"}
            return self._user_mgr.webauthn_start_registration(user_id, email, username=username)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def passkey_finish_registration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._user_mgr.webauthn_finish_registration(
                user_id=str(payload.get("user_id", "")),
                credential_id=str(payload.get("credential_id", "")),
                attestation_object=str(payload.get("attestation_object", "")),
                client_data_json=str(payload.get("client_data_json", "")),
                challenge=str(payload.get("challenge", "")),
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_user_by_email(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Cerca user_id da email per passkey login.
        payload: { email }
        """
        try:
            email = str(payload.get("email", "")).strip().lower()
            if not email:
                return {"ok": False, "error": "Email richiesta"}
            conn = self._user_mgr._conn()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return {"ok": False, "error": "Utente non trovato"}
            return {"ok": True, "user_id": row[0]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def user_login(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Login tradizionale via email/password.
        payload: { email, password }
        """
        try:
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", "")).strip()
            if not email or not password:
                return {"ok": False, "error": "Email e password richiesti"}
            result = self._user_mgr.authenticate(email, password)
            if result.get("ok"):
                # Crea sessione
                user_id = result.get("user_id")
                session_token = self._user_mgr.create_session(str(user_id)) if user_id else ""
                return {
                    "ok": True,
                    "user_id": user_id,
                    "session_token": session_token,
                }
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def register_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Registrazione nuovo utente via email/password.
        payload: { email, password, username? }
        """
        try:
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", "")).strip()
            username = str(payload.get("username", "")).strip() or None
            if not email or not password:
                return {"ok": False, "error": "Email e password richiesti"}
            return self._user_mgr.register(email, password, username=username)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def passkey_start_assertion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_id = str(payload.get("user_id", "")).strip()
            if not user_id:
                return {"ok": False, "error": "User id richiesto"}
            return self._user_mgr.webauthn_start_assertion(user_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def passkey_finish_assertion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._user_mgr.webauthn_finish_assertion(
                user_id=str(payload.get("user_id", "")),
                credential_id=str(payload.get("credential_id", "")),
                authenticator_data=str(payload.get("authenticator_data", "")),
                client_data_json=str(payload.get("client_data_json", "")),
                signature=str(payload.get("signature", "")),
                challenge=str(payload.get("challenge", "")),
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ui_validation(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        candidates = [
            Path("data") / "ui_validation.json",
            Path("data") / "validation" / "ui_validation.json",
        ]
        for p in candidates:
            try:
                if p.exists() and p.is_file():
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return {"ok": True, "rules": data, "path": str(p)}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}

        return {"ok": True, "rules": None, "path": None}

    def ocr_status(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        def _check_import(mod_name: str) -> Dict[str, Any]:
            try:
                __import__(mod_name)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}

        status: Dict[str, Any] = {
            "pytesseract": _check_import("pytesseract"),
            "easyocr": _check_import("easyocr"),
            "paddleocr": _check_import("paddleocr"),
            "rapidocr_onnxruntime": _check_import("rapidocr_onnxruntime"),
        }

        tbin = shutil.which("tesseract")
        status["tesseract_binary"] = {"ok": bool(tbin), "path": tbin}

        hint = (
            "Se uno o più moduli sono NO, il Multi-OCR non può funzionare: "
            "o manca il pacchetto nel venv, o (per Tesseract) manca il binario nel PATH."
        )

        return {"ok": True, "status": status, "hint": hint}

    def pick_images(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            import webview
        except Exception as e:
            return {"ok": False, "paths": [], "items": [], "error": f"pywebview non disponibile: {e}"}

        win = self._window
        if win is None:
            try:
                win = webview.windows[0] if getattr(webview, "windows", None) else None
            except Exception:
                win = None

        if win is None:
            return {"ok": False, "paths": [], "items": [], "error": "Finestra non pronta (window None). Riprova."}

        file_types_strings = (
            "Immagini (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)",
            "PDF (*.pdf)",
            "Word (*.docx;*.doc)",
            "Testo (*.txt;*.log)",
            "Tutti i file (*.*)",
        )

        def _dialog_open_const() -> int:
            fd = getattr(webview, "FileDialog", None)
            if fd is not None and hasattr(fd, "OPEN"):
                return fd.OPEN
            return 1

        def _normalize_paths(raw: Any) -> List[str]:
            if not raw:
                return []
            if isinstance(raw, (list, tuple)):
                return [str(p) for p in raw if p]
            return [str(raw)]

        last_err: Optional[Exception] = None

        try:
            raw = win.create_file_dialog(  # type: ignore[attr-defined]
                _dialog_open_const(),
                allow_multiple=True,
                file_types=file_types_strings,
            )
            paths = _normalize_paths(raw)
            self._selected_paths = paths
            return {
                "ok": True,
                "paths": paths,
                "items": [{"path": p, "kind": _kind_from_path(p)} for p in paths],
                "count": len(paths),
            }
        except Exception as e:
            last_err = e

        file_types_tuple: Any = (
            ("Immagini", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx;*.doc"),
            ("Testo", "*.txt;*.log"),
            ("Tutti", "*.*"),
        )
        try:
            raw = win.create_file_dialog(  # type: ignore[attr-defined]
                _dialog_open_const(),
                allow_multiple=True,
                file_types=file_types_tuple,
            )
            paths = _normalize_paths(raw)
            self._selected_paths = paths
            return {
                "ok": True,
                "paths": paths,
                "items": [{"path": p, "kind": _kind_from_path(p)} for p in paths],
                "count": len(paths),
            }
        except Exception as e:
            last_err = e

        return {"ok": False, "paths": [], "items": [], "error": f"{type(last_err).__name__}: {last_err}"}

    def choose_output_folder(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            import webview
        except Exception as e:
            return {"ok": False, "error": f"pywebview non disponibile: {e}"}

        win = self._window
        if win is None:
            try:
                win = webview.windows[0] if getattr(webview, "windows", None) else None
            except Exception:
                win = None

        if win is None:
            return {"ok": False, "error": "Finestra non pronta (window None). Riprova."}

        fd = getattr(webview, "FileDialog", None)
        folder_const = getattr(fd, "FOLDER", 3) if fd is not None else 3

        try:
            raw = win.create_file_dialog(folder_const)  # type: ignore[attr-defined]
            if not raw:
                return {"ok": True, "path": None}

            path = raw[0] if isinstance(raw, (list, tuple)) else raw
            path = _ensure_elaborate_dir(str(path))
            if path:
                self._output_dir = path
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def choose_input_folder(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Seleziona una cartella di input per analisi batch."""
        try:
            import webview
        except Exception as e:
            return {"ok": False, "error": f"pywebview non disponibile: {e}"}

        win = self._window
        if win is None:
            try:
                win = webview.windows[0] if getattr(webview, "windows", None) else None
            except Exception:
                win = None

        if win is None:
            return {"ok": False, "error": "Finestra non pronta (window None). Riprova."}

        fd = getattr(webview, "FileDialog", None)
        folder_const = getattr(fd, "FOLDER", 3) if fd is not None else 3

        try:
            raw = win.create_file_dialog(folder_const)  # type: ignore[attr-defined]
            if not raw:
                return {"ok": True, "path": None}

            path = raw[0] if isinstance(raw, (list, tuple)) else raw
            path = str(path)
            if path:
                self._input_dir = path
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def batch_start(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Analizza tutti i file di una cartella, in ordine, ed esporta man mano."""
        try:
            pl = payload if isinstance(payload, dict) else {}
        except Exception:
            pl = {}

        # SECURITY: Validate CSRF token
        if not self._validate_csrf(pl):
            return {"ok": False, "error": "CSRF token invalid or missing"}
        
        # CHECK QUOTA: Verifica limiti giornalieri
        if hasattr(self, "_subscription_mgr"):
            quota_check = self._subscription_mgr.check_daily_limit(self._current_user_id)
            if quota_check.get("exceeded"):
                return {
                    "ok": False,
                    "error": f"Limite giornaliero raggiunto ({quota_check.get('remaining', 0)} ricette rimaste)",
                    "quota": quota_check
                }
            
            # CHECK AI QUOTA: Limiti API AI
            ai_quota_check = self._subscription_mgr.check_daily_ai_limit(self._current_user_id)
            if ai_quota_check.get("ok") and ai_quota_check.get("exceeded"):
                return {
                    "ok": False,
                    "error": f"Limite API AI raggiunto (€{ai_quota_check.get('spent_eur', 0):.2f} spesi oggi)",
                    "ai_quota": ai_quota_check
                }

        input_dir = str(pl.get("input_dir") or self._input_dir or "").strip()
        if not input_dir:
            return {"ok": False, "error": "Cartella di input non selezionata"}
        out_dir = str(pl.get("out_dir") or pl.get("output_dir") or self._output_dir or "").strip()
        out_dir = _ensure_elaborate_dir(out_dir)
        self._output_dir = out_dir

        template = str(pl.get("template") or pl.get("pdf_template") or "Template_Ricetta_AI")
        page_size = str(pl.get("page_size") or pl.get("pdf_page_size") or "A4")
        save_to_archive = True
        export_pdf_each = bool(pl.get("export_pdf", True))
        export_docx_each = bool(pl.get("export_docx", True))
        recursive = bool(pl.get("recursive", False))
        skip_processed = bool(pl.get("skip_processed", True))
        skip_method = str(pl.get("skip_method", "hash")).lower()
        if skip_method not in {"hash", "name"}:
            skip_method = "hash"

        with self._batch_lock:
            if self._batch_thread is not None and self._batch_thread.is_alive():
                return {"ok": False, "error": "Batch già in corso"}
            self._batch_error = None
            self._batch_running = True
            self._batch_abort = False
            self._batch_state = {
                "input_dir": input_dir,
                "output_dir": out_dir,
                "template": template,
                "page_size": page_size,
                "total": 0,
                "done": 0,
                "errors": 0,
                "skipped": 0,
                "items": [],
                "current_file": None,
                "current_path": None,
                "timeout_pending": False,
                "timeout_file": None,
                "timeout_started_at": None,
                "timeout_decision": None,
                "started_at": None,
                "finished_at": None,
            }

        # reset progress
        try:
            if self._progress is not None and hasattr(self._progress, "reset"):
                self._progress.reset()
            if self._progress is not None and hasattr(self._progress, "set"):
                self._progress.set(1, "batch", "Preparazione batch...")
        except Exception:
            pass

        def _list_files(folder: Path) -> List[Path]:
            exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf", ".docx", ".doc", ".txt"}
            max_mb = 15
            files: List[Path] = []

            def _eligible(p: Path) -> bool:
                if not p.is_file():
                    return False
                if p.name.startswith(("~", ".")):
                    return False
                if p.suffix.lower() not in exts:
                    return False
                try:
                    if p.stat().st_size > max_mb * 1024 * 1024:
                        return False
                except Exception:
                    return False
                return True

            if recursive:
                for p in folder.rglob("*"):
                    if _eligible(p):
                        files.append(p)
            else:
                for p in folder.iterdir():
                    if _eligible(p):
                        files.append(p)
            files.sort(key=lambda p: _natural_sort_key(p.name))
            return files

        def _unique_path(base: Path) -> Path:
            if not base.exists():
                return base
            stem = base.stem
            suf = base.suffix
            for i in range(2, 5000):
                cand = base.with_name(f"{stem}_{i}{suf}")
                if not cand.exists():
                    return cand
            return base.with_name(f"{stem}_{os.getpid()}{suf}")

        def _worker() -> None:
            try:
                from datetime import datetime
                from backend.pipeline import analyze_files, export_pdf as _export_pdf, export_docx as _export_docx

                in_dir = Path(input_dir)
                if not in_dir.exists() or not in_dir.is_dir():
                    raise RuntimeError("Cartella input non valida")

                # usa direttamente la cartella di output scelta
                out_base = Path(out_dir)
                out_base.mkdir(parents=True, exist_ok=True)
                out_batch = out_base

                retry_dir = (out_batch / "da_analizzare").resolve()
                retry_dir.mkdir(parents=True, exist_ok=True)
                retry_files: List[Path] = []

                # Carica la cache dei file processati
                cache_path = out_base / ".processed_cache.json"
                processed_cache = _load_processed_cache(cache_path)

                files = _list_files(in_dir)
                with self._batch_lock:
                    self._batch_state["total"] = len(files)
                    self._batch_state["output_dir"] = str(out_batch)
                    self._batch_state["started_at"] = datetime.now().isoformat(timespec="seconds")

                db = self._get_archive_db() if save_to_archive else None

                def _process_one(
                    fp: Path,
                    idx: int,
                    total: int,
                    *,
                    timeout_s: int,
                    allow_defer: bool,
                    label: str,
                ) -> None:
                    if self._batch_abort:
                        return
                    file_id = f"{label}_{idx}_{fp.stem}"
                    t_start = time.monotonic()
                    log_event(
                        self._logger,
                        run_id=self._run_id,
                        file_id=file_id,
                        stage="start",
                        status="start",
                        message=f"Batch file start {fp}",
                        extra={"label": label, "idx": idx, "total": total},
                    )
                    try:
                        if self._progress is not None and hasattr(self._progress, "set"):
                            self._progress.set(1, "batch", f"{label} {idx}/{total}: {fp.name}")
                    except Exception:
                        pass

                    with self._batch_lock:
                        self._batch_state["current_file"] = fp.name
                        self._batch_state["current_path"] = str(fp)
                        self._batch_state["timeout_pending"] = False
                        self._batch_state["timeout_file"] = None
                        self._batch_state["timeout_started_at"] = None
                        self._batch_state["timeout_decision"] = None
                        self._batch_state["timeout_retries"] = 0

                    timeout_done = threading.Event()
                    file_started_at = time.monotonic()
                    fp_name = fp.name
                    fp_path = str(fp)

                    def _timeout_watch(fp_local: str = fp_path, name_local: str = fp_name, start_ts: float = file_started_at) -> None:
                        if timeout_done.wait(timeout_s):
                            return
                        response_wait_s = 300
                        max_retries = 3
                        retries = 0

                        def _still_current() -> bool:
                            return (
                                self._batch_state.get("current_path") == fp_local
                                and self._batch_state.get("timeout_decision") is None
                                and self._batch_running
                            )

                        with self._batch_lock:
                            if not _still_current():
                                return
                            self._batch_state["timeout_pending"] = True
                            self._batch_state["timeout_file"] = name_local
                            self._batch_state["timeout_started_at"] = datetime.now().isoformat(timespec="seconds")
                            self._batch_state["timeout_decision"] = None
                            self._batch_state["last_event"] = {
                                "type": "timeout",
                                "message": f"Timeout {timeout_s}s: {name_local}",
                                "file": name_local,
                                "path": fp_local,
                                "elapsed_s": int(time.monotonic() - start_ts),
                            }

                        while retries < max_retries:
                            if timeout_done.wait(response_wait_s):
                                return
                            with self._batch_lock:
                                if not _still_current():
                                    return
                                retries += 1
                                self._batch_state["timeout_retries"] = retries
                                self._batch_state["timeout_started_at"] = datetime.now().isoformat(timespec="seconds")
                                self._batch_state["last_event"] = {
                                    "type": "timeout_retry",
                                    "message": f"Timeout: nessuna risposta ({retries}/{max_retries}) - {name_local}",
                                    "file": name_local,
                                    "path": fp_local,
                                }

                        with self._batch_lock:
                            if not _still_current():
                                return
                            self._batch_state["timeout_pending"] = False
                            self._batch_state["timeout_decision"] = "skip"
                            self._batch_state["last_event"] = {
                                "type": "timeout_autoskip",
                                "message": f"Timeout: nessuna risposta, salto automatico: {name_local}",
                                "file": name_local,
                                "path": fp_local,
                            }

                    threading.Thread(target=_timeout_watch, daemon=True).start()

                    item: Dict[str, Any] = {
                        "index": idx,
                        "file": str(fp),
                        "name": fp.name,
                        "ok": False,
                        "error": None,
                        "title": None,
                        "pdf_path": None,
                        "docx_path": None,
                        "archive_id": None,
                        "pass": label,
                        "skipped": False,
                    }

                    # Controlla se il file è già stato processato
                    if skip_processed and _is_file_processed(fp, processed_cache, method=skip_method):
                        timeout_done.set()
                        item["ok"] = True
                        item["skipped"] = True
                        cached_title = processed_cache.get(fp.name, {}).get("title", fp.stem)
                        item["title"] = cached_title
                        item["error"] = f"Già analizzato (saltato per {skip_method})"
                        with self._batch_lock:
                            self._batch_state["skipped"] = int(self._batch_state.get("skipped", 0)) + 1
                            self._batch_state["last_event"] = {
                                "type": "skip",
                                "ts": time.time(),
                                "message": f"Saltato (già analizzato): {cached_title}",
                                "path": str(fp),
                                "title": cached_title,
                            }
                        log_event(
                            self._logger,
                            run_id=self._run_id,
                            file_id=file_id,
                            stage="skip",
                            status="skip",
                            message=f"File già analizzato: {cached_title}",
                        )
                        with self._batch_lock:
                            self._batch_state["items"].append(item)
                            if label == "batch":
                                self._batch_state["done"] = int(self._batch_state.get("done", 0)) + 1
                        return

                    try:
                        res = analyze_files(
                            [str(fp)],
                            progress=self._progress,
                            options={
                                "use_ai": True,
                                "ai_complete_missing": True,
                                "ai_fill_missing": True,
                                "force_ai_full": True,
                                "run_id": self._run_id,
                                "file_id": file_id,
                            },
                        )
                        recipe = res.get("recipe") if isinstance(res, dict) else None
                        if not isinstance(recipe, dict):
                            raise RuntimeError(res.get("error") or "Ricetta non valida")

                        try:
                            self._record_ai_usage(recipe)
                        except Exception:
                            pass

                        with self._batch_lock:
                            skip_current = self._batch_state.get("timeout_decision") == "skip"

                        title = str(recipe.get("title") or fp.stem)
                        item["title"] = title
                        log_event(
                            self._logger,
                            run_id=self._run_id,
                            file_id=file_id,
                            stage="analyze",
                            status="ok",
                            message=f"Analisi completata: {title}",
                            extra={"elapsed_s": round(time.monotonic() - t_start, 3)},
                        )

                        # export
                        if export_pdf_each and not skip_current:
                            try:
                                fname = _safe_filename(title) + ".pdf"
                                cat = _safe_filename(str(recipe.get("category") or "Altro"))
                                cat_dir = (out_batch / cat).resolve()
                                cat_dir.mkdir(parents=True, exist_ok=True)
                                pdf_path = _unique_path((cat_dir / fname).resolve())
                                _export_pdf(
                                    recipe,
                                    str(pdf_path),
                                    template=str(template),
                                    page_size=str(page_size),
                                    progress=self._progress,
                                )
                                item["pdf_path"] = str(pdf_path)
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "pdf",
                                        "ts": time.time(),
                                        "message": f"PDF salvato: {pdf_path}",
                                        "path": str(pdf_path),
                                        "title": title,
                                    }
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="pdf",
                                    status="ok",
                                    message=f"PDF salvato: {pdf_path}",
                                    extra={"template": str(template), "page_size": str(page_size)},
                                )
                            except Exception as e:
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "pdf_error",
                                        "ts": time.time(),
                                        "message": f"Errore PDF: {e}",
                                        "title": title,
                                    }
                                item["ok"] = False
                                item["error"] = f"PDF: {e}"
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="pdf",
                                    status="error",
                                    message=f"Errore PDF: {e}",
                                )

                        if export_docx_each and not skip_current:
                            try:
                                fname_docx = _safe_filename(title) + ".docx"
                                cat = _safe_filename(str(recipe.get("category") or "Altro"))
                                cat_dir = (out_batch / cat).resolve()
                                cat_dir.mkdir(parents=True, exist_ok=True)
                                docx_path = _unique_path((cat_dir / fname_docx).resolve())
                                _export_docx(recipe, str(docx_path))
                                item["docx_path"] = str(docx_path)
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "docx",
                                        "ts": time.time(),
                                        "message": f"DOCX salvato: {docx_path}",
                                        "path": str(docx_path),
                                        "title": title,
                                    }
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="docx",
                                    status="ok",
                                    message=f"DOCX salvato: {docx_path}",
                                )
                            except Exception as e:
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "docx_error",
                                        "ts": time.time(),
                                        "message": f"Errore DOCX: {e}",
                                        "title": title,
                                    }
                                item["ok"] = False
                                item["error"] = f"DOCX: {e}"
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="docx",
                                    status="error",
                                    message=f"Errore DOCX: {e}",
                                )

                        # salva in archivio
                        if db is not None and not skip_current:
                            try:
                                # Controlla se una ricetta identica esiste già
                                identical_id = db.find_identical_recipe(recipe)
                                if identical_id is not None:
                                    # Ricetta identica trovata, salta
                                    item["ok"] = True
                                    item["archive_id"] = identical_id
                                    item["skipped"] = True
                                    item["error"] = f"Saltato: ricetta identica già in archivio (id {identical_id})"
                                    with self._batch_lock:
                                        self._batch_state["skipped"] = int(self._batch_state.get("skipped", 0)) + 1
                                        self._batch_state["last_event"] = {
                                            "type": "skip_duplicate",
                                            "ts": time.time(),
                                            "message": f"Saltato: ricetta identica già in archivio",
                                            "title": title,
                                            "archive_id": identical_id,
                                        }
                                    log_event(
                                        self._logger,
                                        run_id=self._run_id,
                                        file_id=file_id,
                                        stage="db",
                                        status="skip",
                                        message=f"Ricetta identica già in archivio (id={identical_id})",
                                    )
                                else:
                                    # Ricetta nuova, salva
                                    rid = int(db.save_recipe(recipe))
                                    item["archive_id"] = rid
                                    with self._batch_lock:
                                        self._batch_state["last_event"] = {
                                            "type": "db",
                                            "ts": time.time(),
                                            "message": f"Database aggiornato: {title} (id {rid})",
                                            "id": rid,
                                            "title": title,
                                        }
                                    log_event(
                                        self._logger,
                                        run_id=self._run_id,
                                        file_id=file_id,
                                        stage="db",
                                        status="ok",
                                        message=f"Salvato in archivio id={rid}",
                                    )
                            except Exception as e:
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "db_error",
                                        "ts": time.time(),
                                        "message": f"Errore DB: {e}",
                                        "title": title,
                                    }
                                item["ok"] = False
                                item["error"] = f"DB: {e}"
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="db",
                                    status="error",
                                    message=f"Errore DB: {e}",
                                )

                        if skip_current:
                            item["ok"] = False
                            item["error"] = f"Saltato dopo timeout ({timeout_s}s)"
                        else:
                            item["ok"] = True
                            # Segna il file come processato nella cache
                            _mark_file_processed(fp, processed_cache, title)
                    except Exception as e:
                        item["ok"] = False
                        item["error"] = f"{type(e).__name__}: {e}"
                        with self._batch_lock:
                            self._batch_state["last_event"] = {
                                "type": "error",
                                "ts": time.time(),
                                "message": f"Errore analisi: {e}",
                                "path": str(fp),
                            }
                        log_event(
                            self._logger,
                            run_id=self._run_id,
                            file_id=file_id,
                            stage="error",
                            status="error",
                            message=f"Errore analisi: {e}",
                        )
                    finally:
                        timeout_done.set()

                    with self._batch_lock:
                        self._batch_state["items"].append(item)
                        if label == "batch":
                            self._batch_state["done"] = int(self._batch_state.get("done", 0)) + 1
                        if not item.get("ok"):
                            self._batch_state["errors"] = int(self._batch_state.get("errors", 0)) + 1

                    if allow_defer:
                        with self._batch_lock:
                            skip_current = self._batch_state.get("timeout_decision") == "skip"
                        if skip_current or not item.get("ok"):
                            try:
                                dest = retry_dir / fp.name
                                dest = _unique_path(dest)
                                shutil.move(str(fp), str(dest))
                                retry_files.append(dest)
                                reason_path = dest.with_name(dest.stem + "__MOTIVO.json")
                                reason = {
                                    "reason": item.get("error") or "Timeout/skip",
                                    "stage": "timeout" if skip_current else "error",
                                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                                    "retries": self._batch_state.get("timeout_retries", 0),
                                    "run_id": self._run_id,
                                    "file_id": file_id,
                                }
                                try:
                                    reason_path.write_text(json.dumps(reason, ensure_ascii=False, indent=2), encoding="utf-8")
                                except Exception:
                                    pass
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "defer",
                                        "message": f"Spostato in da_analizzare: {dest}",
                                        "path": str(dest),
                                        "title": item.get("title") or fp.name,
                                    }
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="defer",
                                    status="warn",
                                    message=f"Spostato in da_analizzare: {dest}",
                                )
                            except Exception as e:
                                with self._batch_lock:
                                    self._batch_state["last_event"] = {
                                        "type": "defer_error",
                                        "message": f"Errore spostamento: {e}",
                                        "path": str(fp),
                                    }
                                log_event(
                                    self._logger,
                                    run_id=self._run_id,
                                    file_id=file_id,
                                    stage="defer",
                                    status="error",
                                    message=f"Errore spostamento: {e}",
                                )

                for idx, fp in enumerate(files, start=1):
                    _process_one(fp, idx, len(files), timeout_s=300, allow_defer=True, label="batch")

                # Salva la cache aggiornata
                _save_processed_cache(cache_path, processed_cache)

                if retry_files:
                    with self._batch_lock:
                        self._batch_state["last_event"] = {
                            "type": "retry",
                            "message": f"Riprovo {len(retry_files)} file con timeout 300s...",
                        }
                    for ridx, fp in enumerate(retry_files, start=1):
                        _process_one(fp, ridx, len(retry_files), timeout_s=300, allow_defer=False, label="retry")

                # Salva la cache finale dopo i retry
                _save_processed_cache(cache_path, processed_cache)

                with self._batch_lock:
                    self._batch_state["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    self._batch_running = False

                try:
                    if self._progress is not None and hasattr(self._progress, "mark_done"):
                        self._progress.mark_done("Batch completato")
                except Exception:
                    pass

            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                with self._batch_lock:
                    self._batch_error = err
                    self._batch_running = False
                try:
                    if self._progress is not None and hasattr(self._progress, "mark_error"):
                        self._progress.mark_error(err)
                except Exception:
                    pass

        t = threading.Thread(target=_worker, daemon=True)
        with self._batch_lock:
            self._batch_thread = t
        t.start()
        return {"ok": True, "started": True, "input_dir": input_dir, "out_dir": out_dir}

    def batch_status(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        with self._batch_lock:
            t = self._batch_thread
            running = bool(t and t.is_alive()) or self._batch_running
            state = dict(self._batch_state) if isinstance(self._batch_state, dict) else {}
            err = self._batch_error
        return {"ok": not bool(err), "running": running, "state": state, "error": err}

    def batch_timeout_decision(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            action = None
            if isinstance(payload, dict):
                action = payload.get("action") or payload.get("decision")
            action = str(action or "").strip().lower()
            if action not in {"continue", "stop", "skip"}:
                return {"ok": False, "error": "Azione non valida"}
            with self._batch_lock:
                self._batch_state["timeout_decision"] = action
                if action in {"continue", "skip"}:
                    self._batch_state["timeout_pending"] = False
            return {"ok": True, "decision": action}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def get_templates(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        templates: List[str] = ["Template_Ricetta_AI"]
        try:
            from backend import pipeline
            t = pipeline.list_templates()
            if isinstance(t, list) and t:
                templates = [str(x) for x in t if x]
        except Exception:
            try:
                from backend import pdf_export
                if hasattr(pdf_export, "list_templates"):
                    t = pdf_export.list_templates()
                    if isinstance(t, list) and t:
                        templates = [str(x) for x in t if x]
                elif hasattr(pdf_export, "TEMPLATES") and isinstance(getattr(pdf_export, "TEMPLATES"), dict):
                    templates = list(getattr(pdf_export, "TEMPLATES").keys())
            except Exception:
                pass

        seen = set()
        clean: List[str] = []
        meta: List[Dict[str, Any]] = []

        for t in templates:
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            clean.append(s)

            kind = "builtin"
            label = s.replace("_", " ")
            if s == "Template_Ricetta_AI":
                label = "Default"
            elif s == "pastel_classico":
                label = "Pastel classico"
            elif s.lower().startswith("html:"):
                kind = "html"
                parts = s.split(":", 1)
                label = "HTML — " + (parts[1].replace("_", " ") if len(parts) > 1 else "custom")
            else:
                kind = "py"

            meta.append({"name": s, "label": label, "kind": kind})

        return {"ok": True, "templates": clean, "templates_meta": meta}

    def render_template_preview(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Renderizza un template HTML (Jinja) e ritorna HTML per anteprima in UI."""
        try:
            if not isinstance(payload, dict):
                payload = {}

            def _preview_recipe_base() -> Dict[str, Any]:
                return {
                    "title": "Risotto alla Zucca e Rosmarino",
                    "titolo": "Risotto alla Zucca e Rosmarino",
                    "category": "Primi",
                    "categoria": "Primi",
                    "sottocategoria": "Risotti",
                    "servings": "4",
                    "porzioni": "4",
                    "difficulty": "Media",
                    "difficolta": "Media",
                    "prep_time_min": "20",
                    "tempo_preparazione": "20 min",
                    "cook_time_min": "25",
                    "tempo_cottura": "25 min",
                    "tempo_riposo": "0 min",
                    "total_time_min": "45",
                    "tempo_dettaglio": "Prep 20 min, Cottura 25 min",
                    "tempo": "45 min",
                    "tempo_totale": "45 min",
                    "conservazione": "Conservare in frigo per 24 ore.",
                    "presentazione_impiattamento": "Servire con rosmarino fresco e olio EVO.",
                    "ingredients_text": "- Riso Carnaroli 320 g\n- Zucca 400 g\n- Brodo vegetale 1 L\n- Cipolla 1\n- Burro 40 g\n- Parmigiano 60 g\n- Rosmarino 1 rametto\n- Sale q.b.\n- Pepe q.b.",
                    "ingredienti": "- Riso Carnaroli 320 g\n- Zucca 400 g\n- Brodo vegetale 1 L\n- Cipolla 1\n- Burro 40 g\n- Parmigiano 60 g\n- Rosmarino 1 rametto\n- Sale q.b.\n- Pepe q.b.",
                    "ingredients": [
                        {"name": "Riso Carnaroli", "qty": 320, "unit": "g"},
                        {"name": "Zucca", "qty": 400, "unit": "g"},
                        {"name": "Brodo vegetale", "qty": 1, "unit": "l"},
                        {"name": "Cipolla", "qty": 1, "unit": "pz"},
                        {"name": "Burro", "qty": 40, "unit": "g"},
                        {"name": "Parmigiano", "qty": 60, "unit": "g"},
                        {"name": "Rosmarino", "qty": 1, "unit": "rametto"},
                    ],
                    "ingredienti_componenti": [
                        {
                            "name": "Base",
                            "items": [
                                {"nome": "Riso Carnaroli", "quantita": 320, "unita": "g", "note": "", "costo_ingrediente": 1.54},
                                {"nome": "Zucca", "quantita": 400, "unita": "g", "note": "", "costo_ingrediente": 0.88},
                                {"nome": "Parmigiano", "quantita": 60, "unita": "g", "note": "", "costo_ingrediente": 1.08},
                            ],
                        }
                    ],
                    "steps_text": "1. Trita la cipolla e stufala con il burro.\n2. Aggiungi la zucca a cubetti e cuoci 8 minuti.\n3. Tosta il riso e sfuma con un mestolo di brodo.\n4. Porta a cottura aggiungendo brodo poco alla volta.\n5. Manteca con parmigiano e rosmarino.",
                    "procedimento": "1. Trita la cipolla e stufala con il burro.\n2. Aggiungi la zucca a cubetti e cuoci 8 minuti.\n3. Tosta il riso e sfuma con un mestolo di brodo.\n4. Porta a cottura aggiungendo brodo poco alla volta.\n5. Manteca con parmigiano e rosmarino.",
                    "allergens_text": "Latte",
                    "allergeni_text": "Latte",
                    "allergeni_elenco": "Latte",
                    "allergeni_loghi": [
                        {"code": "latte", "label": "Latte e derivati"}
                    ],
                    "allergeni_tracce_loghi": [
                        {"code": "glutine", "label": "Glutine"}
                    ],
                    "equipment_text": "Casseruola, mestolo, coltello",
                    "attrezzature": "Casseruola, mestolo, coltello",
                    "attrezzature_generiche": "Casseruola, mestolo, coltello",
                    "attrezzature_specifiche": "Piastra induzione",
                    "attrezzature_pasticceria": "Bilancia digitale",
                    "notes": "Servire caldo con rosmarino fresco.",
                    "note_haccp": "Raffreddare rapidamente.",
                    "wine_pairing": "Verdicchio dei Castelli di Jesi",
                    "vino_temperatura_servizio": "10-12",
                    "vino_regione": "Marche",
                    "vino_annata": "2023",
                    "vino_motivo_annata": "Annata equilibrata e aromatica",
                    "stagionalita": "Autunno",
                    "peso_totale_ricetta_g": 1200,
                    "resa_totale": "4 porzioni",
                    "diete_scelta_alimentare": "Vegetariana",
                    "diete_cliniche": "Basso contenuto di lattosio",
                    "diete_culturali": "Nessuna",
                    "diete_stile": "Mediterranea",
                    "diete_text": "Vegetariano",
                    "diet_flags": {
                        "vegetarian": True,
                        "vegan": False,
                        "gluten_free": True,
                        "lactose_free": False,
                    },
                    "nutrition_table": {
                        "100g": {
                            "energia": 130,
                            "carboidrati_totali": 18,
                            "di_cui_zuccheri": 2.2,
                            "grassi_totali": 4.5,
                            "di_cui_saturi": 2.1,
                            "monoinsaturi": 1.2,
                            "polinsaturi": 0.6,
                            "proteine_totali": 3.5,
                            "fibre": 1.8,
                            "sodio": 0.3,
                            "colesterolo": 15,
                        },
                        "totale": {
                            "energia": 520,
                            "carboidrati_totali": 72,
                            "di_cui_zuccheri": 9,
                            "grassi_totali": 18,
                            "di_cui_saturi": 8,
                            "monoinsaturi": 5,
                            "polinsaturi": 2.5,
                            "proteine_totali": 14,
                            "fibre": 7,
                            "sodio": 1.2,
                            "colesterolo": 60,
                        },
                        "porzione": {
                            "energia": 130,
                            "carboidrati_totali": 18,
                            "di_cui_zuccheri": 2.2,
                            "grassi_totali": 4.5,
                            "di_cui_saturi": 2.1,
                            "monoinsaturi": 1.2,
                            "polinsaturi": 0.6,
                            "proteine_totali": 3.5,
                            "fibre": 1.8,
                            "sodio": 0.3,
                            "colesterolo": 15,
                        },
                    },
                    "energia_100g": 130,
                    "energia_100g_kj": 544,
                    "energia_totale": 520,
                    "energia_ricetta": 520,
                    "energia_ricetta_kj": 2176,
                    "energia_porzione": 130,
                    "energia_porzione_kj": 544,
                    "carboidrati_100g": 18,
                    "carboidrati_ricetta": 72,
                    "carboidrati_totali_100g": 18,
                    "carboidrati_totali_totale": 72,
                    "carboidrati_porzione": 18,
                    "di_cui_zuccheri_100g": 2.2,
                    "di_cui_zuccheri_totale": 9,
                    "zuccheri_100g": 2.2,
                    "zuccheri_porzione": 2.2,
                    "zuccheri_ricetta": 9,
                    "grassi_totali_100g": 4.5,
                    "grassi_totali_totale": 18,
                    "grassi_totali_porzione": 4.5,
                    "grassi_totali_ricetta": 18,
                    "di_cui_saturi_100g": 2.1,
                    "di_cui_saturi_totale": 8,
                    "grassi_saturi_100g": 2.1,
                    "grassi_saturi_porzione": 2.1,
                    "grassi_saturi_ricetta": 8,
                    "monoinsaturi_100g": 1.2,
                    "monoinsaturi_totale": 5,
                    "grassi_monoinsaturi_100g": 1.2,
                    "grassi_monoinsaturi_porzione": 1.2,
                    "grassi_monoinsaturi_ricetta": 5,
                    "polinsaturi_100g": 0.6,
                    "polinsaturi_totale": 2.5,
                    "grassi_polinsaturi_100g": 0.6,
                    "grassi_polinsaturi_porzione": 0.6,
                    "grassi_polinsaturi_ricetta": 2.5,
                    "proteine_100g": 3.5,
                    "proteine_totali_100g": 3.5,
                    "proteine_totali_totale": 14,
                    "proteine_porzione": 3.5,
                    "proteine_ricetta": 14,
                    "fibre_100g": 1.8,
                    "fibre_totale": 7,
                    "fibre_porzione": 1.8,
                    "fibre_ricetta": 7,
                    "sodio_100g_mg": 0.3,
                    "sodio_totale": 1.2,
                    "sodio_porzione_mg": 0.3,
                    "sodio_ricetta_mg": 1.2,
                    "colesterolo_100g_mg": 15,
                    "colesterolo_totale": 60,
                    "colesterolo_porzione_mg": 15,
                    "colesterolo_ricetta_mg": 60,
                    "kcal_ricetta": 520,
                    "kcal_porzione": 130,
                    "kcal_per_porzione": 130,
                    "cost_lines": [
                        {
                            "ingrediente": "Riso Carnaroli",
                            "scarto": "0%",
                            "peso_min_acquisto": "1 kg",
                            "quantita_usata": "320 g",
                            "prezzo_kg_ud": "4,80 €/kg",
                            "prezzo_alimento_acquisto": "4,80 €",
                            "prezzo_calcolato": "1,54 €",
                        },
                        {
                            "ingrediente": "Zucca",
                            "scarto": "10%",
                            "peso_min_acquisto": "1 kg",
                            "quantita_usata": "400 g",
                            "prezzo_kg_ud": "2,20 €/kg",
                            "prezzo_alimento_acquisto": "2,20 €",
                            "prezzo_calcolato": "0,88 €",
                        },
                        {
                            "ingrediente": "Parmigiano",
                            "scarto": "0%",
                            "peso_min_acquisto": "1 kg",
                            "quantita_usata": "60 g",
                            "prezzo_kg_ud": "18,00 €/kg",
                            "prezzo_alimento_acquisto": "18,00 €",
                            "prezzo_calcolato": "1,08 €",
                        },
                    ],
                    "spesa_totale_acquisto": 25.0,
                    "spesa_totale_ricetta": 3.5,
                    "spesa_per_porzione": 0.88,
                    "costo_totale_ricetta": 3.5,
                    "costo_per_porzione": 0.88,
                    "selling_price_per_portion": 6.5,
                    "image_src": "",
                }

            import html as html_utils
            import json as json_utils

            recipe = payload.get("recipe")
            if not isinstance(recipe, dict):
                recipe = {}

            def _compact(val: Any) -> Any:
                skip_vals = (None, "", [], {})  # allow unhashable values in membership test
                if isinstance(val, dict):
                    cleaned: Dict[str, Any] = {}
                    for k, v in val.items():
                        c = _compact(v)
                        if c in skip_vals:
                            continue
                        cleaned[k] = c
                    return cleaned
                if isinstance(val, list):
                    items: List[Any] = []
                    for it in val:
                        c = _compact(it)
                        if c in skip_vals:
                            continue
                        items.append(c)
                    return items
                if isinstance(val, str):
                    return val.strip()
                return val

            def _ensure_title(data: Dict[str, Any]) -> Dict[str, Any]:
                out = dict(data or {})
                if out.get("titolo") and not out.get("title"):
                    out["title"] = out.get("titolo")
                if not out.get("title"):
                    out["title"] = "Ricetta in lavorazione"
                return out

            example_recipe = _preview_recipe_base()
            user_recipe = _ensure_title(recipe)

            template = str(payload.get("template") or payload.get("pdf_template") or "").strip()
            if not template:
                return {"ok": False, "error": "template mancante"}

            # accetta solo HTML; se arriva solo nome, proviamo comunque
            template_id = template.strip()
            if template_id.lower().startswith("html:"):
                parts = template_id.split(":", 1)
                template_id = "html:" + (parts[1].strip() if len(parts) > 1 else template_id)
            else:
                template_id = "html:" + template_id

            from backend import pipeline

            # path standard assets: templates/assets or ui/assets
            assets_dir = None
            try:
                root = project_root()
                cand_tpl = root / "templates" / "assets"
                if cand_tpl.exists() and cand_tpl.is_dir():
                    assets_dir = str(cand_tpl)
                else:
                    cand = root / "ui" / "assets"
                    if cand.exists() and cand.is_dir():
                        assets_dir = str(cand)
            except Exception:
                assets_dir = None

            def _embed_svg_as_data_uri(html: str, assets_path: str) -> str:
                """Converte i path SVG in data URI inline per funzionare in iframe srcdoc."""
                import re
                import base64
                from pathlib import Path
                
                replacements = 0
                
                def replace_svg(match):
                    nonlocal replacements
                    svg_path = match.group(1)  # "allergens/latte.svg"
                    full_path = Path(assets_path) / svg_path
                    
                    if full_path.exists() and full_path.suffix == '.svg':
                        try:
                            svg_content = full_path.read_text(encoding='utf-8')
                            # URL encode per data URI
                            import urllib.parse
                            encoded = urllib.parse.quote(svg_content)
                            replacements += 1
                            return f'src="data:image/svg+xml,{encoded}"'
                        except Exception as e:
                            print(f"[DEBUG] Errore lettura SVG {full_path}: {e}")
                    else:
                        print(f"[DEBUG] SVG non trovato: {full_path}")
                    return match.group(0)
                
                # Cerca entrambi i pattern: src="allergens/..." e src="{{ assets_base }}allergens/..."
                pattern1 = r'src="(allergens/[^"]+\.svg)"'
                pattern2 = r'src="\{\{ assets_base \}\}(allergens/[^"]+\.svg)"'
                
                result = re.sub(pattern1, replace_svg, html)
                result = re.sub(pattern2, replace_svg, result)
                print(f"[DEBUG] SVG sostituiti: {replacements}")
                return result

            try:
                example_html = pipeline.render_html_template(example_recipe, template_id, assets_dir=assets_dir, silent_mode=True) or ""
                
                # Converte SVG in data URI per iframe srcdoc
                if assets_dir:
                    example_html = _embed_svg_as_data_uri(example_html, assets_dir)
                
                # Pulisce i dati reali prima del rendering
                user_recipe_clean = pipeline.clean_recipe_data(user_recipe)
                
                # Anteprima sempre con tutti i dati (example_recipe) per mostrare l'output completo
                # Usa example_recipe per entrambe le viste in modo da visualizzare sempre tutti i campi possibili
                result_html = pipeline.render_html_template(example_recipe, template_id, assets_dir=assets_dir, silent_mode=True) or ""
                
                # Converte SVG in data URI per iframe srcdoc
                if assets_dir:
                    result_html = _embed_svg_as_data_uri(result_html, assets_dir)
                
                rendering_success = True
            except Exception as e:
                # Se il rendering fallisce, usa un fallback completo
                err_msg = str(e)
                print(f"[ERROR] Rendering template '{template_id}' fallito: {err_msg}", file=sys.stderr)
                example_html = f"<html><body style='font-family:sans-serif;padding:16px;color:#c41e3a'><h3>Errore Template</h3><p>Il template '{template_id}' non può essere renderizzato.</p><p style='font-size:0.9em;color:#666'>{err_msg}</p></body></html>"
                result_html = example_html
                user_recipe_clean = {}  # Fallback vuoto se rendering fallisce
                rendering_success = False

            def _srcdoc(content: str) -> str:
                try:
                    return html_utils.escape(content or "", quote=True)
                except Exception:
                    return (content or "").replace("\"", "&quot;")

            def _debug_block() -> str:
                debug_payload = {
                    "template": template_id,
                    "example_fields": sorted(list(_compact(example_recipe).keys())),
                    "result_fields": sorted(list(_compact(user_recipe_clean).keys() if not rendering_success else [])),
                    "result": _compact(user_recipe_clean) if not rendering_success else {},
                }
                try:
                    txt = json_utils.dumps(debug_payload, indent=2, ensure_ascii=True)
                except Exception:
                    txt = str(debug_payload)
                txt = (txt[:12000] + "...") if len(txt) > 12000 else txt
                return html_utils.escape(txt, quote=False)

            if not result_html.strip():
                result_html = "<html><body style='font-family:sans-serif;padding:16px'>Nessun dato disponibile per la ricetta.</body></html>"

            # Wrapper: estrai il contenuto dal body del template renderizzato
            # Questo evita doppi tag html/body e permette scrolling completo
            def _extract_body_content(html_doc: str) -> str:
                """Estrae il contenuto del body da un documento HTML."""
                import re
                match = re.search(r'<body[^>]*>(.*?)</body>', html_doc, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                # Se non c'è body, ritorna tutto tranne il doctype e tag html/head
                match_all = re.search(r'</head>(.*)', html_doc, re.DOTALL | re.IGNORECASE)
                if match_all:
                    content = match_all.group(1).strip()
                    # Rimuovi il tag </html> finale se presente
                    content = re.sub(r'</html>\s*$', '', content, flags=re.IGNORECASE)
                    return content
                return html_doc
            
            body_content = _extract_body_content(example_html)
            
            # Wrapper: contiene head del template renderizzato + body content diretto
            # Estrai anche i CSS/metadati dalla head del template originale
            def _extract_head_content(html_doc: str) -> str:
                """Estrae il contenuto della head (meta, style, link) da un documento HTML."""
                import re
                match = re.search(r'<head[^>]*>(.*?)</head>', html_doc, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return ""
            
            head_content = _extract_head_content(example_html)
            
            wrapper = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="utf-8" />
    {head_content}
</head>
<body>
{body_content}
</body>
</html>"""

            return {"ok": True, "template": template_id, "html": wrapper}
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] render_template_preview outer exception: {error_msg}", file=sys.stderr)
            return {"ok": False, "error": error_msg}

    # ---------- Subscription & Tier Management ----------
    def get_user_tier_info(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Recupera info di tier e utilizzo per l'utente corrente"""
        try:
            if not self._current_user_id:
                return {"ok": False, "error": "Non autenticato"}
            
            # Recupera info tier
            sub_info = self._user_mgr.get_user_subscription_info(self._current_user_id)
            if not sub_info:
                return {"ok": False, "error": "Utente non trovato"}
            
            # Recupera utilizzo mensile
            usage = self._user_mgr.get_monthly_usage(self._current_user_id)
            
            # Recupera features del tier
            from backend.subscription_tiers import get_tier_features
            features = get_tier_features(sub_info["tier"])
            if not features:
                return {"ok": False, "error": f"Tier non valido: {sub_info['tier']}"}
            
            # Calcola disponibilità
            available_recipes = features.recipes_per_month - usage["recipes_analyzed"]
            
            return {
                "ok": True,
                "tier": {
                    "id": sub_info["tier"],
                    "name": features.name,
                    "price_eur": features.price_eur,
                    "expires_at": sub_info["expires_at"],
                },
                "usage": {
                    "recipes_this_month": usage["recipes_analyzed"],
                    "recipes_limit": features.recipes_per_month,
                    "recipes_available": max(0, available_recipes),
                    "storage_used_mb": usage["storage_used_mb"],
                    "storage_limit_mb": features.storage_gb * 1024,
                },
                "features": {
                    "max_templates": features.max_templates,
                    "has_ads": features.has_ads,
                    "ai_priority": features.ai_model_priority,
                    "support_level": features.support_level,
                    "batch_processing": features.batch_processing,
                    "custom_templates": features.custom_templates,
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def check_recipe_limit(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Verifica se l'utente può ancora analizzare ricette questo mese"""
        try:
            if not self._current_user_id:
                return {"ok": False, "error": "Non autenticato"}
            
            tier = self._user_mgr.get_subscription_tier(self._current_user_id)
            usage = self._user_mgr.get_monthly_usage(self._current_user_id)
            
            from backend.subscription_tiers import get_tier_features
            features = get_tier_features(tier or "free")
            if not features:
                return {"ok": False, "error": f"Tier non valido"}
            
            can_analyze = usage["recipes_analyzed"] < features.recipes_per_month
            
            return {
                "ok": True,
                "can_analyze": can_analyze,
                "recipes_used": usage["recipes_analyzed"],
                "recipes_limit": features.recipes_per_month,
                "tier": tier,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_available_templates(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Recupera i template disponibili per il tier dell'utente"""
        try:
            if not self._current_user_id:
                # Utente non autenticato: template base
                return {
                    "ok": True,
                    "templates": ["classico"],
                    "tier": "free",
                }
            
            tier = self._user_mgr.get_subscription_tier(self._current_user_id)
            
            # Leggi lista di tutti i template disponibili
            templates_list_path = Path("templates") / "templates_list.json"
            all_templates = []
            if templates_list_path.exists():
                try:
                    data = json.loads(templates_list_path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        all_templates = [t.get("id", "") for t in data if t.get("id")]
                except Exception:
                    pass
            
            # Filtra in base al tier
            from backend.subscription_tiers import get_available_templates
            available = get_available_templates(tier or "free", all_templates or ["classico"])
            
            return {
                "ok": True,
                "templates": available,
                "tier": tier,
                "total_available": len(available),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_ai_costs_summary(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Recupera riepilogo dei costi API AI per l'utente corrente"""
        try:
            if not self._current_user_id:
                return {"ok": False, "error": "Non autenticato"}
            
            try:
                from backend.ai_costs import AICostsManager
                ai_mgr = AICostsManager()
                
                # Riepilogo giornaliero
                daily_summary = ai_mgr.get_daily_summary(self._current_user_id)
                monthly_summary = ai_mgr.get_monthly_summary(self._current_user_id)
                
                # Limiti quota
                sub = self._subscription_mgr.get_subscription(self._current_user_id)
                tier = sub.get("tier", "free")
                daily_check = self._subscription_mgr.check_daily_ai_limit(self._current_user_id)
                monthly_check = self._subscription_mgr.check_monthly_ai_limit(self._current_user_id)
                
                return {
                    "ok": True,
                    "tier": tier,
                    "daily": {
                        "summary": daily_summary if daily_summary.get("ok") else None,
                        "quota": daily_check,
                    },
                    "monthly": {
                        "summary": monthly_summary if monthly_summary.get("ok") else None,
                        "quota": monthly_check,
                    }
                }
            except ImportError:
                return {
                    "ok": True,
                    "message": "AI costs tracking non abilitato",
                    "tier": self._subscription_mgr.get_subscription(self._current_user_id).get("tier", "free") if hasattr(self, "_subscription_mgr") else "free"
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ads_for_user(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Recupera gli annunci pubblicitari appropriati per l'utente"""
        try:
            if not self._current_user_id:
                return {"ok": False, "error": "Non autenticato"}
            
            tier = self._user_mgr.get_subscription_tier(self._current_user_id)
            usage = self._user_mgr.get_monthly_usage(self._current_user_id)
            
            # Solo Starter e Free vedono annunci
            if tier not in ["starter", "free"]:
                return {"ok": True, "ads": [], "tier": tier}
            
            from backend.ads_manager import get_ads_manager
            am = get_ads_manager()
            ads_context = am.get_ads_context(tier, usage["recipes_analyzed"])
            
            return {
                "ok": True,
                "ads": ads_context,
                "tier": tier,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_user_tier(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Aggiorna il tier di sottoscrizione (uso interno, post pagamento Stripe)"""
        try:
            if not self._current_user_id:
                return {"ok": False, "error": "Non autenticato"}
            
            tier = (payload or {}).get("tier", "free").lower()
            stripe_customer_id = (payload or {}).get("stripe_customer_id")
            stripe_subscription_id = (payload or {}).get("stripe_subscription_id")
            expires_at = (payload or {}).get("expires_at")
            
            # Valida il tier
            from backend.subscription_tiers import get_tier_features
            if not get_tier_features(tier):
                return {"ok": False, "error": f"Tier non valido: {tier}"}
            
            result = self._user_mgr.set_subscription_tier(
                self._current_user_id,
                tier,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                expires_at=expires_at,
            )
            
            return {"ok": True, "tier": tier}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def analyze_start(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Avvia l'analisi in background.

        Motivo: in pywebview le chiamate API sono sincrone: se 'analyze' resta bloccata,
        la UI non può aggiornare il progresso. Con questa API, la UI può leggere get_progress()
        mentre l'analisi prosegue.
        """
        try:
            pl = payload if isinstance(payload, dict) else {}
        except Exception:
            pl = {}

        # SECURITY: Validate CSRF token
        if not self._validate_csrf(pl):
            return {"ok": False, "error": "CSRF token invalid or missing"}
        
        # CHECK QUOTA: Verifica limiti giornalieri
        if hasattr(self, "_subscription_mgr"):
            quota_check = self._subscription_mgr.check_daily_limit(self._current_user_id)
            if quota_check.get("exceeded"):
                return {
                    "ok": False,
                    "error": f"Limite giornaliero raggiunto ({quota_check.get('remaining', 0)} ricette rimaste)",
                    "quota": quota_check
                }
            
            # CHECK AI QUOTA: Limiti API AI
            ai_quota_check = self._subscription_mgr.check_daily_ai_limit(self._current_user_id)
            if ai_quota_check.get("ok") and ai_quota_check.get("exceeded"):
                return {
                    "ok": False,
                    "error": f"Limite API AI raggiunto (€{ai_quota_check.get('spent_eur', 0):.2f} spesi oggi)",
                    "ai_quota": ai_quota_check
                }

        with self._analysis_lock:
            if self._analysis_thread is not None and self._analysis_thread.is_alive():
                return {"ok": False, "error": "Analisi già in corso"}
            self._analysis_result = None
            self._analysis_error = None
            self._analysis_running = True
            self._analysis_usage_recorded = False

        # reset progress
        try:
            if self._progress is not None and hasattr(self._progress, "reset"):
                self._progress.reset()
            if self._progress is not None and hasattr(self._progress, "set"):
                self._progress.set(1, "start", "Avvio analisi...")
        except Exception:
            pass

        def _worker() -> None:
            try:
                from backend.pipeline import analyze_files

                paths = pl.get("paths")
                if not isinstance(paths, list) or not paths:
                    paths = list(self._selected_paths)

                # richiesta esplicita Multi-OCR + Ollama
                if isinstance(pl, dict):
                    pl.setdefault("ocr_strategy", "multi")
                    pl["use_ai"] = True
                    pl["ai_complete_missing"] = True
                    pl["ai_fill_missing"] = True

                try:
                    res = analyze_files(paths, progress=self._progress, options=pl)
                except TypeError:
                    # compat versioni precedenti
                    res = analyze_files(paths, progress=self._progress)

                if not isinstance(res, dict):
                    res = {"ok": False, "error": "Risultato analisi non valido", "recipe": None}

                # se non è arrivato a 100, chiudi comunque con uno stato
                try:
                    if self._progress is not None and hasattr(self._progress, "pct"):
                        pct = int(getattr(self._progress, "pct", 0) or 0)
                        if pct < 100 and hasattr(self._progress, "mark_done"):
                            self._progress.mark_done("Analisi completata")
                except Exception:
                    pass

                with self._analysis_lock:
                    self._analysis_result = res
                    self._analysis_error = None
                    self._analysis_running = False
                    try:
                        if not self._analysis_usage_recorded and isinstance(res, dict) and res.get("ok") and isinstance(res.get("recipe"), dict):
                            recipe_data = res.get("recipe")
                            if recipe_data and isinstance(recipe_data, dict):
                                self._record_ai_usage(recipe_data)
                            self._analysis_usage_recorded = True
                    except Exception:
                        pass
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                try:
                    if self._progress is not None and hasattr(self._progress, "mark_error"):
                        self._progress.mark_error(err)
                except Exception:
                    pass
                with self._analysis_lock:
                    self._analysis_result = {"ok": False, "error": err}
                    self._analysis_error = err
                    self._analysis_running = False

        t = threading.Thread(target=_worker, daemon=True)
        with self._analysis_lock:
            self._analysis_thread = t
        t.start()
        return {"ok": True, "started": True}

    def analyze_result(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Ritorna lo stato dell'analisi asincrona."""
        with self._analysis_lock:
            t = self._analysis_thread
            running = bool(t and t.is_alive()) or self._analysis_running
            if running:
                return {"ok": True, "ready": False}

            res = self._analysis_result
            err = self._analysis_error

        if res and not err:
            try:
                if not self._analysis_usage_recorded and isinstance(res, dict) and res.get("ok") and isinstance(res.get("recipe"), dict):
                    self._record_ai_usage(res.get("recipe") or {})
                    self._analysis_usage_recorded = True
            except Exception:
                pass

        if res is None:
            return {"ok": False, "ready": True, "error": "Nessun risultato disponibile"}

        out: Dict[str, Any] = {"ok": True, "ready": True, "result": res}
        if err:
            out["ok"] = False
            out["error"] = err
        return out

    def analyze(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                payload = {}

            paths = payload.get("paths")
            if not isinstance(paths, list) or not paths:
                paths = list(self._selected_paths)

            payload.setdefault("ocr_strategy", "multi")
            payload["use_ai"] = True
            payload["ai_complete_missing"] = True
            payload["ai_fill_missing"] = True

            from backend.pipeline import analyze_files

            try:
                res = analyze_files(paths, progress=self._progress, options=payload)
            except TypeError:
                res = analyze_files(paths, progress=self._progress)

            if isinstance(res, dict) and res.get("ok") and isinstance(res.get("recipe"), dict):
                try:
                    self._record_ai_usage(res.get("recipe") or {})
                except Exception:
                    pass

            if isinstance(res, dict):
                res.setdefault("selected_files", [{"path": p, "kind": _kind_from_path(p)} for p in paths])

                dbg = res.get("debug")
                if isinstance(dbg, dict):
                    print(
                        "[Cooksy][DEBUG] "
                        f"ocr={dbg.get('ocr_engine_used')} | "
                        f"chars={dbg.get('ocr_text_len')} | "
                        f"ingredienti={dbg.get('ingredients_count')} | "
                        f"step={dbg.get('steps_count')} | "
                        f"porzioni={dbg.get('servings')} | "
                        f"titolo={dbg.get('title')}"
                    )

            return res

        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def export_pdf(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                payload = {}

            # SECURITY: Validate CSRF token
            if not self._validate_csrf(payload):
                return {"ok": False, "error": "CSRF token invalid or missing"}

            recipe = payload.get("recipe")
            if not isinstance(recipe, dict):
                return {"ok": False, "error": "recipe mancante o non valido"}

            template = payload.get("template") or payload.get("pdf_template") or "Template_Ricetta_AI"
            page_size = payload.get("page_size") or payload.get("pdf_page_size") or "A4"

            out_path = payload.get("out_path") or payload.get("output_path")
            out_dir = payload.get("out_dir") or payload.get("output_dir") or self._output_dir
            out_dir = _ensure_elaborate_dir(str(out_dir) if out_dir else None)
            self._output_dir = out_dir
            suggested_name = payload.get("suggested_name") or recipe.get("title") or "ricetta"

            if not out_path:
                base_dir = Path(out_dir) if out_dir else Path(_default_output_dir())
                if not out_dir:
                    self._output_dir = str(base_dir)
                base_dir.mkdir(parents=True, exist_ok=True)
                fname = _safe_filename(str(suggested_name)) + ".pdf"
                out_path = str((base_dir / fname).resolve())

            from backend.pipeline import export_pdf

            try:
                res = export_pdf(
                    recipe,
                    str(out_path),
                    template=str(template),
                    page_size=str(page_size),
                    progress=self._progress,
                )
            except TypeError:
                res = export_pdf(recipe, str(out_path), progress=self._progress)

            if isinstance(res, dict) and res.get("ok"):
                if "out_path" not in res and "output_path" in res:
                    res["out_path"] = res["output_path"]
                if "output_path" not in res and "out_path" in res:
                    res["output_path"] = res["out_path"]
            return res

        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def open_file(self, path: str, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            _open_path(str(path))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def print_file(self, path: str, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            if not path:
                return {"ok": False, "error": "Percorso vuoto"}
            if sys.platform.startswith("win"):
                os.startfile(str(path), "print")  # type: ignore[attr-defined]
                return {"ok": True}
            return {"ok": False, "error": "Stampa diretta non supportata su questo OS"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def open_folder(self, path: str, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            _open_path(str(path))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def ping(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"ok": True, "msg": "pong"}

    
    # -----------------------------
    # Archivio Ricette (SQLite)
    # -----------------------------
    def archive_info(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            from backend.archive_db import CATEGORIES_FIXED
            db = self._get_archive_db()
            return {"ok": True, "db_path": str(getattr(db, "db_path", "")), "categories": list(CATEGORIES_FIXED)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def archive_save(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            pl = payload if isinstance(payload, dict) else {}
            recipe = pl.get("recipe")
            if not isinstance(recipe, dict):
                return {"ok": False, "error": "recipe mancante o non valido"}
            db = self._get_archive_db()
            rid = int(db.save_recipe(recipe))
            return {"ok": True, "id": rid}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def archive_search(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            pl = payload if isinstance(payload, dict) else {}
            q = str(pl.get("query") or "")
            category = str(pl.get("category") or "")
            ingredient = str(pl.get("ingredient") or "")
            difficulty = str(pl.get("difficulty") or "")
            seasonality = str(pl.get("seasonality") or "")
            diets = pl.get("require_diets")
            allergens = pl.get("exclude_allergens")
            limit = int(pl.get("limit") or 200)
            missing_only = bool(pl.get("missing_only"))
            missing_field = str(pl.get("missing_field") or "").strip()

            require_diets = [str(x) for x in diets] if isinstance(diets, list) else []
            exclude_allergens = [str(x) for x in allergens] if isinstance(allergens, list) else []

            def _to_float(val: Any) -> Optional[float]:
                if val is None:
                    return None
                if isinstance(val, (int, float)):
                    return float(val)
                s = str(val).strip().replace(",", ".")
                if not s:
                    return None
                try:
                    return float(s)
                except Exception:
                    return None

            servings_min = _to_float(pl.get("servings_min"))
            servings_max = _to_float(pl.get("servings_max"))
            prep_min = _to_float(pl.get("prep_min"))
            prep_max = _to_float(pl.get("prep_max"))
            cook_min = _to_float(pl.get("cook_min"))
            cook_max = _to_float(pl.get("cook_max"))
            total_min = _to_float(pl.get("total_min"))
            total_max = _to_float(pl.get("total_max"))
            kcal_100_min = _to_float(pl.get("kcal_100_min"))
            kcal_100_max = _to_float(pl.get("kcal_100_max"))
            kcal_tot_min = _to_float(pl.get("kcal_tot_min"))
            kcal_tot_max = _to_float(pl.get("kcal_tot_max"))
            cost_min = _to_float(pl.get("cost_min"))
            cost_max = _to_float(pl.get("cost_max"))
            protein_100_min = _to_float(pl.get("protein_100_min"))
            protein_100_max = _to_float(pl.get("protein_100_max"))
            fat_100_min = _to_float(pl.get("fat_100_min"))
            fat_100_max = _to_float(pl.get("fat_100_max"))
            fiber_100_min = _to_float(pl.get("fiber_100_min"))
            fiber_100_max = _to_float(pl.get("fiber_100_max"))
            carb_100_min = _to_float(pl.get("carb_100_min"))
            carb_100_max = _to_float(pl.get("carb_100_max"))
            sugar_100_min = _to_float(pl.get("sugar_100_min"))
            sugar_100_max = _to_float(pl.get("sugar_100_max"))
            protein_tot_min = _to_float(pl.get("protein_tot_min"))
            protein_tot_max = _to_float(pl.get("protein_tot_max"))
            fat_tot_min = _to_float(pl.get("fat_tot_min"))
            fat_tot_max = _to_float(pl.get("fat_tot_max"))
            fiber_tot_min = _to_float(pl.get("fiber_tot_min"))
            fiber_tot_max = _to_float(pl.get("fiber_tot_max"))
            carb_tot_min = _to_float(pl.get("carb_tot_min"))
            carb_tot_max = _to_float(pl.get("carb_tot_max"))
            sugar_tot_min = _to_float(pl.get("sugar_tot_min"))
            sugar_tot_max = _to_float(pl.get("sugar_tot_max"))
            sat_100_min = _to_float(pl.get("sat_100_min"))
            sat_100_max = _to_float(pl.get("sat_100_max"))
            mono_100_min = _to_float(pl.get("mono_100_min"))
            mono_100_max = _to_float(pl.get("mono_100_max"))
            poly_100_min = _to_float(pl.get("poly_100_min"))
            poly_100_max = _to_float(pl.get("poly_100_max"))
            chol_100_min = _to_float(pl.get("chol_100_min"))
            chol_100_max = _to_float(pl.get("chol_100_max"))
            sat_tot_min = _to_float(pl.get("sat_tot_min"))
            sat_tot_max = _to_float(pl.get("sat_tot_max"))
            mono_tot_min = _to_float(pl.get("mono_tot_min"))
            mono_tot_max = _to_float(pl.get("mono_tot_max"))
            poly_tot_min = _to_float(pl.get("poly_tot_min"))
            poly_tot_max = _to_float(pl.get("poly_tot_max"))
            chol_tot_min = _to_float(pl.get("chol_tot_min"))
            chol_tot_max = _to_float(pl.get("chol_tot_max"))
            sodium_100_min = _to_float(pl.get("sodium_100_min"))
            sodium_100_max = _to_float(pl.get("sodium_100_max"))
            sodium_tot_min = _to_float(pl.get("sodium_tot_min"))
            sodium_tot_max = _to_float(pl.get("sodium_tot_max"))
            cost_total_min = _to_float(pl.get("cost_total_min"))
            cost_total_max = _to_float(pl.get("cost_total_max"))

            db = self._get_archive_db()
            items = db.search(
                query=q,
                category=category,
                ingredient_query=ingredient,
                require_diets=require_diets,
                exclude_allergens=exclude_allergens,
                difficulty=difficulty,
                seasonality=seasonality,
                servings_min=servings_min,
                servings_max=servings_max,
                prep_min=prep_min,
                prep_max=prep_max,
                cook_min=cook_min,
                cook_max=cook_max,
                total_min=total_min,
                total_max=total_max,
                kcal_100_min=kcal_100_min,
                kcal_100_max=kcal_100_max,
                kcal_tot_min=kcal_tot_min,
                kcal_tot_max=kcal_tot_max,
                cost_min=cost_min,
                cost_max=cost_max,
                protein_100_min=protein_100_min,
                protein_100_max=protein_100_max,
                fat_100_min=fat_100_min,
                fat_100_max=fat_100_max,
                fiber_100_min=fiber_100_min,
                fiber_100_max=fiber_100_max,
                carb_100_min=carb_100_min,
                carb_100_max=carb_100_max,
                sugar_100_min=sugar_100_min,
                sugar_100_max=sugar_100_max,
                protein_tot_min=protein_tot_min,
                protein_tot_max=protein_tot_max,
                fat_tot_min=fat_tot_min,
                fat_tot_max=fat_tot_max,
                fiber_tot_min=fiber_tot_min,
                fiber_tot_max=fiber_tot_max,
                carb_tot_min=carb_tot_min,
                carb_tot_max=carb_tot_max,
                sugar_tot_min=sugar_tot_min,
                sugar_tot_max=sugar_tot_max,
                sat_100_min=sat_100_min,
                sat_100_max=sat_100_max,
                mono_100_min=mono_100_min,
                mono_100_max=mono_100_max,
                poly_100_min=poly_100_min,
                poly_100_max=poly_100_max,
                chol_100_min=chol_100_min,
                chol_100_max=chol_100_max,
                sat_tot_min=sat_tot_min,
                sat_tot_max=sat_tot_max,
                mono_tot_min=mono_tot_min,
                mono_tot_max=mono_tot_max,
                poly_tot_min=poly_tot_min,
                poly_tot_max=poly_tot_max,
                chol_tot_min=chol_tot_min,
                chol_tot_max=chol_tot_max,
                sodium_100_min=sodium_100_min,
                sodium_100_max=sodium_100_max,
                sodium_tot_min=sodium_tot_min,
                sodium_tot_max=sodium_tot_max,
                cost_total_min=cost_total_min,
                cost_total_max=cost_total_max,
                missing_only=missing_only,
                missing_field=missing_field,
                limit=limit,
            )
            return {
                "ok": True,
                "items": [
                    {"id": it.id, "title": it.title, "category": it.category, "updated_at": it.updated_at}
                    for it in items
                ],
            }
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def archive_load(self, recipe_id: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            rid = int(recipe_id) if recipe_id is not None else 0
            if rid <= 0:
                return {"ok": False, "error": "id non valido"}
            db = self._get_archive_db()
            recipe = db.load_recipe(rid)
            if not recipe:
                return {"ok": False, "error": "Ricetta non trovata"}
            return {"ok": True, "recipe": recipe}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def archive_delete(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            pl = payload if isinstance(payload, dict) else {}
            ids = pl.get("ids")
            if not isinstance(ids, list) or not ids:
                return {"ok": False, "error": "ids mancanti"}
            db = self._get_archive_db()
            n = db.delete_recipes(ids)
            return {"ok": True, "deleted": n}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def archive_export_batch(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Esporta più ricette come PDF singoli in una cartella."""
        try:
            pl = payload if isinstance(payload, dict) else {}
            ids = pl.get("ids")
            if not isinstance(ids, list) or not ids:
                return {"ok": False, "error": "ids mancanti"}

            template = pl.get("template") or pl.get("pdf_template") or "Template_Ricetta_AI"
            out_dir = pl.get("out_dir") or pl.get("output_dir") or self._output_dir
            if not out_dir:
                out_dir = _default_output_dir()
                self._output_dir = out_dir
            Path(out_dir).mkdir(parents=True, exist_ok=True)

            db = self._get_archive_db()
            from backend.pipeline import export_pdf as _export_pdf

            out_paths: List[str] = []
            for rid_raw in ids:
                rid = int(rid_raw)
                recipe = db.load_recipe(rid)
                if not recipe:
                    continue
                title = recipe.get("title") or f"ricetta_{rid}"
                fname = _safe_filename(str(title)) + ".pdf"
                path = str((Path(out_dir) / fname).resolve())
                try:
                    _export_pdf(recipe, path, template=str(template), progress=self._progress)
                    out_paths.append(path)
                except Exception:
                    continue

            return {"ok": True, "out_dir": out_dir, "files": out_paths, "count": len(out_paths)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------
    # Cloud AI settings (OpenAI/Gemini): gestione da UI
    # ------------------------------------------------------------
    def get_cloud_ai_settings(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            from backend.cloud_settings import masked_settings_for_ui
            return {"ok": True, "settings": masked_settings_for_ui()}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def set_cloud_ai_settings(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                payload = {}
            from backend.cloud_settings import update_settings_from_ui, masked_settings_for_ui
            s = update_settings_from_ui(payload)
            return {"ok": True, "settings": masked_settings_for_ui(s)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def test_cloud_ai(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        try:
            from backend.cloud_ai import test_cloud_connection
            return test_cloud_connection()
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    def recipe_load(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Carica una ricetta dal database"""
        try:
            pl = payload if isinstance(payload, dict) else {}
            recipe_id = int(pl.get("id", 0))
            if recipe_id <= 0:
                return {"ok": False, "error": "ID ricetta non valido"}
            
            db = self._get_archive_db()
            recipe = db.load_recipe(recipe_id)
            if not recipe:
                return {"ok": False, "error": f"Ricetta {recipe_id} non trovata"}
            
            return {"ok": True, "recipe": recipe}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def recipe_scale(self, payload: Any = None, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Scala gli ingredienti di una ricetta
        Supporta scaling per:
        - porzioni (scala da porzioni_originali a porzioni_richieste)
        - fattore (scala di X volte)
        - peso_totale (scala per raggiungere peso totale target)
        """
        try:
            pl = payload if isinstance(payload, dict) else {}
            recipe = pl.get("recipe")
            if not isinstance(recipe, dict):
                return {"ok": False, "error": "Ricetta non valida"}
            
            # Tipo di scaling
            scale_type = str(pl.get("scale_type", "porzioni")).lower()  # porzioni, fattore, peso
            
            scaled = dict(recipe)
            ingredients = recipe.get("ingredients", [])
            if not isinstance(ingredients, list):
                return {"ok": False, "error": "Ingredienti non validi"}
            
            # Calcola fattore di scala
            scale_factor = 1.0
            
            if scale_type == "fattore":
                scale_factor = float(pl.get("factor", 1.0))
            
            elif scale_type == "porzioni":
                original_portions = float(recipe.get("servings", 1) or 1)
                target_portions = float(pl.get("target_servings", 1) or 1)
                scale_factor = target_portions / original_portions if original_portions > 0 else 1.0
            
            elif scale_type == "peso":
                # Calcola peso totale ingredienti
                total_weight = 0
                for ing in ingredients:
                    if isinstance(ing, dict):
                        qty = ing.get("quantity", 0)
                        if isinstance(qty, (int, float)):
                            total_weight += qty
                
                target_weight = float(pl.get("target_weight", total_weight) or total_weight)
                scale_factor = target_weight / total_weight if total_weight > 0 else 1.0
            
            # Scala ingredienti
            scaled_ingredients = []
            for ing in ingredients:
                if isinstance(ing, dict):
                    scaled_ing = dict(ing)
                    qty = ing.get("quantity", 0)
                    if isinstance(qty, (int, float)):
                        scaled_ing["quantity"] = round(qty * scale_factor, 2)
                    scaled_ingredients.append(scaled_ing)
                else:
                    scaled_ingredients.append(ing)
            
            scaled["ingredients"] = scaled_ingredients
            scaled["scale_factor"] = round(scale_factor, 2)
            scaled["original_servings"] = recipe.get("servings", 1)
            scaled["scaled_servings"] = round(float(recipe.get("servings", 1) or 1) * scale_factor, 1)
            
            return {"ok": True, "recipe": scaled}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    
    # ============ SUBSCRIPTION & API USAGE ============
    
    def get_subscription(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera la sottoscrizione corrente"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            return self._subscription_mgr.get_subscription(user_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def check_quota(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica quota disponibile"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            quota = self._subscription_mgr.check_quota(user_id)
            return {"ok": True, **quota}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def record_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Registra una ricetta AI creata (per tracking)"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            result = self._subscription_mgr.record_api_call(user_id)
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def upgrade_subscription(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Esegui upgrade della sottoscrizione"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            new_tier = payload.get("tier", "pro")
            result = self._subscription_mgr.upgrade_tier(user_id, new_tier)
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_monthly_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera riepilogo mensile"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            month = payload.get("month")
            summary = self._subscription_mgr.get_monthly_summary(user_id, month)
            return {"ok": True, **summary}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def generate_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Genera fattura per il mese"""
        try:
            user_id = payload.get("user_id", self._current_user_id)
            month = payload.get("month")
            invoice = self._subscription_mgr.generate_invoice(user_id, month)
            return {"ok": True, **invoice}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ============ STRIPE PAYMENTS ============
    
    def create_checkout_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Crea sessione checkout Stripe per upgrade"""
        try:
            if not self._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            user_id = payload.get("user_id", self._current_user_id)
            tier = payload.get("tier", "pro")
            email = payload.get("email", f"{user_id}@cooksy.local")
            
            result = self._stripe_mgr.create_checkout_session(user_id, tier, email)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_stripe_publishable_key(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Restituisce la chiave pubblica Stripe per il frontend"""
        try:
            if not self._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            key = self._stripe_mgr.get_publishable_key()
            return {"ok": True, "publishable_key": key}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_subscription_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera lo stato della sottoscrizione Stripe"""
        try:
            if not self._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            customer_id = payload.get("customer_id")
            if not customer_id:
                return {"ok": False, "error": "customer_id richiesto"}
            
            result = self._stripe_mgr.get_subscription_status(customer_id)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def cancel_subscription(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Annulla una sottoscrizione Stripe"""
        try:
            if not self._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            subscription_id = payload.get("subscription_id")
            if not subscription_id:
                return {"ok": False, "error": "subscription_id richiesto"}
            
            result = self._stripe_mgr.cancel_subscription(subscription_id)
            
            # Se cancellazione riuscita, downgrade a free
            if result.get("ok"):
                user_id = payload.get("user_id", self._current_user_id)
                self._subscription_mgr.upgrade_tier(user_id, "free")
            
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_install_info(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Ritorna info installazione (terms_bypass per primo avvio da EXE)"""
        return {
            "terms_bypass_fresh_install": self._terms_bypass_fresh_install
        }

    def open_external_browser(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Apre un URL nel browser esterno predefinito del sistema"""
        try:
            import webbrowser
            url = payload.get("url", "")
            if not url:
                return {"ok": False, "error": "URL mancante"}
            
            # Apre nel browser predefinito
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_legal_document(self, doc_type: str = "terms", *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        """Legge i documenti legali (TERMS_AND_CONDITIONS.md o LICENSE.md)"""
        try:
            if doc_type == "terms":
                filename = "TERMS_AND_CONDITIONS.md"
            elif doc_type == "license":
                filename = "LICENSE.md"
            else:
                return {"ok": False, "error": "Tipo documento non valido"}
            
            # Cerca il file in data/legal/ (dentro l'installer)
            legal_path = project_root() / "data" / "legal" / filename
            
            if legal_path.exists():
                with open(legal_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return {"ok": True, "content": content, "filename": filename}
            else:
                return {"ok": False, "error": f"File {filename} non trovato"}
        except Exception as e:
            print(f"[ERROR] get_legal_document failed: {e}", file=sys.stderr)
            return {"ok": False, "error": str(e)}