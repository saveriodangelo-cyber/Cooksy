from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ======================================================================================
# ALLERGENI + FLAG DIETA
#
# Obiettivo:
#   infer_allergens(recipe: Recipe) -> AllergenSummary
#
# - Mappa ingredienti→allergeni (14 UE)
# - Flag: vegetariano, vegano, senza glutine, senza lattosio (con motivazione)
# - Gestione “tracce” se presente nel testo
# - Collegamento ad allergens_it.json (schema flessibile, inclusa la tua struttura schema_version=1)
#
# Vincolo: NON crashare mai.
# ======================================================================================


# ---------------------------
# Output models
# ---------------------------

@dataclass
class DietFlag:
    value: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": bool(self.value), "reasons": list(self.reasons)}


@dataclass
class AllergenSummary:
    present: List[str] = field(default_factory=list)   # allergeni “presenti”
    traces: List[str] = field(default_factory=list)    # allergeni “in tracce” (se rilevati)

    detected_terms: Dict[str, List[str]] = field(default_factory=dict)  # spiegabilità

    vegetarian: DietFlag = field(default_factory=lambda: DietFlag(True))
    vegan: DietFlag = field(default_factory=lambda: DietFlag(True))
    gluten_free: DietFlag = field(default_factory=lambda: DietFlag(True))
    lactose_free: DietFlag = field(default_factory=lambda: DietFlag(True))

    notes: List[str] = field(default_factory=list)
    source_db_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "present": list(self.present),
            "traces": list(self.traces),
            "detected_terms": {k: list(v) for k, v in (self.detected_terms or {}).items()},
            "diet_flags": {
                "vegetarian": self.vegetarian.to_dict(),
                "vegan": self.vegan.to_dict(),
                "gluten_free": self.gluten_free.to_dict(),
                "lactose_free": self.lactose_free.to_dict(),
            },
            "notes": list(self.notes),
            "source_db_path": self.source_db_path,
        }


@dataclass
class AllergenDB:
    mapping: Dict[str, List[str]]
    trace_phrases_norm: List[str]
    source_path: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @staticmethod
    def load(path: Any = None) -> "AllergenDB":
        mapping, trace_phrases_norm, used_path, notes = load_allergens_db_with_phrases(
            str(path) if path else None
        )
        return AllergenDB(mapping=mapping, trace_phrases_norm=trace_phrases_norm, source_path=used_path, notes=notes)

    def detect_in_text(self, text: str) -> Dict[str, Any]:
        lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
        recipe = {"title": "", "ingredients": lines, "steps": []}
        summary = infer_allergens(recipe, allergens_db_path=self.source_path)
        return summary.to_dict()


# ---------------------------
# 14 allergeni UE (chiavi stabili)
# ---------------------------

ALLERGEN_LABELS_IT: Dict[str, str] = {
    "glutine": "Cereali con glutine",
    "grano": "Grano",
    "crostacei": "Crostacei",
    "uova": "Uova",
    "pesce": "Pesci",
    "arachidi": "Arachidi",
    "soia": "Soia",
    "latte": "Latte",
    "frutta_a_guscio": "Frutta a guscio",
    "sedano": "Sedano",
    "senape": "Senape",
    "sesamo": "Sesamo",
    "solfiti": "Solfiti",
    "lupini": "Lupino",
    "molluschi": "Molluschi - Frutti di mare",
}

DEFAULT_ALLERGENS_DB_CANDIDATES: Sequence[str] = (
    os.path.join("data", "allergens_it.json"),
    os.path.join(os.path.dirname(__file__), "..", "data", "allergens_it.json"),
)


# ---------------------------
# Normalizzazione testo
# ---------------------------

_PARENS_RE = re.compile(r"\([^)]*\)")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\sàèéìòù%/-]+", flags=re.IGNORECASE)


def _strip_accents(s: str) -> str:
    try:
        nfkd = unicodedata.normalize("NFKD", s)
        return "".join([c for c in nfkd if not unicodedata.combining(c)])
    except Exception:
        return s


def normalize_text(s: Any) -> str:
    """Lowercase, rimuove parentesi e punteggiatura, normalizza spazi. Non crasha."""
    try:
        if s is None:
            return ""
        s = str(s).strip()
        s = _PARENS_RE.sub(" ", s)
        s = s.replace("’", "'")
        s = s.lower()
        s = _strip_accents(s)
        s = _PUNCT_RE.sub(" ", s)
        s = _WS_RE.sub(" ", s).strip()
        return s
    except Exception:
        return ""


# ---------------------------
# Estrazione ingredienti / testo ricetta (duck-typing)
# ---------------------------

def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    try:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    except Exception:
        return default


def _extract_ingredient_name(ing: Any) -> str:
    try:
        if isinstance(ing, str):
            return ing
        if isinstance(ing, dict):
            return str(ing.get("name") or ing.get("ingredient") or ing.get("nome") or "")
        return str(getattr(ing, "name", "") or getattr(ing, "ingredient", "") or getattr(ing, "nome", "") or "")
    except Exception:
        return ""


def _iter_ingredient_strings(recipe: Any) -> List[str]:
    out: List[str] = []
    try:
        ingredients = _safe_get(recipe, "ingredients", None)
        if ingredients is None:
            ingredients = _safe_get(recipe, "ingredienti", None)

        if isinstance(ingredients, str):
            out.extend([line.strip() for line in ingredients.splitlines() if line.strip()])
        elif isinstance(ingredients, (list, tuple)):
            for ing in ingredients:
                name = _extract_ingredient_name(ing).strip()
                if name:
                    out.append(name)
        elif ingredients is not None:
            out.append(str(ingredients))
    except Exception:
        pass
    return out


def _recipe_full_text(recipe: Any) -> str:
    parts: List[str] = []
    try:
        parts.append(str(_safe_get(recipe, "title", "") or _safe_get(recipe, "titolo", "") or ""))
        parts.extend(_iter_ingredient_strings(recipe))

        steps = _safe_get(recipe, "steps", None) or _safe_get(recipe, "procedimento", None) or _safe_get(recipe, "method", None)
        if isinstance(steps, str):
            parts.append(steps)
        elif isinstance(steps, (list, tuple)):
            parts.extend([str(x) for x in steps if x is not None])
        elif steps is not None:
            parts.append(str(steps))

        return "\n".join([p for p in parts if p]).strip()
    except Exception:
        return "\n".join([p for p in parts if p]).strip()


# ---------------------------
# DB Allergeni (JSON) - parsing flessibile (incluso schema_version=1 del tuo file)
# ---------------------------

def _default_mapping() -> Dict[str, List[str]]:
    # Fallback “ampio”: meglio un alert in più che uno in meno.
    return {
        "glutine": [
            "glutine", "farina", "grano", "frumento", "semola", "segale", "orzo", "avena", "farro", "spelta", "kamut",
            "pane", "pasta", "cous cous", "couscous", "bulgur", "seitan", "pangrattato", "lievito madre",
            "wheat", "barley", "rye", "oats", "spelt"
        ],
        "crostacei": ["crostacei", "gamberi", "gambero", "mazzancolle", "scampi", "aragosta", "granchio", "astice", "krill", "shrimp", "prawn", "lobster", "crab"],
        "uova": ["uovo", "uova", "albume", "albumi", "tuorlo", "tuorli", "ovoprodotti", "maionese", "pasta all'uovo", "egg", "eggs", "egg white", "egg yolk"],
        "pesce": ["pesce", "tonno", "salmone", "acciughe", "alici", "merluzzo", "baccalà", "sgombro", "fish", "tuna", "salmon", "anchovy", "cod"],
        "arachidi": ["arachidi", "arachide", "noccioline", "burro di arachidi", "peanut", "peanuts", "groundnut"],
        "soia": ["soia", "salsa di soia", "tofu", "edamame", "lecitina di soia", "proteine di soia", "tempeh", "soy", "soybean", "soy sauce", "lecithin", "soya"],
        "latte": ["latte", "lattosio", "burro", "panna", "yogurt", "formaggio", "ricotta", "mozzarella", "mascarpone", "siero di latte", "caseina", "milk", "butter", "cream", "whey", "casein", "lactose"],
        "frutta_a_guscio": ["frutta a guscio", "mandorle", "mandorla", "nocciole", "nocciola", "noci", "noce", "pecan", "anacardi", "pistacchi", "pistacchio", "macadamia", "pinoli", "castagne", "pralinato", "almond", "hazelnut", "walnut", "cashew", "pistachio", "nuts"],
        "sedano": ["sedano", "sale di sedano", "celery", "celeri"],
        "senape": ["senape", "mostarda", "mustard", "semi di senape"],
        "sesamo": ["sesamo", "semi di sesamo", "tahina", "tahin", "sesame", "sesame seeds", "pasta di sesamo"],
        "solfiti": ["solfiti", "anidride solforosa", "metabisolfito", "vino", "aceto", "uvetta", "sulphite", "sulfite", "sulphites", "sulfites", "so2", "e220", "e221", "e222", "e223", "e224", "e226", "e227", "e228"],
        "lupini": ["lupini", "lupino", "farina di lupini", "lupin", "lupine", "lupin flour"],
        "molluschi": ["molluschi", "mollusco", "cozze", "vongole", "ostriche", "calamari", "seppie", "polpo", "chiocciole", "shellfish", "mussels", "clams", "oysters", "squid", "octopus"],
    }


def _coerce_list(obj: Any) -> List[str]:
    if obj is None:
        return []
    if isinstance(obj, str):
        parts = [p.strip() for p in obj.split(",")]
        return [p for p in parts if p]
    if isinstance(obj, (list, tuple)):
        return [str(x) for x in obj if x is not None and str(x).strip()]
    if isinstance(obj, dict):
        # non è una lista: prova a prendere campi noti
        return _coerce_list(obj.get("keywords") or obj.get("terms") or obj.get("aliases") or obj.get("synonyms"))
    return [str(obj)]


def _to_canonical_key(k: str) -> str:
    nk = normalize_text(k).replace(" ", "_")
    # normalizzazioni specifiche
    if nk == "frutta_a_guscio":
        return "frutta_a_guscio"
    if nk in ("anidride_solforosa_e_solfiti", "solfiti"):
        return "solfiti"
    return nk


def load_allergens_db_with_phrases(path: Optional[str] = None) -> Tuple[Dict[str, List[str]], List[str], Optional[str], List[str]]:
    """
    Ritorna:
      mapping: allergen_key -> keywords
      trace_phrases: frasi che indicano 'può contenere/tracce...' (union globale)
      source_path: path effettivo usato o None
      notes: note/parsing issues
    """
    notes: List[str] = []
    candidates: List[str] = []
    if path:
        candidates.append(path)
    candidates.extend(list(DEFAULT_ALLERGENS_DB_CANDIDATES))

    # fallback phrases (sempre attive)
    default_phrases = [
        "tracce",
        "tracce di",
        "puo contenere",
        "può contenere",
        "puo contenere tracce",
        "può contenere tracce",
        "may contain",
        "traces of",
        "in uno stabilimento che utilizza",
    ]

    for p in candidates:
        try:
            if not p:
                continue
            ap = os.path.abspath(p)
            if not os.path.exists(ap):
                continue

            with open(ap, "r", encoding="utf-8") as f:
                data = json.load(f)

            mapping: Dict[str, List[str]] = {}
            trace_phrases: List[str] = list(default_phrases)

            # Supporta:
            # - schema_version=1 con chiave "allergens": list di item con "short_name", "keywords", "may_contain_phrases"
            # - dict diretto {"latte":[...], ...}
            # - list di record [{"key":..., "keywords":[...]}, ...]
            if isinstance(data, dict) and "allergens" in data and isinstance(data["allergens"], (list, tuple)):
                for it in data["allergens"]:
                    if not isinstance(it, dict):
                        continue
                    # chiavi possibili: key / short_name / name / id / code
                    raw_k = (
                        it.get("key")
                        or it.get("short_name")
                        or it.get("shortName")
                        or it.get("name")
                        or it.get("id")
                        or it.get("code")
                        or ""
                    )
                    raw_k = str(raw_k).strip()
                    if not raw_k:
                        continue

                    ck = _to_canonical_key(raw_k)

                    kws = _coerce_list(it.get("keywords") or it.get("terms") or it.get("aliases"))
                    # aggiungi anche synonyms/synonyms array se presente
                    kws.extend(_coerce_list(it.get("synonyms")))
                    kws = [x for x in kws if x]

                    if ck and ck in ALLERGEN_LABELS_IT and kws:
                        mapping[ck] = kws

                    # frasi tracce (global union)
                    trace_phrases.extend(_coerce_list(it.get("may_contain_phrases")))

                # completa con fallback per chiavi mancanti
                fb = _default_mapping()
                for k, v in fb.items():
                    mapping.setdefault(k, v)

                # normalizza/unique trace phrases
                trace_phrases_norm = []
                seen = set()
                for ph in trace_phrases:
                    nph = normalize_text(ph)
                    if not nph:
                        continue
                    if nph in seen:
                        continue
                    seen.add(nph)
                    trace_phrases_norm.append(nph)

                if not mapping:
                    notes.append(f"DB allergeni letto ma mapping vuoto/non compatibile: {ap}. Uso fallback interno.")
                    return _default_mapping(), [normalize_text(x) for x in default_phrases], ap, notes

                return mapping, trace_phrases_norm, ap, notes

            # dict diretto
            if isinstance(data, dict):
                for k, v in data.items():
                    ck = _to_canonical_key(str(k))
                    if ck not in ALLERGEN_LABELS_IT:
                        continue
                    kws = _coerce_list(v)
                    if kws:
                        mapping[ck] = kws

                fb = _default_mapping()
                for k, v in fb.items():
                    mapping.setdefault(k, v)

                return mapping, [normalize_text(x) for x in default_phrases], ap, notes

            # list record
            if isinstance(data, (list, tuple)):
                for it in data:
                    if not isinstance(it, dict):
                        continue
                    raw_k = str(it.get("key") or it.get("short_name") or it.get("name") or it.get("id") or "").strip()
                    if not raw_k:
                        continue
                    ck = _to_canonical_key(raw_k)
                    if ck not in ALLERGEN_LABELS_IT:
                        continue
                    kws = _coerce_list(it.get("keywords") or it.get("terms") or it.get("aliases") or it.get("synonyms"))
                    if kws:
                        mapping[ck] = kws

                fb = _default_mapping()
                for k, v in fb.items():
                    mapping.setdefault(k, v)

                return mapping, [normalize_text(x) for x in default_phrases], ap, notes

        except Exception as e:
            notes.append(f"Impossibile leggere DB allergeni '{p}': {e!r}. Provo alternative.")

    notes.append("DB allergeni non trovato o non leggibile. Uso mapping interno di fallback.")
    return _default_mapping(), [normalize_text(x) for x in default_phrases], None, notes


def load_allergens_db(path: Optional[str] = None) -> Tuple[Dict[str, List[str]], Optional[str], List[str]]:
    """
    Wrapper retro-compatibile: mantiene la firma semplice (mapping, source_path, notes).
    """
    mapping, _phrases, src, notes = load_allergens_db_with_phrases(path)
    return mapping, src, notes


# ---------------------------
# Match engine (regex)
# ---------------------------

def _compile_keyword_patterns(mapping: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, re.Pattern]]]:
    compiled: Dict[str, List[Tuple[str, re.Pattern]]] = {}
    for allergen, kws in (mapping or {}).items():
        pats: List[Tuple[str, re.Pattern]] = []
        for kw in kws or []:
            nkw = normalize_text(kw)
            if not nkw:
                continue
            if " " not in nkw:
                pat = re.compile(rf"(?<!\w){re.escape(nkw)}(?!\w)")
            else:
                pat = re.compile(re.escape(nkw))
            pats.append((kw, pat))
        compiled[allergen] = pats
    return compiled


# Alcuni termini sono troppo “generici” e generano falsi positivi (es. "cracker").
# Qui adottiamo una regola prudente:
# - per il glutine, termini di prodotto (pane/pasta/cracker/biscotti...) sono WEAK:
#   li usiamo come indizio (note), ma non per dichiarare l'allergene presente da soli.
_GLUTINE_WEAK_TERMS = {
    "pane", "pasta", "cracker", "crackers", "biscotti", "torte", "impasti", "pangrattato", "pan grattato"
}
# termini “forti” glutine: se presenti => allergene glutine certo
_GLUTINE_STRONG_TERMS = {
    "glutine", "farina", "grano", "frumento", "semola", "segale", "orzo", "avena", "farro", "spelta", "kamut",
    "wheat", "barley", "rye", "oats", "spelt", "bulgur", "seitan", "cous cous", "couscous"
}


def _is_explicitly_free(text: str, kind: str) -> bool:
    t = normalize_text(text)
    if kind == "gluten":
        return ("senza glutine" in t) or ("gluten free" in t)
    if kind == "lactose":
        return ("senza lattosio" in t) or ("lactose free" in t)
    return False


def _detect_trace_lines(lines: Sequence[str], trace_phrases_norm: Sequence[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        n = normalize_text(ln)
        if not n:
            continue
        for ph in trace_phrases_norm:
            try:
                if ph and ph in n:
                    out.append(ln)
                    break
            except Exception:
                continue
    return out


# ---------------------------
# Diet flag heuristics
# ---------------------------

_NON_VEGETARIAN_TERMS = [
    "carne", "manzo", "vitello", "maiale", "pollo", "tacchino", "agnello", "coniglio",
    "prosciutto", "speck", "salame", "salsiccia", "mortadella", "pancetta", "guanciale", "lardo",
    "tonno", "salmone", "acciuga", "alici", "merluzzo", "sgombro", "baccalà", "pesce",
    "brodo di carne", "dado carne", "gelatina di carne",
    "cozze", "vongole", "calamaro", "seppia", "polpo", "ostrica",
    "gamberi", "scampi", "aragosta", "astice", "granchio",
]

_NON_VEGAN_TERMS_EXTRA = [
    "uovo", "uova", "albume", "tuorlo",
    "latte", "burro", "panna", "yogurt", "formaggio", "caseina", "siero di latte",
    "miele",
    "gelatina", "colla di pesce",
]

_DAIRY_TERMS = [
    "latte", "burro", "panna", "yogurt", "formaggio", "ricotta", "mascarpone",
    "mozzarella", "parmigiano", "grana", "pecorino", "gorgonzola",
    "caseina", "siero di latte", "lattosio",
]


def _contains_any(text: str, needles: Sequence[str]) -> Optional[str]:
    t = normalize_text(text)
    for n in needles:
        nn = normalize_text(n)
        if nn and nn in t:
            return n
    return None


# ---------------------------
# API principale
# ---------------------------

def infer_allergens(recipe: Any, allergens_db_path: Optional[str] = None) -> AllergenSummary:
    """
    Inferisce:
    - Allergeni presenti (da ingredienti)
    - Tracce (se presenti frasi tipo "può contenere tracce...")
    - Flag dieta: vegetariano, vegano, senza glutine, senza lattosio (con motivazione)

    Non lancia eccezioni: ritorna sempre AllergenSummary.
    """
    summary = AllergenSummary()

    try:
        mapping, trace_phrases_norm, used_path, notes = load_allergens_db_with_phrases(allergens_db_path)
        summary.source_db_path = used_path
        summary.notes.extend(notes)

        compiled = _compile_keyword_patterns(mapping)

        ingredient_lines = _iter_ingredient_strings(recipe)
        full_text = _recipe_full_text(recipe)

        # tracce: cerca frasi (da DB + fallback)
        trace_lines = _detect_trace_lines(ingredient_lines + full_text.splitlines(), trace_phrases_norm)

        present_set = set()
        traces_set = set()
        detected_terms: Dict[str, List[str]] = {k: [] for k in ALLERGEN_LABELS_IT.keys()}

        # Per gestire il glutine in modo prudente:
        glutine_weak_hits: List[str] = []
        glutine_strong_hit = False

        for raw_line in ingredient_lines:
            nline = normalize_text(raw_line)
            if not nline:
                continue

            # match per ogni allergene
            for allergen, pats in compiled.items():
                # eccezione: se la riga dichiara "senza glutine", non usiamola per marcare glutine
                if allergen == "glutine" and _is_explicitly_free(raw_line, "gluten"):
                    continue

                for original_kw, pat in pats:
                    try:
                        nkw = normalize_text(original_kw)
                        if not nkw:
                            continue
                        if not pat.search(nline):
                            continue

                        # gestione speciale glutine: weak vs strong
                        if allergen == "glutine":
                            if nkw in _GLUTINE_STRONG_TERMS:
                                glutine_strong_hit = True
                            elif nkw in _GLUTINE_WEAK_TERMS:
                                glutine_weak_hits.append(original_kw)
                                # NON aggiungiamo subito a present_set
                                detected_terms.setdefault("glutine", [])
                                if original_kw not in detected_terms["glutine"]:
                                    detected_terms["glutine"].append(original_kw)
                                continue  # non dichiarare glutine "presente" per keyword debole
                            else:
                                # se non classificato, consideriamolo strong per prudenza
                                glutine_strong_hit = True

                        present_set.add(allergen)
                        detected_terms.setdefault(allergen, [])
                        if original_kw not in detected_terms[allergen]:
                            detected_terms[allergen].append(original_kw)

                    except Exception:
                        continue

            # se la riga è di tracce, prova ad associare allergeni presenti nella riga stessa
            if raw_line in trace_lines:
                for allergen, pats in compiled.items():
                    for original_kw, pat in pats:
                        try:
                            nkw = normalize_text(original_kw)
                            if not nkw:
                                continue
                            if pat.search(nline):
                                # per glutine: anche qui usiamo prudenza (weak keyword da sola non basta)
                                if allergen == "glutine" and (nkw in _GLUTINE_WEAK_TERMS) and not glutine_strong_hit:
                                    continue
                                traces_set.add(allergen)
                                detected_terms.setdefault(allergen, [])
                                if original_kw not in detected_terms[allergen]:
                                    detected_terms[allergen].append(original_kw)
                        except Exception:
                            continue

        # Finalizzazione glutine: se abbiamo solo weak hits (e nessun strong), non lo dichiarare presente.
        if glutine_strong_hit:
            present_set.add("glutine")
        else:
            # se ci sono weak hits, lascia una nota (utile in OCR: "cracker" spesso implica glutine, ma non sempre)
            if glutine_weak_hits:
                summary.notes.append(
                    "Rilevati termini generici associati al glutine (es. 'cracker/pane/pasta') ma senza evidenze forti (farina/grano/semola...). "
                    "Non dichiaro l'allergene 'glutine' come presente automaticamente: verifica se il prodotto è senza glutine."
                )

        # Se troviamo frasi di tracce ma non riusciamo ad associare allergeni: nota
        if trace_lines and not traces_set:
            summary.notes.append(
                "Rilevate frasi di 'tracce/può contenere', ma non è stato possibile associare allergeni specifici."
            )

        # ---------------------------
        # Diet flags
        # ---------------------------
        vegetarian = True
        vegan = True
        gf = True
        lf = True

        # Vegetarian / Vegan
        for s in ingredient_lines + [full_text]:
            hit_nv = _contains_any(s, _NON_VEGETARIAN_TERMS)
            if hit_nv:
                vegetarian = False
                summary.vegetarian.reasons.append(f"Trovato ingrediente non vegetariano: '{hit_nv}'.")
                vegan = False
                summary.vegan.reasons.append(f"Trovato ingrediente non vegano (carne/pesce): '{hit_nv}'.")
                break

        if vegan:
            for s in ingredient_lines + [full_text]:
                hit_nvg = _contains_any(s, _NON_VEGAN_TERMS_EXTRA)
                if hit_nvg:
                    vegan = False
                    summary.vegan.reasons.append(f"Trovato ingrediente non vegano: '{hit_nvg}'.")
                    break

        # Gluten-free
        explicit_gf_claim = _is_explicitly_free(full_text, "gluten") or any(_is_explicitly_free(x, "gluten") for x in ingredient_lines)
        if "glutine" in present_set:
            gf = False
            if explicit_gf_claim:
                summary.gluten_free.reasons.append(
                    "Nel testo è indicato 'senza glutine', ma sono stati rilevati indicatori di glutine. Verifica ingredienti."
                )
            else:
                summary.gluten_free.reasons.append("Rilevati indicatori di glutine negli ingredienti.")
        else:
            if "glutine" in traces_set:
                summary.gluten_free.reasons.append("Possibili tracce di glutine indicate nel testo.")

        # Lactose-free
        explicit_lf_claim = _is_explicitly_free(full_text, "lactose") or any(_is_explicitly_free(x, "lactose") for x in ingredient_lines)
        dairy_hit = _contains_any(full_text, _DAIRY_TERMS) or next((d for d in _DAIRY_TERMS if any(normalize_text(d) in normalize_text(x) for x in ingredient_lines)), None)

        if dairy_hit:
            if explicit_lf_claim:
                lf = True
                summary.lactose_free.reasons.append("Indicazione 'senza lattosio' rilevata nel testo/ingredienti.")
                # Nota importante: allergene latte può essere presente comunque
                if "latte" in present_set:
                    summary.lactose_free.reasons.append("Nota: l'allergene 'latte' può essere comunque presente (proteine del latte).")
            else:
                lf = False
                summary.lactose_free.reasons.append(f"Contiene derivati del latte: '{dairy_hit}'.")
        else:
            if explicit_lf_claim:
                summary.lactose_free.reasons.append("Indicazione 'senza lattosio' rilevata nel testo.")

        # motivazioni default
        if vegetarian and not summary.vegetarian.reasons:
            summary.vegetarian.reasons.append("Non sono stati rilevati ingredienti di carne/pesce/crostacei/molluschi.")
        if vegan and not summary.vegan.reasons:
            summary.vegan.reasons.append("Non sono stati rilevati ingredienti di origine animale (in base alle euristiche).")
        if gf and not summary.gluten_free.reasons:
            summary.gluten_free.reasons.append("Non sono stati rilevati indicatori di glutine (in base alle euristiche).")
        if lf and not summary.lactose_free.reasons:
            summary.lactose_free.reasons.append("Non sono stati rilevati derivati del latte/lattosio (in base alle euristiche).")

        summary.vegetarian.value = bool(vegetarian)
        summary.vegan.value = bool(vegan)
        summary.gluten_free.value = bool(gf)
        summary.lactose_free.value = bool(lf)

        # output allergeni
        summary.present = sorted([a for a in present_set if a in ALLERGEN_LABELS_IT])
        summary.traces = sorted([a for a in traces_set if a in ALLERGEN_LABELS_IT])

        summary.detected_terms = {k: v for k, v in detected_terms.items() if v}

        # coerenze minime
        if summary.vegan.value and (("uova" in summary.present) or ("latte" in summary.present)):
            summary.notes.append("Possibile incoerenza: flag vegano True ma rilevati 'uova/latte'. Verifica testo ingredienti.")

        return summary

    except Exception as e:
        summary.notes.append(f"Errore inatteso in infer_allergens (gestito): {e!r}")
        return summary


def allergen_label_it(key: str) -> str:
    k = normalize_text(key).replace(" ", "_")
    return ALLERGEN_LABELS_IT.get(k, key)
