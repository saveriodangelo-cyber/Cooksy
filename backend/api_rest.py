"""
REST API per Cooksy - Espone core functions come HTTP API.
Permette a web/mobile di connettersi al backend Python.
"""

import os
import sys
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Inizializza Flask
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Import user manager for auth endpoints
try:
    from backend.user_manager import UserManager
    user_manager = UserManager()
    _user_manager_available = True
except Exception as e:
    logger.warning(f"UserManager not available: {e}")
    user_manager = None
    _user_manager_available = False

# Import bridge for generic method calls
# NOTA: Bridge ha molte dipendenze (OCR, ML, ecc.) che potrebbero non essere
# disponibili in deployment minimale. Se fallisce, endpoint dedicati gestiranno
# le funzioni critiche senza Bridge.
try:
    from backend.bridge import Bridge
    _bridge = Bridge()
    _bridge_available = True
    logger.info("Bridge loaded successfully")
except Exception as e:
    logger.warning(f"Bridge not available (this is OK for web-only deployment): {e}")
    _bridge = None
    _bridge_available = False

# Config
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['JSON_SORT_KEYS'] = False

# Upload folder - compatibile con Windows e Linux
if sys.platform == 'win32':
    UPLOAD_FOLDER = Path.home() / 'AppData' / 'Local' / 'Cooksy' / 'uploads'
else:
    UPLOAD_FOLDER = Path('/tmp/cooksy_uploads')

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


@app.route('/api/health', methods=['GET'])
def health():
    """Health check."""
    return jsonify({
        "status": "ok",
        "service": "cooksy-api",
        "version": "1.0.0"
    }), 200


@app.route('/api/templates', methods=['GET'])
def get_templates():
    """Lista template disponibili - versione REST pura."""
    try:
        # Prova a leggere templates_list.json
        templates_list_file = Path(__file__).parent.parent / 'templates' / 'templates_list.json'
        
        if templates_list_file.exists():
            try:
                with open(templates_list_file, 'r', encoding='utf-8') as f:
                    templates = json.load(f)
                return jsonify({
                    "ok": True,
                    "templates": templates,
                    "count": len(templates)
                }), 200
            except Exception as e:
                logger.warning(f"Failed to load templates_list.json: {e}")
        
        # Fallback: scannerizza cartella templates
        templates_dir = Path(__file__).parent.parent / 'templates'
        templates = []
        
        if templates_dir.exists():
            for html_file in sorted(templates_dir.glob('*.html')):
                if not html_file.name.startswith('_'):
                    template_id = html_file.stem
                    templates.append({
                        "id": template_id,
                        "name": template_id.replace('_', ' ').title(),
                        "file": html_file.name
                    })
        
        return jsonify({
            "ok": True,
            "templates": templates,
            "count": len(templates)
        }), 200
    except Exception as e:
        logger.error(f"Get templates error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/templates/<template_id>', methods=['GET'])
def get_template_content(template_id):
    """Serve il contenuto HTML di un template."""
    try:
        # Sanitizza l'ID
        template_id = str(template_id or '').strip()
        if not template_id or '/' in template_id or '\\' in template_id:
            return jsonify({"ok": False, "error": "Invalid template ID"}), 400
        
        # Cerca il file template
        templates_dir = Path(__file__).parent.parent / 'templates'
        template_file = templates_dir / f"{template_id}.html"
        
        # Verifica che il file esista e sia nella cartella templates
        if not template_file.exists() or not template_file.resolve().is_relative_to(templates_dir.resolve()):
            return jsonify({"ok": False, "error": "Template not found"}), 404
        
        # Leggi e servi il contenuto
        with open(template_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            "ok": True,
            "id": template_id,
            "html": content
        }), 200
    except Exception as e:
        logger.error(f"Get template content error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload file ricetta."""
    try:
        if 'file' not in request.files:
            return jsonify({"ok": False, "error": "No file provided"}), 400
        
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({"ok": False, "error": "No file selected"}), 400
        
        filename = secure_filename(file.filename or "upload")
        filepath = UPLOAD_FOLDER / filename
        file.save(str(filepath))
        
        return jsonify({
            "ok": True,
            "file_path": str(filepath),
            "filename": filename,
            "size_mb": filepath.stat().st_size / (1024*1024)
        }), 200
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    """Status API."""
    return jsonify({
        "ok": True,
        "upload_folder": str(UPLOAD_FOLDER),
        "disk_free_gb": __get_disk_free_gb(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }), 200


# ===== AUTHENTICATION ENDPOINTS =====

@app.route('/api/auth_register', methods=['POST'])
def auth_register():
    """Registrazione nuovo utente."""
    if not _user_manager_available or not user_manager:
        return jsonify({"ok": False, "error": "Auth service not available"}), 503
    
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        username = data.get('username', '').strip() or None
        
        if not email or not password:
            return jsonify({"ok": False, "error": "Email e password sono obbligatorie"}), 400
        
        # Registra utente
        reg_result = user_manager.register(email, password, username)
        if not reg_result.get('ok'):
            return jsonify({
                "ok": False,
                "error": reg_result.get('error', 'Registration failed')
            }), 409
        
        user_id = reg_result.get('user_id')
        
        # Crea sessione
        token = user_manager.create_session(user_id, days=30)
        
        # Carica info utente
        user = user_manager.get_user(user_id)
        
        return jsonify({
            "ok": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role
            },
            "token": token
        }), 201
    
    except Exception as e:
        logger.error(f"Auth register error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/auth_login', methods=['POST'])
def auth_login():
    """Login con email e password."""
    if not _user_manager_available or not user_manager:
        return jsonify({"ok": False, "error": "Auth service not available"}), 503
    
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({"ok": False, "error": "Email e password sono obbligatorie"}), 400
        
        # Autentica
        auth_result = user_manager.authenticate(email, password)
        if not auth_result.get('ok'):
            return jsonify({
                "ok": False,
                "error": auth_result.get('error', 'Authentication failed')
            }), 401
        
        user_id = auth_result.get('user_id')
        token = auth_result.get('token')
        
        # Carica info utente
        user = user_manager.get_user(user_id)
        
        return jsonify({
            "ok": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role
            },
            "token": token
        }), 200
    
    except Exception as e:
        logger.error(f"Auth login error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/auth_logout', methods=['POST'])
def auth_logout():
    """Logout - invalida la sessione."""
    if not _user_manager_available or not user_manager:
        return jsonify({"ok": False, "error": "Auth service not available"}), 503
    
    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        
        if token:
            # Invalida sessione
            user_manager.logout(token)
        
        return jsonify({"ok": True}), 200
    
    except Exception as e:
        logger.error(f"Auth logout error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/auth_me', methods=['GET'])
def auth_me():
    """Ottieni info utente corrente dal token."""
    if not _user_manager_available or not user_manager:
        return jsonify({"ok": False, "error": "Auth service not available"}), 503
    
    try:
        # Leggi token da Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '').strip() if auth_header else ''
        
        if not token:
            return jsonify({"ok": False, "error": "Token non fornito"}), 401
        
        # Valida sessione
        session_result = user_manager.validate_session(token)
        if not session_result.get('ok'):
            return jsonify({"ok": False, "error": session_result.get('error', 'Invalid token')}), 401
        
        user_id = session_result.get('user_id')
        
        # Carica user
        user = user_manager.get_user(user_id)
        if not user:
            return jsonify({"ok": False, "error": "Utente non trovato"}), 404
        
        return jsonify({
            "ok": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Auth me error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# Generic API endpoint for method calls like api('get_templates')
@app.route('/api/<method>', methods=['POST'])
def api_method(method):
    """
    Generic API endpoint - Delega chiamate al Bridge se disponibile.
    Fallback a implementazioni dedicate per funzioni critiche web-only.
    """
    # Fallback per get_templates se Bridge non disponibile
    if method == 'get_templates':
        try:
            templates_dir = Path(__file__).parent.parent / 'templates'
            templates = []
            
            if templates_dir.exists():
                # Leggi da templates_list.json se esiste
                templates_list_file = templates_dir / 'templates_list.json'
                if templates_list_file.exists():
                    import json
                    with open(templates_list_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        templates = data.get('templates', [])
                else:
                    # Scan directory
                    for html_file in sorted(templates_dir.glob('*.html')):
                        if not html_file.name.startswith('_'):
                            template_id = html_file.stem
                            templates.append({
                                "id": template_id,
                                "name": template_id.replace('_', ' ').title(),
                                "file": html_file.name
                            })
            
            return jsonify({
                "ok": True,
                "templates": templates,
                "count": len(templates)
            }), 200
        except Exception as e:
            logger.error(f"get_templates fallback error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    
    # Se Bridge disponibile, delega a lui
    if _bridge_available and _bridge:
        try:
            # Get payload from request
            payload = request.get_json() or {}
            
            # Get Authorization header for token-based auth
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.replace('Bearer ', '').strip()
                if token and 'token' not in payload:
                    payload['token'] = token
            
            # Check if bridge has this method
            if not hasattr(_bridge, method):
                return jsonify({"ok": False, "error": f"Unknown method: {method}"}), 400
            
            # Call the bridge method
            bridge_method = getattr(_bridge, method)
            result = bridge_method(payload)
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"ok": True, "result": result}
            
            return jsonify(result), 200
            
        except Exception as e:
            logger.error(f"API method {method} error: {e}", exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500
    
    # Bridge non disponibile e nessun fallback per questo metodo
    return jsonify({
        "ok": False,
        "error": f"Method '{method}' requires Bridge which is not available in this deployment"
    }), 503


def __get_disk_free_gb():
    """Ritorna spazio libero su disco in GB."""
    try:
        import shutil
        stat = shutil.disk_usage(str(UPLOAD_FOLDER))
        return round(stat.free / (1024**3), 2)
    except:
        return -1



@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "error": "Internal server error"}), 500


def run_api(host: str = '0.0.0.0', port: int = None, debug: bool = False) -> None:
    """Avvia API server."""
    if port is None:
        port = int(os.getenv('PORT', '5000'))
    logger.info(f"Starting Cooksy API on {host}:{port}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    port = int(os.getenv('PORT', '5000'))
    run_api(debug=debug_mode, port=port)

