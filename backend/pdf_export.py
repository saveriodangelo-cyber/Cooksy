from __future__ import annotations

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Cache globale per template compilati e environment Jinja2
_JINJA_ENV_CACHE: Any = None
_JINJA_ENV_CACHE_SILENT: Any = None
_TEMPLATE_CACHE: Dict[str, Any] = {}
_TEMPLATE_CACHE_SILENT: Dict[str, Any] = {}

def _get_jinja_env_types():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape, StrictUndefined
        return Environment, FileSystemLoader, select_autoescape, StrictUndefined
    except Exception:
        return None, None, None, None

def _get_jinja_env_types_silent():
    """Ritorna Jinja2 types con Undefined base per preview (non lancia errori su variabili mancanti)"""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape, Undefined
        return Environment, FileSystemLoader, select_autoescape, Undefined
    except Exception:
        return None, None, None, None

_TEMPLATE_FALLBACK = "Template_Ricetta_AI"


def list_templates() -> List[str]:
    meipass = getattr(sys, "_MEIPASS", None)
    frozen = getattr(sys, "frozen", False)
    
    # Try multiple paths for template location
    candidates = []
    
    if frozen and meipass:
        candidates.append(Path(meipass) / "templates")
        candidates.append(Path(meipass) / "_internal" / "templates")
    
    # Always add source path (works in dev and as fallback)
    candidates.append(Path(__file__).parent.parent / "templates")
    
    # For frozen builds, also try executable directory
    if frozen:
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "_internal" / "templates")
        candidates.append(exe_dir / "templates")
    
    base = None
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            base = candidate
            break
    
    if not base:
        err_msg = f"[pdf_export] Templates dir not found. Tried: {[str(c) for c in candidates]}. frozen={frozen}, meipass={meipass}, exe={sys.executable if frozen else 'N/A'}"
        print(err_msg, file=sys.stderr)
        return [_TEMPLATE_FALLBACK]
    
    try:
        # Include all .html files except _* files (private)
        templates = sorted([f.stem for f in base.glob("*.html") if not f.name.startswith("_")])
        msg = f"[pdf_export] Found {len(templates)} templates at {base}"
        print(msg, file=sys.stderr)
        return templates if templates else [_TEMPLATE_FALLBACK]
    except Exception as e:
        print(f"[pdf_export] Error scanning templates: {e}", file=sys.stderr)
        return [_TEMPLATE_FALLBACK]


def _resolve_template_name(template: str) -> str:
    t = (template or "").strip()
    if t.lower().startswith("html:"):
        t = t.split(":", 1)[1].strip()
    if not t:
        return _TEMPLATE_FALLBACK
    return t


def _template_path(name: str) -> Path:
    # PyInstaller: usa _MEIPASS se presente, altrimenti path normale
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        base = Path(meipass) / "templates"
    else:
        base = Path(__file__).parent.parent / "templates"
    backup = base / "_backup"
    if name != _TEMPLATE_FALLBACK and backup.exists():
        candidate = backup / f"{name}.html"
        if candidate.exists():
            return candidate
    return base / f"{name}.html"


def _page_css(page_size: str) -> str:
    ps = (page_size or "A4").strip().upper()
    css = {
        "A3": "@page { size: A3; margin: 18mm; }",
        "A4": "@page { size: A4; margin: 15mm; }",
        "A5": "@page { size: A5; margin: 10mm; } body { font-size: 0.9em; }",
        "A6": "@page { size: A6; margin: 8mm; } body { font-size: 0.85em; }",
        "B5": "@page { size: B5; margin: 12mm; } body { font-size: 0.95em; }",
        "LETTER": "@page { size: Letter; margin: 15mm; }",
        "LEGAL": "@page { size: Legal; margin: 15mm; }",
        "TABLOID": "@page { size: Tabloid; margin: 18mm; }",
        "KDP_6X9": "@page { size: 6in 9in; margin: 0.5in; } body { font-size: 10pt; }",
        "KDP": "@page { size: 6in 9in; margin: 0.5in; } body { font-size: 10pt; }",
        "KDP_5X8": "@page { size: 5in 8in; margin: 0.45in; } body { font-size: 10pt; }",
        "KDP_5_5X8_5": "@page { size: 5.5in 8.5in; margin: 0.5in; } body { font-size: 10pt; }",
        "KDP_7_5X9_25": "@page { size: 7.5in 9.25in; margin: 0.6in; } body { font-size: 11pt; }",
        "KDP_8_5X8_5": "@page { size: 8.5in 8.5in; margin: 0.6in; } body { font-size: 11pt; }",
        "KDP_8_5X11": "@page { size: 8.5in 11in; margin: 0.6in; } body { font-size: 11pt; }",
    }
    return css.get(ps, css["A4"])


def _ensure_jinja_rendered(html: str, template_name: str = "") -> str:
    """Verifica che l'HTML non contenga tag Jinja non renderizzati.
    Se trovati, lancia RuntimeError con messaggio esplicito.
    """
    jinja_markers = ["{%", "{{", "{#"]
    for marker in jinja_markers:
        if marker in html:
            raise RuntimeError(
                f"Errore rendering template '{template_name}': "
                f"trovati tag Jinja non renderizzati ('{marker}') nell'HTML finale. "
                f"Il template potrebbe contenere variabili o include non definiti."
            )
    return html


def render_html_template(
    context: Dict[str, Any],
    template: str,
    assets_dir: Optional[str] = None,
    silent_mode: bool = False,
) -> str:
    """Renderizza un template HTML via Jinja2 con supporto completo di include e autoescape.
    
    Args:
        context: dati da passare al template
        template: nome template (es. "html:serra", "Template_Ricetta_AI")
        assets_dir: cartella assets per risoluzione risorse relative
        silent_mode: se True, non lancia errori su variabili non definite (usa SilentUndefined)
    
    Returns:
        HTML renderizzato completamente (nessun tag Jinja visibile)
        
    Raises:
        RuntimeError: se rendering fallisce o tag Jinja rimangono nell'output
    """
    base = Path(__file__).parent.parent / "templates"
    backup = base / "_backup"
    if not assets_dir:
        default_assets = base / "assets"
        if default_assets.exists() and default_assets.is_dir():
            assets_dir = str(default_assets)
    
    name = _resolve_template_name(template)
    tpl_path = _template_path(name)
    if not tpl_path.exists():
        name = _TEMPLATE_FALLBACK
        tpl_path = _template_path(name)

    ctx = dict(context or {})
    if "recipe" not in ctx:
        ctx["recipe"] = dict(context or {})

    if assets_dir:
        try:
            base_uri = Path(assets_dir).resolve().as_uri()
            if not base_uri.endswith("/"):
                base_uri += "/"
            ctx["assets_base"] = base_uri
        except Exception:
            ctx["assets_base"] = str(assets_dir)

    if silent_mode:
        Environment, FileSystemLoader, select_autoescape, UndefinedClass = _get_jinja_env_types_silent()
    else:
        Environment, FileSystemLoader, select_autoescape, UndefinedClass = _get_jinja_env_types()
    
    if not (Environment and FileSystemLoader):
        raw = tpl_path.read_text(encoding="utf-8", errors="replace")
        return raw

    global _JINJA_ENV_CACHE, _JINJA_ENV_CACHE_SILENT, _TEMPLATE_CACHE, _TEMPLATE_CACHE_SILENT

    search_paths = [str(base)]
    if backup.exists():
        search_paths.insert(0, str(backup))

    # Usa cache separate per modalità strict vs silent
    if silent_mode:
        cache_var_name = '_JINJA_ENV_CACHE_SILENT'
        env_cache = _JINJA_ENV_CACHE_SILENT
        tpl_cache = _TEMPLATE_CACHE_SILENT
    else:
        cache_var_name = '_JINJA_ENV_CACHE'
        env_cache = _JINJA_ENV_CACHE
        tpl_cache = _TEMPLATE_CACHE

    if env_cache is None:
        try:
            env_kwargs: Dict[str, Any] = {
                "loader": FileSystemLoader(search_paths),
            }
            if select_autoescape:
                env_kwargs["autoescape"] = select_autoescape(enabled_extensions=("html", "xml"))
            if UndefinedClass:
                env_kwargs["undefined"] = UndefinedClass
            env_cache = Environment(**env_kwargs)
            # Aggiorna il cache globale appropriato
            if silent_mode:
                _JINJA_ENV_CACHE_SILENT = env_cache
            else:
                _JINJA_ENV_CACHE = env_cache
        except Exception as e:
            raise RuntimeError(f"Errore inizializzazione Jinja2: {e}")
    env = env_cache

    try:
        # Carica template da cache o compila se non presente
        tpl_key = f"{name}.html"
        if tpl_key not in tpl_cache:
            tpl_cache[tpl_key] = env.get_template(tpl_key)
            # Aggiorna anche la cache globale appropriata
            if silent_mode:
                _TEMPLATE_CACHE_SILENT[tpl_key] = tpl_cache[tpl_key]
            else:
                _TEMPLATE_CACHE[tpl_key] = tpl_cache[tpl_key]
        tpl = tpl_cache[tpl_key]
        html = tpl.render(**ctx)
    except Exception as render_err:
        raise RuntimeError(
            f"Errore rendering template '{name}': {render_err}\n"
            f"Verifica che tutte le variabili e include siano disponibili."
        )

    # Guardrail: verifica che non ci siano tag Jinja nell'output
    # In silent_mode, i tag Jinja che rimangono sono normali (variabili non definite)
    if not silent_mode:
        _ensure_jinja_rendered(html, template_name=name)

    return html



def export_recipe_pdf(
    recipe: Any,
    out_path: str,
    template: str = _TEMPLATE_FALLBACK,
    page_size: str = "A4",
    assets_dir: Optional[str] = None,
) -> str:
    ctx = recipe if isinstance(recipe, dict) else {}
    html = render_html_template(ctx, template=template, assets_dir=assets_dir)
    html = f"<style>{_page_css(page_size)}</style>" + html

    tmp = Path(tempfile.mkdtemp()) / "render.html"
    tmp.write_text(html, encoding="utf-8")

    browsers = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    exe = next((b for b in browsers if os.path.exists(b)), None)

    if not exe:
        raise RuntimeError("Nessun browser supportato trovato (Edge/Chrome)")

    subprocess.run(
        [
            exe,
            "--headless=new",
            "--allow-file-access-from-files",
            "--disable-logging",
            "--log-level=3",
            "--disable-background-networking",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            f"--print-to-pdf={os.path.abspath(out_path)}",
            "--no-margins",
            str(tmp),
        ],
        check=True,
    )

    return out_path
