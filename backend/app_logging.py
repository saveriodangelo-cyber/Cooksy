import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional
import threading
import time

_LOG_LOCK = threading.Lock()
_LOGGER: Optional[logging.Logger] = None
_AUDIT_LOGGER: Optional[logging.Logger] = None


def _default_output_dir() -> Path:
    try:
        if os.name == "nt":
            try:
                import winreg  # type: ignore

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                ) as k:
                    desktop, _ = winreg.QueryValueEx(k, "Desktop")
                if desktop:
                    desktop = os.path.expandvars(str(desktop))
                    return (Path(desktop) / "Elaborate").resolve()
            except Exception:
                pass
        home = Path(os.environ.get("USERPROFILE") or Path.home())
        desktop = home / "Desktop"
        base = desktop if desktop.exists() else home
        return (base / "Elaborate").resolve()
    except Exception:
        return (Path(".") / "Elaborate").resolve()


def _ensure_logs_dir() -> Path:
    base = _default_output_dir()
    logs = base / "_logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def get_logger(run_id: Optional[str] = None) -> logging.Logger:
    global _LOGGER
    with _LOG_LOCK:
        if _LOGGER is not None:
            return _LOGGER
        logs_dir = _ensure_logs_dir()
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_name = f"run_{run_id or ts}.log"
        log_path = logs_dir / log_name
        logger = logging.getLogger("ricette")
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] run=%(run_id)s file=%(file_id)s stage=%(stage)s status=%(status)s %(message)s"
        )
        handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.propagate = False
        _LOGGER = logger
        return logger


def get_audit_logger() -> logging.Logger:
    """Logger dedicato agli eventi di sicurezza (auth, sessioni)."""
    global _AUDIT_LOGGER
    with _LOG_LOCK:
        if _AUDIT_LOGGER is not None:
            return _AUDIT_LOGGER
        logs_dir = _ensure_logs_dir()
        log_path = logs_dir / "security_audit.log"
        logger = logging.getLogger("ricette.audit")
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] user=%(user_id)s event=%(event)s status=%(status)s %(message)s"
        )
        handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.propagate = False
        _AUDIT_LOGGER = logger
        return logger


def truncate_text(text: Any, max_len: int = 500) -> str:
    try:
        s = str(text or "")
        if len(s) > max_len:
            return s[:max_len] + "..." + f"[truncated {len(s) - max_len} chars]"
        return s
    except Exception:
        return ""


def log_event(
    logger: logging.Logger,
    *,
    run_id: str,
    file_id: str,
    stage: str,
    status: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    data = extra or {}
    try:
        logger.info(message, extra={"run_id": run_id, "file_id": file_id, "stage": stage, **data, "status": status})
    except Exception:
        try:
            logger.error(f"Logging failure: {message}")
        except Exception:
            pass


def log_security_event(
    *,
    event: str,
    status: str,
    user_id: Optional[str] = None,
    detail: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Logga eventi di sicurezza in un file dedicato."""
    data = extra or {}
    logger = get_audit_logger()
    message = detail or ""
    try:
        logger.info(message, extra={"user_id": user_id or "-", "event": event, "status": status, **data})
    except Exception:
        try:
            logger.error(f"Logging failure: {event} {message}")
        except Exception:
            pass
