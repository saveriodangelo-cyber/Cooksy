# -*- coding: utf-8 -*-
"""
Integration points for Stripe payment system in Bridge.
"""
from typing import Dict, Any, Optional


def inject_stripe_methods(bridge_instance):
    """Inject Stripe-related methods into Bridge instance."""
    
    def create_checkout_session(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea una sessione di checkout Stripe.
        
        Payload:
        - tier: "starter" o "pro"
        - token: session token dell'utente
        """
        try:
            token = str(payload.get("token") or bridge_instance._session_token or "")
            user_id = str(payload.get("user_id") or bridge_instance._current_user_id or "")
            tier = str(payload.get("tier") or "pro").strip().lower()
            
            if not token or user_id == "default_user":
                return {"ok": False, "error": "Utente non autenticato"}
            
            if tier not in ["starter", "pro"]:
                return {"ok": False, "error": "Tier non valido"}
            
            if not bridge_instance._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            # Recupera user per email
            user = bridge_instance._user_mgr.get_user_by_id(user_id)
            if not user:
                return {"ok": False, "error": "Utente non trovato"}
            
            email = user.email
            
            # Crea sessione checkout
            result = bridge_instance._stripe_mgr.create_checkout_session(
                user_id=user_id,
                tier=tier,
                email=email
            )
            
            if result.get("ok"):
                print(f"[stripe] Checkout session created: {result.get('session_id')}")
            
            return result
        except Exception as e:
            print(f"[stripe] Error creating checkout: {e}")
            return {"ok": False, "error": str(e)}
    
    def get_subscription_status(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera lo stato della sottoscrizione Stripe dell'utente."""
        try:
            token = str(payload.get("token") or bridge_instance._session_token or "")
            user_id = str(payload.get("user_id") or bridge_instance._current_user_id or "")
            
            if not token or user_id == "default_user":
                return {"ok": False, "error": "Utente non autenticato"}
            
            if not bridge_instance._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            # Recupera customer ID da subscription
            subscription = bridge_instance._subscription_mgr.get_subscription(user_id)
            if not subscription:
                return {"ok": False, "error": "Nessun abbonamento trovato"}
            
            customer_id = subscription.get("stripe_customer_id")
            if not customer_id:
                return {
                    "ok": True,
                    "tier": subscription.get("tier", "free"),
                    "status": "local_only",
                    "message": "Account locale, nessun Stripe"
                }
            
            result = bridge_instance._stripe_mgr.get_subscription_status(customer_id)
            return result
        except Exception as e:
            print(f"[stripe] Error getting subscription: {e}")
            return {"ok": False, "error": str(e)}
    
    def cancel_subscription(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Annulla la sottoscrizione Stripe."""
        try:
            token = str(payload.get("token") or bridge_instance._session_token or "")
            user_id = str(payload.get("user_id") or bridge_instance._current_user_id or "")
            
            if not token or user_id == "default_user":
                return {"ok": False, "error": "Utente non autenticato"}
            
            if not bridge_instance._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            subscription = bridge_instance._subscription_mgr.get_subscription(user_id)
            if not subscription:
                return {"ok": False, "error": "Nessun abbonamento trovato"}
            
            subscription_id = subscription.get("stripe_subscription_id")
            if not subscription_id:
                return {"ok": False, "error": "Nessuna sottoscrizione Stripe attiva"}
            
            result = bridge_instance._stripe_mgr.cancel_subscription(subscription_id)
            
            if result.get("ok"):
                # Downgrade a free
                bridge_instance._subscription_mgr.downgrade_to_free(user_id)
                print(f"[stripe] Subscription cancelled for {user_id}")
            
            return result
        except Exception as e:
            print(f"[stripe] Error cancelling subscription: {e}")
            return {"ok": False, "error": str(e)}
    
    def get_tier_pricing(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera i prezzi dei tier."""
        try:
            from backend.subscription_tiers import get_all_tiers
            tiers_data = get_all_tiers()
            
            tiers = {
                "free": {
                    "name": tiers_data["free"]["name"],
                    "price": tiers_data["free"]["price_eur"],
                    "currency": "EUR",
                    "recipes_per_month": tiers_data["free"]["recipes_per_month"],
                    "description": f"{tiers_data['free']['recipes_per_month']} ricette/mese",
                    "has_ads": tiers_data["free"]["has_ads"],
                },
                "starter": {
                    "name": tiers_data["starter"]["name"],
                    "price": tiers_data["starter"]["price_eur"],
                    "currency": "EUR",
                    "recipes_per_month": tiers_data["starter"]["recipes_per_month"],
                    "description": f"{tiers_data['starter']['recipes_per_month']} ricette/mese",
                    "has_ads": tiers_data["starter"]["has_ads"],
                    "max_templates": tiers_data["starter"]["max_templates"],
                    "features": ["Pubblicità", "Email support"]
                },
                "pro": {
                    "name": tiers_data["pro"]["name"],
                    "price": tiers_data["pro"]["price_eur"],
                    "currency": "EUR",
                    "recipes_per_month": tiers_data["pro"]["recipes_per_month"],
                    "description": f"{tiers_data['pro']['recipes_per_month']} ricette/mese",
                    "has_ads": tiers_data["pro"]["has_ads"],
                    "max_templates": tiers_data["pro"]["max_templates"],
                    "features": ["Priorità API", "Email support", "Batch processing"]
                }
            }
            return {"ok": True, "tiers": tiers}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def process_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Processa webhook da Stripe (per backend)."""
        try:
            if not bridge_instance._stripe_mgr:
                return {"ok": False, "error": "Stripe non disponibile"}
            
            event_body = payload.get("body")
            sig_header = payload.get("sig_header")
            
            if not event_body or not sig_header:
                return {"ok": False, "error": "Payload incompleto"}
            
            result = bridge_instance._stripe_mgr.process_webhook(event_body, sig_header)
            
            if result.get("ok"):
                event_type = result.get("event")
                
                if event_type == "checkout_completed":
                    # Aggiorna sottoscrizione utente
                    user_id = result.get("user_id")
                    tier = result.get("tier")
                    customer_id = result.get("customer_id")
                    subscription_id = result.get("subscription_id")
                    
                    if user_id and tier:
                        bridge_instance._subscription_mgr.upgrade_subscription(
                            user_id,
                            tier,
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id
                        )
                        print(f"[stripe] User {user_id} upgraded to {tier}")
                
                elif event_type == "payment_failed":
                    print(f"[stripe] Payment failed for customer {result.get('customer_id')}")
                
                elif event_type == "subscription_canceled":
                    print(f"[stripe] Subscription cancelled for {result.get('customer_id')}")
            
            return result
        except Exception as e:
            print(f"[stripe] Error processing webhook: {e}")
            return {"ok": False, "error": str(e)}
    
    # Inject methods
    bridge_instance.create_checkout_session = create_checkout_session
    bridge_instance.get_subscription_status = get_subscription_status
    bridge_instance.cancel_subscription = cancel_subscription
    bridge_instance.get_tier_pricing = get_tier_pricing
    bridge_instance.process_webhook = process_webhook
