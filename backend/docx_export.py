from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None


def _pick(recipe: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        val = recipe.get(k)
        if val is None:
            continue
        s = str(val).strip()
        if s:
            return s
    return default


def _sanitize_for_docx(val: Any) -> str:
    """Sanitizza i dati per evitare problemi con XML nel DOCX"""
    if val is None:
        return ""
    s = str(val)
    # Rimuovi o escape caratteri problematici
    # # è problematico in alcuni contesti XML
    s = s.replace("\x00", "").replace("\r\n", "\n")
    return s


def export_recipe_docx(recipe: Dict[str, Any], output_path: str) -> bool:
    """
    Fill template_base.docx with recipe data.
    """
    if not DocxTemplate:
        print("[DOCX] docxtpl non disponibile: installa docxtpl")
        return False

    base_dir = Path(__file__).resolve().parent.parent / "templates"
    tpl_path = base_dir / "template_base.docx"

    if not tpl_path.exists():
        return False

    try:
        doc = DocxTemplate(str(tpl_path))

        ingredients_text = _pick(recipe, "ingredients_text", "ingredienti_blocco", "ingredienti")
        steps_text = _pick(
            recipe,
            "steps_text_plain",
            "procedimento_blocco_plain",
            "steps_text",
            "procedimento_blocco",
            "procedimento",
        )

        ctx = dict(recipe or {})
        ctx.update(
            {
                "titolo": _sanitize_for_docx(_pick(recipe, "titolo", "title", default="Ricetta")),
                "categoria": _sanitize_for_docx(_pick(recipe, "categoria", "category", default="Altro")),
                "porzioni": _sanitize_for_docx(_pick(recipe, "porzioni", "servings", default="")),
                "difficolta": _sanitize_for_docx(_pick(recipe, "difficolta", "difficulty", default="Media")),
                "tempo_prep": _sanitize_for_docx(_pick(recipe, "prep_time_min", "tempo_preparazione", default="")),
                "tempo_cott": _sanitize_for_docx(_pick(recipe, "cook_time_min", "tempo_cottura", default="")),
                "tempo_tot": _sanitize_for_docx(_pick(recipe, "total_time_min", "tempo_totale", default="")),
                "ingredienti_testo": _sanitize_for_docx(ingredients_text),
                "ingredienti": recipe.get("ingredients", []),
                "procedimento_testo": _sanitize_for_docx(steps_text),
                "procedimento": recipe.get("steps", []),
                "spesa_totale": _sanitize_for_docx(_pick(recipe, "spesa_totale_ricetta", "costo_totale_ricetta", default="0.00")),
                "calorie": recipe.get("energia_totale", recipe.get("kcal_ricetta", 0)),
                "allergeni": _sanitize_for_docx(_pick(recipe, "allergeni_elenco", "allergens_text", "allergeni", default="")),
                "costo_materia_usata": _sanitize_for_docx(_pick(recipe, "spesa_totale_ricetta", "costo_totale_ricetta", default="")),
                "costo_per_porzione": _sanitize_for_docx(_pick(recipe, "spesa_per_porzione", "costo_per_porzione", default="")),
                "costo_spesa_totale": _sanitize_for_docx(_pick(recipe, "spesa_totale_acquisto", default="")),
                "costo_spesa_per_porzione": _sanitize_for_docx(_pick(recipe, "spesa_per_porzione", "costo_per_porzione", default="")),
                "prezzo_consigliato": "",
                "acquisto_minimo_g": "",
            }
        )

        cost_lines = recipe.get("cost_lines") or recipe.get("ingredienti_dettaglio") or []
        if not isinstance(cost_lines, list):
            cost_lines = []

        for i in range(1, 13):
            row = cost_lines[i - 1] if i - 1 < len(cost_lines) and isinstance(cost_lines[i - 1], dict) else {}
            ctx[f"p{i}_ingrediente"] = _sanitize_for_docx(row.get("ingrediente") or row.get("ingredient"))
            ctx[f"p{i}_peso_min_acquisto"] = _sanitize_for_docx(row.get("peso_min_acquisto"))
            ctx[f"p{i}_prezzo_ud"] = _sanitize_for_docx(row.get("prezzo_kg_ud"))
            ctx[f"p{i}_quantita_usata"] = _sanitize_for_docx(row.get("quantita_usata"))
            ctx[f"p{i}_prezzo_alimento"] = _sanitize_for_docx(row.get("prezzo_alimento_acquisto"))
            ctx[f"p{i}_prezzo_calcolato"] = _sanitize_for_docx(row.get("prezzo_calcolato"))

        doc.render(ctx)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        return True
    except Exception as e:
        print(f"[DOCX] Errore export: {e}")
        return False
