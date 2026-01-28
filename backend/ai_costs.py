# -*- coding: utf-8 -*-
"""
Gestione costi API AI
Traccia e limita l'utilizzo delle API AI per controllare i costi
"""
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import json
from typing import Dict, Any, Optional

from backend.utils import project_root

DB_PATH = project_root() / "data" / "recipes" / "recipes.db"

# Costi per provider (in EUR)
AI_COSTS = {
    "openai": {
        "gpt-3.5": 0.002,      # €0.002 per ricetta
        "gpt-4": 0.015,        # €0.015 per ricetta
        "gpt-4-turbo": 0.010,  # €0.010 per ricetta
    },
    "gemini": {
        "free": 0.0,           # Gratuito
        "basic": 0.0005,       # €0.0005 per ricetta
        "pro": 0.001,          # €0.001 per ricetta
    },
    "ollama": {
        "local": 0.0,          # Gratuito (locale)
    },
    "claude": {
        "claude-3-haiku": 0.005,
        "claude-3-sonnet": 0.010,
        "claude-3-opus": 0.020,
    }
}

# Limiti giornalieri per tier (EUR)
DAILY_SPENDING_LIMITS = {
    "free": 0.0,                 # No AI per free tier
    "starter": 1.0,              # €1/giorno
    "pro": 10.0,                 # €10/giorno  
    "business": None,            # Unlimited
}

# Limiti mensili per tier (EUR)
MONTHLY_SPENDING_LIMITS = {
    "free": 0.0,
    "starter": 20.0,             # €20/mese
    "pro": 100.0,                # €100/mese
    "business": None,
}

# Fallback quando quota superata
FALLBACK_AI_PROVIDERS = {
    "free": "ollama",            # Usa local Ollama
    "starter": "gemini",         # Usa Gemini free
    "pro": "openai",             # Usa OpenAI
}


class AICostsManager:
    """Gestisce i costi e i limiti di utilizzo delle API AI"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Crea le tabelle se non esistono"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Tabella api_calls - traccia ogni chiamata API
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                date DATE,
                hour TIME,
                provider TEXT,  -- openai, gemini, ollama, claude
                model TEXT,
                recipe_id TEXT,
                cost_eur REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                completion_time_s REAL,
                status TEXT DEFAULT 'success',  -- success, error, skipped
                error_msg TEXT,
                created_at TEXT,
                UNIQUE(user_id, date, hour, recipe_id, provider)
            )
        """)
        
        # Tabella daily_spending - totali giornalieri
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_daily_spending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                date DATE,
                provider TEXT,
                calls_count INTEGER DEFAULT 0,
                total_cost_eur REAL DEFAULT 0.0,
                quota_exceeded BOOLEAN DEFAULT 0,
                PRIMARY KEY (user_id, date, provider)
            )
        """)
        
        # Tabella monthly_spending - totali mensili
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_monthly_spending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                month TEXT,  -- YYYY-MM
                tier TEXT,
                provider TEXT,
                calls_count INTEGER DEFAULT 0,
                total_cost_eur REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, month, provider)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def record_api_call(
        self,
        user_id: str,
        provider: str,
        model: str,
        recipe_id: Optional[str] = None,
        cost_eur: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        completion_time_s: float = 0.0,
        status: str = "success",
        error_msg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registra una chiamata API AI"""
        try:
            now = datetime.utcnow()
            today = now.date().isoformat()
            hour = now.time().isoformat(timespec='hours')
            month = now.strftime('%Y-%m')
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Registra la singola chiamata
            cursor.execute("""
                INSERT INTO ai_api_calls
                (user_id, date, hour, provider, model, recipe_id, cost_eur,
                 input_tokens, output_tokens, completion_time_s, status, error_msg, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, today, hour, provider, model, recipe_id,
                cost_eur, input_tokens, output_tokens, completion_time_s,
                status, error_msg, now.isoformat()
            ))
            
            # Aggiorna totali giornalieri
            cursor.execute("""
                INSERT OR REPLACE INTO ai_daily_spending
                (user_id, date, provider, calls_count, total_cost_eur)
                VALUES (?,?,?,
                    (SELECT COALESCE(calls_count,0) + 1 FROM ai_daily_spending
                     WHERE user_id=? AND date=? AND provider=?),
                    (SELECT COALESCE(total_cost_eur,0) + ? FROM ai_daily_spending
                     WHERE user_id=? AND date=? AND provider=?)
                )
            """, (user_id, today, provider, user_id, today, provider, cost_eur, user_id, today, provider))
            
            # Aggiorna totali mensili
            cursor.execute("""
                INSERT OR REPLACE INTO ai_monthly_spending
                (user_id, month, tier, provider, calls_count, total_cost_eur)
                VALUES (?,?,?,?,
                    (SELECT COALESCE(calls_count,0) + 1 FROM ai_monthly_spending
                     WHERE user_id=? AND month=? AND provider=?),
                    (SELECT COALESCE(total_cost_eur,0) + ? FROM ai_monthly_spending
                     WHERE user_id=? AND month=? AND provider=?)
                )
            """, (user_id, month, None, provider, user_id, month, provider, cost_eur, user_id, month, provider))
            
            conn.commit()
            conn.close()
            
            return {
                "ok": True,
                "call_id": cursor.lastrowid,
                "cost_eur": cost_eur,
                "date": today,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def check_daily_limit(self, user_id: str, tier: str) -> Dict[str, Any]:
        """Verifica se l'utente ha superato il limite giornaliero"""
        try:
            today = datetime.utcnow().date().isoformat()
            limit = DAILY_SPENDING_LIMITS.get(tier, 0.0)
            
            if limit is None:  # Unlimited
                return {"ok": True, "exceeded": False, "remaining": None}
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COALESCE(SUM(total_cost_eur), 0) FROM ai_daily_spending
                WHERE user_id = ? AND date = ?
            """, (user_id, today))
            
            spent = cursor.fetchone()[0]
            conn.close()
            
            exceeded = spent >= limit
            remaining = max(0, limit - spent)
            
            return {
                "ok": True,
                "exceeded": exceeded,
                "spent": spent,
                "limit": limit,
                "remaining": remaining if not exceeded else 0.0,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def check_monthly_limit(self, user_id: str, tier: str) -> Dict[str, Any]:
        """Verifica se l'utente ha superato il limite mensile"""
        try:
            month = datetime.utcnow().strftime('%Y-%m')
            limit = MONTHLY_SPENDING_LIMITS.get(tier, 0.0)
            
            if limit is None:  # Unlimited
                return {"ok": True, "exceeded": False, "remaining": None}
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COALESCE(SUM(total_cost_eur), 0) FROM ai_monthly_spending
                WHERE user_id = ? AND month = ?
            """, (user_id, month))
            
            spent = cursor.fetchone()[0]
            conn.close()
            
            exceeded = spent >= limit
            remaining = max(0, limit - spent)
            
            return {
                "ok": True,
                "exceeded": exceeded,
                "spent": spent,
                "limit": limit,
                "remaining": remaining if not exceeded else 0.0,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_daily_summary(self, user_id: str) -> Dict[str, Any]:
        """Ottiene il riepilogo dell'utilizzo odierno"""
        try:
            today = datetime.utcnow().date().isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT provider, calls_count, total_cost_eur FROM ai_daily_spending
                WHERE user_id = ? AND date = ?
                ORDER BY total_cost_eur DESC
            """, (user_id, today))
            
            calls = cursor.fetchall()
            conn.close()
            
            summary = {
                "ok": True,
                "date": today,
                "by_provider": [
                    {
                        "provider": call[0],
                        "calls": call[1],
                        "cost_eur": round(call[2], 4),
                    } for call in calls
                ],
                "total_calls": sum(c[1] for c in calls),
                "total_cost": round(sum(c[2] for c in calls), 4),
            }
            
            return summary
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_monthly_summary(self, user_id: str) -> Dict[str, Any]:
        """Ottiene il riepilogo dell'utilizzo mensile"""
        try:
            month = datetime.utcnow().strftime('%Y-%m')
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT provider, calls_count, total_cost_eur FROM ai_monthly_spending
                WHERE user_id = ? AND month = ?
                ORDER BY total_cost_eur DESC
            """, (user_id, month))
            
            calls = cursor.fetchall()
            conn.close()
            
            summary = {
                "ok": True,
                "month": month,
                "by_provider": [
                    {
                        "provider": call[0],
                        "calls": call[1],
                        "cost_eur": round(call[2], 4),
                    } for call in calls
                ],
                "total_calls": sum(c[1] for c in calls),
                "total_cost": round(sum(c[2] for c in calls), 4),
            }
            
            return summary
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_fallback_provider(self, tier: str) -> str:
        """Ottiene il provider fallback quando quota superata"""
        return FALLBACK_AI_PROVIDERS.get(tier, "ollama")
    
    def get_ai_cost(self, provider: str, model: str) -> float:
        """Ottiene il costo per una singola ricetta"""
        try:
            return AI_COSTS.get(provider, {}).get(model, 0.0)
        except Exception:
            return 0.0


if __name__ == "__main__":
    manager = AICostsManager()
    
    # Test
    print("=" * 60)
    print("AI COSTS MANAGER - TEST")
    print("=" * 60)
    
    user_id = "test_user_001"
    
    # Registra alcune chiamate
    for i in range(3):
        result = manager.record_api_call(
            user_id=user_id,
            provider="openai",
            model="gpt-3.5",
            recipe_id=f"recipe_{i}",
            cost_eur=0.002,
            input_tokens=500,
            output_tokens=300,
            completion_time_s=1.2,
        )
        print(f"Call {i+1}: {result}")
    
    # Verifica limiti
    daily = manager.check_daily_limit(user_id, "starter")
    print(f"\n📊 Daily limit (Starter): {daily}")
    
    monthly = manager.check_monthly_limit(user_id, "pro")
    print(f"📊 Monthly limit (Pro): {monthly}")
    
    # Riepilogo
    daily_summary = manager.get_daily_summary(user_id)
    print(f"\n📈 Daily summary: {daily_summary}")
