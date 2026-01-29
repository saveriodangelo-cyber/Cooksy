#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WEBAPP FUNCTION VERIFICATION TEST
Verifica quali funzioni sono effettivamente disponibili nella web app su Railway
"""

import requests
import json
import time
import sys
import os
from datetime import datetime

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Railway backend URL
RAILWAY_API = "https://cooksy-finaly.up.railway.app"
TIMEOUT = 10

# Colori per output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
END = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*60}{END}")
    print(f"{BLUE}{text:^60}{END}")
    print(f"{BLUE}{'='*60}{END}\n")

def print_test(name, status, message=""):
    icon = "OK" if status else "FAIL"
    print(f"[{icon}] {name:40} {message}")

def test_health():
    """Test: API health check"""
    try:
        resp = requests.get(f"{RAILWAY_API}/api/health", timeout=TIMEOUT)
        ok = resp.status_code == 200
        print_test("API Health Check", ok, f"[{resp.status_code}]")
        return ok
    except Exception as e:
        print_test("API Health Check", False, str(e))
        return False

def test_templates():
    """Test: Get templates list"""
    try:
        resp = requests.post(f"{RAILWAY_API}/api/get_templates", timeout=TIMEOUT)
        data = resp.json()
        ok = data.get('ok', False)
        count = len(data.get('templates', []))
        print_test(f"Get Templates ({count} templates)", ok, f"[{resp.status_code}]")
        return ok
    except Exception as e:
        print_test("Get Templates", False, str(e))
        return False

def test_auth_register():
    """Test: User registration"""
    try:
        payload = {
            "email": f"test_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "username": "testuser"
        }
        resp = requests.post(
            f"{RAILWAY_API}/api/auth_register",
            json=payload,
            timeout=TIMEOUT
        )
        ok = resp.status_code in [201, 200, 409]  # 409 = already exists
        print_test("Auth Register", ok, f"[{resp.status_code}]")
        return resp.status_code == 201, payload
    except Exception as e:
        print_test("Auth Register", False, str(e))
        return False, None

def test_auth_login(email, password):
    """Test: User login"""
    try:
        payload = {
            "email": email,
            "password": password
        }
        resp = requests.post(
            f"{RAILWAY_API}/api/auth_login",
            json=payload,
            timeout=TIMEOUT
        )
        data = resp.json()
        ok = data.get('ok', False) or resp.status_code == 200
        token = data.get('token', '')
        print_test("Auth Login", ok, f"[{resp.status_code}]" + (f" Token: {token[:20]}..." if token else ""))
        return ok, token
    except Exception as e:
        print_test("Auth Login", False, str(e))
        return False, None

def test_auth_me(token):
    """Test: Get current user"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"{RAILWAY_API}/api/auth_me",
            headers=headers,
            timeout=TIMEOUT
        )
        data = resp.json()
        ok = data.get('ok', False) and resp.status_code == 200
        user = data.get('user', {})
        print_test(f"Auth Me (User: {user.get('email', 'N/A')})", ok, f"[{resp.status_code}]")
        return ok
    except Exception as e:
        print_test("Auth Me", False, str(e))
        return False

def test_cors_headers():
    """Test: CORS headers"""
    try:
        headers = {"Origin": "https://cooksy-vercel.vercel.app"}
        resp = requests.get(
            f"{RAILWAY_API}/api/health",
            headers=headers,
            timeout=TIMEOUT
        )
        cors_header = resp.headers.get('Access-Control-Allow-Origin', '')
        ok = '*' in cors_header or 'cooksy' in cors_header
        print_test("CORS Headers", ok, f"Allow-Origin: {cors_header}")
        return ok
    except Exception as e:
        print_test("CORS Headers", False, str(e))
        return False

def test_bridge_fallback():
    """Test: Bridge fallback endpoints"""
    endpoints = [
        '/api/get_templates',
    ]
    
    all_ok = True
    for endpoint in endpoints:
        try:
            resp = requests.post(
                f"{RAILWAY_API}{endpoint}",
                timeout=TIMEOUT
            )
            ok = resp.status_code in [200, 201, 400, 503]
            all_ok = all_ok and ok
            print_test(f"Bridge Fallback: {endpoint}", ok, f"[{resp.status_code}]")
        except Exception as e:
            print_test(f"Bridge Fallback: {endpoint}", False, str(e))
            all_ok = False
    
    return all_ok

def test_error_handling():
    """Test: Error handling"""
    try:
        resp = requests.post(
            f"{RAILWAY_API}/api/invalid_endpoint",
            timeout=TIMEOUT
        )
        ok = resp.status_code == 404
        print_test("Error Handling (404 for invalid)", ok, f"[{resp.status_code}]")
        return ok
    except Exception as e:
        print_test("Error Handling", False, str(e))
        return False

def test_response_format():
    """Test: Response format consistency"""
    try:
        # Test templates response
        resp = requests.post(f"{RAILWAY_API}/api/get_templates", timeout=TIMEOUT)
        data = resp.json()
        
        # Check for required fields
        has_ok = 'ok' in data
        has_data = 'templates' in data or 'error' in data
        
        ok = has_ok and has_data
        print_test("Response Format Consistency", ok, 
                  f"{'ok' in data and 'templates' in data}")
        return ok
    except Exception as e:
        print_test("Response Format", False, str(e))
        return False

def run_all_tests():
    """Run comprehensive test suite"""
    
    print_header("WEBAPP FUNCTION VERIFICATION TEST")
    print(f"Railway API: {RAILWAY_API}")
    print(f"Test Time: {datetime.now().isoformat()}\n")
    
    results = {}
    
    # Basic connectivity
    print(f"\n{YELLOW}[1/5] BASIC CONNECTIVITY{END}\n")
    results['health'] = test_health()
    results['cors'] = test_cors_headers()
    results['error_handling'] = test_error_handling()
    results['response_format'] = test_response_format()
    
    # Public endpoints (no auth)
    print(f"\n{YELLOW}[2/5] PUBLIC ENDPOINTS{END}\n")
    results['templates'] = test_templates()
    results['bridge_fallback'] = test_bridge_fallback()
    
    # Authentication flow
    print(f"\n{YELLOW}[3/5] AUTHENTICATION FLOW{END}\n")
    
    # Register new user
    registered, credentials = test_auth_register()
    results['auth_register'] = registered
    
    if registered and credentials:
        # Try to login
        print(f"\n{YELLOW}[4/5] LOGIN WITH NEW CREDENTIALS{END}\n")
        logged_in, token = test_auth_login(credentials['email'], credentials['password'])
        results['auth_login'] = logged_in
        
        if logged_in and token:
            # Get current user
            print(f"\n{YELLOW}[5/5] AUTHENTICATED ENDPOINTS{END}\n")
            results['auth_me'] = test_auth_me(token)
    else:
        results['auth_login'] = False
    
    # Summary
    print_header("TEST SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {GREEN}{passed}{END}")
    print(f"Failed: {RED}{total - passed}{END}")
    print(f"Success Rate: {GREEN}{(passed/total*100):.1f}%{END}\n")
    
    # Recommendations
    print(f"{BLUE}RECOMMENDATIONS:{END}\n")
    
    if results.get('health'):
        print(f"{GREEN}[OK] Railway backend is operational{END}")
    else:
        print(f"{RED}[FAIL] Railway backend unreachable - check deployment{END}")
    
    if results.get('cors'):
        print(f"{GREEN}[OK] CORS headers correctly configured{END}")
    else:
        print(f"{RED}[FAIL] CORS issues - web app may not connect{END}")
    
    if results.get('templates'):
        print(f"{GREEN}[OK] Templates endpoint working{END}")
    else:
        print(f"{RED}[FAIL] Templates not loading - check database{END}")
    
    if results.get('auth_login'):
        print(f"{GREEN}[OK] Full authentication flow working{END}")
    else:
        print(f"{RED}[FAIL] Auth issues - check user manager{END}")
    
    print(f"\n{BLUE}WEB APP STATUS:{END}\n")
    
    essential_ok = results.get('health') and results.get('cors') and results.get('templates')
    auth_ok = results.get('auth_register') and results.get('auth_login')
    
    if essential_ok and auth_ok:
        print(f"{GREEN}WEBAPP IS FULLY FUNCTIONAL - READY FOR PRODUCTION{END}")
    elif essential_ok:
        print(f"{YELLOW}WARNING: WEBAPP IS PARTIALLY FUNCTIONAL - BASIC FEATURES WORK{END}")
    else:
        print(f"{RED}FAIL: WEBAPP HAS CRITICAL ISSUES - NOT PRODUCTION READY{END}")
    
    return passed == total

if __name__ == '__main__':
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
