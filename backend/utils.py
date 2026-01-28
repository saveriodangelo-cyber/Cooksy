from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, TypeAlias

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


def project_root() -> Path:
    """
    Best-effort project root locator.
    Assumes this file is in <root>/backend/utils.py => root is parent of 'backend'.
    In a frozen (PyInstaller) app, returns the _internal directory path.
    """
    if getattr(sys, "frozen", False):
        # App congelata con PyInstaller
        exe_dir = Path(sys.executable).parent
        return exe_dir / "_internal"
    return Path(__file__).resolve().parents[1]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_under(base: Path, *parts: str) -> Path:
    """
    Resolve a path under `base`, preventing path traversal.
    Raises ValueError if the resolved path escapes `base`.
    """
    base_resolved = base.resolve()
    candidate = (base_resolved.joinpath(*parts)).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes base directory: {candidate}") from exc
    return candidate


def as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y", "ok", "on"}:
            return True
        if v in {"false", "0", "no", "n", "off"}:
            return False
    return default


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return default
    return default


def json_safe(value: Any, *, strict: bool = False) -> JSONValue:
    """
    Convert arbitrary data into JSON-serializable structures.

    - Dataclasses/models: uses .to_dict() if present
    - Path: converted to str
    - Unknown objects: str(value) unless strict=True (then raises TypeError)
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (list, tuple)):
        return [json_safe(v, strict=strict) for v in value]

    if isinstance(value, dict):
        out: dict[str, JSONValue] = {}
        for k, v in value.items():
            out[as_str(k)] = json_safe(v, strict=strict)
        return out

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return json_safe(to_dict(), strict=strict)

    if strict:
        raise TypeError(f"Value is not JSON-serializable: {type(value)!r}")
    return str(value)


def dumps(data: Any, *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(
        json_safe(data, strict=False),
        ensure_ascii=False,
        indent=indent,
        sort_keys=sort_keys,
    )


def loads(text: str) -> Any:
    return json.loads(text)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any, *, indent: int = 2, sort_keys: bool = True) -> None:
    """
    Atomic-ish write: write to temp file then replace.
    """
    ensure_dir(path.parent)
    payload = dumps(data, indent=indent, sort_keys=sort_keys)

    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
        os.replace(tmp_name, path)
    finally:
        # If replace failed, cleanup temp.
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass


def get_mapping(d: Any) -> Mapping[str, Any]:
    if not isinstance(d, Mapping):
        raise TypeError(f"Expected mapping/dict, got: {type(d)!r}")
    return d
