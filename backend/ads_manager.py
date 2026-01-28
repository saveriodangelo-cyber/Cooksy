#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Gestione annunci pubblicitari per tier Starter
Fornisce API per iniettare banner e annunci nella UI
"""
from typing import Dict, List, Optional
from datetime import datetime
import secrets


class Advertisement:
    """Rappresenta un annuncio pubblicitario"""
    def __init__(
        self,
        ad_id: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
        cta_text: str = "Scopri di più",
        cta_url: str = "#",
        placement: str = "sidebar",  # sidebar, banner, modal
        show_after_recipes: int = 3,  # Mostra dopo N ricette elaborate
    ):
        self.ad_id = ad_id
        self.title = title
        self.description = description
        self.image_url = image_url
        self.cta_text = cta_text
        self.cta_url = cta_url
        self.placement = placement
        self.show_after_recipes = show_after_recipes

    def to_dict(self) -> Dict:
        return {
            "id": self.ad_id,
            "title": self.title,
            "description": self.description,
            "image_url": self.image_url,
            "cta_text": self.cta_text,
            "cta_url": self.cta_url,
            "placement": self.placement,
            "show_after_recipes": self.show_after_recipes,
        }


# Annunci di esempio (in produzione verrebbero caricati da DB)
DEFAULT_ADVERTISEMENTS = [
    Advertisement(
        ad_id="upgrade_pro",
        title="Passa a Pro",
        description="Sbloccadi 100 ricette al mese senza pubblicità",
        cta_text="Upgrade a €9.99/mese",
        cta_url="/subscription?tier=pro",
        placement="banner",
        show_after_recipes=5,
    ),
    Advertisement(
        ad_id="upgrade_business",
        title="Per i Professionisti",
        description="Cooksy Business: 500 ricette, supporto prioritario",
        cta_text="Scopri Business",
        cta_url="/subscription?tier=business",
        placement="sidebar",
        show_after_recipes=10,
    ),
    Advertisement(
        ad_id="template_premium",
        title="Potenzia i Tuoi Template",
        description="Con Pro hai accesso a 30+ design professionali",
        cta_text="Vedi tutti i template",
        cta_url="/templates",
        placement="sidebar",
        show_after_recipes=7,
    ),
    Advertisement(
        ad_id="batch_processing",
        title="Elaborazione in Batch",
        description="Pro: elabora più ricette contemporaneamente",
        cta_text="Attiva Batch Processing",
        cta_url="/batch",
        placement="modal",
        show_after_recipes=15,
    ),
]


class AdsManager:
    """Gestisce gli annunci pubblicitari per utenti Starter"""

    def __init__(self):
        self.ads = {ad.ad_id: ad for ad in DEFAULT_ADVERTISEMENTS}

    def get_ad_for_tier(self, tier: str, recipes_analyzed_this_month: int) -> Optional[Dict]:
        """
        Recupera un annuncio appropriato per il tier e uso corrente

        Returns:
            Dict con i dettagli dell'annuncio, o None se nessuno da mostrare
        """
        # Solo Starter e Free vedono annunci
        if tier not in ["starter", "free"]:
            return None

        # Seleziona annunci appropriati in base all'utilizzo
        suitable_ads = []
        for ad in self.ads.values():
            if recipes_analyzed_this_month >= ad.show_after_recipes:
                suitable_ads.append(ad)

        if not suitable_ads:
            return None

        # Ritorna un annuncio casuale
        selected = secrets.choice(suitable_ads)
        return selected.to_dict()

    def get_all_ads_for_sidebar(self, tier: str, recipes_this_month: int) -> List[Dict]:
        """Recupera tutti gli annunci da mostrare nella sidebar"""
        if tier not in ["starter", "free"]:
            return []

        ads_list = []
        for ad in self.ads.values():
            if (
                ad.placement == "sidebar"
                and recipes_this_month >= ad.show_after_recipes
            ):
                ads_list.append(ad.to_dict())

        return ads_list

    def get_banner_ad(self, tier: str, recipes_this_month: int) -> Optional[Dict]:
        """Recupera l'annuncio per il banner principale"""
        if tier not in ["starter", "free"]:
            return None

        for ad in self.ads.values():
            if (
                ad.placement == "banner"
                and recipes_this_month >= ad.show_after_recipes
            ):
                return ad.to_dict()

        return None

    def get_modal_ad(self, tier: str, recipes_this_month: int) -> Optional[Dict]:
        """Recupera l'annuncio per modal (mostra dopo molte ricette)"""
        if tier not in ["starter", "free"]:
            return None

        for ad in self.ads.values():
            if (
                ad.placement == "modal"
                and recipes_this_month >= ad.show_after_recipes
            ):
                return ad.to_dict()

        return None

    def add_custom_ad(
        self,
        ad_id: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
        cta_text: str = "Scopri di più",
        cta_url: str = "#",
        placement: str = "sidebar",
        show_after_recipes: int = 3,
    ) -> Dict:
        """Aggiunge un annuncio personalizzato"""
        ad = Advertisement(
            ad_id=ad_id,
            title=title,
            description=description,
            image_url=image_url,
            cta_text=cta_text,
            cta_url=cta_url,
            placement=placement,
            show_after_recipes=show_after_recipes,
        )
        self.ads[ad_id] = ad
        return {"ok": True, "ad_id": ad_id}

    def get_ads_context(self, tier: str, recipes_this_month: int) -> Dict:
        """
        Ritorna un dizionario con tutti gli annunci da mostrare nel template

        Questo può essere passato al template di rendering PDF/DOCX
        """
        return {
            "has_ads": tier in ["starter", "free"],
            "tier": tier,
            "sidebar_ads": self.get_all_ads_for_sidebar(tier, recipes_this_month),
            "banner_ad": self.get_banner_ad(tier, recipes_this_month),
            "modal_ad": self.get_modal_ad(tier, recipes_this_month),
            "single_ad": self.get_ad_for_tier(tier, recipes_this_month),
        }


# Singleton globale
_ads_manager_instance: Optional[AdsManager] = None


def get_ads_manager() -> AdsManager:
    """Ritorna l'istanza globale di AdsManager"""
    global _ads_manager_instance
    if _ads_manager_instance is None:
        _ads_manager_instance = AdsManager()
    return _ads_manager_instance


if __name__ == "__main__":
    # Test
    print("=== Ads Manager Test ===\n")

    am = get_ads_manager()

    # Test Starter tier con poche ricette
    print("Starter tier, 3 ricette analizzate:")
    ctx = am.get_ads_context("starter", 3)
    print(f"  Has ads: {ctx['has_ads']}")
    print(f"  Sidebar ads: {len(ctx['sidebar_ads'])}")
    print(f"  Banner ad: {ctx['banner_ad']}")
    print()

    # Test Starter tier con molte ricette
    print("Starter tier, 20 ricette analizzate:")
    ctx = am.get_ads_context("starter", 20)
    print(f"  Has ads: {ctx['has_ads']}")
    print(f"  Sidebar ads: {len(ctx['sidebar_ads'])}")
    print(f"  Banner ad: {ctx['banner_ad']['title'] if ctx['banner_ad'] else 'None'}")
    print(f"  Modal ad: {ctx['modal_ad']['title'] if ctx['modal_ad'] else 'None'}")
    print()

    # Test Pro tier (senza annunci)
    print("Pro tier, 20 ricette analizzate:")
    ctx = am.get_ads_context("pro", 20)
    print(f"  Has ads: {ctx['has_ads']}")
    print(f"  Sidebar ads: {len(ctx['sidebar_ads'])}")
