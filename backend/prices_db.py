from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"[^\w\s']", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

@dataclass(frozen=True)
class PriceEntry:
    ingredient: str
    purchase_qty: float
    purchase_unit: str
    price_per_unit: float
    source: str = ""

_UNIT_ALIASES = {
    "kg": "kg", "kilogrammi": "kg",
    "g": "g", "gr": "g", "grammi": "g",
    "l": "l", "lt": "l", "litri": "l",
    "ml": "ml", "cc": "ml",
    "pz": "pz", "pz.": "pz", "pezzi": "pz", "uova": "pz", "uovo": "pz", "baccello": "pz",
    "ud": "pz", "unita": "pz", "unità": "pz", "unit": "pz"
}

def _parse_qty_unit(s: str) -> Tuple[Optional[float], Optional[str]]:
    s = s.strip()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z\.]+)", s)
    if not m: return None, None
    qty = float(m.group(1).replace(",", "."))
    unit_raw = m.group(2).lower().strip(".")
    unit = _UNIT_ALIASES.get(unit_raw, unit_raw)
    return qty, unit

def _to_purchase_units(qty: float, unit: str, purchase_unit: str) -> Optional[float]:
    unit = unit.lower()
    purchase_unit = purchase_unit.lower()
    if unit == purchase_unit: return qty
    # g -> kg
    if unit == "g" and purchase_unit == "kg": return qty / 1000.0
    if unit == "kg" and purchase_unit == "g": return qty * 1000.0
    # ml -> l
    if unit == "ml" and purchase_unit == "l": return qty / 1000.0
    if unit == "l" and purchase_unit == "ml": return qty * 1000.0
    return None

class PricesDB:
    def __init__(self, entries: List[PriceEntry]) -> None:
        self.entries = entries
        self._by_norm: Dict[str, PriceEntry] = {_norm(e.ingredient): e for e in entries}

    @staticmethod
    def load(path: Path) -> "PricesDB":
        if not path.exists(): return PricesDB([])
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            data = json.loads(raw)
            entries = []
            if isinstance(data, list):
                for obj in data:
                    entries.append(PriceEntry(
                        ingredient=str(obj["ingredient"]),
                        purchase_qty=float(obj.get("purchase_qty",0)),
                        purchase_unit=str(obj.get("purchase_unit","")),
                        price_per_unit=float(obj.get("price_per_unit",0)),
                        source=str(obj.get("source", ""))
                    ))
                return PricesDB(entries)
        except: pass
        return PricesDB([])

    def find(self, ingredient_name: str) -> Tuple[Optional[PriceEntry], float, Optional[str]]:
        key = _norm(ingredient_name)
        
        # 1. Match Esatto
        if key in self._by_norm:
            return self._by_norm[key], 1.0, key

        # 2. Fuzzy Match (difflib) - per errori di battitura
        keys = list(self._by_norm.keys())
        matches = get_close_matches(key, keys, n=1, cutoff=0.8)
        if matches:
            mk = matches[0]
            return self._by_norm[mk], 0.9, mk

        # 3. SMART SUBSTRING MATCH (Il segreto!)
        # Se cerco "farina", trova "farina 00". Se cerco "zucchero", trova "zucchero semolato"
        # Cerchiamo la chiave nel DB che contiene la nostra parola (o viceversa)
        best_match = None
        best_len = 999
        
        for k_db in keys:
            # Caso A: DB contiene la ricerca (es. DB="Farina 00", Input="Farina") -> OK
            if key in k_db:
                # Preferiamo la stringa più corta che contiene la parola (es. meglio "Farina 00" di "Farina di mais tostato")
                if len(k_db) < best_len:
                    best_match = k_db
                    best_len = len(k_db)
            
            # Caso B: Input contiene DB (es. Input="Farina Barilla", DB="Farina") -> OK
            elif k_db in key:
                 if len(k_db) < best_len: # Qui è euristica, ma va bene
                    best_match = k_db
                    best_len = len(k_db)
        
        if best_match:
            return self._by_norm[best_match], 0.75, best_match

        return None, 0.0, None

    def cost_for_quantity(self, ingredient_name: str, qty: float, unit: str) -> Dict[str, Any]:
        entry, conf, mk = self.find(ingredient_name)
        if not entry:
            return {"ok": False, "reason": "not_found", "ingredient": ingredient_name}
        
        pu_qty = _to_purchase_units(float(qty), str(unit), entry.purchase_unit)
        if pu_qty is None:
             return {"ok": False, "reason": "unit_mismatch", "ingredient": ingredient_name}

        cost = pu_qty * entry.price_per_unit
        return {
            "ok": True,
            "ingredient": ingredient_name,
            "matched_ingredient": entry.ingredient,
            "cost_eur": cost,
            "price_per_unit_eur": entry.price_per_unit,
            "price_unit": entry.purchase_unit,
            "source": entry.source
        }
