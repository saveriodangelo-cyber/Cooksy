#!/usr/bin/env python
"""
Script launcher locale per testing API + frontend.
Avvia:
1. Flask API on port 5000
2. Simple HTTP server for frontend on port 8000
3. Both accessible via http://localhost:8000 (proxy)
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

def start_api():
    """Avvia Flask API."""
    print("\n[API] Starting Flask API on http://localhost:5000...")
    os.chdir(Path(__file__).parent)
    subprocess.run([sys.executable, "-m", "backend.api_rest"])

def start_frontend():
    """Avvia HTTP server per frontend."""
    print("[FRONTEND] Starting HTTP server on http://localhost:8000...")
    ui_dir = Path(__file__).parent / "ui"
    os.chdir(ui_dir)
    subprocess.run([sys.executable, "-m", "http.server", "8000"])

def main():
    print("=" * 60)
    print("Cooksy Local Dev Server")
    print("=" * 60)
    
    # Avvia API in thread
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # Attendi API ready
    time.sleep(2)
    
    # Avvia frontend
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()
    
    # Apri browser
    time.sleep(2)
    print("\n[INFO] Opening browser on http://localhost:8000...")
    try:
        webbrowser.open("http://localhost:8000")
    except:
        pass
    
    print("\n✅ Dev servers running!")
    print("   - Frontend: http://localhost:8000")
    print("   - API:      http://localhost:5000")
    print("   - Service Worker: Check Console (Ctrl+Shift+I)")
    print("\nPress Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[INFO] Shutting down...")
        sys.exit(0)

if __name__ == "__main__":
    main()
