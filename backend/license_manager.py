# -*- coding: utf-8 -*-
"""
Sistema di licenze gratuito per Cooksy
Genera chiavi basate sull'hardware del PC
"""
import hashlib
import platform
import uuid
from pathlib import Path
import json

from backend.utils import project_root

LICENSE_FILE = project_root() / "data" / "config" / "license.json"

def get_machine_id():
    """Genera ID univoco basato sull'hardware"""
    # Combina diversi identificatori hardware
    try:
        machine_uuid = str(uuid.getnode())  # MAC address
        platform_info = platform.platform()
        processor = platform.processor()
        
        combined = f"{machine_uuid}-{platform_info}-{processor}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    except:
        return "UNKNOWN"

def generate_license_key(machine_id, license_type="FREE"):
    """Genera chiave di licenza per questo PC"""
    data = f"{machine_id}-COOKSY-{license_type}"
    key = hashlib.sha256(data.encode()).hexdigest()[:24].upper()
    # Formatta come: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
    return '-'.join([key[i:i+4] for i in range(0, 24, 4)])

def validate_license():
    """Verifica se la licenza è valida per questo PC"""
    if not LICENSE_FILE.exists():
        return False, "Nessuna licenza trovata"
    
    try:
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stored_key = data.get('license_key')
        license_type = data.get('type', 'FREE')
        
        # Genera chiave attesa per questo PC
        machine_id = get_machine_id()
        expected_key = generate_license_key(machine_id, license_type)
        
        if stored_key == expected_key:
            return True, f"Licenza {license_type} valida"
        else:
            return False, "Licenza non valida per questo PC"
    except Exception as e:
        return False, f"Errore verifica: {str(e)}"

def create_license(license_type="FREE"):
    """Crea licenza per questo PC"""
    machine_id = get_machine_id()
    license_key = generate_license_key(machine_id, license_type)
    
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    license_data = {
        "license_key": license_key,
        "type": license_type,
        "machine_id": machine_id[:8] + "...",  # Parziale per privacy
    }
    
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(license_data, f, indent=2)
    
    return license_key

def check_or_create_license():
    """Controlla licenza o ne crea una FREE"""
    valid, msg = validate_license()
    
    if not valid:
        print(f"[LICENSE] {msg}")
        print("[LICENSE] Generazione licenza FREE...")
        key = create_license("FREE")
        print(f"[LICENSE] Licenza creata: {key}")
        return True
    
    print(f"[LICENSE] {msg}")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("COOKSY - LICENSE MANAGER")
    print("=" * 60)
    print(f"\nMachine ID: {get_machine_id()}")
    
    valid, msg = validate_license()
    print(f"\nStato: {msg}")
    
    if not valid:
        print("\nGenerazione nuova licenza FREE...")
        key = create_license("FREE")
        print(f"Chiave: {key}")
