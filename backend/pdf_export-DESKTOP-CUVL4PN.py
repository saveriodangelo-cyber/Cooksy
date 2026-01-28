from __future__ import annotations

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.utils import project_root

# Cache globale per template compilati e environment Jinja2
_JINJA_ENV_CACHE: Any = None
_TEMPLATE_CACHE: Dict[str, Any] = {}

def _get_jinja_env_types():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape, StrictUndefined
        return Environment, FileSystemLoader, select_autoescape, StrictUndefined
    except Exception:
        return None, None, None, None

_TEMPLATE_FALLBACK = "Template_Ricetta_AI"


def _templates_base() -> Path:
    """Risolvi la cartella templates sia in sviluppo che in eseguibile PyInstaller."""
    try:
        logfile = Path(sys.executable).parent / "templates_debug.txt" if getattr(sys, "frozen", False) else Path("templates_debug.txt")
        with open(logfile, "a", encoding="utf-8") as f:
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent
                cand = exe_dir / "_internal" / "templates"
                f.write(f"[pdf_export] FROZEN mode: exe_dir={exe_dir}, templates={cand}, exists={cand.exists()}\n")
                if cand.exists():
                    return cand
            root = project_root() / "templates"
            f.write(f"[pdf_export] DEV mode: templates={root}, exists={root.exists()}\n")
            return root
    except Exception as e:
        print(f"[pdf_export] Errore logging: {e}")
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "_internal" / "templates"
        return project_root() / "templates"


def list_templates() -> List[str]:
    base = _templates_base()
    try:
        logfile = Path(sys.executable).parent / "templates_debug.txt" if getattr(sys, "frozen", False) else Path("templates_debug.txt")
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"[pdf_export] list_templates() - base={base}\n")
            if not base.exists():
                f.write(f"[pdf_export] Templates dir NOT FOUND at {base}\n")
                return [_TEMPLATE_FALLBACK]

            templates = [f.stem for f in base.glob("*.html") if not f.name.startswith("_")]
            f.write(f"[pdf_export] Trovati {len(templates)} file .html: {templates[:10]}\n")
            return templates if templates else [_TEMPLATE_FALLBACK]
    except Exception as e:
        print(f"[pdf_export] Errore list_templates: {e}")
        return [_TEMPLATE_FALLBACK]


def _resolve_template_name(template: str) -> str:
    t = (template or "").strip()
    if t.lower().startswith("html:"):
        t = t.split(":", 1)[1].strip()
    if not t:
        return _TEMPLATE_FALLBACK
    return t


def _template_path(name: str) -> Path:
    base = _templates_base()
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
) -> str:
    """Renderizza un template HTML via Jinja2 con supporto completo di include e autoescape.
    
    Args:
        context: dati da passare al template
        template: nome template (es. "html:serra", "Template_Ricetta_AI")
        assets_dir: cartella assets per risoluzione risorse relative
    
    Returns:
        HTML renderizzato completamente (nessun tag Jinja visibile)
        
    Raises:
        RuntimeError: se rendering fallisce o tag Jinja rimangono nell'output
    """
    base = _templates_base()
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

    Environment, FileSystemLoader, select_autoescape, StrictUndefined = _get_jinja_env_types()
    if not (Environment and FileSystemLoader):
        raw = tpl_path.read_text(encoding="utf-8", errors="replace")
        return raw

    global _JINJA_ENV_CACHE, _TEMPLATE_CACHE

    search_paths = [str(base)]
    if backup.exists():
        search_paths.insert(0, str(backup))

    if _JINJA_ENV_CACHE is None:
        try:
            env_kwargs: Dict[str, Any] = {
                "loader": FileSystemLoader(search_paths),
            }
            if select_autoescape:
                env_kwargs["autoescape"] = select_autoescape(enabled_extensions=("html", "xml"))
            if StrictUndefined:
                env_kwargs["undefined"] = StrictUndefined
            _JINJA_ENV_CACHE = Environment(**env_kwargs)
        except Exception as e:
            raise RuntimeError(f"Errore inizializzazione Jinja2: {e}")
    env = _JINJA_ENV_CACHE

    try:
        # Carica template da cache o compila se non presente
        tpl_key = f"{name}.html"
        if tpl_key not in _TEMPLATE_CACHE:
            _TEMPLATE_CACHE[tpl_key] = env.get_template(tpl_key)
        tpl = _TEMPLATE_CACHE[tpl_key]
        html = tpl.render(**ctx)
    except Exception as render_err:
        raise RuntimeError(
            f"Errore rendering template '{name}': {render_err}\n"
            f"Verifica che tutte le variabili e include siano disponibili."
        )

    # Guardrail: verifica che non ci siano tag Jinja nell'output
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
