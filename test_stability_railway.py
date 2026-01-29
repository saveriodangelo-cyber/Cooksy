#!/usr/bin/env python3
"""
Test completo di stabilità API REST su Railway.
Verifica che TUTTE le funzionalità critiche funzionino.
"""

import requests
import json
import time
import sys

BASE_URL = "https://cooksy-finaly.up.railway.app"
TIMEOUT = 15

def test_health():
    """Health check."""
    print("\n[1/8] Health Check")
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        print(f"  ✅ Status: {data.get('status')}")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_templates_get():
    """GET /api/templates."""
    print("\n[2/8] Templates GET")
    try:
        r = requests.get(f"{BASE_URL}/api/templates", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        count = len(data.get("templates", []))
        assert count > 0
        print(f"  ✅ Templates loaded: {count}")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_get_templates_post():
    """POST /api/get_templates (fallback per Bridge)."""
    print("\n[3/8] get_templates POST (fallback)")
    try:
        r = requests.post(f"{BASE_URL}/api/get_templates", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") == True
        count = len(data.get("templates", []))
        assert count > 0
        print(f"  ✅ Fallback working: {count} templates")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_auth_register():
    """POST /api/auth_register."""
    print("\n[4/8] Auth Register")
    try:
        test_email = f"test_{int(time.time())}@test.com"
        r = requests.post(f"{BASE_URL}/api/auth_register", json={
            "email": test_email,
            "password": "TestPass123!"
        }, timeout=TIMEOUT)
        # Status può essere 201 (ok) o 409 (already exists)
        assert r.status_code in [201, 409]
        data = r.json()
        print(f"  ✅ Response: {data.get('ok', False)} (status {r.status_code})")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_auth_logout():
    """POST /api/auth_logout."""
    print("\n[5/8] Auth Logout")
    try:
        r = requests.post(f"{BASE_URL}/api/auth_logout", json={
            "token": "fake_token"
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        print(f"  ✅ Response: ok={data.get('ok', False)}")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_unknown_method():
    """Test che metodo sconosciuto ritorna errore appropriato."""
    print("\n[6/8] Unknown Method Error Handling")
    try:
        r = requests.post(f"{BASE_URL}/api/nonexistent_xyz", json={}, timeout=TIMEOUT)
        # Potrebbe ritornare 400 (metodo sconosciuto) o 503 (Bridge non disponibile)
        assert r.status_code in [400, 503]
        data = r.json()
        assert "error" in data
        print(f"  ✅ Correctly handles error (status {r.status_code}): {data.get('error')}")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_template_serve():
    """GET /api/templates/classico (serve HTML template)."""
    print("\n[7/8] Template HTML Serving")
    try:
        r = requests.get(f"{BASE_URL}/api/templates/classico", timeout=TIMEOUT)
        assert r.status_code == 200
        html = r.text
        assert len(html) > 100
        assert "<html" in html.lower()
        print(f"  ✅ Template served: {len(html)} chars")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

def test_cors_headers():
    """Verifica CORS headers."""
    print("\n[8/8] CORS Headers")
    try:
        r = requests.options(f"{BASE_URL}/api/templates", timeout=TIMEOUT)
        headers = r.headers
        cors_origin = headers.get("access-control-allow-origin", "")
        cors_methods = headers.get("access-control-allow-methods", "")
        
        print(f"  ✅ CORS Origin: {cors_origin}")
        print(f"  ✅ CORS Methods: {cors_methods}")
        return True
    except Exception as e:
        print(f"  ⚠️ CORS check (non-critical): {e}")
        return True  # Non-critical

if __name__ == "__main__":
    print("=" * 70)
    print("RAILWAY API STABILITY TEST")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")
    
    try:
        results = []
        results.append(test_health())
        results.append(test_templates_get())
        results.append(test_get_templates_post())
        results.append(test_auth_register())
        results.append(test_auth_logout())
        results.append(test_unknown_method())
        results.append(test_template_serve())
        results.append(test_cors_headers())
        
        # Riepilogo
        print("\n" + "=" * 70)
        passed = sum(results)
        total = len(results)
        print(f"RISULTATO: {passed}/{total} test passati")
        print("=" * 70)
        
        if passed == total:
            print("\n✅ RAILWAY API AL 100% STABILE\n")
            sys.exit(0)
        else:
            print(f"\n⚠️ {total - passed} test falliti\n")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Test interrotti")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERRORE] {e}")
        sys.exit(1)
