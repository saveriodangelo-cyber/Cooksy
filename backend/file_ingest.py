from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog
from typing import List, Optional

# --- LISTA COMPLETA ESTENSIONI ---
VALID_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
    ".pdf",
    ".txt", ".log",
    ".docx"
}

# Limite dimensione file (MB)
MAX_MB = 15

@dataclass(frozen=True)
class PickResult:
    paths: List[str]
    errors: List[str]
    cancelled: bool = False

def _is_valid(p: Path) -> bool:
    if not p.is_file():
        return False
    if p.name.startswith(("~", ".")):
        return False
    if p.suffix.lower() not in VALID_EXTS:
        return False
    try:
        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > MAX_MB:
            return False
    except Exception:
        return False
    return True

def get_files_recursive(folder_path: str) -> List[str]:
    """Cerca in TUTTE le sottocartelle."""
    found = []
    root = Path(folder_path).resolve()
    if not root.exists(): return []
    
    for r, d, f in os.walk(str(root)):
        for name in f:
            p = Path(r) / name
            if _is_valid(p): found.append(str(p))
    found.sort()
    return found

def pick_folder_tk(initial_dir: Optional[str] = None) -> PickResult:
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        d = filedialog.askdirectory(title="Seleziona Cartella Ricette", initialdir=initial_dir or str(Path.home()))
        root.destroy()
        if not d: return PickResult([], [], True)
        
        files = get_files_recursive(d)
        if not files: return PickResult([], ["Nessun file valido (.docx, .pdf, img) trovato."])
        return PickResult(files, [])
    except Exception as e:
        return PickResult([], [str(e)])

def pick_any_files_tk(title="Seleziona file", initial_dir=None, patterns=None) -> PickResult:
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        if not patterns: patterns = [("Tutti", "*.docx *.pdf *.png *.jpg"), ("Word", "*.docx"), ("PDF", "*.pdf")]
        f = filedialog.askopenfilenames(title=title, initialdir=initial_dir or str(Path.home()), filetypes=patterns)
        root.destroy()
        if not f: return PickResult([], [], True)
        return PickResult([str(Path(p).resolve()) for p in f], [])
    except Exception as e:
        return PickResult([], [str(e)])

pick_images_tk = pick_any_files_tk