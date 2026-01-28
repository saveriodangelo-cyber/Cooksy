# -*- coding: utf-8 -*-
"""
Sistema di tracking API usage e gestione abbonamenti
Monitora ricette elaborate e gestisce quota mensile
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from backend.utils import project_root

DB_PATH = project_root() / "data" / "recipes" / "recipes.db"

# Prezzi in EUR
SUBSCRIPTION_TIER = {
    "free": {
        "name": "Free",
        "monthly_price": 0.0,
        "recipes_per_month": 3,
        "description": "3 ricette AI al mese"
    },
    "pro": {
        "name": "Pro",
        "monthly_price": 9.99,
        "recipes_per_month": 100,
        "description": "100 ricette AI al mese"
    },
    "business": {
        "name": "Business",
        "monthly_price": 29.99,
        "recipes_per_month": 500,
        "description": "500 ricette AI al mese"
    }
}

COST_PER_API_CALL = 0.08  # EUR
OVERAGE_PRICE = 0.99  # EUR per ricetta oltre limite


class SubscriptionManager:
    """Gestisce abbonamenti e quote mensili"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Crea le tabelle se non esistono"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Tabella sottoscrizioni
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                tier TEXT DEFAULT 'free',
                monthly_price REAL,
                recipes_per_month INTEGER,
                valid_from TEXT,
                valid_until TEXT,
                auto_renew BOOLEAN DEFAULT 1,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT
            )
        """)
        
        # Tabella utilizzo mensile
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                month TEXT,
                recipes_used INTEGER DEFAULT 0,
                recipes_paid INTEGER DEFAULT 0,
                overage_cost REAL DEFAULT 0.0,
                api_cost REAL DEFAULT 0.0,
                total_cost REAL DEFAULT 0.0,
                created_at TEXT,
                UNIQUE(user_id, month)
            )
        """)
        
        # Tabella fatture
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                month TEXT,
                subscription_price REAL,
                overage_charges REAL,
                api_costs REAL,
                total REAL,
                status TEXT DEFAULT 'pending',
                stripe_invoice_id TEXT,
                created_at TEXT,
                paid_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_subscription(self, user_id: str, tier: str = "free") -> Dict[str, Any]:
        """Crea una nuova sottoscrizione"""
        if tier not in SUBSCRIPTION_TIER:
            tier = "free"
        
        tier_data = SUBSCRIPTION_TIER[tier]
        now = datetime.utcnow()
        valid_from = now.isoformat()
        valid_until = (now + timedelta(days=30)).isoformat()
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO subscriptions 
                (user_id, tier, monthly_price, recipes_per_month, valid_from, valid_until)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                tier,
                tier_data["monthly_price"],
                tier_data["recipes_per_month"],
                valid_from,
                valid_until
            ))
            
            conn.commit()
            
            return {
                "ok": True,
                "user_id": user_id,
                "tier": tier,
                "tier_data": tier_data,
                "valid_from": valid_from,
                "valid_until": valid_until
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()
    
    def get_subscription(self, user_id: str) -> Dict[str, Any]:
        """Recupera la sottoscrizione di un utente"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tier, monthly_price, recipes_per_month, valid_from, valid_until
            FROM subscriptions
            WHERE user_id = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            # Crea subscription free automatica
            return self.create_subscription(user_id, "free")
        
        tier, price, recipes, valid_from, valid_until = result
        return {
            "user_id": user_id,
            "tier": tier,
            "monthly_price": price,
            "recipes_per_month": recipes,
            "valid_from": valid_from,
            "valid_until": valid_until,
            **SUBSCRIPTION_TIER[tier]
        }
    
    def record_api_call(self, user_id: str) -> Dict[str, Any]:
        """Registra una ricetta AI creata"""
        sub = self.get_subscription(user_id)
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Recupera uso corrente
        cursor.execute("""
            SELECT recipes_used FROM api_usage
            WHERE user_id = ? AND month = ?
        """, (user_id, current_month))
        
        result = cursor.fetchone()
        recipes_used = (result[0] if result else 0) + 1
        recipes_limit = sub["recipes_per_month"]
        
        # Calcola costi
        is_overage = recipes_used > recipes_limit
        overage_qty = max(0, recipes_used - recipes_limit)
        overage_cost = overage_qty * OVERAGE_PRICE
        api_cost = COST_PER_API_CALL
        
        # Aggiorna uso
        cursor.execute("""
            INSERT OR REPLACE INTO api_usage
            (user_id, month, recipes_used, overage_cost, api_cost, total_cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            current_month,
            recipes_used,
            overage_cost,
            api_cost,
            api_cost + (overage_cost if is_overage else 0),
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "ok": True,
            "user_id": user_id,
            "month": current_month,
            "recipes_used": recipes_used,
            "recipes_limit": recipes_limit,
            "is_overage": is_overage,
            "overage_cost": overage_cost,
            "can_use_ai": recipes_used <= recipes_limit or sub["tier"] != "free"
        }
    
    def check_quota(self, user_id: str) -> Dict[str, Any]:
        """Verifica quota disponibile per l'utente"""
        sub = self.get_subscription(user_id)
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT recipes_used FROM api_usage
            WHERE user_id = ? AND month = ?
        """, (user_id, current_month))
        
        result = cursor.fetchone()
        recipes_used = result[0] if result else 0
        recipes_limit = int(sub.get("recipes_per_month", 3))
        
        conn.close()
        
        remaining = max(0, recipes_limit - recipes_used)
        
        return {
            "user_id": user_id,
            "tier": sub.get("tier", "free"),
            "month": current_month,
            "recipes_used": recipes_used,
            "recipes_limit": recipes_limit,
            "remaining": remaining,
            "percentage_used": (recipes_used / recipes_limit * 100) if recipes_limit > 0 else 0,
            "can_use": remaining > 0 or sub.get("tier", "free") != "free"
        }
    
    def get_monthly_summary(self, user_id: str, month: Optional[str] = None) -> Dict[str, Any]:
        """Recupera il riepilogo mensile"""
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")
        
        sub = self.get_subscription(user_id)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT recipes_used, overage_cost, api_cost, total_cost
            FROM api_usage
            WHERE user_id = ? AND month = ?
        """, (user_id, month))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            recipes, overage, api_cost, total = result
        else:
            recipes, overage, api_cost, total = 0, 0, 0, 0
        
        subscription_cost = sub["monthly_price"]
        
        return {
            "user_id": user_id,
            "month": month,
            "tier": sub["tier"],
            "subscription_cost": subscription_cost,
            "recipes_used": recipes,
            "recipes_limit": sub["recipes_per_month"],
            "api_cost": api_cost,
            "overage_charges": overage,
            "total_cost": subscription_cost + api_cost + overage
        }
    
    def generate_invoice(self, user_id: str, month: Optional[str] = None) -> Dict[str, Any]:
        """Genera fattura per il mese"""
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")
        
        summary = self.get_monthly_summary(user_id, month)
        
        invoice_id = f"INV-{user_id}-{month}"
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO invoices
            (id, user_id, month, subscription_price, overage_charges, api_costs, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            user_id,
            month,
            summary["subscription_cost"],
            summary["overage_charges"],
            summary["api_cost"],
            summary["total_cost"],
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "ok": True,
            "invoice_id": invoice_id,
            **summary
        }
    
    def upgrade_tier(self, user_id: str, new_tier: str) -> Dict[str, Any]:
        """Upgrade abbonamento utente"""
        if new_tier not in SUBSCRIPTION_TIER:
            return {"ok": False, "error": "Tier non valido"}
        
        return self.create_subscription(user_id, new_tier)
    
    def upgrade_subscription(
        self, user_id: str, tier: str,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Aggiorna sottoscrizione con dati Stripe"""
        if tier not in SUBSCRIPTION_TIER:
            return {"ok": False, "error": "Tier non valido"}
        
        tier_data = SUBSCRIPTION_TIER[tier]
        now = datetime.utcnow()
        valid_from = now.isoformat()
        valid_until = (now + timedelta(days=30)).isoformat()
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO subscriptions 
                (user_id, tier, monthly_price, recipes_per_month, valid_from, valid_until, 
                 stripe_customer_id, stripe_subscription_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                tier,
                tier_data["monthly_price"],
                tier_data["recipes_per_month"],
                valid_from,
                valid_until,
                stripe_customer_id,
                stripe_subscription_id
            ))
            
            conn.commit()
            print(f"[subscription] User {user_id} upgraded to {tier} with Stripe")
            
            return {
                "ok": True,
                "user_id": user_id,
                "tier": tier,
                "stripe_customer_id": stripe_customer_id,
                "stripe_subscription_id": stripe_subscription_id
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()
    
    def check_daily_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica il limite giornaliero di ricette per l'utente.
        Usa i limiti dalla subscription_tiers.py se disponibili.
        """
        sub = self.get_subscription(user_id)
        tier = sub.get("tier", "free")
        today = datetime.utcnow().date().isoformat()
        
        # Importa limiti giornalieri dai subscription_tiers
        try:
            from subscription_tiers import TIER_FEATURES, SubscriptionTier
            tier_enum = SubscriptionTier[tier.upper()]
            tier_features = TIER_FEATURES[tier_enum]
            daily_limit = tier_features.recipes_per_day
        except (ImportError, KeyError, AttributeError):
            # Fallback: nessun limite se modulo non disponibile
            daily_limit = 999
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Conta ricette elaborate oggi (assumendo esista campo 'date' in api_usage)
        cursor.execute("""
            SELECT COUNT(*) FROM api_usage
            WHERE user_id = ? AND date(created_at) = ?
        """, (user_id, today))
        
        result = cursor.fetchone()
        recipes_today = result[0] if result else 0
        conn.close()
        
        remaining = max(0, daily_limit - recipes_today)
        exceeded = recipes_today >= daily_limit
        
        return {
            "ok": True,
            "user_id": user_id,
            "tier": tier,
            "date": today,
            "daily_limit": daily_limit,
            "recipes_today": recipes_today,
            "remaining": remaining,
            "exceeded": exceeded,
            "can_analyze": remaining > 0 or tier != "free",
        }
    
    def check_daily_ai_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica il limite giornaliero di chiamate API AI.
        Consulta ai_costs.py per il tracking dettagliato.
        """
        sub = self.get_subscription(user_id)
        tier = sub.get("tier", "free")
        today = datetime.utcnow().date().isoformat()
        
        # Importa limiti giornalieri AI
        try:
            from ai_costs import AICostsManager, DAILY_SPENDING_LIMITS
            ai_mgr = AICostsManager()
            daily_limit_eur = DAILY_SPENDING_LIMITS.get(tier, 0.0)
            daily_check = ai_mgr.check_daily_limit(user_id, tier)
            
            return {
                "ok": True,
                "user_id": user_id,
                "tier": tier,
                "date": today,
                "daily_limit_eur": daily_limit_eur,
                "spent_eur": daily_check.get("spent", 0.0),
                "remaining_eur": daily_check.get("remaining", 0.0),
                "exceeded": daily_check.get("exceeded", False),
                "can_use_ai": not daily_check.get("exceeded", False),
            }
        except ImportError:
            return {
                "ok": False,
                "error": "AI costs manager non disponibile"
            }
    
    def check_monthly_ai_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica il limite mensile di chiamate API AI.
        Consulta ai_costs.py per il tracking dettagliato.
        """
        sub = self.get_subscription(user_id)
        tier = sub.get("tier", "free")
        month = datetime.utcnow().strftime('%Y-%m')
        
        # Importa limiti mensili AI
        try:
            from ai_costs import AICostsManager, MONTHLY_SPENDING_LIMITS
            ai_mgr = AICostsManager()
            monthly_limit_eur = MONTHLY_SPENDING_LIMITS.get(tier, 0.0)
            monthly_check = ai_mgr.check_monthly_limit(user_id, tier)
            
            return {
                "ok": True,
                "user_id": user_id,
                "tier": tier,
                "month": month,
                "monthly_limit_eur": monthly_limit_eur,
                "spent_eur": monthly_check.get("spent", 0.0),
                "remaining_eur": monthly_check.get("remaining", 0.0),
                "exceeded": monthly_check.get("exceeded", False),
                "can_use_ai": not monthly_check.get("exceeded", False),
            }
        except ImportError:
            return {
                "ok": False,
                "error": "AI costs manager non disponibile"
            }
    
    def downgrade_to_free(self, user_id: str) -> Dict[str, Any]:
        """Downgrade a piano free (cancellazione sottoscrizione)"""
        return self.create_subscription(user_id, "free")


if __name__ == "__main__":
    manager = SubscriptionManager()
    
    # Test
    print("=" * 60)
    print("SUBSCRIPTION MANAGER - TEST")
    print("=" * 60)
    
    # Crea sottoscrizione
    user_id = "test_user_001"
    result = manager.create_subscription(user_id, "pro")
    print(f"\n✓ Sottoscrizione creata: {result['tier']}")
    
    # Registra utilizzo
    for i in range(5):
        result = manager.record_api_call(user_id)
        quota = manager.check_quota(user_id)
        print(f"  Ricetta {i+1}: {quota['remaining']} rimaste")
    
    # Riepilogo
    summary = manager.get_monthly_summary(user_id)
    print(f"\n📊 Riepilogo mese: {summary['month']}")
    print(f"  Tier: {summary['tier']}")
    print(f"  Ricette usate: {summary['recipes_used']}/{summary['recipes_limit']}")
    print(f"  Costo sottoscrizione: €{summary['subscription_cost']:.2f}")
    print(f"  Costo API: €{summary['api_cost']:.2f}")
    print(f"  Totale: €{summary['total_cost']:.2f}")
    
    # Fattura
    invoice = manager.generate_invoice(user_id)
    print(f"\n📄 Fattura generata: {invoice['invoice_id']}")
