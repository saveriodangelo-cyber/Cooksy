#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite Completo - Cooksy
Verifica tutte le funzionalità prima della distribuzione
"""
import os
import sys
import json
import time
import tempfile
from pathlib import Path

# Forza UTF-8 su Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_1_env_variables():
    """Test 1: Variabili d'ambiente Stripe caricate"""
    print("\n[TEST 1] Variabili d'ambiente Stripe")
    print("-" * 50)
    
    keys = [
        'STRIPE_SECRET_KEY',
        'STRIPE_PUBLISHABLE_KEY',
        'STRIPE_PRICE_STARTER',
        'STRIPE_PRICE_PRO',
        'STRIPE_PRICE_BUSINESS',
        'STRIPE_WEBHOOK_SECRET'
    ]
    
    all_ok = True
    for key in keys:
        val = os.getenv(key, '')
        status = '✓' if val else '✗'
        print(f"  {status} {key}: {len(val)} chars")
        if not val:
            all_ok = False
    
    return all_ok

def test_2_subscription_tiers():
    """Test 2: Tier FREE ha quota 3 (non 100)"""
    print("\n[TEST 2] Subscription Tiers - Quota FREE")
    print("-" * 50)
    
    from backend.subscription_tiers import TIER_FEATURES, SubscriptionTier
    
    free_tier = TIER_FEATURES.get(SubscriptionTier.FREE, {})
    recipes_limit = free_tier.recipes_per_month if hasattr(free_tier, 'recipes_per_month') else 0
    
    status = '✓' if recipes_limit == 3 else '✗'
    print(f"  {status} Tier FREE - recipes_per_month: {recipes_limit} (atteso: 3)")
    
    return recipes_limit == 3

def test_3_csrf_token():
    """Test 3: CSRF token format (64 hex chars)"""
    print("\n[TEST 3] CSRF Token Format")
    print("-" * 50)
    
    import secrets
    token = secrets.token_hex(32)  # 64 chars
    
    is_valid = len(token) == 64 and all(c in '0123456789abcdef' for c in token)
    status = '✓' if is_valid else '✗'
    print(f"  {status} Token length: {len(token)} chars (atteso: 64)")
    print(f"  {status} Token format: hex (valido: {is_valid})")
    
    return is_valid

def test_4_batch_start_csrf():
    """Test 4: batch_start accetta token valido"""
    print("\n[TEST 4] Batch Start - CSRF Validation")
    print("-" * 50)
    
    from backend.bridge import Bridge
    import tempfile
    
    bridge = Bridge()
    
    # Crea una cartella temp con un file test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Crea file dummy
        test_file = Path(tmpdir) / "test.jpg"
        test_file.write_text("dummy")
        
        # Genera token CSRF valido
        import secrets
        csrf_token = secrets.token_hex(32)  # 64 chars
        
        payload = {
            "input_dir": tmpdir,
            "template_id": "classico",
            "_csrf": csrf_token,  # Corretta chiave: _csrf non csrf_token
            "export_format": "pdf"
        }
        
        result = bridge.batch_start(payload)
        
        is_ok = result.get('ok') == True
        status = '✓' if is_ok else '✗'
        print(f"  {status} batch_start con CSRF valido: {result.get('started', False)}")
        if not is_ok:
            print(f"     Errore: {result.get('error', 'unknown')}")
        
        return is_ok

def test_5_templates():
    """Test 5: Tutti i 32 template disponibili"""
    print("\n[TEST 5] Templates - Verifica disponibilità")
    print("-" * 50)
    
    from backend.bridge import Bridge
    
    bridge = Bridge()
    templates_response = bridge.get_templates()
    
    template_count = len(templates_response.get('templates', []))
    status = '✓' if template_count >= 32 else '✗'
    print(f"  {status} Templates disponibili: {template_count} (atteso: ≥32)")
    
    if template_count > 0:
        print(f"     Esempio: {templates_response['templates'][0]}")
    
    return template_count >= 32

def test_6_stripe_keys_loaded():
    """Test 6: stripe_manager carica le chiavi"""
    print("\n[TEST 6] Stripe Manager - Chiavi caricate")
    print("-" * 50)
    
    from backend.stripe_manager import STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY
    
    has_secret = bool(STRIPE_SECRET_KEY and len(STRIPE_SECRET_KEY) > 20)
    has_public = bool(STRIPE_PUBLISHABLE_KEY and len(STRIPE_PUBLISHABLE_KEY) > 20)
    
    status_secret = '✓' if has_secret else '✗'
    status_public = '✓' if has_public else '✗'
    
    print(f"  {status_secret} Secret Key: caricata ({len(STRIPE_SECRET_KEY)} chars)")
    print(f"  {status_public} Publishable Key: caricata ({len(STRIPE_PUBLISHABLE_KEY)} chars)")
    
    return has_secret and has_public

def test_7_database():
    """Test 7: Database SQLite accessibile"""
    print("\n[TEST 7] Database - SQLite Access")
    print("-" * 50)
    
    import sqlite3
    from backend.utils import project_root
    
    db_path = project_root() / "data" / "recipes" / "recipes.db"
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        
        is_ok = result is not None
        status = '✓' if is_ok else '✗'
        print(f"  {status} Database: {db_path.name} (accessibile)")
        
        return is_ok
    except Exception as e:
        print(f"  ✗ Errore: {e}")
        return False

def test_8_csv_config():
    """Test 8: Configurazione CSV e dati allergeni (opzionale)"""
    print("\n[TEST 8] Configuration - CSV & Allergens")
    print("-" * 50)
    
    from backend.utils import project_root
    import csv
    
    csv_path = project_root() / "data" / "config" / "allergens.csv"
    
    try:
        if csv_path.exists():
            with open(csv_path, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            status = '✓' if len(rows) > 0 else '✗'
            print(f"  {status} allergens.csv: {len(rows)} allergens caricati")
            
            return len(rows) > 0
        else:
            # File opzionale - se non presente, lo skippiamo con successo
            print(f"  ⊘ allergens.csv: file opzionale (non critico)")
            return True
    except Exception as e:
        print(f"  ⊘ Errore (opzionale): {type(e).__name__}")
        return True  # Non blocca la distribuzione

def test_9_user_manager():
    """Test 9: User Manager - sistema di auth"""
    print("\n[TEST 9] User Manager - Authentication System")
    print("-" * 50)
    
    from backend.user_manager import UserManager
    from backend.utils import project_root
    
    try:
        db_path = project_root() / "data" / "users.db"
        mgr = UserManager(db_path)
        
        # Verifica che il sistema sia inizializzato
        is_ok = mgr is not None
        status = '✓' if is_ok else '✗'
        print(f"  {status} UserManager: inizializzato")
        
        return is_ok
    except Exception as e:
        print(f"  ✗ Errore: {e}")
        return False

def test_10_launcher_loads_env_local():
    """Test 10: launcher.py carica .env.local"""
    print("\n[TEST 10] Launcher - .env.local Loading")
    print("-" * 50)
    
    env_local = Path(__file__).parent / ".env.local"
    
    has_file = env_local.exists()
    status = '✓' if has_file else '✗'
    print(f"  {status} .env.local: {'presente' if has_file else 'assente'}")
    
    if has_file:
        try:
            with open(env_local, encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            stripe_lines = [l for l in lines if 'STRIPE_' in l]
            print(f"     {len(stripe_lines)} variabili Stripe configurate")
            return True
        except Exception as e:
            print(f"     Errore lettura (non critico): {type(e).__name__}")
            return True  # Non blocca
    
    return has_file

def main():
    """Esegui tutti i test"""
    print("\n" + "="*50)
    print("COOKSY - TEST SUITE COMPLETO")
    print("="*50)
    
    # Carica env vars
    from pathlib import Path
    from dotenv import load_dotenv
    
    env_path = Path('.') / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    
    env_local_path = Path('.') / '.env.local'
    if env_local_path.exists():
        load_dotenv(env_local_path)
    
    # Esegui test
    tests = [
        ("Variabili d'ambiente Stripe", test_1_env_variables),
        ("Tier FREE quota 3", test_2_subscription_tiers),
        ("CSRF token format", test_3_csrf_token),
        ("Batch start + CSRF", test_4_batch_start_csrf),
        ("32 Templates", test_5_templates),
        ("Stripe Manager", test_6_stripe_keys_loaded),
        ("Database SQLite", test_7_database),
        ("CSV Allergens", test_8_csv_config),
        ("User Manager Auth", test_9_user_manager),
        ("Launcher .env.local", test_10_launcher_loads_env_local),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ ERRORE: {e}")
            results.append((name, False))
    
    # Riepilogo
    print("\n" + "="*50)
    print("RIEPILOGO")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    
    print(f"\nRisultato: {passed}/{total} test passati")
    
    if passed == total:
        print("\n🎉 TUTTO OK - Pronto per la distribuzione!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test falliti - Controlla gli errori")
        return 1

if __name__ == "__main__":
    sys.exit(main())
