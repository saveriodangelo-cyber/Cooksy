# FILE: backend/ai_free.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .data_store import DataStore


def _normalize_text(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _guess_title(text: str) -> Optional[str]:
    # prima riga “significativa”
    for ln in _normalize_text(text).split("\n"):
        s = ln.strip(" -:\t").strip()
        if len(s) >= 4:
            # evita intestazioni tipiche
            if s.lower() in {"ingredienti", "procedimento", "preparazione", "metodo"}:
                continue
            return s[:120]
    return None


def _extract_possible_ingredients_lines(text: str) -> List[str]:
    """
    Estrae righe ingredienti “probabili” (euristica): presenza di quantità+unità o elenchi puntati.
    Serve per IA offline (allergeni/equipment) anche se il parser non è ancora perfetto.
    """
    lines = [ln.strip() for ln in _normalize_text(text).split("\n") if ln.strip()]
    out: List[str] = []
    for ln in lines:
        if re.search(r"\b\d+(?:[.,]\d+)?\s*(g|kg|ml|l|pz|uova)\b", ln, re.I):
            out.append(ln)
            continue
        if ln.startswith(("-", "•", "*")) and len(ln) > 3:
            out.append(ln.lstrip("-•* ").strip())
    return out


def analyze_text_offline(text: str, datastore: Optional[DataStore] = None) -> Dict[str, Any]:
    """
    “IA free” = arricchimento offline (niente API a pagamento):
    - titolo (guess)
    - allergeni (match keywords)
    - attrezzature suggerite (match keywords)
    - hint ingredienti (righe probabili)

    Se hai già un parser che produce strutture Recipe, puoi passare direttamente
    ingredienti+step a funzioni più precise (vedi enrich_recipe_dict).
    """
    ds = datastore or DataStore()

    title = _guess_title(text)
    ingredient_lines = _extract_possible_ingredients_lines(text)

    # allergeni: meglio usare ingredient_lines + testo completo
    allerg = ds.allergens.detect_in_text("\n".join(ingredient_lines) + "\n" + text)

    # attrezzature: usa testo completo (ingredienti + procedura)
    equip = ds.equipment.suggest_from_text(text, max_items=25)

    return {
        "ok": True,
        "title_guess": title,
        "ingredient_lines_guess": ingredient_lines,
        "allergens": allerg,
        "equipment": equip,
    }


def enrich_recipe_dict(
    recipe: Dict[str, Any],
    datastore: Optional[DataStore] = None,
) -> Dict[str, Any]:
    """
    Arricchisce una ricetta già parsata (dict JSON-safe).
    Atteso (minimo):
      recipe["ingredients"] = [{ "name": "...", "qty": 100, "unit": "g" }, ...]

    Aggiunge:
      recipe["enrichment"]["allergens"]
      recipe["enrichment"]["equipment"]
      recipe["enrichment"]["cost_lines"]
      recipe["enrichment"]["nutrition_lines"]
    """
    ds = datastore or DataStore()
    ingredients = recipe.get("ingredients") or []

    # testo ingredienti per allergeni/equipment
    ing_text = "\n".join([str(x.get("name", "")) for x in ingredients if isinstance(x, dict)])
    steps_text = "\n".join([str(x) for x in (recipe.get("steps") or [])])
    full_text = (recipe.get("title") or "") + "\n" + ing_text + "\n" + steps_text

    allergens = ds.allergens.detect_in_text(ing_text)

    equipment = ds.equipment.suggest_from_text(full_text, max_items=25)

    cost_lines: List[Dict[str, Any]] = []
    nutrition_lines: List[Dict[str, Any]] = []

    for it in ingredients:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        qty = it.get("qty")
        unit = str(it.get("unit", "")).strip() or "g"

        if name:
            # prezzi
            if isinstance(qty, (int, float)):
                cost_lines.append(ds.prices.cost_for_quantity(name, float(qty), unit))
            else:
                cost_lines.append({"ok": False, "reason": "missing_qty", "ingredient": name})

            # nutrienti: solo se unit è g (o convertibile) e qty numerico
            if isinstance(qty, (int, float)) and unit.lower() in {"g"}:
                nutrition_lines.append(ds.nutrition.nutrients_for_quantity_g(name, float(qty)))
            else:
                nutrition_lines.append({"ok": False, "reason": "qty_unit_not_supported", "ingredient": name, "qty": qty, "unit": unit})

    recipe = dict(recipe)  # shallow copy
    recipe["enrichment"] = {
        "allergens": allergens,
        "equipment": equipment,
        "cost_lines": cost_lines,
        "nutrition_lines": nutrition_lines,
    }
    return recipe


# Opzionale: integrazione con LLM locale (gratis) se installi llama-cpp-python e un modello GGUF.
# Non è obbligatorio. È solo un “upgrade” eventuale.
def local_llm_available() -> bool:
    try:
        import llama_cpp  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False
