"""Static file and frontend routes"""
import logging
import os

from flask import Blueprint, send_from_directory

logger = logging.getLogger(__name__)

static_bp = Blueprint('static', __name__)

# Get the base directory (project root)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
ASSETS_DIR = os.path.join(BASE_DIR, 'docs', 'assets')


@static_bp.route("/")
def serve_frontend():
    """Serve the frontend index.html file"""
    return send_from_directory(FRONTEND_DIR, "index.html")


@static_bp.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve assets from the docs/assets directory"""
    try:
        return send_from_directory(ASSETS_DIR, filename)
    except:
        return "Asset not found", 404


@static_bp.route("/<path:filename>")
def serve_static_files(filename):
    """Serve static files from the frontend directory"""
    # Don't serve API routes through static file handler
    api_routes = ["m3u", "xmltv", "categories", "series", "episodes", "image-proxy", "stream-proxy", "assets"]
    if filename.split("/")[0] in api_routes:
        return "Not found", 404

    # Only serve files that exist in the frontend directory
    try:
        return send_from_directory(FRONTEND_DIR, filename)
    except:
        # If file doesn't exist in frontend, return 404
        return "File not found", 404
