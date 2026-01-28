from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from difflib import get_close_matches

def _norm_name(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"[^\w\s']", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

@dataclass(frozen=True)
class NutritionItem:
    name: str
    kcal: float
    carbs_g: float
    sugars_g: float
    fats_g: float
    saturates_g: float
    proteins_g: float
    fiber_g: float
    salt_g: float

class NutritionDB:
    def __init__(self, items: List[NutritionItem]) -> None:
        self.items = items
        self._by_norm: Dict[str, NutritionItem] = {_norm_name(it.name): it for it in items}

    @staticmethod
    def load(path: Path) -> "NutritionDB":
        if not path.exists(): return NutritionDB([])
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
            data = json.loads(raw)
            items = []
            for obj in data:
                items.append(NutritionItem(
                    name=str(obj["name"]),
                    kcal=float(obj.get("kcal") or 0),
                    carbs_g=float(obj.get("carbs_g") or 0),
                    sugars_g=float(obj.get("sugars_g") or 0),
                    fats_g=float(obj.get("fats_g") or 0),
                    saturates_g=float(obj.get("saturates_g") or 0),
                    proteins_g=float(obj.get("proteins_g") or 0),
                    fiber_g=float(obj.get("fiber_g") or 0),
                    salt_g=float(obj.get("salt_g") or 0),
                ))
            return NutritionDB(items)
        except: return NutritionDB([])

    def find(self, name: str) -> Tuple[Optional[NutritionItem], float, Optional[str]]:
        key = _norm_name(name)
        
        # 1. Match Esatto
        if key in self._by_norm:
            return self._by_norm[key], 1.0, key

        keys = list(self._by_norm.keys())
        
        # 2. Fuzzy Match
        matches = get_close_matches(key, keys, n=1, cutoff=0.8)
        if matches:
            mk = matches[0]
            return self._by_norm[mk], 0.9, mk
            
        # 3. SMART SUBSTRING MATCH
        # Se cerco "farina", trova "farina 00"
        best_match = None
        best_len = 999
        
        for k_db in keys:
            if key in k_db: # DB contiene Input
                if len(k_db) < best_len:
                    best_match = k_db
                    best_len = len(k_db)
            elif k_db in key: # Input contiene DB
                 if len(k_db) < best_len:
                    best_match = k_db
                    best_len = len(k_db)
        
        if best_match:
            return self._by_norm[best_match], 0.75, best_match

        return None, 0.0, None

    def nutrients_for_quantity_g(self, name: str, qty_g: float) -> Dict[str, Any]:
        item, conf, matched = self.find(name)
        if not item:
            return {"ok": False, "name": name}

        factor = float(qty_g) / 100.0
        return {
            "ok": True,
            "name": name,
            "matched_name": item.name,
            "qty_g": qty_g,
            "kcal": item.kcal * factor,
            "carbs_g": item.carbs_g * factor,
            "sugars_g": item.sugars_g * factor,
            "fats_g": item.fats_g * factor,
            "saturates_g": item.saturates_g * factor,
            "proteins_g": item.proteins_g * factor,
            "fiber_g": item.fiber_g * factor,
            "salt_g": item.salt_g * factor,
        }