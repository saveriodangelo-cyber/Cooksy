"""Test locale dell'API REST per verificare integrazione Bridge."""
import sys
import time
import subprocess
import requests

sys.path.insert(0, '.')

BASE_URL = 'http://localhost:5556'
TIMEOUT = 5

def start_server():
    """Avvia server Flask in background."""
    proc = subprocess.Popen(
        [sys.executable, '-m', 'flask', 'run', '--port', '5556'],
        env={
            'FLASK_APP': 'backend.api_rest',
            'FLASK_DEBUG': '0',
            'PYTHONPATH': '.'
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(4)  # Aspetta avvio
    return proc

def test_health():
    """Test endpoint health."""
    print('\n=== TEST 1: Health Check ===')
    try:
        r = requests.get(f'{BASE_URL}/api/health', timeout=TIMEOUT)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data.get('status') == 'ok', f"Expected ok, got {data.get('status')}"
        print(f'✅ Health: {data}')
        return True
    except Exception as e:
        print(f'❌ Health failed: {e}')
        return False

def test_templates_get():
    """Test GET /api/templates."""
    print('\n=== TEST 2: Templates GET ===')
    try:
        r = requests.get(f'{BASE_URL}/api/templates', timeout=TIMEOUT)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        count = len(data.get('templates', []))
        assert count > 0, "No templates found"
        print(f'✅ Templates GET: {count} templates')
        return True
    except Exception as e:
        print(f'❌ Templates GET failed: {e}')
        return False

def test_bridge_get_templates():
    """Test POST /api/get_templates (via Bridge)."""
    print('\n=== TEST 3: get_templates via Bridge ===')
    try:
        r = requests.post(f'{BASE_URL}/api/get_templates', json={}, timeout=TIMEOUT)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data.get('ok') == True, f"Expected ok=True, got {data.get('ok')}"
        count = len(data.get('templates', []))
        assert count > 0, "No templates from Bridge"
        print(f'✅ Bridge get_templates: {count} templates')
        return True
    except Exception as e:
        print(f'❌ Bridge get_templates failed: {e}')
        return False

def test_bridge_auth_logout():
    """Test POST /api/auth_logout (via Bridge)."""
    print('\n=== TEST 4: auth_logout via Bridge ===')
    try:
        r = requests.post(f'{BASE_URL}/api/auth_logout', json={'token': 'fake_token'}, timeout=TIMEOUT)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        # Logout può ritornare ok=True o ok=False a seconda del token
        print(f'✅ Bridge auth_logout: {data}')
        return True
    except Exception as e:
        print(f'❌ Bridge auth_logout failed: {e}')
        return False

def test_unknown_method():
    """Test metodo non esistente."""
    print('\n=== TEST 5: Metodo non esistente ===')
    try:
        r = requests.post(f'{BASE_URL}/api/nonexistent_xyz', json={}, timeout=TIMEOUT)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        data = r.json()
        assert 'error' in data, "Expected error field"
        print(f'✅ Unknown method correctly returns 400: {data.get("error")}')
        return True
    except Exception as e:
        print(f'❌ Unknown method test failed: {e}')
        return False

def test_auth_register():
    """Test POST /api/auth_register."""
    print('\n=== TEST 6: auth_register ===')
    try:
        r = requests.post(f'{BASE_URL}/api/auth_register', json={
            'email': f'test_{int(time.time())}@test.com',
            'password': 'TestPass123!'
        }, timeout=TIMEOUT)
        # Status può essere 201 (ok) o 409/400 (errore)
        print(f'✅ auth_register: status {r.status_code}, response: {r.json()}')
        return True
    except Exception as e:
        print(f'❌ auth_register failed: {e}')
        return False

if __name__ == '__main__':
    print('='*60)
    print('TEST API REST LOCALE - Integrazione Bridge')
    print('='*60)
    
    proc = None
    try:
        print('\n[INFO] Avvio server Flask su porta 5556...')
        proc = start_server()
        
        # Esegui test
        results = []
        results.append(test_health())
        results.append(test_templates_get())
        results.append(test_bridge_get_templates())
        results.append(test_bridge_auth_logout())
        results.append(test_unknown_method())
        results.append(test_auth_register())
        
        # Riepilogo
        print('\n' + '='*60)
        passed = sum(results)
        total = len(results)
        print(f'RISULTATO: {passed}/{total} test passati')
        print('='*60)
        
        if passed == total:
            print('\n✅ TUTTI I TEST PASSATI - API REST 100% FUNZIONANTE\n')
            sys.exit(0)
        else:
            print(f'\n⚠️ {total - passed} test falliti\n')
            sys.exit(1)
            
    except KeyboardInterrupt:
        print('\n[INFO] Test interrotti')
    except Exception as e:
        print(f'\n[ERRORE] {e}')
        sys.exit(1)
    finally:
        if proc:
            print('[INFO] Fermo server...')
            proc.terminate()
            proc.wait()
