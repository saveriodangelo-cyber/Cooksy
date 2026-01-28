from __future__ import annotations

import dataclasses
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


# =========================
# Fallback model (se backend.models non c'è ancora / cambia)
# =========================

@dataclass
class _FallbackNutrition:
    # Dizionari con chiavi standardizzate:
    # kcal, carbs_g, sugars_g, fat_g, sat_fat_g, protein_g, fibre_g, salt_g
    total: Dict[str, float] = field(default_factory=dict)
    per_portion: Optional[Dict[str, float]] = None
    per_100g: Optional[Dict[str, float]] = None
    total_weight_g: Optional[float] = None
    servings: Optional[int] = None
    missing_nutrition: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


try:
    # Se esiste già nel tuo progetto, useremo questo
    from backend.models import Nutrition as _ProjectNutrition  # type: ignore
except Exception:
    _ProjectNutrition = _FallbackNutrition  # type: ignore


# =========================
# Costanti e normalizzazioni
# =========================

# Chiavi standard di output
STD_KEYS = (
    "kcal",
    "carbs_g",
    "sugars_g",
    "fat_g",
    "sat_fat_g",
    "protein_g",
    "fibre_g",
    "salt_g",
)

# Mappa i nomi più comuni che si trovano nel DB (es. il tuo file usa fats_g, saturates_g, proteins_g, fiber_g)
NUTRIENT_KEY_MAP = {
    "kcal": "kcal",
    "energy_kcal": "kcal",
    "carbs_g": "carbs_g",
    "carbohydrates_g": "carbs_g",
    "sugars_g": "sugars_g",
    "fat_g": "fat_g",
    "fats_g": "fat_g",
    "lipids_g": "fat_g",
    "saturates_g": "sat_fat_g",
    "sat_fat_g": "sat_fat_g",
    "saturated_fat_g": "sat_fat_g",
    "proteins_g": "protein_g",
    "protein_g": "protein_g",
    "fiber_g": "fibre_g",
    "fibre_g": "fibre_g",
    "salt_g": "salt_g",
}

UNIT_ALIASES = {
    "g": {"g", "gr", "grammo", "grammi"},
    "kg": {"kg", "kilo", "kilogrammo", "kilogrammi"},
    "mg": {"mg"},
    "ml": {"ml"},
    "l": {"l", "lt", "litro", "litri"},
    "cl": {"cl"},
    "dl": {"dl"},
    "pz": {"pz", "pezzo", "pezzi", "uovo", "uova", "unita", "unità"},
    # misure domestiche (supporto “base”; se vuoi precisione, aggiungi unit_weights_g nel DB)
    "cucchiaino": {"cucchiaino", "cucchiaini", "tsp"},
    "cucchiaio": {"cucchiaio", "cucchiai", "tbsp"},
    "tazza": {"tazza", "tazze", "cup"},
}

DEFAULT_DENSITY_G_ML = 1.0  # approssimazione: 1 ml ~ 1 g (acqua/latte circa)


# =========================
# Utility “safe”
# =========================

def _safe_read_json(path: str) -> Any:
    # Supporta UTF-8 con BOM (utf-8-sig) e file tipici Windows/Excel.
    # In caso di caratteri non validi, sostituisce senza crashare.
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return json.load(f)


def _project_root() -> str:
    # backend/nutrition_engine.py -> project root è una cartella sopra "backend"
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def _coerce_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().lower().replace(",", ".")
        if not s:
            return None
        # frazioni tipo "1/2"
        if re.fullmatch(r"\d+\s*/\s*\d+", s):
            num, den = re.split(r"\s*/\s*", s)
            try:
                return float(num) / float(den)
            except Exception:
                return None
        # misto tipo "1 1/2"
        m = re.fullmatch(r"(\d+)\s+(\d+)\s*/\s*(\d+)", s)
        if m:
            try:
                a = float(m.group(1))
                b = float(m.group(2))
                c = float(m.group(3))
                return a + (b / c)
            except Exception:
                return None
        # numero semplice
        try:
            return float(s)
        except Exception:
            return None
    return None


def _strip_accents(s: str) -> str:
    # normalizzazione: utile per match robusto
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_text(s: str) -> str:
    s = s or ""
    s = s.strip().lower()
    s = _strip_accents(s)
    # rimuovi note tra parentesi: "zucchero (semolato)" -> "zucchero"
    s = re.sub(r"\([^)]*\)", " ", s)
    # rimuovi caratteri strani, tieni lettere/numeri/spazi
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(s: str) -> List[str]:
    s = _normalize_text(s)
    if not s:
        return []
    return [t for t in s.split(" ") if t]


def _best_match(query: str, candidates: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    candidates: norm_name -> entry
    Strategia:
      1) match esatto su normalized
      2) match token-based (Jaccard) con soglia
    """
    qn = _normalize_text(query)
    if not qn:
        return None
    if qn in candidates:
        return candidates[qn]

    qt = set(_tokens(query))
    if not qt:
        return None

    best_score = 0.0
    best = None

    for cn, entry in candidates.items():
        ct = set(cn.split(" ")) if cn else set()
        if not ct:
            continue
        inter = len(qt & ct)
        if inter == 0:
            continue
        union = len(qt | ct)
        score = inter / max(1, union)
        # bonus se la query è “contenuta” (string) o (token subset)
        if cn in qn or qn in cn:
            score += 0.15
        if qt.issubset(ct):
            score += 0.20
        if score > best_score:
            best_score = score
            best = entry

    # Soglia: leggermente più permissiva ma con bonus token-subset che evita match "a caso"
    return best if best_score >= 0.48 else None


def _normalize_unit(unit: Any) -> Optional[str]:
    if unit is None:
        return None
    if isinstance(unit, str):
        u = unit.strip().lower()
        u = u.replace(".", "")
        u = _strip_accents(u)
        u = re.sub(r"\s+", " ", u)
        # mappa alias
        for k, aliases in UNIT_ALIASES.items():
            if u in aliases:
                return k
        # se arriva già standard
        if u in UNIT_ALIASES:
            return u
        return u
    return None


def _get_any(obj: Any, keys: Iterable[str], default: Any = None) -> Any:
    """
    Legge obj come dict o come oggetto con attributi.
    """
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            return obj.get(k)
        if hasattr(obj, k):
            return getattr(obj, k)
    return default


# =========================
# DB loader
# =========================

def load_nutrition_db(path: str) -> Dict[str, Dict[str, Any]]:
    """
    Ritorna un indice:
      normalized_name -> entry
    dove entry contiene:
      {
        "name": original_name,
        "nutrients_per_100g": {std_key: float, ...},
        "density_g_ml": float|None,
        "piece_g": float|None,
        "unit_weights_g": { "cucchiaio": 12, ... } | None
      }

    Supporta DB in forme:
      - lista di record (come il tuo: [{name,kcal,carbs_g,...}, ...])
      - dict { "nome": { ... } } o { "nome": {per_100g:{...}} }
    """
    raw = _safe_read_json(path)

    entries: List[Dict[str, Any]] = []

    if isinstance(raw, list):
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            name = rec.get("name") or rec.get("ingredient") or rec.get("nome")
            if not name:
                continue
            entries.append(rec)

    elif isinstance(raw, dict):
        # due possibili: dict di record o dict con lista sotto una chiave
        if "items" in raw and isinstance(raw["items"], list):
            for rec in raw["items"]:
                if isinstance(rec, dict):
                    entries.append(rec)
        else:
            # interpretazione: { "farina 00": {...}, ...}
            for k, v in raw.items():
                if isinstance(v, dict):
                    rec = dict(v)
                    rec.setdefault("name", k)
                    entries.append(rec)
    else:
        return {}

    index: Dict[str, Dict[str, Any]] = {}

    for rec in entries:
        name = rec.get("name") or rec.get("ingredient") or rec.get("nome")
        if not isinstance(name, str) or not name.strip():
            continue

        # Nutrienti: o "per_100g" annidato oppure in root
        per100 = rec.get("per_100g")
        if isinstance(per100, dict):
            src = per100
        else:
            src = rec

        nutrients: Dict[str, float] = {}
        for k, v in src.items():
            if k in ("name", "ingredient", "nome", "per_100g", "aliases", "densita_g_ml", "density_g_ml", "piece_g", "unit_weights_g"):
                continue
            stdk = NUTRIENT_KEY_MAP.get(str(k).strip().lower())
            if not stdk:
                continue
            fv = _coerce_float(v)
            if fv is None:
                continue
            nutrients[stdk] = fv

        # se il record non contiene nulla di nutrizionale utile, salta
        if not nutrients:
            continue

        density = _coerce_float(rec.get("density_g_ml") or rec.get("densita_g_ml"))
        piece_g = _coerce_float(rec.get("piece_g") or rec.get("grams_per_piece"))
        unit_weights_g = rec.get("unit_weights_g")
        if not isinstance(unit_weights_g, dict):
            unit_weights_g = None

        entry = {
            "name": name.strip(),
            "nutrients_per_100g": nutrients,
            "density_g_ml": density,
            "piece_g": piece_g,
            "unit_weights_g": unit_weights_g,
        }

        # Indicizza il nome principale
        nn = _normalize_text(name)
        if nn:
            index[nn] = entry

        # Alias opzionali
        aliases = rec.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str) and a.strip():
                    na = _normalize_text(a)
                    if na:
                        index[na] = entry

    return index


# =========================
# Conversioni quantità -> grammi
# =========================

def _to_grams(qty: Any, unit: Any, matched_entry: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    """
    Converte qty+unit in grammi.
    Ritorna (grams, note). Se non convertibile, (None, motivo).
    """
    q = _coerce_float(qty)
    u = _normalize_unit(unit)

    if q is None or q <= 0:
        return None, "missing_or_invalid_qty"
    if not u:
        return None, "missing_unit"

    # Densità (per ml/l ecc.)
    density = None
    piece_g = None
    unit_weights_g = None
    if matched_entry:
        density = matched_entry.get("density_g_ml")
        piece_g = matched_entry.get("piece_g")
        unit_weights_g = matched_entry.get("unit_weights_g")

    if u == "g":
        return q, None
    if u == "kg":
        return q * 1000.0, None
    if u == "mg":
        return q / 1000.0, None

    if u == "ml":
        d = float(density) if isinstance(density, (int, float)) else DEFAULT_DENSITY_G_ML
        return q * d, "density_assumed" if density is None else None
    if u == "cl":
        d = float(density) if isinstance(density, (int, float)) else DEFAULT_DENSITY_G_ML
        return (q * 10.0) * d, "density_assumed" if density is None else None
    if u == "dl":
        d = float(density) if isinstance(density, (int, float)) else DEFAULT_DENSITY_G_ML
        return (q * 100.0) * d, "density_assumed" if density is None else None
    if u == "l":
        d = float(density) if isinstance(density, (int, float)) else DEFAULT_DENSITY_G_ML
        return (q * 1000.0) * d, "density_assumed" if density is None else None

    # pezzi (richiede peso per pezzo)
    if u == "pz":
        if isinstance(piece_g, (int, float)) and piece_g > 0:
            return q * float(piece_g), None
        return None, "missing_piece_weight"

    # misure domestiche: se DB fornisce unit_weights_g, usalo
    if u in ("cucchiaino", "cucchiaio", "tazza"):
        if isinstance(unit_weights_g, dict):
            ug = _coerce_float(unit_weights_g.get(u))
            if ug and ug > 0:
                return q * ug, None
        # fallback “prudente” (non inventiamo grammi)
        return None, "missing_unit_weight_in_db"

    return None, f"unsupported_unit:{u}"


# =========================
# Builder Nutrition compatibile col tuo backend.models
# =========================

def _build_nutrition(payload: Dict[str, Any]) -> Any:
    """
    Prova a costruire backend.models.Nutrition se esiste e combacia,
    altrimenti usa il fallback.
    """
    cls = _ProjectNutrition

    # Se è già fallback, costruisci diretto
    if cls is _FallbackNutrition:
        return _FallbackNutrition(
            total=payload.get("total", {}) or {},
            per_portion=payload.get("per_portion"),
            per_100g=payload.get("per_100g"),
            total_weight_g=payload.get("total_weight_g"),
            servings=payload.get("servings"),
            missing_nutrition=payload.get("missing_nutrition", []) or [],
            notes=payload.get("notes", []) or [],
        )

    try:
        # dataclass: prendiamo i campi reali
        if dataclasses.is_dataclass(cls):
            field_names = {f.name for f in dataclasses.fields(cls)}
        else:
            field_names = set(getattr(cls, "__annotations__", {}).keys())

        kwargs: Dict[str, Any] = {}

        # Caso A: modello con dict total/per_portion/per_100g
        if "total" in field_names:
            kwargs["total"] = payload.get("total", {}) or {}
        if "per_portion" in field_names:
            kwargs["per_portion"] = payload.get("per_portion")
        if "per_100g" in field_names:
            kwargs["per_100g"] = payload.get("per_100g")
        if "total_weight_g" in field_names:
            kwargs["total_weight_g"] = payload.get("total_weight_g")
        if "servings" in field_names:
            kwargs["servings"] = payload.get("servings")
        if "missing_nutrition" in field_names:
            kwargs["missing_nutrition"] = payload.get("missing_nutrition", []) or []
        if "notes" in field_names:
            kwargs["notes"] = payload.get("notes", []) or []

        # Caso B: modello “piatto” con kcal, carbs_g, ...
        total = payload.get("total", {}) or {}
        for k, v in total.items():
            if k in field_names:
                kwargs[k] = v

        obj = cls(**kwargs)  # type: ignore

        # Se il modello non espone quei campi ma non è frozen, proviamo ad attaccare attributi (senza rompere niente)
        for extra_k in ("total", "per_portion", "per_100g", "total_weight_g", "servings", "missing_nutrition", "notes"):
            if not hasattr(obj, extra_k):
                try:
                    setattr(obj, extra_k, payload.get(extra_k))
                except Exception:
                    pass

        return obj

    except Exception:
        # fallback super-safe
        return _FallbackNutrition(
            total=payload.get("total", {}) or {},
            per_portion=payload.get("per_portion"),
            per_100g=payload.get("per_100g"),
            total_weight_g=payload.get("total_weight_g"),
            servings=payload.get("servings"),
            missing_nutrition=payload.get("missing_nutrition", []) or [],
            notes=payload.get("notes", []) or [],
        )


# =========================
# API principale
# =========================

def compute_nutrition_safe(recipe: Any, nutrition_db_path: Optional[str] = None) -> Any:
    """
    compute_nutrition_safe(recipe, nutrition_db_path=None) -> Nutrition

    - Totale ricetta
    - Per porzione (se servings/porzioni disponibili)
    - Per 100g (se peso totale stimabile)
    - missing_nutrition: ingredienti senza match nel DB o senza qty/unit convertibile

    Vincolo: non deve crashare mai.
    """
    notes: List[str] = []
    missing: List[str] = []

    try:
        # risolvi path DB
        if nutrition_db_path is None:
            nutrition_db_path = os.path.join(_project_root(), "data", "nutrition", "nutrition_db.json")

        db_index: Dict[str, Dict[str, Any]] = {}
        try:
            if nutrition_db_path and os.path.exists(nutrition_db_path):
                db_index = load_nutrition_db(nutrition_db_path)
            else:
                notes.append(f"nutrition_db_not_found:{nutrition_db_path}")
        except Exception as e:
            notes.append(f"nutrition_db_load_error:{type(e).__name__}")

        # servings
        servings_raw = _get_any(recipe, ("servings", "porzioni", "portions", "portion_count", "resa"), None)
        servings = None
        try:
            s = _coerce_float(servings_raw)
            if s and s > 0:
                servings = int(round(s))
        except Exception:
            servings = None

        # ingredienti
        ingredients = _get_any(recipe, ("ingredients", "ingredienti"), [])  # list
        if ingredients is None:
            ingredients = []
        if not isinstance(ingredients, list):
            # ultimo tentativo: iterable generico
            try:
                ingredients = list(ingredients)  # type: ignore
            except Exception:
                ingredients = []

        total_weight_g = 0.0
        total: Dict[str, float] = {k: 0.0 for k in STD_KEYS}

        for ing in ingredients:
            ing_name = _get_any(ing, ("name", "nome", "ingredient"), "") or ""
            # se presente, usa un nome canonico per il match (senza cambiare il nome mostrato)
            try:
                nd = _get_any(ing, ("name_db", "matched_name"), None)
                if isinstance(nd, str) and nd.strip():
                    ing_name_for_match = nd.strip()
                else:
                    ing_name_for_match = None
            except Exception:
                ing_name_for_match = None
            ing_name = str(ing_name).strip()
            if not ing_name:
                continue

            qty = _get_any(ing, ("qty", "quantity", "qta", "amount", "valore"), None)
            unit = _get_any(ing, ("unit", "um", "u", "misura"), None)

            match_term = ing_name_for_match or ing_name
            matched = _best_match(match_term, db_index) if db_index else None
            if not matched:
                missing.append(ing_name)
                continue

            grams, why = _to_grams(qty, unit, matched)
            if grams is None or grams <= 0:
                missing.append(ing_name)
                if why:
                    notes.append(f"{_normalize_text(ing_name)}:{why}")
                continue

            total_weight_g += grams

            per100 = matched.get("nutrients_per_100g", {}) or {}
            if not isinstance(per100, dict):
                per100 = {}

            factor = grams / 100.0
            for k, v in per100.items():
                if k not in total:
                    # se nel DB ci sono chiavi extra mappate, le includiamo comunque
                    total[k] = 0.0
                try:
                    total[k] += float(v) * factor
                except Exception:
                    # ignora valori strani
                    continue

            if why == "density_assumed":
                notes.append(f"{_normalize_text(ing_name)}:density_assumed_1g_ml")

        # pulizia: rimuovi chiavi che sono rimaste tutte zero e non standard? (manteniamo STD_KEYS sempre)
        # standard: arrotondiamo leggero (ma lasciamo float “puliti”)
        def _round_dict(d: Dict[str, float]) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for k, v in d.items():
                try:
                    out[k] = round(float(v), 3)
                except Exception:
                    continue
            return out

        total = _round_dict(total)

        per_portion = None
        if servings and servings > 0:
            per_portion = _round_dict({k: (v / float(servings)) for k, v in total.items()})

        per_100g = None
        if total_weight_g > 0:
            per_100g = _round_dict({k: (v / total_weight_g * 100.0) for k, v in total.items()})

        payload = {
            "total": total,
            "per_portion": per_portion,
            "per_100g": per_100g,
            "total_weight_g": round(total_weight_g, 1) if total_weight_g > 0 else None,
            "servings": servings,
            "missing_nutrition": missing,
            "notes": notes,
        }
        return _build_nutrition(payload)

    except Exception as e:
        # hard fallback
        payload = {
            "total": {},
            "per_portion": None,
            "per_100g": None,
            "total_weight_g": None,
            "servings": None,
            "missing_nutrition": [],
            "notes": [f"compute_nutrition_safe_error:{type(e).__name__}"],
        }
        return _build_nutrition(payload)


# =========================
# Mini self-test (manuale)
# =========================

if __name__ == "__main__":
    # Test “a prova di modello”: usiamo dict, così non dipendiamo dal costruttore delle tue dataclass.
    demo_recipe = {
        "title": "Torta demo",
        "servings": 8,
        "ingredients": [
            {"name": "farina 00", "qty": 250, "unit": "g"},
            {"name": "zucchero semolato", "qty": 200, "unit": "g"},
            {"name": "burro", "qty": 150, "unit": "g"},
            {"name": "uova", "qty": 3, "unit": "pz"},
        ],
    }

    n = compute_nutrition_safe(demo_recipe)
    if hasattr(n, "to_dict"):
        print(json.dumps(n.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(n)
