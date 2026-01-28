# backend/progress.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from threading import Lock
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProgressSnapshot:
    pct: int
    stage: str
    message: str
    running: bool
    done: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        # compat: UI/bridge si aspettano anche 'msg'
        d = asdict(self)
        d["msg"] = d.get("message", "")
        return d


class Progress:
    """Progress thread-safe, serializzabile.

    Convenzione usata da UI/pipeline:
      - progress.set(pct:int, stage:str, message:str)
      - bridge.get_progress() -> {pct, stage, msg}
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._pct: int = 0
        self._stage: str = "idle"
        self._message: str = ""
        self._running: bool = False
        self._done: bool = False
        self._error: Optional[str] = None

    # --------------------
    # Properties (read-only)
    # --------------------
    @property
    def pct(self) -> int:
        with self._lock:
            return int(self._pct)

    @property
    def stage(self) -> str:
        with self._lock:
            return str(self._stage)

    @property
    def message(self) -> str:
        with self._lock:
            return str(self._message)

    @property
    def msg(self) -> str:
        # alias richiesto dalla UI
        return self.message

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._running)

    @property
    def done(self) -> bool:
        with self._lock:
            return bool(self._done)

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    # --------------------
    # Mutators
    # --------------------
    def reset(self) -> None:
        with self._lock:
            self._pct = 0
            self._stage = "idle"
            self._message = ""
            self._running = False
            self._done = False
            self._error = None

    def set(self, pct: int, stage: str, message: str = "") -> None:
        pct_i = int(pct)
        if pct_i < 0:
            pct_i = 0
        if pct_i > 100:
            pct_i = 100

        with self._lock:
            self._pct = pct_i
            self._stage = str(stage)
            self._message = str(message)
            self._running = True
            self._done = pct_i >= 100
            # aggiornando il progresso consideriamo l'esecuzione "in corso"
            # e resettiamo eventuale errore precedente
            if self._stage != "error":
                self._error = None

    def mark_done(self, message: str = "Completato") -> None:
        with self._lock:
            self._pct = 100
            self._stage = "done"
            self._message = str(message)
            self._running = False
            self._done = True

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._error = str(message)
            self._stage = "error"
            self._message = str(message)
            self._running = False
            self._done = True

    # --------------------
    # Snapshots
    # --------------------
    def snapshot(self) -> ProgressSnapshot:
        with self._lock:
            return ProgressSnapshot(
                pct=int(self._pct),
                stage=str(self._stage),
                message=str(self._message),
                running=bool(self._running),
                done=bool(self._done),
                error=self._error,
            )

    def get(self) -> Dict[str, Any]:
        """Compat per bridge/ui: ritorna dict con 'msg'."""
        return self.snapshot().to_dict()
