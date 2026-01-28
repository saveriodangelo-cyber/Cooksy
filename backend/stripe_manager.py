# -*- coding: utf-8 -*-
"""
Integrazione Stripe per pagamenti ricorrenti
Gestisce checkout, webhook e gestione sottoscrizioni
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from backend.utils import project_root

# Installa con: pip install stripe
try:
    import stripe as _stripe  # type: ignore
    stripe: Any = _stripe
except ImportError:
    stripe = None  # type: ignore[assignment]

# Chiavi Stripe (da variabili d'ambiente - richieste in produzione)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# Prezzi Stripe (Product IDs)
STRIPE_PRICES = {
    "free": None,  # No stripe price for free
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "business": os.getenv("STRIPE_PRICE_BUSINESS", ""),
}

CONFIG_PATH = project_root() / "data" / "config" / "stripe_config.json"


def _ensure_config():
    """Crea il file di configurazione se non esiste"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        config = {
            "stripe_secret_key": "${STRIPE_SECRET_KEY}",
            "stripe_publishable_key": "${STRIPE_PUBLISHABLE_KEY}",
            "stripe_price_starter": "${STRIPE_PRICE_STARTER}",
            "stripe_price_pro": "${STRIPE_PRICE_PRO}",
            "stripe_price_business": "${STRIPE_PRICE_BUSINESS}",
            "webhook_secret": "${STRIPE_WEBHOOK_SECRET}",
            "success_url": "http://localhost:8080/?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": "http://localhost:8080/subscription"
        }
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding='utf-8')


class StripeManager:
    """Gestisce pagamenti Stripe"""
    
    def __init__(self):
        _ensure_config()
        
        if not stripe:
            raise ImportError("stripe non installato. Esegui: pip install stripe")
        
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config_raw = json.load(f)
        
        # Sostituisci placeholders ${VAR} con variabili d'ambiente
        self.config = {}
        for key, value in config_raw.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]  # Estrai VAR da ${VAR}
                self.config[key] = os.getenv(env_var, "")
            else:
                self.config[key] = value
        
        stripe.api_key = self.config["stripe_secret_key"]
    
    def create_checkout_session(
        self,
        user_id: str,
        tier: str,
        email: str
    ) -> Dict[str, Any]:
        """Crea una sessione checkout Stripe"""
        
        # Get price from config first, then fallback to STRIPE_PRICES
        price_id = None
        if tier == "starter":
            price_id = self.config.get("stripe_price_starter") or STRIPE_PRICES.get("starter")
        elif tier == "pro":
            price_id = self.config.get("stripe_price_pro") or STRIPE_PRICES.get("pro")
        elif tier == "business":
            price_id = self.config.get("stripe_price_business") or STRIPE_PRICES.get("business")
        
        if not price_id:
            return {"ok": False, "error": f"Tier {tier} non disponibile o price_id mancante"}
        
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=self.config["success_url"],
                cancel_url=self.config["cancel_url"],
                customer_email=email,
                metadata={
                    "user_id": user_id,
                    "tier": tier
                }
            )
            
            return {
                "ok": True,
                "session_id": session.id,
                "checkout_url": session.url,
                "client_secret": session.client_secret
            }
        except stripe.error.CardError as e:
            return {"ok": False, "error": f"Errore carta: {e.user_message}"}
        except stripe.error.RateLimitError:
            return {"ok": False, "error": "Troppi tentativi, riprova"}
        except stripe.error.InvalidRequestError as e:
            return {"ok": False, "error": f"Errore richiesta: {e}"}
        except stripe.error.AuthenticationError:
            return {"ok": False, "error": "Errore autenticazione Stripe"}
        except stripe.error.APIConnectionError:
            return {"ok": False, "error": "Errore connessione Stripe"}
        except stripe.error.StripeError as e:
            return {"ok": False, "error": f"Errore Stripe: {str(e)}"}
    
    def get_subscription_status(self, customer_id: str) -> Dict[str, Any]:
        """Recupera lo stato della sottoscrizione"""
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                limit=1
            )
            
            if not subscriptions or not subscriptions.data:
                return {"ok": False, "error": "Nessuna sottoscrizione trovata"}
            
            sub = subscriptions.data[0]
            
            return {
                "ok": True,
                "subscription_id": sub.id,
                "status": sub.status,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "price_id": sub.items.data[0].price.id if sub.items.data else None
            }
        except stripe.error.StripeError as e:
            return {"ok": False, "error": str(e)}
    
    def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Annulla una sottoscrizione"""
        try:
            sub = stripe.Subscription.delete(subscription_id)
            return {
                "ok": True,
                "subscription_id": sub.id,
                "status": sub.status
            }
        except stripe.error.StripeError as e:
            return {"ok": False, "error": str(e)}
    
    def process_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Processa webhook da Stripe"""
        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                self.config["webhook_secret"]
            )
        except ValueError:
            return {"ok": False, "error": "Payload non valido"}
        except stripe.error.SignatureVerificationError:
            return {"ok": False, "error": "Firma webhook non valida"}
        
        event_type = event["type"]
        
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            return {
                "ok": True,
                "event": "checkout_completed",
                "user_id": session["metadata"].get("user_id"),
                "tier": session["metadata"].get("tier"),
                "customer_id": session["customer"],
                "subscription_id": session.get("subscription")
            }
        
        elif event_type == "invoice.payment_succeeded":
            invoice = event["data"]["object"]
            return {
                "ok": True,
                "event": "payment_succeeded",
                "customer_id": invoice["customer"],
                "amount": invoice["amount_paid"],
                "currency": invoice["currency"]
            }
        
        elif event_type == "invoice.payment_failed":
            invoice = event["data"]["object"]
            return {
                "ok": True,
                "event": "payment_failed",
                "customer_id": invoice["customer"],
                "error": invoice.get("last_finalization_error", {}).get("message")
            }
        
        elif event_type == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            return {
                "ok": True,
                "event": "subscription_canceled",
                "customer_id": subscription["customer"],
                "subscription_id": subscription["id"]
            }
        
        return {"ok": True, "event": event_type}
    
    def get_publishable_key(self) -> str:
        """Restituisce la chiave pubblica Stripe per il frontend"""
        return self.config["stripe_publishable_key"]


if __name__ == "__main__":
    print("=" * 60)
    print("STRIPE MANAGER - SETUP")
    print("=" * 60)
    
    print("\n[INFO] Configurazione Stripe salvata in:")
    print(f"  {CONFIG_PATH}")
    
    print("\n[INFO] Per abilitare i pagamenti reali:")
    print("  1. Registrati su stripe.com")
    print("  2. Copia le chiavi da dashboard.stripe.com")
    print("  3. Imposta le variabili d'ambiente:")
    print("     - STRIPE_SECRET_KEY")
    print("     - STRIPE_PUBLISHABLE_KEY")
    print("     - STRIPE_WEBHOOK_SECRET")
    print("     - STRIPE_PRICE_PRO")
    print("     - STRIPE_PRICE_BUSINESS")
    
    print("\n[INFO] Per il testing locale:")
    print("  - Usa le chiavi di test di Stripe")
    print("  - Numero carta test: 4242 4242 4242 4242")
    print("  - Scadenza: 12/34")
    print("  - CVC: 123")
