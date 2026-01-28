#!/usr/bin/env python3
"""Test batch_start function"""
import tempfile
import os
from backend import bridge

# Crea una cartella temp con un file test
with tempfile.TemporaryDirectory() as tmpdir:
    # Crea un file test
    test_file = os.path.join(tmpdir, "test.txt")
    with open(test_file, "w") as f:
        f.write("test")
    
    b = bridge.Bridge()
    
    # Genera un token CSRF valido (64 hex chars)
    csrf_token = ''.join(f'{i:02x}' for i in range(32))
    
    payload = {
        "input_dir": tmpdir,
        "out_dir": tmpdir,
        "template": "Template_Ricetta_AI",
        "export_pdf": False,
        "export_docx": False,
        "recursive": False,
        "_csrf": csrf_token
    }
    
    print("Testing batch_start...")
    print(f"Input dir: {tmpdir}")
    print(f"CSRF token: {csrf_token}")
    result = b.batch_start(payload)
    print("Result:", result)
    print("OK" if result.get("ok") else f"ERROR: {result.get('error')}")

