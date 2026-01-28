from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import Recipe


# Categorie fisse (coerenti con la scelta dell'utente)
CATEGORIES_FIXED: List[str] = [
    "Antipasti",
    "Primi",
    "Secondi",
    "Contorni",
    "Piatto unico",
    "Dolci",
    "Molecolare",
    "Pane e lievitati",
    "Salse e condimenti",
    "Bevande",
    "Altro",
]


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _norm(s: str) -> str:
    """Normalizzazione semplice (IT) per matching e ricerca."""
    s = (s or "").strip().lower()
    if not s:
        return ""
    # rimuovi accenti
    s = "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )
    # pulizia base
    out = []
    prev_space = False
    for ch in s:
        if ch.isalnum() or ch in {"_", "-"}:
            out.append(ch)
            prev_space = False
        else:
            if not prev_space:
                out.append(" ")
                prev_space = True
    return " ".join("".join(out).split())


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _parse_minutes(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).lower().strip()
    if not s:
        return None
    mh = re.search(r"(\d+)\s*h", s)
    mm = re.search(r"(\d+)\s*(min|m)\b", s)
    if mh or mm:
        h = int(mh.group(1)) if mh else 0
        m = int(mm.group(1)) if mm else 0
        return float(h * 60 + m)
    return _to_float(s)


def _parse_allergens(recipe: Dict[str, Any]) -> List[str]:
    # preferisci lista strutturata
    raw: List[str] = []
    allergens_raw = recipe.get("allergens")
    if isinstance(allergens_raw, list):
        raw = [str(x) for x in allergens_raw if x]
    else:
        txt = str(recipe.get("allergens_text") or "").strip()
        if txt:
            # split su virgole e nuove linee
            parts = [p.strip() for p in txt.replace("\n", ",").split(",")]
            raw = [p for p in parts if p]
    # dedup
    seen = set()
    out: List[str] = []
    for a in raw:
        k = _norm(a)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(a.strip())
    return out


def _parse_diets(recipe: Dict[str, Any]) -> List[str]:
    df = recipe.get("diet_flags")
    out: List[str] = []
    if isinstance(df, dict):
        if df.get("vegan"):
            out.append("vegana")
        elif df.get("vegetarian"):
            out.append("vegetariana")
        if df.get("gluten_free"):
            out.append("senza glutine")
        if df.get("lactose_free"):
            out.append("senza lattosio")
    # fallback su testo
    if not out:
        txt = str(recipe.get("diet_text") or "").strip().lower()
        for key in ["vegana", "vegetariana", "senza glutine", "senza lattosio"]:
            if key in txt:
                out.append(key)
    # dedup
    seen = set()
    final: List[str] = []
    for d in out:
        k = _norm(d)
        if not k or k in seen:
            continue
        seen.add(k)
        final.append(d)
    return final


def _parse_ingredients(recipe: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    ingredients_raw = recipe.get("ingredients")
    if isinstance(ingredients_raw, list):
        for x in ingredients_raw:
            if isinstance(x, dict):
                nm = str(x.get("name") or "").strip()
                if nm:
                    out.append(nm)
            else:
                s = str(x).strip()
                if s:
                    out.append(s)
    else:
        txt = str(recipe.get("ingredients_text") or "").strip()
        if txt:
            for line in txt.splitlines():
                line = line.strip().lstrip("•").strip()
                if not line:
                    continue
                out.append(line)
    # dedup norm
    seen = set()
    final: List[str] = []
    for ing in out:
        k = _norm(ing)
        if not k or k in seen:
            continue
        seen.add(k)
        final.append(ing)
    return final


@dataclass
class ArchiveItem:
    id: int
    title: str
    category: str
    updated_at: str


class ArchiveDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @classmethod
    def default(cls, project_root: Optional[Path] = None) -> "ArchiveDB":
        root = project_root or Path(__file__).resolve().parent.parent
        db_path = root / "data" / "recipes" / "recipes.db"
        return cls(db_path)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        # Abilita WAL mode per migliori performance su scritture parallele
        con.execute("PRAGMA journal_mode=WAL;")
        return con

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    title_norm TEXT NOT NULL,
                    category TEXT NOT NULL,
                    recipe_json TEXT NOT NULL,
                    missing_fields TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_recipes_title_norm ON recipes(title_norm);")
            con.execute("CREATE INDEX IF NOT EXISTS idx_recipes_category ON recipes(category);")
            con.execute("CREATE INDEX IF NOT EXISTS idx_recipes_updated_at ON recipes(updated_at);")

            try:
                cols = [row[1] for row in con.execute("PRAGMA table_info(recipes);").fetchall()]
            except Exception:
                cols = []
            if "missing_fields" not in cols:
                try:
                    con.execute("ALTER TABLE recipes ADD COLUMN missing_fields TEXT;")
                except Exception:
                    pass

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    recipe_id INTEGER NOT NULL,
                    ingredient TEXT NOT NULL,
                    ingredient_norm TEXT NOT NULL,
                    FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_ing_norm ON recipe_ingredients(ingredient_norm);")

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS recipe_allergens (
                    recipe_id INTEGER NOT NULL,
                    allergen TEXT NOT NULL,
                    allergen_norm TEXT NOT NULL,
                    FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_all_norm ON recipe_allergens(allergen_norm);")

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS recipe_diets (
                    recipe_id INTEGER NOT NULL,
                    diet TEXT NOT NULL,
                    diet_norm TEXT NOT NULL,
                    FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_diet_norm ON recipe_diets(diet_norm);")

            con.execute("PRAGMA foreign_keys=ON;")

    def save_recipe(self, recipe: Dict[str, Any]) -> int:
        title = str(recipe.get("title") or "Ricetta").strip() or "Ricetta"
        category = str(recipe.get("category") or "").strip()
        if category not in CATEGORIES_FIXED:
            category = "Antipasti"  # default sicuro

        title_norm = _norm(title)
        now = _now_iso()
        blob = json.dumps(recipe, ensure_ascii=False)
        missing_raw = recipe.get("missing_fields")
        if isinstance(missing_raw, (list, tuple, set)):
            missing_list = [str(x) for x in missing_raw if str(x).strip()]
        elif isinstance(missing_raw, str):
            missing_list = [x.strip() for x in missing_raw.split(",") if x.strip()]
        else:
            missing_list = []
        missing_text = ", ".join(missing_list)

        ingredients = _parse_ingredients(recipe)
        allergens = _parse_allergens(recipe)
        diets = _parse_diets(recipe)

        with self._connect() as con:
            con.execute("PRAGMA foreign_keys=ON;")
            cur = con.execute(
                """
                INSERT INTO recipes(title, title_norm, category, recipe_json, missing_fields, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (title, title_norm, category, blob, missing_text, now, now),
            )
            last_rowid = cur.lastrowid
            if last_rowid is None:
                raise RuntimeError("Impossibile ottenere l'ID della ricetta appena inserita.")
            rid = int(last_rowid)

            con.executemany(
                "INSERT INTO recipe_ingredients(recipe_id, ingredient, ingredient_norm) VALUES(?, ?, ?)",
                [(rid, ing, _norm(ing)) for ing in ingredients],
            )
            con.executemany(
                "INSERT INTO recipe_allergens(recipe_id, allergen, allergen_norm) VALUES(?, ?, ?)",
                [(rid, a, _norm(a)) for a in allergens],
            )
            con.executemany(
                "INSERT INTO recipe_diets(recipe_id, diet, diet_norm) VALUES(?, ?, ?)",
                [(rid, d, _norm(d)) for d in diets],
            )

        return rid

    def find_identical_recipe(self, recipe: Dict[str, Any]) -> Optional[int]:
        """Cerca una ricetta identica nel database basandosi sul JSON.
        Ritorna l'ID della ricetta identica se trovata, None altrimenti."""
        import hashlib
        
        recipe_json = json.dumps(recipe, sort_keys=True, ensure_ascii=False)
        recipe_hash = hashlib.md5(recipe_json.encode('utf-8')).hexdigest()
        
        with self._connect() as con:
            row = con.execute("""
                SELECT id FROM recipes
                WHERE recipe_json IS NOT NULL
            """).fetchall()
            
            for (existing_id,) in row:
                existing_recipe = self.load_recipe(existing_id)
                if existing_recipe is None:
                    continue
                existing_json = json.dumps(existing_recipe, sort_keys=True, ensure_ascii=False)
                existing_hash = hashlib.md5(existing_json.encode('utf-8')).hexdigest()
                if recipe_hash == existing_hash:
                    return existing_id
        
        return None

    def load_recipe(self, recipe_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            row = con.execute("SELECT recipe_json FROM recipes WHERE id=?", (int(recipe_id),)).fetchone()
            if not row:
                return None
            try:
                data = json.loads(str(row[0]))
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
        return None

    def delete_recipes(self, ids: Iterable[int]) -> int:
        id_list = [int(x) for x in ids if x is not None]
        if not id_list:
            return 0
        with self._connect() as con:
            con.execute("PRAGMA foreign_keys=ON;")
            cur = con.executemany("DELETE FROM recipes WHERE id=?", [(i,) for i in id_list])
            return cur.rowcount if cur.rowcount is not None else 0

    def search(
        self,
        query: str = "",
        category: str = "",
        ingredient_query: str = "",
        missing_only: bool = False,
        missing_field: str = "",
        require_diets: list[str] | None = None,
        exclude_allergens: list[str] | None = None,
        difficulty: str = "",
        seasonality: str = "",
        servings_min: Optional[float] = None,
        servings_max: Optional[float] = None,
        prep_min: Optional[float] = None,
        prep_max: Optional[float] = None,
        cook_min: Optional[float] = None,
        cook_max: Optional[float] = None,
        total_min: Optional[float] = None,
        total_max: Optional[float] = None,
        kcal_100_min: Optional[float] = None,
        kcal_100_max: Optional[float] = None,
        kcal_tot_min: Optional[float] = None,
        kcal_tot_max: Optional[float] = None,
        cost_min: Optional[float] = None,
        cost_max: Optional[float] = None,
        protein_100_min: Optional[float] = None,
        protein_100_max: Optional[float] = None,
        fat_100_min: Optional[float] = None,
        fat_100_max: Optional[float] = None,
        fiber_100_min: Optional[float] = None,
        fiber_100_max: Optional[float] = None,
        carb_100_min: Optional[float] = None,
        carb_100_max: Optional[float] = None,
        sugar_100_min: Optional[float] = None,
        sugar_100_max: Optional[float] = None,
        protein_tot_min: Optional[float] = None,
        protein_tot_max: Optional[float] = None,
        fat_tot_min: Optional[float] = None,
        fat_tot_max: Optional[float] = None,
        fiber_tot_min: Optional[float] = None,
        fiber_tot_max: Optional[float] = None,
        carb_tot_min: Optional[float] = None,
        carb_tot_max: Optional[float] = None,
        sugar_tot_min: Optional[float] = None,
        sugar_tot_max: Optional[float] = None,
        sat_100_min: Optional[float] = None,
        sat_100_max: Optional[float] = None,
        mono_100_min: Optional[float] = None,
        mono_100_max: Optional[float] = None,
        poly_100_min: Optional[float] = None,
        poly_100_max: Optional[float] = None,
        chol_100_min: Optional[float] = None,
        chol_100_max: Optional[float] = None,
        sat_tot_min: Optional[float] = None,
        sat_tot_max: Optional[float] = None,
        mono_tot_min: Optional[float] = None,
        mono_tot_max: Optional[float] = None,
        poly_tot_min: Optional[float] = None,
        poly_tot_max: Optional[float] = None,
        chol_tot_min: Optional[float] = None,
        chol_tot_max: Optional[float] = None,
        sodium_100_min: Optional[float] = None,
        sodium_100_max: Optional[float] = None,
        sodium_tot_min: Optional[float] = None,
        sodium_tot_max: Optional[float] = None,
        cost_total_min: Optional[float] = None,
        cost_total_max: Optional[float] = None,
        limit: int = 200,
        offset: int = 0,
        # ...altri parametri...
    ) -> list[ArchiveItem]:
        """Ricerca con protezione contro loop infiniti e record corrotti."""

        qn = _norm(query)
        in_qn = _norm(ingredient_query)
        req_d = [_norm(x) for x in (require_diets or []) if _norm(x)]
        exc_a = [_norm(x) for x in (exclude_allergens or []) if _norm(x)]

        where: List[str] = []
        params: List[Any] = []

        if category and category in CATEGORIES_FIXED:
            where.append("r.category = ?")
            params.append(category)

        if qn:
            # titolo o JSON (fallback) - titolo_norm è indicizzato
            where.append("(r.title_norm LIKE ? OR r.recipe_json LIKE ?)")
            params.extend([f"%{qn}%", f"%{query}%"])

        if in_qn:
            where.append(
                "EXISTS(SELECT 1 FROM recipe_ingredients i WHERE i.recipe_id=r.id AND i.ingredient_norm LIKE ?)"
            )
            params.append(f"%{in_qn}%")

        if missing_only:
            where.append("r.missing_fields IS NOT NULL AND TRIM(r.missing_fields) <> ''")

        if missing_field:
            parts = [p.strip() for p in str(missing_field).split(",") if p.strip()]
            if parts:
                likes = []
                for part in parts:
                    likes.append("r.missing_fields LIKE ?")
                    params.append(f"%{part}%")
                where.append("(" + " OR ".join(likes) + ")")

        # diete richieste: tutte devono essere presenti
        for d in req_d:
            where.append(
                "EXISTS(SELECT 1 FROM recipe_diets d WHERE d.recipe_id=r.id AND d.diet_norm = ?)"
            )
            params.append(d)

        # allergeni esclusi: nessuno deve essere presente
        for a in exc_a:
            where.append(
                "NOT EXISTS(SELECT 1 FROM recipe_allergens a WHERE a.recipe_id=r.id AND a.allergen_norm = ?)"
            )
            params.append(a)

        extra_filters = any(
            x is not None
            for x in (
                servings_min,
                servings_max,
                prep_min,
                prep_max,
                cook_min,
                cook_max,
                total_min,
                total_max,
                kcal_100_min,
                kcal_100_max,
                kcal_tot_min,
                kcal_tot_max,
                cost_min,
                cost_max,
                protein_100_min,
                protein_100_max,
                fat_100_min,
                fat_100_max,
                fiber_100_min,
                fiber_100_max,
                carb_100_min,
                carb_100_max,
                sugar_100_min,
                sugar_100_max,
                protein_tot_min,
                protein_tot_max,
                fat_tot_min,
                fat_tot_max,
                fiber_tot_min,
                fiber_tot_max,
                carb_tot_min,
                carb_tot_max,
                sugar_tot_min,
                sugar_tot_max,
                sat_100_min,
                sat_100_max,
                mono_100_min,
                mono_100_max,
                poly_100_min,
                poly_100_max,
                chol_100_min,
                chol_100_max,
                sat_tot_min,
                sat_tot_max,
                mono_tot_min,
                mono_tot_max,
                poly_tot_min,
                poly_tot_max,
                chol_tot_min,
                chol_tot_max,
                sodium_100_min,
                sodium_100_max,
                sodium_tot_min,
                sodium_tot_max,
                cost_total_min,
                cost_total_max,
                seasonality,
            )
        ) or bool(difficulty or seasonality)

        sql = "SELECT r.id, r.title, r.category, r.updated_at"
        if extra_filters:
            sql += ", r.recipe_json"
        sql += " FROM recipes r"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY r.updated_at DESC LIMIT ? OFFSET ?"
        base_limit = max(int(limit or 0), 1)
        sql_limit = base_limit
        if extra_filters:
            sql_limit = min(max(base_limit * 5, base_limit), 2000)
        params.append(int(sql_limit))
        params.append(int(offset))

        out: List[ArchiveItem] = []
        with self._connect() as con:
            rows = con.execute(sql, tuple(params)).fetchall()
            if not extra_filters:
                for row in rows:
                    out.append(
                        ArchiveItem(
                            id=int(row[0]),
                            title=str(row[1] or ""),
                            category=str(row[2] or ""),
                            updated_at=str(row[3] or ""),
                        )
                    )
                return out

            def _recipe_num(recipe: Dict[str, Any], keys: List[str]) -> Optional[float]:
                for key in keys:
                    if key in recipe:
                        num = _to_float(recipe.get(key))
                        if num is not None:
                            return num
                return None

            def _recipe_difficulty(recipe: Dict[str, Any]) -> str:
                raw = recipe.get("difficulty") or recipe.get("difficolta") or recipe.get("difficoltà") or ""
                s = _norm(str(raw))
                if not s:
                    return ""
                if "bass" in s or "facile" in s:
                    return "bassa"
                if "medi" in s:
                    return "media"
                if "alt" in s or "diffic" in s:
                    return "alta"
                return s

            def _extract_time(label: str, raw: str) -> Optional[float]:
                if not raw:
                    return None
                m = re.search(rf"{label}\s*[:\-]?\s*([0-9][^,;]*)", raw)
                if not m:
                    return None
                return _parse_minutes(m.group(1))

            def _recipe_time(recipe: Dict[str, Any], kind: str) -> Optional[float]:
                key_map = {
                    "prep": ["prep_time_min", "tempo_preparazione"],
                    "cook": ["cook_time_min", "tempo_cottura"],
                    "total": ["total_time_min", "tempo_totale"],
                }
                for key in key_map.get(kind, []):
                    num = _parse_minutes(recipe.get(key))
                    if num is not None:
                        return num
                raw = str(recipe.get("tempo_dettaglio") or recipe.get("tempo") or "")
                raw = raw.lower().strip()
                if raw:
                    if kind == "prep":
                        n = _extract_time(r"(?:prep|preparazione)", raw)
                        if n is not None:
                            return n
                    if kind == "cook":
                        n = _extract_time(r"(?:cottura|cook)", raw)
                        if n is not None:
                            return n
                    if kind == "total":
                        n = _extract_time(r"(?:totale|complessivo|total)", raw)
                        if n is not None:
                            return n
                    return _parse_minutes(raw)
                return None

            def _recipe_energy(recipe: Dict[str, Any], scope: str) -> Optional[float]:
                nt = recipe.get("nutrition_table")
                if isinstance(nt, dict):
                    block = nt.get(scope)
                    if scope == "100g" and block is None:
                        block = nt.get("per_100g") or nt.get("100")
                    if scope != "100g" and block is None:
                        block = nt.get("total") or nt.get("tot")
                    if isinstance(block, dict):
                        num = _to_float(block.get("energia") or block.get("energy") or block.get("kcal"))
                        if num is not None:
                            return num
                if scope == "100g":
                    return _recipe_num(recipe, ["energia_100g", "energia100g"])
                return _recipe_num(recipe, ["energia_totale", "energia_ricetta", "energia_tot"])

            def _nutrient_keys(field: str) -> List[str]:
                if field == "proteine_totali":
                    return ["proteine_totali", "proteine", "protein", "proteins"]
                if field == "grassi_totali":
                    return ["grassi_totali", "grassi", "fat", "fats"]
                if field == "fibre":
                    return ["fibre", "fiber", "fibers"]
                if field == "carboidrati_totali":
                    return ["carboidrati_totali", "carboidrati", "carbs", "carbs_g", "carbohydrates"]
                if field == "di_cui_zuccheri":
                    return ["di_cui_zuccheri", "zuccheri", "sugars", "sugars_g"]
                if field == "di_cui_saturi":
                    return ["di_cui_saturi", "saturi", "sat_fat", "sat_fat_g", "saturated_fat"]
                if field == "monoinsaturi":
                    return ["monoinsaturi", "mono", "monounsaturated", "mono_fat"]
                if field == "polinsaturi":
                    return ["polinsaturi", "poli", "polyunsaturated", "poly_fat"]
                if field == "colesterolo":
                    return ["colesterolo", "colesterolo_totale", "cholesterol"]
                if field == "sodio":
                    return ["sodio", "sodium", "sale", "salt"]
                return [field]

            def _recipe_nutrient(recipe: Dict[str, Any], field: str, scope: str) -> Optional[float]:
                nt = recipe.get("nutrition_table")
                if isinstance(nt, dict):
                    block = nt.get(scope)
                    if scope == "100g" and block is None:
                        block = nt.get("per_100g") or nt.get("100")
                    if scope != "100g" and block is None:
                        block = nt.get("total") or nt.get("totale")
                    if isinstance(block, dict):
                        for key in _nutrient_keys(field):
                            num = _to_float(block.get(key))
                            if num is not None:
                                return num
                if scope == "100g":
                    candidates = [f"{field}_100g"]
                    if field == "proteine_totali":
                        candidates += ["proteine_100g", "protein_100g"]
                    if field == "grassi_totali":
                        candidates += ["grassi_100g", "fat_100g"]
                    if field == "fibre":
                        candidates += ["fibre_100g", "fiber_100g"]
                    if field == "carboidrati_totali":
                        candidates += ["carboidrati_100g", "carbs_100g"]
                    if field == "di_cui_zuccheri":
                        candidates += ["zuccheri_100g", "sugars_100g"]
                    if field == "di_cui_saturi":
                        candidates += ["saturi_100g", "saturi_100"]
                    if field == "monoinsaturi":
                        candidates += ["monoinsaturi_100g", "mono_100g"]
                    if field == "polinsaturi":
                        candidates += ["polinsaturi_100g", "poli_100g"]
                    if field == "colesterolo":
                        candidates += ["colesterolo_100g", "colesterolo_totale_100g"]
                    if field == "sodio":
                        candidates += ["sodio_100g", "sale_100g", "sodium_100g", "salt_100g"]
                    return _recipe_num(recipe, candidates)
                candidates = [f"{field}_totale", f"{field}_ricetta"]
                if field == "proteine_totali":
                    candidates += ["proteine_totale", "proteine_ricetta"]
                if field == "grassi_totali":
                    candidates += ["grassi_totale", "grassi_ricetta"]
                if field == "fibre":
                    candidates += ["fibre_totale", "fibre_ricetta"]
                if field == "carboidrati_totali":
                    candidates += ["carboidrati_totale", "carboidrati_ricetta", "carbs_totale", "carbs_ricetta"]
                if field == "di_cui_zuccheri":
                    candidates += ["zuccheri_totale", "zuccheri_ricetta", "sugars_totale", "sugars_ricetta"]
                if field == "di_cui_saturi":
                    candidates += ["saturi_totale", "saturi_ricetta", "saturi_tot"]
                if field == "monoinsaturi":
                    candidates += ["monoinsaturi_totale", "monoinsaturi_ricetta", "mono_tot"]
                if field == "polinsaturi":
                    candidates += ["polinsaturi_totale", "polinsaturi_ricetta", "poli_tot"]
                if field == "colesterolo":
                    candidates += [
                        "colesterolo_totale",
                        "colesterolo_ricetta",
                        "colesterolo_totale_totale",
                    ]
                if field == "sodio":
                    candidates += [
                        "sodio_totale",
                        "sodio_ricetta",
                        "sale_totale",
                        "sale_ricetta",
                        "sodium_totale",
                    ]
                return _recipe_num(recipe, candidates)

            def _recipe_cost_per_portion(recipe: Dict[str, Any]) -> Optional[float]:
                return _recipe_num(recipe, ["spesa_per_porzione", "costo_per_porzione", "cost_per_portion"])

            def _recipe_cost_total(recipe: Dict[str, Any]) -> Optional[float]:
                return _recipe_num(
                    recipe,
                    [
                        "spesa_totale_ricetta",
                        "costo_totale_ricetta",
                        "spesa_ricetta",
                        "cost_total",
                    ],
                )

            def _recipe_seasonality(recipe: Dict[str, Any]) -> str:
                return str(recipe.get("stagionalita") or recipe.get("seasonality") or "").strip().lower()

            def _in_range(val: Optional[float], vmin: Optional[float], vmax: Optional[float]) -> bool:
                if val is None:
                    return False
                if vmin is not None and val < vmin:
                    return False
                if vmax is not None and val > vmax:
                    return False
                return True

            diff_norm = _norm(difficulty) if difficulty else ""
            season_norm = _norm(seasonality) if seasonality else ""

            for row in rows:
                try:
                    recipe = json.loads(str(row[4] or "{}"))
                except Exception:
                    continue
                if not isinstance(recipe, dict):
                    continue

                if diff_norm:
                    if _recipe_difficulty(recipe) != diff_norm:
                        continue

                if servings_min is not None or servings_max is not None:
                    servings = _recipe_num(recipe, ["servings", "porzioni", "servings_count"])
                    if not _in_range(servings, servings_min, servings_max):
                        continue

                if prep_min is not None or prep_max is not None:
                    prep = _recipe_time(recipe, "prep")
                    if not _in_range(prep, prep_min, prep_max):
                        continue

                if cook_min is not None or cook_max is not None:
                    cook = _recipe_time(recipe, "cook")
                    if not _in_range(cook, cook_min, cook_max):
                        continue

                if total_min is not None or total_max is not None:
                    total = _recipe_time(recipe, "total")
                    if not _in_range(total, total_min, total_max):
                        continue

                if kcal_100_min is not None or kcal_100_max is not None:
                    kcal100 = _recipe_energy(recipe, "100g")
                    if not _in_range(kcal100, kcal_100_min, kcal_100_max):
                        continue

                if kcal_tot_min is not None or kcal_tot_max is not None:
                    kcaltot = _recipe_energy(recipe, "totale")
                    if not _in_range(kcaltot, kcal_tot_min, kcal_tot_max):
                        continue

                if cost_min is not None or cost_max is not None:
                    cost = _recipe_cost_per_portion(recipe)
                    if not _in_range(cost, cost_min, cost_max):
                        continue

                if cost_total_min is not None or cost_total_max is not None:
                    cost_total = _recipe_cost_total(recipe)
                    if not _in_range(cost_total, cost_total_min, cost_total_max):
                        continue

                if protein_100_min is not None or protein_100_max is not None:
                    proteins = _recipe_nutrient(recipe, "proteine_totali", "100g")
                    if not _in_range(proteins, protein_100_min, protein_100_max):
                        continue

                if fat_100_min is not None or fat_100_max is not None:
                    fats = _recipe_nutrient(recipe, "grassi_totali", "100g")
                    if not _in_range(fats, fat_100_min, fat_100_max):
                        continue

                if fiber_100_min is not None or fiber_100_max is not None:
                    fibre = _recipe_nutrient(recipe, "fibre", "100g")
                    if not _in_range(fibre, fiber_100_min, fiber_100_max):
                        continue

                if carb_100_min is not None or carb_100_max is not None:
                    carbs = _recipe_nutrient(recipe, "carboidrati_totali", "100g")
                    if not _in_range(carbs, carb_100_min, carb_100_max):
                        continue

                if sugar_100_min is not None or sugar_100_max is not None:
                    sugars = _recipe_nutrient(recipe, "di_cui_zuccheri", "100g")
                    if not _in_range(sugars, sugar_100_min, sugar_100_max):
                        continue

                if protein_tot_min is not None or protein_tot_max is not None:
                    proteins_tot = _recipe_nutrient(recipe, "proteine_totali", "totale")
                    if not _in_range(proteins_tot, protein_tot_min, protein_tot_max):
                        continue

                if fat_tot_min is not None or fat_tot_max is not None:
                    fats_tot = _recipe_nutrient(recipe, "grassi_totali", "totale")
                    if not _in_range(fats_tot, fat_tot_min, fat_tot_max):
                        continue

                if fiber_tot_min is not None or fiber_tot_max is not None:
                    fibre_tot = _recipe_nutrient(recipe, "fibre", "totale")
                    if not _in_range(fibre_tot, fiber_tot_min, fiber_tot_max):
                        continue

                if carb_tot_min is not None or carb_tot_max is not None:
                    carbs_tot = _recipe_nutrient(recipe, "carboidrati_totali", "totale")
                    if not _in_range(carbs_tot, carb_tot_min, carb_tot_max):
                        continue

                if sugar_tot_min is not None or sugar_tot_max is not None:
                    sugars_tot = _recipe_nutrient(recipe, "di_cui_zuccheri", "totale")
                    if not _in_range(sugars_tot, sugar_tot_min, sugar_tot_max):
                        continue

                if sat_100_min is not None or sat_100_max is not None:
                    sat100 = _recipe_nutrient(recipe, "di_cui_saturi", "100g")
                    if not _in_range(sat100, sat_100_min, sat_100_max):
                        continue

                if mono_100_min is not None or mono_100_max is not None:
                    mono100 = _recipe_nutrient(recipe, "monoinsaturi", "100g")
                    if not _in_range(mono100, mono_100_min, mono_100_max):
                        continue

                if poly_100_min is not None or poly_100_max is not None:
                    poly100 = _recipe_nutrient(recipe, "polinsaturi", "100g")
                    if not _in_range(poly100, poly_100_min, poly_100_max):
                        continue

                if chol_100_min is not None or chol_100_max is not None:
                    chol100 = _recipe_nutrient(recipe, "colesterolo", "100g")
                    if not _in_range(chol100, chol_100_min, chol_100_max):
                        continue

                if sat_tot_min is not None or sat_tot_max is not None:
                    sattot = _recipe_nutrient(recipe, "di_cui_saturi", "totale")
                    if not _in_range(sattot, sat_tot_min, sat_tot_max):
                        continue

                if mono_tot_min is not None or mono_tot_max is not None:
                    monotot = _recipe_nutrient(recipe, "monoinsaturi", "totale")
                    if not _in_range(monotot, mono_tot_min, mono_tot_max):
                        continue

                if poly_tot_min is not None or poly_tot_max is not None:
                    polytot = _recipe_nutrient(recipe, "polinsaturi", "totale")
                    if not _in_range(polytot, poly_tot_min, poly_tot_max):
                        continue

                if chol_tot_min is not None or chol_tot_max is not None:
                    choltot = _recipe_nutrient(recipe, "colesterolo", "totale")
                    if not _in_range(choltot, chol_tot_min, chol_tot_max):
                        continue

                if sodium_100_min is not None or sodium_100_max is not None:
                    sod100 = _recipe_nutrient(recipe, "sodio", "100g")
                    if not _in_range(sod100, sodium_100_min, sodium_100_max):
                        continue

                if sodium_tot_min is not None or sodium_tot_max is not None:
                    sodtot = _recipe_nutrient(recipe, "sodio", "totale")
                    if not _in_range(sodtot, sodium_tot_min, sodium_tot_max):
                        continue

                if season_norm:
                    season_val = _norm(_recipe_seasonality(recipe))
                    if not season_val or season_norm not in season_val:
                        continue

                out.append(
                    ArchiveItem(
                        id=int(row[0]),
                        title=str(row[1] or ""),
                        category=str(row[2] or ""),
                        updated_at=str(row[3] or ""),
                    )
                )
                if len(out) >= base_limit:
                    break
        return out

    def _row_to_recipe(self, row: Any) -> Recipe | None:
        """Converte riga DB in Recipe, proteggendo contro JSON corrotto."""
        try:
            # Protezione: JSON parsing con fallback
            if isinstance(row["recipe_json"], str):
                try:
                    data = json.loads(row["recipe_json"])
                except json.JSONDecodeError as je:
                    print(f"[ERROR] JSON corrotto per recipe id={row['id']}: {je}")
                    # Ritorna None o crea ricetta minima
                    return None
            else:
                data = row["recipe_json"] or {}

            # ...rest of code...

        except Exception as e:
            print(f"[ERROR] Conversione riga fallita: {e}")
            return None

def _default_db() -> ArchiveDB:
    return ArchiveDB.default()


def save_recipe(recipe: Dict[str, Any]) -> int:
    return _default_db().save_recipe(recipe)


def delete_recipe(ids: Any) -> int:
    if ids is None:
        return 0
    if isinstance(ids, (list, tuple, set)):
        return _default_db().delete_recipes(ids)
    return _default_db().delete_recipes([ids])


def search_recipes(query: str = "", filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    pl = filters if isinstance(filters, dict) else {}
    q = str(query or "")
    category = str(pl.get("category") or "")
    ingredient = str(pl.get("ingredient") or pl.get("ingredient_query") or "")
    difficulty = str(pl.get("difficulty") or "")
    seasonality = str(pl.get("seasonality") or "")

    diets = pl.get("require_diets")
    allergens = pl.get("exclude_allergens")
    limit = int(pl.get("limit") or 200)

    require_diets = [str(x) for x in diets] if isinstance(diets, list) else []
    exclude_allergens = [str(x) for x in allergens] if isinstance(allergens, list) else []

    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    items = _default_db().search(
        query=q,
        category=category,
        ingredient_query=ingredient,
        require_diets=require_diets,
        exclude_allergens=exclude_allergens,
        difficulty=difficulty,
        seasonality=seasonality,
        servings_min=_to_float(pl.get("servings_min")),
        servings_max=_to_float(pl.get("servings_max")),
        prep_min=_to_float(pl.get("prep_min")),
        prep_max=_to_float(pl.get("prep_max")),
        cook_min=_to_float(pl.get("cook_min")),
        cook_max=_to_float(pl.get("cook_max")),
        total_min=_to_float(pl.get("total_min")),
        total_max=_to_float(pl.get("total_max")),
        kcal_100_min=_to_float(pl.get("kcal_100_min")),
        kcal_100_max=_to_float(pl.get("kcal_100_max")),
        kcal_tot_min=_to_float(pl.get("kcal_tot_min")),
        kcal_tot_max=_to_float(pl.get("kcal_tot_max")),
        cost_min=_to_float(pl.get("cost_min")),
        cost_max=_to_float(pl.get("cost_max")),
        protein_100_min=_to_float(pl.get("protein_100_min")),
        protein_100_max=_to_float(pl.get("protein_100_max")),
        fat_100_min=_to_float(pl.get("fat_100_min")),
        fat_100_max=_to_float(pl.get("fat_100_max")),
        fiber_100_min=_to_float(pl.get("fiber_100_min")),
        fiber_100_max=_to_float(pl.get("fiber_100_max")),
        carb_100_min=_to_float(pl.get("carb_100_min")),
        carb_100_max=_to_float(pl.get("carb_100_max")),
        sugar_100_min=_to_float(pl.get("sugar_100_min")),
        sugar_100_max=_to_float(pl.get("sugar_100_max")),
        protein_tot_min=_to_float(pl.get("protein_tot_min")),
        protein_tot_max=_to_float(pl.get("protein_tot_max")),
        fat_tot_min=_to_float(pl.get("fat_tot_min")),
        fat_tot_max=_to_float(pl.get("fat_tot_max")),
        fiber_tot_min=_to_float(pl.get("fiber_tot_min")),
        fiber_tot_max=_to_float(pl.get("fiber_tot_max")),
        carb_tot_min=_to_float(pl.get("carb_tot_min")),
        carb_tot_max=_to_float(pl.get("carb_tot_max")),
        sugar_tot_min=_to_float(pl.get("sugar_tot_min")),
        sugar_tot_max=_to_float(pl.get("sugar_tot_max")),
        sat_100_min=_to_float(pl.get("sat_100_min")),
        sat_100_max=_to_float(pl.get("sat_100_max")),
        mono_100_min=_to_float(pl.get("mono_100_min")),
        mono_100_max=_to_float(pl.get("mono_100_max")),
        poly_100_min=_to_float(pl.get("poly_100_min")),
        poly_100_max=_to_float(pl.get("poly_100_max")),
        chol_100_min=_to_float(pl.get("chol_100_min")),
        chol_100_max=_to_float(pl.get("chol_100_max")),
        sat_tot_min=_to_float(pl.get("sat_tot_min")),
        sat_tot_max=_to_float(pl.get("sat_tot_max")),
        mono_tot_min=_to_float(pl.get("mono_tot_min")),
        mono_tot_max=_to_float(pl.get("mono_tot_max")),
        poly_tot_min=_to_float(pl.get("poly_tot_min")),
        poly_tot_max=_to_float(pl.get("poly_tot_max")),
        chol_tot_min=_to_float(pl.get("chol_tot_min")),
        chol_tot_max=_to_float(pl.get("chol_tot_max")),
        sodium_100_min=_to_float(pl.get("sodium_100_min")),
        sodium_100_max=_to_float(pl.get("sodium_100_max")),
        sodium_tot_min=_to_float(pl.get("sodium_tot_min")),
        sodium_tot_max=_to_float(pl.get("sodium_tot_max")),
        cost_total_min=_to_float(pl.get("cost_total_min")),
        cost_total_max=_to_float(pl.get("cost_total_max")),
        limit=limit,
    )

    return [
        {"id": it.id, "title": it.title, "category": it.category, "updated_at": it.updated_at}
        for it in items
    ]
