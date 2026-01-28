import binascii
import os

def get_csrf_token():
    """Genera un token CSRF valido: hex di 64 caratteri"""
    return binascii.hexlify(os.urandom(32)).decode('ascii')

token = get_csrf_token()
print(f'Token: {token}')
print(f'Length: {len(token)}')
print(f'Valid: {len(token) == 64}')
print(f'Is hex: {all(c in "0123456789abcdef" for c in token)}')

# Testa validazione
try:
    int(token, 16)
    print(f'Hex parsing: OK')
except:
    print(f'Hex parsing: FAIL')
