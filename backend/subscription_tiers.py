#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Subscription Tier Management
Definisce i 2 livelli di abbonamento e i loro limiti
"""
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional


class SubscriptionTier(Enum):
    """Tier disponibili"""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


@dataclass
class TierFeatures:
    """Definizione completa di un tier"""
    tier_id: str
    name: str
    price_eur: float
    billing_period: str  # "month", "year"
    
    # Limiti di utilizzo (GIORNALIERI E MENSILI)
    recipes_per_day: int      # Limite giornaliero
    recipes_per_month: int    # Limite mensile
    storage_gb: int
    max_concurrent_api_calls: int
    
    # Limiti AI
    ai_requests_per_day: int  # Limit API calls giornaliero
    ai_model_priority: str    # "free", "standard", "priority"
    
    # Features
    max_templates: int  # -1 = unlimited
    has_ads: bool
    support_level: str  # "community", "email", "priority"
    custom_templates: bool
    batch_processing: bool
    
    # Export
    export_formats: List[str]  # ["pdf", "docx"]
    
    def to_dict(self) -> Dict:
        """Converte a dizionario"""
        return {
            "tier_id": self.tier_id,
            "name": self.name,
            "price_eur": self.price_eur,
            "billing_period": self.billing_period,
            "recipes_per_day": self.recipes_per_day,
            "recipes_per_month": self.recipes_per_month,
            "storage_gb": self.storage_gb,
            "max_concurrent_api_calls": self.max_concurrent_api_calls,
            "ai_requests_per_day": self.ai_requests_per_day,
            "ai_model_priority": self.ai_model_priority,
            "max_templates": self.max_templates,
            "has_ads": self.has_ads,
            "support_level": self.support_level,
            "custom_templates": self.custom_templates,
            "batch_processing": self.batch_processing,
            "export_formats": self.export_formats,
        }


# Definizioni dei tier
TIER_FEATURES = {
    SubscriptionTier.FREE: TierFeatures(
        tier_id="free",
        name="Free",
        price_eur=0.0,
        billing_period="free",
        
        recipes_per_day=2,         # Max 2 ricette/giorno
        recipes_per_month=3,       # Max 3 ricette/mese
        storage_gb=0,
        max_concurrent_api_calls=1,
        
        ai_requests_per_day=5,     # Max 5 chiamate AI/giorno
        ai_model_priority="free",  # Usa modello free/ollama
        max_templates=1,           # Solo template basic
        has_ads=True,
        support_level="community",
        custom_templates=False,
        batch_processing=False,
        export_formats=["pdf"],
    ),
    
    SubscriptionTier.STARTER: TierFeatures(
        tier_id="starter",
        name="Starter",
        price_eur=5.99,
        billing_period="month",
        
        recipes_per_day=15,        # Max 15 ricette/giorno
        recipes_per_month=300,     # Max 300 ricette/mese
        storage_gb=1,
        max_concurrent_api_calls=3,
        
        ai_requests_per_day=50,    # Max 50 chiamate AI/giorno
        ai_model_priority="standard",  # ChatGPT 3.5 / Gemini basic
        max_templates=5,           # 5 template selezionati
        has_ads=True,
        support_level="email",
        custom_templates=False,
        batch_processing=False,
        export_formats=["pdf", "docx"],
    ),
    
    SubscriptionTier.PRO: TierFeatures(
        tier_id="pro",
        name="Pro",
        price_eur=9.99,
        billing_period="month",
        
        recipes_per_day=-1,        # Unlimited
        recipes_per_month=1000,    # Limite pratico
        storage_gb=5,
        max_concurrent_api_calls=5,
        
        ai_requests_per_day=200,   # Max 200 chiamate AI/giorno
        ai_model_priority="priority",  # ChatGPT 4 / Gemini Pro
        max_templates=-1,          # Tutti i template
        has_ads=False,
        support_level="email",
        custom_templates=False,
        batch_processing=True,
        export_formats=["pdf", "docx"],
    ),
}


def get_tier_features(tier: str) -> Optional[TierFeatures]:
    """Recupera le features di un tier"""
    try:
        tier_enum = SubscriptionTier(tier.lower())
        return TIER_FEATURES.get(tier_enum)
    except ValueError:
        return None


def get_tier_by_id(tier_id: str) -> Optional[TierFeatures]:
    """Alias per get_tier_features"""
    return get_tier_features(tier_id)


def get_all_tiers() -> Dict[str, Dict]:
    """Ritorna tutti i tier disponibili"""
    return {
        tier.value: features.to_dict()
        for tier, features in TIER_FEATURES.items()
    }


def get_tier_name(tier: str) -> str:
    """Recupera il nome leggibile del tier"""
    features = get_tier_features(tier)
    return features.name if features else "Unknown"


def get_tier_price(tier: str) -> float:
    """Recupera il prezzo del tier"""
    features = get_tier_features(tier)
    return features.price_eur if features else 0.0


def check_usage_limit(
    tier: str,
    recipes_this_month: int,
    storage_used_mb: float,
    concurrent_calls: int = 1
) -> Dict[str, bool]:
    """
    Controlla se l'utente ha raggiunto i limiti del suo tier
    
    Returns:
        Dict con le keys:
        - "recipes": True se non ha raggiunto il limite ricette
        - "storage": True se non ha raggiunto il limite storage
        - "concurrent": True se non ha raggiunto il limite API
    """
    features = get_tier_features(tier)
    if not features:
        return {"recipes": False, "storage": False, "concurrent": False}
    
    storage_gb = storage_used_mb / 1024
    
    return {
        "recipes": recipes_this_month < features.recipes_per_month,
        "storage": storage_gb < features.storage_gb,
        "concurrent": concurrent_calls <= features.max_concurrent_api_calls,
    }


def get_available_templates(tier: str, all_templates: List[str]) -> List[str]:
    """
    Filtra i template disponibili per il tier
    
    Args:
        tier: ID del tier
        all_templates: Lista di tutti i template disponibili
    
    Returns:
        Lista di template disponibili per questo tier
    """
    features = get_tier_features(tier)
    if not features:
        return []
    
    if features.max_templates == -1:
        # Tutti i template
        return all_templates
    
    # Starter: template base selezionati
    if tier.lower() == "starter":
        starter_templates = [
            "classico",
            "minimal",
            "bifno",
            "carta",
            "design_moderno",
        ]
        return [t for t in starter_templates if t in all_templates]
    
    # Free: solo basic
    return ["classico"]


# Mapping tra tier e Stripe Price ID (configurato in .env)
STRIPE_PRICE_IDS: Dict[SubscriptionTier, Optional[str]] = {
    SubscriptionTier.STARTER: None,  # Impostato da env
    SubscriptionTier.PRO: None,      # Impostato da env
}


def set_stripe_price_id(tier: str, price_id: str) -> None:
    """Imposta il Price ID di Stripe per un tier"""
    try:
        tier_enum = SubscriptionTier(tier.lower())
        STRIPE_PRICE_IDS[tier_enum] = price_id
    except ValueError:
        pass


def get_stripe_price_id(tier: str) -> Optional[str]:
    """Recupera il Price ID di Stripe per un tier"""
    try:
        tier_enum = SubscriptionTier(tier.lower())
        return STRIPE_PRICE_IDS.get(tier_enum)
    except ValueError:
        return None


if __name__ == "__main__":
    # Test
    print("=== Subscription Tiers ===\n")
    
    for tier_id, features in get_all_tiers().items():
        print(f"{features['name']} (€{features['price_eur']}):")
        print(f"  Ricette/mese: {features['recipes_per_month']}")
        print(f"  Storage: {features['storage_gb']}GB")
        print(f"  Template: {features['max_templates'] if features['max_templates'] > 0 else 'Unlimited'}")
        print(f"  Pubblicità: {'Sì' if features['has_ads'] else 'No'}")
        print(f"  AI: {features['ai_priority']}")
        print(f"  Supporto: {features['support_level']}")
        print()
