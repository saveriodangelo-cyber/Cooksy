from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


_RE_TITLE = re.compile(r"^\s*Titolo\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_SERV = re.compile(r"^\s*Porzioni\s*:\s*(.+?)\s*$", re.IGNORECASE)

_RE_DIFF = re.compile(r"^\s*Difficolt(?:a|\u00E0|\ufffd)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_CAT = re.compile(r"^\s*Categoria\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_PREP = re.compile(r"^\s*Tempo\s*(?:di\s*)?preparazione\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_COOK = re.compile(r"^\s*Tempo\s*cottura\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_TOTAL = re.compile(r"^\s*Tempo\s*(totale|complessivo)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_PREP_ANY = re.compile(r"\bTempo\s*(?:di\s*)?preparazione\s*:\s*([0-9][^,;]*)", re.IGNORECASE)
_RE_COOK_ANY = re.compile(r"\bCottura\s*:\s*([0-9][^,;]*)", re.IGNORECASE)
_RE_TOTAL_ANY = re.compile(r"\bTempo\s*(?:totale|complessivo)\s*:\s*([0-9][^,;]*)", re.IGNORECASE)
_RE_DIETS = re.compile(r"^\s*Diete\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_TIME = re.compile(r"\bTempo\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_DIETS_ALT = re.compile(r"^\s*Adatto\s+a[^:]*:\s*(.+?)\s*$", re.IGNORECASE)
_RE_META_HDR = re.compile(
    r"^\s*(Conservazione|Allergeni|Abbinamento\s+vino|Attrezzature|Presentazione|Stagionalit(?:a|\u00E0))\s*:\s*(.*)\s*$",
    re.IGNORECASE,
)
_RE_BREAK_HDR = re.compile(r"^\s*(Valori\s+Nutrizionali|Prezzo\s+del\s+Piatto)\b", re.IGNORECASE)

_RE_ING_HDR = re.compile(r"^\s*Ingredienti\s*:\s*$", re.IGNORECASE)
_RE_STP_HDR = re.compile(r"^\s*(Procedimento|Preparazione|Metodo)\s*:\s*$", re.IGNORECASE)

_RE_ING_HDR_ANY = re.compile(r"\bingredienti\s*:\s*", re.IGNORECASE)
_RE_STP_HDR_ANY = re.compile(r"\b(procedimento|preparazione|metodo|instructions?|method)\s*:\s*", re.IGNORECASE)
_RE_NUM_PREFIX = re.compile(r"^\s*\d+[\.\)]\s*")

_RE_BULLET = re.compile(r"^\s*[\-\•\*]\s*")
_RE_STEP_NUM = re.compile(r"^\s*(\d+)[\.\)]\s*(.+)$")
_RE_QTY_UNIT = re.compile(
    r"^\s*(?P<qty>(?:\d+[\.,]?\d*)|(?:\d+\s*/\s*\d+)|(?:\d+\s+\d+/\d+))\s*"
    r"(?P<unit>[a-zA-Zàèéìòù%\.]+)?\s*(?P<name>.+?)\s*$"
)
_RE_QTY_UNIT_TAIL = re.compile(
    r"^\s*(?P<name>.+?)\s+"
    r"(?P<qty>(?:\d+[\.,]?\d*)|(?:\d+\s*/\s*\d+)|(?:\d+\s+\d+/\d+))\s*"
    r"(?P<unit>[a-zA-Z%\.]+)?\s*$"
)
_RE_QB = re.compile(r"\bq\.?b\.?\b", re.IGNORECASE)

_NON_ING_PREFIXES = (
    'porzioni',
    'difficolt',
    'tempo',
    'procedimento',
    'preparazione',
    'metodo',
    'conservazione',
    'allergeni',
    'abbinamento vino',
    'attrezzature',
    'presentazione',
    'stagionalita',
    'prezzi',
    'valori nutrizionali',
    'prezzo del piatto',
    'spesa',
    'costo',
    'adatto a',
    'diete',
    'categoria',
    'titolo',
)


def _is_non_ingredient_line(line: str) -> bool:
    low = (line or '').strip().lower()
    if not low:
        return True
    if low in {"\u20ac", "eur", "euro"}:
        return True
    if re.fullmatch(r"[\d\.,]+\s*(?:\u20ac|eur|euro)", low):
        return True
    if re.fullmatch(r"[\u20ac$]+", low):
        return True

    if _RE_BREAK_HDR.match(low):
        return True

    name_part = low
    m = _RE_QTY_UNIT.match(low)
    if m:
        name_part = (m.group("name") or "").strip().lower()

    name_part = re.sub(r"\s+", " ", name_part)

    for prefix in _NON_ING_PREFIXES:
        if name_part.startswith(prefix):
            if ":" in name_part or name_part == prefix:
                return True

    if name_part.startswith("per ") and ("porzion" in name_part or "persone" in name_part):
        return True

    if ":" in name_part and re.search(
        r"\b(tempo|porzioni|difficolt|allergen|conservazion|attrezzatur|presentazion|valori nutrizionali|prezzo|prezzi|costo|spesa|abbinamento)\b",
        name_part,
    ):
        return True

    if "prezzi aggiornati" in name_part or name_part.startswith("prezzi aggiorna") or name_part.startswith("prezzi aggiorn"):
        return True
    if "dati costo" in name_part:
        return True
    if "," in name_part and not re.search(r"\d", name_part):
        if any(w in name_part for w in ("allergeni", "tracce", "glutine")):
            return True

    return False


def _as_lines(text: str) -> List[str]:
    return [ln.rstrip() for ln in (text or "").splitlines()]

def _clean_line_prefix(line: str) -> str:
    s = (line or "").strip()
    if not s:
        return ""
    s = _RE_BULLET.sub("", s)
    s = _RE_NUM_PREFIX.sub("", s)
    return s.strip()

def _parse_ingredient_line(line: str) -> Optional[Dict[str, Any]]:
    s = _clean_line_prefix(line)
    if not s:
        return None
    if _is_non_ingredient_line(s):
        return None

    qb_unit: Optional[str] = None
    if _RE_QB.search(s):
        s = _RE_QB.sub("", s).strip().strip("-").strip()
        qb_unit = "q.b."
        if not s:
            return None

    s_norm = re.sub(r"\s*[-\u2013\u2014]\s*(?=\d)", " ", s)
    m = _RE_QTY_UNIT.match(s_norm)
    if not m:
        m = _RE_QTY_UNIT_TAIL.match(s_norm)

    if m:
        name = (m.group("name") or "").strip()
        qty = _safe_float(m.group("qty"))
        unit = _normalize_unit(m.group("unit"))
        if qb_unit and unit is None:
            unit = qb_unit
        if name:
            return {"name": name, "qty": qty, "unit": unit}
        return None

    if qb_unit:
        return {"name": s.strip(), "qty": None, "unit": qb_unit}

    return {"name": s.strip(), "qty": None, "unit": None}

def _parse_ingredient_block(raw: Any) -> List[Dict[str, Any]]:
    lines: List[str] = []
    if isinstance(raw, list):
        lines = [str(x) for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        lines = _as_lines(raw)
    else:
        return []

    items: List[Dict[str, Any]] = []
    for line in lines:
        ing = _parse_ingredient_line(line)
        if ing:
            items.append(ing)
    return items

def _clean_step_line(line: str) -> str:
    s = _clean_line_prefix(line)
    if not s or re.fullmatch(r"\d+(?:[\.\)\-]+)?", s):
        return ""
    return s

def _parse_steps_block(raw: Any) -> List[Dict[str, Any]]:
    lines: List[str] = []
    if isinstance(raw, list):
        lines = [str(x) for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        lines = _as_lines(raw)
    else:
        return []

    steps: List[Dict[str, Any]] = []
    for line in lines:
        txt = _clean_step_line(line)
        if txt:
            steps.append({"text": txt})
    return steps


def _parse_cost_lines_block(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        if all(isinstance(x, dict) for x in raw):
            return [dict(x) for x in raw]
        lines = [str(x) for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        lines = _as_lines(raw)
    else:
        return []

    out: List[Dict[str, Any]] = []
    keys = [
        "ingrediente",
        "scarto",
        "peso_min_acquisto",
        "prezzo_kg_ud",
        "quantita_usata",
        "prezzo_alimento_acquisto",
        "prezzo_calcolato",
    ]
    for raw_line in lines:
        line = _clean_line_prefix(raw_line)
        if not line:
            continue
        if re.match(r"^ingrediente\b", line, re.IGNORECASE):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 1:
            parts = [p.strip() for p in re.split(r"\t+|\s{2,}", line) if p.strip()]
        if not parts:
            continue
        if len(parts) > len(keys):
            parts = parts[: len(keys) - 1] + [" ".join(parts[len(keys) - 1 :]).strip()]
        while len(parts) < len(keys):
            parts.append("")
        row = {keys[i]: parts[i] for i in range(len(keys))}
        out.append(row)
    return out


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    s = (text or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # prova a trovare un blocco JSON nel testo
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    if not s:
        return None
    # frazioni tipo 1/2
    if "/" in s:
        try:
            parts = [p.strip() for p in s.split("/") if p.strip()]
            if len(parts) == 2:
                return float(parts[0]) / float(parts[1])
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None


def _normalize_unit(unit: Optional[str]) -> Optional[str]:
    # Normalizza unità per ingredienti (best-effort su testo OCR).
    if not unit:
        return None

    u = str(unit).strip().lower()
    u = u.replace('.', '').replace(',', '').replace('’', "'")

    # correzioni OCR frequenti
    if u in {'b', '9'}:
        u = 'g'
    if u.startswith('ucch') or u.startswith('cucch'):
        # 'ucchi', 'cucchi' ecc.
        u = 'cucchiai'

    # normalizzazioni standard
    unit_map = {
        'g': 'g', 'gr': 'g', 'grammo': 'g', 'grammi': 'g',
        'kg': 'kg', 'kilo': 'kg', 'kilogrammo': 'kg', 'kilogrammi': 'kg',
        'mg': 'mg',
        'ml': 'ml', 'cl': 'cl',
        'l': 'l', 'lt': 'l', 'litro': 'l', 'litri': 'l',
        'pz': 'pz', 'p': 'pz', 'pc': 'pz', 'pezzo': 'pz', 'pezzi': 'pz', 'n': 'pz', 'nr': 'pz',
        'ud': 'pz', 'u': 'pz', 'unita': 'pz', 'unità': 'pz', 'unit': 'pz',
        'cucchiaio': 'cucchiai', 'cucchiai': 'cucchiai',
        'cucchiaino': 'cucchiaini', 'cucchiaini': 'cucchiaini',
        'q.b': 'q.b.', 'qb': 'q.b.',
    }

    u = unit_map.get(u, u)

    # piccoli aggiustamenti (singolare->plurale coerente)
    if u == 'cucchiaio':
        u = 'cucchiai'
    if u == 'cucchiaino':
        u = 'cucchiaini'

    # filtra unità troppo strane (1-2 caratteri non riconosciuti)
    if len(u) <= 2 and u not in {'g','kg','mg','ml','cl','l','pz'}:
        return None

    return u or None


def _parse_minutes(raw: str) -> Optional[int]:
    s = (raw or "").strip().lower()
    if not s or s in {"n/d", "nd", "n.d.", "n.d", "n/a", "na"}:
        return None

    # 1h 30m / 1 h 30 min / 90 min
    h = 0
    m = 0

    mh = re.search(r"(\d+)\s*h", s)
    if mh:
        try:
            h = int(mh.group(1))
        except Exception:
            h = 0

    mm = re.search(r"(\d+)\s*(min|m)\b", s)
    if mm:
        try:
            m = int(mm.group(1))
        except Exception:
            m = 0

    if h or m:
        return h * 60 + m

    # fallback: primo numero = minuti
    mn = re.search(r"(\d+)", s)
    if mn:
        try:
            return int(mn.group(1))
        except Exception:
            return None

    return None


def _normalize_difficulty(raw: str) -> Optional[str]:
    s = (raw or "").strip().lower()
    if not s or s in {"n/d", "nd", "n.d.", "n.d", "n/a", "na"}:
        return None
    if "bass" in s or "facile" in s:
        return "bassa"
    if "medi" in s or "intermed" in s:
        return "media"
    if "alt" in s or "diffic" in s:
        return "alta"
    # restituiamo comunque testo pulito
    return s[:32]


def _diet_flags_from_text(raw: str) -> Dict[str, bool]:
    s = (raw or "").strip().lower()
    flags = {
        "vegetarian": False,
        "vegan": False,
        "gluten_free": False,
        "lactose_free": False,
    }
    if not s or s in {"n/d", "nd", "n.d.", "n.d", "n/a", "na"}:
        return flags

    if "vegano" in s or "vegan" in s:
        flags["vegan"] = True
    if "vegetar" in s:
        flags["vegetarian"] = True
    if "senza glutine" in s or "gluten free" in s or "gluten-free" in s:
        flags["gluten_free"] = True
    if "senza lattosio" in s or "lactose free" in s or "lactose-free" in s:
        flags["lactose_free"] = True

    # vegano implica vegetariano (se l'utente vuole può deselezionare in UI)
    if flags["vegan"]:
        flags["vegetarian"] = True

    return flags


def _append_text(current: str, extra: str) -> str:
    extra = (extra or "").strip()
    if not extra:
        return current
    if not current:
        return extra
    return current + "\n" + extra


def _as_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        if not val.strip():
            return []
        return [x.strip() for x in re.split(r"[;,/]+", val) if x.strip()]
    return []


def _list_to_text(val: Any) -> str:
    items = _as_list(val)
    return ", ".join(items) if items else ""

def _block_to_text(val: Any) -> str:
    if isinstance(val, str):
        items = [ln.strip(" -") for ln in _as_lines(val) if ln.strip()]
        return ", ".join(items) if items else ""
    return _list_to_text(val)


def _parse_time_block(raw: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    s = (raw or "").strip().lower()
    if not s:
        return None, None, None

    def _extract(label: str) -> Optional[int]:
        m = re.search(rf"{label}\s*[:\-]?\s*([0-9][^,;]*)", s)
        if not m:
            return None
        return _parse_minutes(m.group(1))

    prep = _extract(r"(?:prep|preparazione)")
    cook = _extract(r"(?:cottura|cook)")
    total = _extract(r"(?:totale|complessivo|total)")

    if prep is None and cook is None and total is None:
        total = _parse_minutes(raw)

    return prep, cook, total


def parse_recipe_text(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parser locale stabile.

    Input atteso (varianti tollerate):
      Titolo: ...
      Porzioni: ...
      Difficoltà: ...
      Tempo preparazione: ...
      Tempo cottura: ...
      Tempo totale: ...
      Diete: ...
      Ingredienti:
      - ...
      Procedimento:
      1. ...

    Output:
      (recipe_dict, missing_fields)
    """
    missing: List[str] = []
    src = (text or "").strip()

    # 1) JSON (se presente)
    obj = _try_parse_json(src)
    if obj is not None:
        title = str(obj.get("title") or obj.get("titolo") or "Ricetta").strip() or "Ricetta"
        title = re.sub(r"\bTitolo\s*:\s*", "", title, flags=re.IGNORECASE).strip() or "Ricetta"
        if "|" in title:
            parts = [p.strip() for p in title.split("|") if p.strip()]
            uniq: List[str] = []
            for p in parts:
                if p.lower() not in [u.lower() for u in uniq]:
                    uniq.append(p)
            if uniq:
                title = uniq[0]
        servings = obj.get("servings", obj.get("porzioni", obj.get("portions")))
        try:
            servings_i: Optional[int] = int(float(str(servings).replace(",", "."))) if servings not in (None, "") else None
        except Exception:
            servings_i = None

        if servings_i is None and isinstance(servings, str):
            m_serv = re.search(r"(\d+)", servings)
            if m_serv:
                servings_i = int(m_serv.group(1))

        ingredients: List[Dict[str, Any]] = []
        for it in obj.get("ingredients", []) if isinstance(obj.get("ingredients"), list) else []:
            if isinstance(it, dict):
                ingredients.append(
                    {
                        "name": str(it.get("name") or it.get("ingrediente") or "").strip(),
                        "qty": _safe_float(it.get("qty", it.get("quantita", it.get("amount")))),
                        "unit": _normalize_unit(it.get("unit", it.get("unita"))),
                    }
                )

        ing_block_raw = obj.get("ingredienti_blocco")
        if ing_block_raw is None and isinstance(obj.get("ingredienti"), (str, list)):
            ing_block_raw = obj.get("ingredienti")
        if not ingredients and ing_block_raw is not None:
            ingredients = _parse_ingredient_block(ing_block_raw)

        steps: List[Dict[str, Any]] = []
        for st in obj.get("steps", []) if isinstance(obj.get("steps"), list) else []:
            if isinstance(st, dict):
                t = str(st.get("text") or st.get("step") or "").strip()
            else:
                t = str(st).strip()
            if t:
                steps.append({"text": t})

        step_block_raw = obj.get("procedimento_blocco")
        if step_block_raw is None and isinstance(obj.get("procedimento"), (str, list)):
            step_block_raw = obj.get("procedimento")
        if not steps and step_block_raw is not None:
            steps = _parse_steps_block(step_block_raw)

        diff = _normalize_difficulty(str(obj.get("difficulty") or obj.get("difficolta") or obj.get("difficoltà") or ""))
        category = str(obj.get("category") or obj.get("categoria") or "").strip() or None
        prep = _parse_minutes(str(obj.get("prep_time") or obj.get("prep_time_min") or obj.get("tempo_preparazione") or ""))
        cook = _parse_minutes(str(obj.get("cook_time") or obj.get("cook_time_min") or obj.get("tempo_cottura") or ""))
        total = _parse_minutes(str(obj.get("total_time") or obj.get("total_time_min") or obj.get("tempo_totale") or ""))
        tempo_raw = obj.get("tempo_dettaglio") or obj.get("tempo dettaglio") or obj.get("tempo") or ""
        if tempo_raw:
            p2, c2, t2 = _parse_time_block(str(tempo_raw))
            if prep is None:
                prep = p2
            if cook is None:
                cook = c2
            if total is None:
                total = t2
        tempo_dettaglio = str(tempo_raw).strip() if tempo_raw else ""
        diets_raw = str(obj.get("diets") or obj.get("diete") or obj.get("diet") or obj.get("diet_text") or "")
        conservazione = str(obj.get("conservazione") or obj.get("storage") or obj.get("conservazione_text") or "").strip()
        allergens_text = str(
            obj.get("allergens_text")
            or obj.get("allergeni")
            or obj.get("allergeni elenco")
            or obj.get("allergeni_elenco")
            or obj.get("allergeni_text")
            or ""
        ).strip()
        vino_descrizione = str(
            obj.get("wine_pairing")
            or obj.get("vino")
            or obj.get("vino descrizione")
            or obj.get("vino_descrizione")
            or ""
        ).strip()
        vino_temp = str(
            obj.get("vino temperatura servizio")
            or obj.get("vino_temperatura_servizio")
            or obj.get("temperatura servizio vino")
            or obj.get("temperatura servizio")
            or ""
        ).strip()
        vino_regione = str(
            obj.get("vino regione")
            or obj.get("vino_regione")
            or obj.get("regione vino")
            or ""
        ).strip()
        vino_annata = str(
            obj.get("vino annata")
            or obj.get("vino_annata")
            or obj.get("annata vino")
            or ""
        ).strip()
        vino_motivo_annata = str(
            obj.get("vino motivo annata")
            or obj.get("vino_motivo_annata")
            or obj.get("motivo annata")
            or obj.get("perche annata")
            or ""
        ).strip()
        attrezzature_specifiche_raw = obj.get("attrezzature specifiche") or obj.get("attrezzature_specifiche")
        attrezzature_generiche_raw = obj.get("attrezzature generiche") or obj.get("attrezzature_generiche")
        attrezzature_semplici_raw = (
            obj.get("attrezzature semplici") or obj.get("attrezzature_semplici") or obj.get("equipment_simple")
        )
        attrezzature_professionali_raw = (
            obj.get("attrezzature professionali") or obj.get("attrezzature_professionali") or obj.get("equipment_professional")
        )
        attrezzature_pasticceria_raw = (
            obj.get("attrezzature pasticceria") or obj.get("attrezzature_pasticceria") or obj.get("equipment_pasticceria")
        )
        equipment_text = str(
            obj.get("equipment_text")
            or obj.get("attrezzature")
            or attrezzature_generiche_raw
            or obj.get("equipment")
            or ""
        ).strip()
        attrezzature_specifiche = _block_to_text(attrezzature_specifiche_raw)
        attrezzature_generiche = _block_to_text(attrezzature_generiche_raw)
        if attrezzature_generiche:
            equipment_text = attrezzature_generiche
        presentazione = str(
            obj.get("presentazione_impiattamento")
            or obj.get("presentazione impiattamento")
            or obj.get("presentazione")
            or obj.get("plating")
            or ""
        ).strip()
        stagionalita = str(
            obj.get("stagionalita")
            or obj.get("stagionalità")
            or obj.get("stagione")
            or ""
        ).strip()
        note_errori = str(obj.get("note errori") or obj.get("note_errori") or obj.get("notes") or "").strip()
        allergens_present = _as_list(obj.get("allergens") or obj.get("allergens_present"))
        allergens_traces = _as_list(obj.get("allergens_traces") or obj.get("traces_allergens") or obj.get("tracce_allergeni"))
        attrezzature_semplici = _block_to_text(attrezzature_semplici_raw or attrezzature_generiche_raw)
        attrezzature_professionali = _block_to_text(attrezzature_professionali_raw or attrezzature_specifiche_raw)
        attrezzature_pasticceria = _list_to_text(attrezzature_pasticceria_raw)
        if not attrezzature_generiche and attrezzature_semplici:
            attrezzature_generiche = attrezzature_semplici
            if not equipment_text:
                equipment_text = attrezzature_generiche
        if not attrezzature_specifiche and attrezzature_professionali:
            attrezzature_specifiche = attrezzature_professionali
        nutrition_table = obj.get("nutrition_table") if isinstance(obj.get("nutrition_table"), dict) else None

        def _num_key(*keys: str) -> Optional[float]:
            for k in keys:
                if k in obj:
                    val = _safe_float(obj.get(k))
                    if val is not None:
                        return val
            return None

        if nutrition_table is None:
            nt100: Dict[str, Any] = {}
            nttot: Dict[str, Any] = {}

            def _set(block: Dict[str, Any], key: str, val: Optional[float]) -> None:
                if val is not None:
                    block[key] = val

            _set(nt100, "energia", _num_key("energia 100g", "energia_100g"))
            _set(nttot, "energia", _num_key("energia totale", "energia_totale"))
            _set(nt100, "carboidrati_totali", _num_key("carboidrati totali 100g", "carboidrati_totali_100g"))
            _set(nttot, "carboidrati_totali", _num_key("carboidrati totali totale", "carboidrati_totali_totale"))
            _set(nt100, "di_cui_zuccheri", _num_key("di cui zuccheri 100g", "di_cui_zuccheri_100g"))
            _set(nttot, "di_cui_zuccheri", _num_key("di cui zuccheri totale", "di_cui_zuccheri_totale"))
            _set(nt100, "grassi_totali", _num_key("grassi totali 100g", "grassi_totali_100g"))
            _set(nttot, "grassi_totali", _num_key("grassi totali totale", "grassi_totali_totale"))
            _set(nt100, "di_cui_saturi", _num_key("di cui saturi 100g", "di_cui_saturi_100g"))
            _set(nttot, "di_cui_saturi", _num_key("di cui saturi totale", "di_cui_saturi_totale"))
            _set(nt100, "monoinsaturi", _num_key("monoinsaturi 100g", "monoinsaturi_100g"))
            _set(nttot, "monoinsaturi", _num_key("monoinsaturi totale", "monoinsaturi_totale"))
            _set(nt100, "polinsaturi", _num_key("polinsaturi 100g", "polinsaturi_100g"))
            _set(nttot, "polinsaturi", _num_key("polinsaturi totale", "polinsaturi_totale"))
            _set(nt100, "proteine_totali", _num_key("proteine totali 100g", "proteine_totali_100g"))
            _set(nttot, "proteine_totali", _num_key("proteine totali totale", "proteine_totali_totale"))
            _set(nt100, "colesterolo", _num_key("colesterolo totale 100g", "colesterolo_100g"))
            _set(nttot, "colesterolo", _num_key("colesterolo totale totale", "colesterolo_totale"))
            _set(nt100, "fibre", _num_key("fibre 100g", "fibre_100g"))
            _set(nttot, "fibre", _num_key("fibre totale", "fibre_totale"))
            _set(nt100, "sodio", _num_key("sodio 100g", "sodio_100g"))
            _set(nttot, "sodio", _num_key("sodio totale", "sodio_totale"))

            if nt100 or nttot:
                nutrition_table = {"100g": nt100, "totale": nttot, "porzione": {}}

        energia_totale = None
        if isinstance(nutrition_table, dict):
            energia_totale = (nutrition_table.get("totale") or {}).get("energia")
        cost_lines = obj.get("cost_lines")
        if not isinstance(cost_lines, list):
            cost_lines = obj.get("ingredienti_dettaglio")
        if isinstance(cost_lines, str) or (isinstance(cost_lines, list) and not all(isinstance(x, dict) for x in cost_lines)):
            cost_lines = _parse_cost_lines_block(cost_lines)
        if not isinstance(cost_lines, list):
            cost_lines = None

        def _has_cost_values(rows: Optional[List[Dict[str, Any]]]) -> bool:
            if not isinstance(rows, list):
                return False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in (
                    "prezzo_calcolato",
                    "prezzo_kg_ud",
                    "prezzo_alimento_acquisto",
                    "prezzo_acquisto",
                    "price_value",
                    "cost",
                    "scarto",
                    "scarto_pct",
                    "waste_pct",
                ):
                    val = row.get(key)
                    if val is None:
                        continue
                    s = str(val).strip().replace(",", ".")
                    if not s:
                        continue
                    if s.lower() in {"none", "null", "n/d", "n.d", "n.a", "n/a"}:
                        continue
                    if s in {"0", "0.0", "0.00"}:
                        continue
                    return True
            return False

        if cost_lines and not _has_cost_values(cost_lines):
            cost_lines = None
        spesa_totale_ricetta = (
            obj.get("spesa_totale_ricetta")
            or obj.get("costo_totale_ricetta")
            or obj.get("spesa totale ricetta")
        )
        spesa_per_porzione = (
            obj.get("spesa_per_porzione")
            or obj.get("costo_per_porzione")
            or obj.get("spesa per porzione")
        )
        spesa_totale_acquisto = obj.get("spesa_totale_acquisto") or obj.get("spesa totale acquisto")
        fonte_prezzi = (
            obj.get("fonte_prezzi")
            or obj.get("prezzi_aggiornati_secondo")
            or obj.get("prezzi aggiornati secondo")
        )
        diet_flags_raw = obj.get("diet_flags")
        if isinstance(diet_flags_raw, dict):
            flags = {
                "vegetarian": bool(diet_flags_raw.get("vegetarian")),
                "vegan": bool(diet_flags_raw.get("vegan")),
                "gluten_free": bool(diet_flags_raw.get("gluten_free")),
                "lactose_free": bool(diet_flags_raw.get("lactose_free")),
            }
        else:
            flags = _diet_flags_from_text(diets_raw)

        veg_flag_raw = obj.get("vegetariano flag") or obj.get("vegetariano_flag")
        if veg_flag_raw is not None and str(veg_flag_raw).strip():
            veg_val = str(veg_flag_raw).strip().lower()
            if veg_val in {"si", "s\u00ec", "yes", "true", "1"}:
                flags["vegetarian"] = True
                if not diets_raw.strip():
                    diets_raw = "vegetariana"
            elif veg_val in {"no", "false", "0"}:
                flags["vegetarian"] = False
        vegetariano_flag = str(veg_flag_raw).strip() if veg_flag_raw is not None else ""

        if servings_i is None:
            missing.append("servings")
        if not ingredients:
            missing.append("ingredients")
        if not steps:
            missing.append("steps")
        if ingredients:
            cleaned_ingredients: List[Dict[str, Any]] = []
            for ing in ingredients:
                name = str((ing or {}).get("name") or "").strip()
                if not name:
                    continue
                if _is_non_ingredient_line(name):
                    continue
                cleaned_ingredients.append(ing)
            ingredients = cleaned_ingredients
        def _fmt_ing_qty(val: Any) -> str:
            q = _safe_float(val)
            if q is None or abs(q) < 1e-9:
                return ""
            if q.is_integer():
                return str(int(q))
            return str(q).replace(".", ",")

        ingredients_text = "\n".join(
            [
                f"- {_fmt_ing_qty(i.get('qty'))}{('' if not i.get('unit') else ' ' + str(i.get('unit')))} {i.get('name','')}".strip()
                for i in ingredients
                if i.get("name")
            ]
        ).strip() + ("\n" if ingredients else "")

        if not ingredients_text and ing_block_raw is not None:
            raw_lines = ing_block_raw if isinstance(ing_block_raw, list) else _as_lines(str(ing_block_raw))
            cleaned_lines: List[str] = []
            for ln in raw_lines:
                s = _clean_line_prefix(str(ln))
                if not s:
                    continue
                if _is_non_ingredient_line(s):
                    continue
                cleaned_lines.append(s)
            if cleaned_lines:
                ingredients_text = "\n".join([f"- {ln}" for ln in cleaned_lines]).strip()
                if not ingredients_text.endswith("\n"):
                    ingredients_text = ingredients_text + "\n"

        steps_text = "\n".join([f"{idx+1}) {s['text']}" for idx, s in enumerate(steps) if s.get("text")]).strip() + ("\n" if steps else "")
        steps_text_plain = "\n".join([str(s.get("text") or "").strip() for s in steps if s.get("text")]).strip()
        if not steps_text and step_block_raw is not None:
            if isinstance(step_block_raw, list):
                steps_text = "\n".join([str(x).strip() for x in step_block_raw if str(x).strip()]).strip()
            else:
                steps_text = str(step_block_raw).strip()
            if steps_text and not steps_text.endswith("\n"):
                steps_text = steps_text + "\n"
        if not steps_text_plain and step_block_raw is not None:
            if isinstance(step_block_raw, list):
                steps_text_plain = "\n".join([str(x).strip() for x in step_block_raw if str(x).strip()]).strip()
            else:
                steps_text_plain = str(step_block_raw).strip()

        return {
            "title": title,
            "category": category,
            "servings": servings_i,
            "difficulty": diff,
            "prep_time_min": prep,
            "cook_time_min": cook,
            "total_time_min": total,
            "tempo_dettaglio": tempo_dettaglio,
            "diet_flags": flags,
            "diet_text": diets_raw.strip() if diets_raw.strip() else "",
            "conservazione": conservazione,
            "allergens_text": allergens_text,
            "vino_descrizione": vino_descrizione,
            "wine_pairing": vino_descrizione,
            "vino_temperatura_servizio": vino_temp,
            "vino_regione": vino_regione,
            "vino_annata": vino_annata,
            "vino_motivo_annata": vino_motivo_annata,
            "equipment_text": equipment_text,
            "attrezzature_generiche": attrezzature_generiche or equipment_text,
            "attrezzature_specifiche": attrezzature_specifiche,
            "attrezzature_semplici": attrezzature_semplici,
            "attrezzature_professionali": attrezzature_professionali,
            "attrezzature_pasticceria": attrezzature_pasticceria,
            "presentazione_impiattamento": presentazione,
            "stagionalita": stagionalita,
            "notes": note_errori,
            "note_errori": note_errori,
            "vegetariano_flag": vegetariano_flag,
            "allergens": allergens_present,
            "traces_allergens": allergens_traces,
            "nutrition_table": nutrition_table,
            "energia_totale": energia_totale,
            "kcal_ricetta": energia_totale,
            "cost_lines": cost_lines,
            "spesa_totale_ricetta": spesa_totale_ricetta,
            "spesa_per_porzione": spesa_per_porzione,
            "spesa_totale_acquisto": spesa_totale_acquisto,
            "fonte_prezzi": fonte_prezzi,
            "ingredients": ingredients,
            "steps": steps,
            "ingredients_text": ingredients_text,
            "steps_text": steps_text,
            "steps_text_plain": steps_text_plain,
        }, missing

    # 2) testo strutturato
    lines = _as_lines(src)
    title: Optional[str] = None
    category: Optional[str] = None
    servings: Optional[int] = None
    difficulty: Optional[str] = None
    prep_time_min: Optional[int] = None
    cook_time_min: Optional[int] = None
    total_time_min: Optional[int] = None
    diet_text: str = ""
    diet_flags: Dict[str, bool] = {
        "vegetarian": False,
        "vegan": False,
        "gluten_free": False,
        "lactose_free": False,
    }
    conservazione: str = ""
    allergens_text: str = ""
    vino_descrizione: str = ""
    equipment_text: str = ""
    presentazione: str = ""
    stagionalita: str = ""
    active_block: Optional[str] = None

    in_ing = False
    in_steps = False

    # In alcuni OCR (soprattutto PDF fotografati) le righe ingredienti vengono spezzate
    # su più linee, es: "112" -> "g" -> "Farina". Qui ricomponiamo in modo conservativo.
    pending_qty: Optional[float] = None
    pending_unit: Optional[str] = None

    ingredients: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []

    for raw in lines:
        s = (raw or "").strip()
        if not s:
            continue

        m_meta = _RE_META_HDR.match(s)
        if m_meta:
            label = m_meta.group(1).strip().lower()
            rest = m_meta.group(2).strip()
            in_steps = False
            in_ing = False
            if "conservazione" in label:
                active_block = "conservazione"
                conservazione = _append_text(conservazione, rest)
            elif "allergeni" in label:
                active_block = "allergeni"
                allergens_text = _append_text(allergens_text, rest)
            elif "abbinamento" in label or "vino" in label:
                active_block = "vino"
                vino_descrizione = _append_text(vino_descrizione, rest)
            elif "attrezzature" in label:
                active_block = "attrezzature"
                equipment_text = _append_text(equipment_text, rest)
            elif "presentazione" in label:
                active_block = "presentazione"
                presentazione = _append_text(presentazione, rest)
            elif "stagional" in label:
                active_block = "stagionalita"
                stagionalita = _append_text(stagionalita, rest)
            else:
                active_block = None
            continue

        m_diet_alt = _RE_DIETS_ALT.match(s)
        if m_diet_alt:
            diet_text = m_diet_alt.group(1).strip()
            diet_flags = _diet_flags_from_text(diet_text)
            in_steps = False
            in_ing = False
            active_block = None
            continue

        if _RE_BREAK_HDR.match(s):
            in_steps = False
            in_ing = False
            active_block = None
            continue

        if active_block and not _RE_ING_HDR_ANY.search(s) and not _RE_STP_HDR_ANY.search(s):
            if active_block == "conservazione":
                conservazione = _append_text(conservazione, s)
            elif active_block == "allergeni":
                allergens_text = _append_text(allergens_text, s)
            elif active_block == "vino":
                vino_descrizione = _append_text(vino_descrizione, s)
            elif active_block == "attrezzature":
                equipment_text = _append_text(equipment_text, s)
            elif active_block == "presentazione":
                presentazione = _append_text(presentazione, s)
            elif active_block == "stagionalita":
                stagionalita = _append_text(stagionalita, s)
            continue
        if active_block and (_RE_ING_HDR_ANY.search(s) or _RE_STP_HDR_ANY.search(s)):
            active_block = None

        # intestazioni meta (solo fuori dalle sezioni)
        if not in_ing and not in_steps:
            mt = _RE_TITLE.match(s)
            if mt:
                title = mt.group(1).strip()

            ms = _RE_SERV.match(s)
            if ms:
                v = ms.group(1).strip()
                v = re.split(r"\bTempo\s*:", v, flags=re.IGNORECASE)[0].strip()
                if v and v.lower() not in {"n/d", "nd", "n.d.", "n.d"}:
                    try:
                        servings = int(float(v.replace(",", ".")))
                    except Exception:
                        servings = None

            if servings is None:
                ms2 = re.search(r"\bPorzioni\s*:\s*([0-9]+(?:[\\.,][0-9]+)?)", s, re.IGNORECASE)
                if ms2:
                    try:
                        servings = int(float(ms2.group(1).replace(",", ".")))
                    except Exception:
                        servings = None
            if servings is None:
                ms3 = re.search(r"\bper\s+([0-9]+)\s*(?:persone|porzion)", s, re.IGNORECASE)
                if ms3:
                    try:
                        servings = int(float(ms3.group(1).replace(",", ".")))
                    except Exception:
                        servings = None

            md = _RE_DIFF.match(s)
            if md:
                difficulty = _normalize_difficulty(md.group(1))

            mcat = _RE_CAT.match(s)
            if mcat:
                category = mcat.group(1).strip()

            mp = _RE_PREP.match(s)
            if mp:
                prep_time_min = _parse_minutes(mp.group(1))
            else:
                mp_any = _RE_PREP_ANY.search(s)
                if mp_any:
                    prep_time_min = _parse_minutes(mp_any.group(1))

            mcook = _RE_COOK.match(s)
            if mcook:
                cook_time_min = _parse_minutes(mcook.group(1))
            else:
                mcook_any = _RE_COOK_ANY.search(s)
                if mcook_any:
                    cook_time_min = _parse_minutes(mcook_any.group(1))

            mtot = _RE_TOTAL.match(s)
            if mtot:
                total_time_min = _parse_minutes(mtot.group(2))
            else:
                mtot_any = _RE_TOTAL_ANY.search(s)
                if mtot_any:
                    total_time_min = _parse_minutes(mtot_any.group(1))

            mdiet = _RE_DIETS.match(s)
            if mdiet:
                diet_text = mdiet.group(1).strip()
                diet_flags = _diet_flags_from_text(diet_text)

            mtime = _RE_TIME.search(s)
            if mtime:
                p, c, t = _parse_time_block(mtime.group(1))
                if p is not None:
                    prep_time_min = p
                if c is not None:
                    cook_time_min = c
                if t is not None:
                    total_time_min = t

        # Header "sporchi": Ingredienti/Procedimento dentro la stessa riga (es. "Mascarpone Ingredienti: ...")
        m_ing = _RE_ING_HDR_ANY.search(s)
        m_stp = _RE_STP_HDR_ANY.search(s)

        # Se nella stessa riga compaiono entrambi, scegli quello che appare per primo
        if m_ing and (not m_stp or m_ing.start() < m_stp.start()):
            in_ing = True
            in_steps = False
            tail = s[m_ing.end():].strip()
            if not tail:
                continue
            s = tail  # processa il resto riga come contenuto ingredienti

        elif m_stp:
            in_steps = True
            in_ing = False
            tail = s[m_stp.end():].strip()
            if not tail:
                continue
            s = tail  # processa il resto riga come contenuto procedimento

        if _RE_ING_HDR.match(s):
            in_ing = True
            in_steps = False
            continue
        if _RE_STP_HDR.match(s):
            in_steps = True
            in_ing = False
            continue

        if in_ing:
            # bullet o riga semplice
            s2 = _RE_BULLET.sub("", s).strip()
            s2 = _RE_NUM_PREFIX.sub("", s2).strip()

            if _is_non_ingredient_line(s2):
                continue

            # fuzzy header: molti OCR sbagliano "Procedimento" (es. Procedimer)
            s2_l = s2.lower()
            if re.match(r"^(proced|prepar|metod|instruction|method)", s2_l):
                in_steps = True
                in_ing = False
                pending_qty = None
                pending_unit = None
                continue

            # --- Ricomposizione ingredienti spezzati su più righe (OCR) ---
            # Caso 1: riga solo numero -> trattala come quantità in attesa
            if re.fullmatch(r"\d+(?:[\.,]\d+)?", s2):
                pending_qty = _safe_float(s2)
                continue

            # Caso 2: riga solo unità -> trattala come unità in attesa
            # (accettiamo anche varianti comuni)
            u_only = _normalize_unit(s2)
            if u_only and re.fullmatch(r"[A-Za-zàèéìòùÀÈÉÌÒÙ\.]+", s2):
                pending_unit = u_only
                continue

            # Caso 3: riga "qty unit" senza nome -> metti in attesa
            m_only = re.fullmatch(r"(?P<qty>\d+(?:[\.,]\d+)?)\s*(?P<unit>[A-Za-zàèéìòùÀÈÉÌÒÙ\.]+)", s2)
            if m_only and not re.search(r"\s", (m_only.group("unit") or "").strip()):
                qv = _safe_float(m_only.group("qty"))
                uv = _normalize_unit(m_only.group("unit"))
                if qv is not None:
                    pending_qty = qv
                if uv:
                    pending_unit = uv
                continue

            # Caso 4: se abbiamo qty/unit in attesa e questa riga sembra un nome,
            # crea l'ingrediente usando i pending.
            if (pending_qty is not None or pending_unit is not None) and s2 and not _RE_QTY_UNIT.match(s2) and not re.match(r"^\d", s2):
                # Evita di attaccare pending a righe che sono chiaramente intestazioni
                if not _RE_ING_HDR.match(s2) and not _RE_STP_HDR.match(s2):
                    name = s2.strip(" -–—,;:").strip()
                    if name:
                        ingredients.append({"name": name, "qty": pending_qty, "unit": pending_unit})
                        if pending_qty is None:
                            missing.append(f"qty:{name}")
                        if (pending_qty is not None) and (not pending_unit):
                            missing.append(f"unit:{name}")
                        pending_qty = None
                        pending_unit = None
                        continue

            # gestione q.b.
            if "q.b" in s2.lower() or "qb" in s2.lower():
                name = re.sub(r"\b(q\.?b\.?|qb)\b", "", s2, flags=re.IGNORECASE).strip(" -–—,;:").strip()
                if not name:
                    name = s2
                ingredients.append({"name": name, "qty": None, "unit": "q.b."})
                missing.append(f"qty:{name}")
                continue

            s2_norm = re.sub(r"\s*[-\u2013\u2014]\s*(?=\d)", " ", s2)
            m2 = _RE_QTY_UNIT.match(s2_norm)
            if m2:
                qty = _safe_float(m2.group("qty"))
                unit = _normalize_unit(m2.group("unit"))
                name = (m2.group("name") or "").strip().strip(" -\u2013\u2014,;:")
                if name:
                    if qty is None:
                        missing.append(f"qty:{name}")
                    if not unit and qty is not None:
                        missing.append(f"unit:{name}")
                    ingredients.append({"name": name, "qty": qty, "unit": unit})
                continue
            m2t = _RE_QTY_UNIT_TAIL.match(s2_norm)
            if m2t:
                qty = _safe_float(m2t.group("qty"))
                unit = _normalize_unit(m2t.group("unit"))
                name = (m2t.group("name") or "").strip().strip(" -\u2013\u2014,;:")
                if name:
                    if qty is None:
                        missing.append(f"qty:{name}")
                    if not unit and qty is not None:
                        missing.append(f"unit:{name}")
                    ingredients.append({"name": name, "qty": qty, "unit": unit})
                continue

            # fallback: solo nome
            name = s2.strip()
            if name:
                ingredients.append({"name": name, "qty": None, "unit": None})
                missing.append(f"qty:{name}")
            continue

        if in_steps:
            msn = _RE_STEP_NUM.match(s)
            if msn:
                txt = msn.group(2).strip()
            else:
                txt = _RE_BULLET.sub("", s).strip()
            if txt:
                steps.append({"text": txt})
            continue

    # calcola totale se non presente ma abbiamo prep+cottura
    if total_time_min is None and (prep_time_min is not None or cook_time_min is not None):
        total_time_min = int((prep_time_min or 0) + (cook_time_min or 0)) if (prep_time_min or 0) + (cook_time_min or 0) > 0 else None

    if difficulty is None:
        md_any = re.search(r"\bDifficolt(?:a|\u00E0|\ufffd)\s*:\s*([^\n]+)", src, re.IGNORECASE)
        if md_any:
            difficulty = _normalize_difficulty(md_any.group(1))

    # pulizie + missing
    if not title:
        title = "Ricetta"

    # Fallback: se ingredienti sono vuoti ma nel testo (spesso nel procedimento) compare "Ingredienti:",
    # estrai un blocco ingredienti e prova a ricostruire qty/unit/nome.
    if not ingredients and steps:
        merged_steps = "\\n".join([str(st.get("text", "")).strip() for st in steps if isinstance(st, dict) and st.get("text")]).strip()
        m = _RE_ING_HDR_ANY.search(merged_steps)
        if m:
            chunk = merged_steps[m.end():]
            m2 = _RE_STP_HDR_ANY.search(chunk)
            if m2:
                chunk = chunk[:m2.start()]

            for raw_ln in chunk.splitlines():
                ln = (raw_ln or "").strip()
                if not ln:
                    continue
                ln = _RE_NUM_PREFIX.sub("", ln)
                ln = _RE_BULLET.sub("", ln).strip()
                if not ln:
                    continue

                if _is_non_ingredient_line(ln):
                    continue

                # evita righe chiaramente non-ingredienti
                low = ln.lower()
                if low.startswith(("proced", "prep", "metod", "instruction", "method")):
                    continue

                mi = _RE_QTY_UNIT.match(ln)
                if mi:
                    qty = _safe_float(mi.group("qty"))
                    unit = _normalize_unit(mi.group("unit"))
                    name = (mi.group("name") or "").strip()
                    if name:
                        ingredients.append({"name": name, "qty": qty, "unit": unit})
                else:
                    ingredients.append({"name": ln, "qty": None, "unit": None})


    if ingredients:
        cleaned_ingredients: List[Dict[str, Any]] = []
        for ing in ingredients:
            name = str((ing or {}).get("name") or "").strip()
            if not name:
                continue
            if _is_non_ingredient_line(name):
                continue
            cleaned_ingredients.append(ing)
        ingredients = cleaned_ingredients

    missing_clean: List[str] = []
    if servings is None:
        missing_clean.append("servings")
    if not ingredients:
        missing_clean.append("ingredients")
    if not steps:
        missing_clean.append("steps")
    # conserva qty/unit mancanti (già in missing)
    for m in missing:
        if m not in missing_clean:
            missing_clean.append(m)

    def _fmt_ing_qty(val: Any) -> str:
        q = _safe_float(val)
        if q is None or abs(q) < 1e-9:
            return ""
        if q.is_integer():
            return str(int(q))
        return str(q).replace(".", ",")

    ingredients_text = "\n".join(
        [
            f"- {_fmt_ing_qty(i.get('qty'))}{('' if not i.get('unit') else ' ' + str(i.get('unit')))} {i.get('name','')}".strip()
            for i in ingredients
            if i.get("name")
        ]
    ).strip() + ("\n" if ingredients else "")

    # Ripulisci “meta-frasi” che alcuni modelli inseriscono nel procedimento.
    _meta_re = re.compile(
        r"(non\s+trovo|non\s+riesco|scrivo\s+con\s+contenuto\s+minimo|contenuto\s+minimo|quest[ei]\s+ingredienti\s+non\s+sono\s+presenti|porzioni\s*:\s*n/?d)",
        re.IGNORECASE,
    )
    cleaned_steps: List[Dict[str, Any]] = []
    for s in steps:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        if _meta_re.search(txt):
            continue
        cleaned_steps.append({"text": txt})
    steps = cleaned_steps

    steps_text = "\n".join([f"{idx+1}) {s['text']}" for idx, s in enumerate(steps) if s.get("text")]).strip() + ("\n" if steps else "")

    return {
        "title": title,
        "category": category,
        "servings": servings,
        "difficulty": difficulty,
        "prep_time_min": prep_time_min,
        "cook_time_min": cook_time_min,
        "total_time_min": total_time_min,
        "diet_flags": diet_flags,
        "diet_text": diet_text,
        "conservazione": conservazione,
        "allergens_text": allergens_text,
        "vino_descrizione": vino_descrizione,
        "wine_pairing": vino_descrizione,
        "vino_temperatura_servizio": "",
        "vino_regione": "",
        "vino_annata": "",
        "vino_motivo_annata": "",
        "equipment_text": equipment_text,
        "attrezzature_generiche": equipment_text,
        "presentazione_impiattamento": presentazione,
        "stagionalita": stagionalita,
        "ingredients": ingredients,
        "steps": steps,
        "ingredients_text": ingredients_text,
        "steps_text": steps_text,
    }, missing_clean
