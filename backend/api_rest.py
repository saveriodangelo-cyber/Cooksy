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

# Config
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['JSON_SORT_KEYS'] = False
UPLOAD_FOLDER = Path.home() / 'AppData' / 'Local' / 'Cooksy' / 'uploads'
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
    """Lista template disponibili."""
    try:
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


def run_api(host: str = '0.0.0.0', port: int = 5000, debug: bool = False) -> None:
    """Avvia API server."""
    logger.info(f"Starting Cooksy API on {host}:{port}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    port = int(os.getenv('PORT', '5000'))
    run_api(debug=debug_mode, port=port)

