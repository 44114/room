"""
Security middleware for the chat room application.

Provides:
- CSRF protection (double-submit cookie pattern)
- Security HTTP response headers
- Rate limiting on sensitive endpoints
- Input validation
"""

import logging
from functools import wraps

from flask import request, session, make_response, jsonify, current_app, g

from config import Config
from utils import generate_csrf_token, constant_time_compare, sanitize_html

logger = logging.getLogger(__name__)


def setup_security_headers(app):
    """Add security headers to every response."""

    @app.after_request
    def add_security_headers(response):
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS protection for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://challenges.cloudflare.com https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "frame-src https://challenges.cloudflare.com; "
            "connect-src 'self' ws: wss:; "
            "media-src 'self'; "
            "font-src 'self'"
        )
        return response


def get_or_create_csrf_token():
    """Get the current CSRF token from session, or create a new one."""
    if "csrf_token" not in session:
        session["csrf_token"] = generate_csrf_token()
        session.modified = True
    return session["csrf_token"]


def csrf_protect(f):
    """Decorator: require valid CSRF token on state-changing methods."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return f(*args, **kwargs)

        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        session_token = session.get("csrf_token", "")

        if not token or not session_token:
            logger.warning("CSRF: missing token (client=%s, session=%s)",
                           bool(token), bool(session_token))
            return jsonify({"error": "CSRF token missing"}), 403

        if not constant_time_compare(token, session_token):
            logger.warning("CSRF: token mismatch")
            return jsonify({"error": "CSRF token invalid"}), 403

        return f(*args, **kwargs)

    return decorated


def csrf_exempt(f):
    """Mark a view as CSRF-exempt."""
    f._csrf_exempt = True
    return f


def validate_input(f):
    """Decorator: basic input sanitization on request data."""

    @wraps(f)
    def decorated(*args, **kwargs):
        # Sanitize form data
        if request.form:
            sanitized = {}
            for key, value in request.form.items():
                if isinstance(value, str) and key != "csrf_token":
                    sanitized[key] = sanitize_html(value)
                else:
                    sanitized[key] = value
            g.clean_form = sanitized

        # Sanitize JSON data
        if request.is_json:
            json_data = request.get_json(silent=True) or {}
            sanitized = {}
            for key, value in json_data.items():
                if isinstance(value, str) and key != "csrf_token":
                    sanitized[key] = sanitize_html(value)
                elif isinstance(value, dict):
                    sanitized[key] = {
                        k: sanitize_html(v) if isinstance(v, str) else v
                        for k, v in value.items()
                    }
                else:
                    sanitized[key] = value
            g.clean_json = sanitized

        return f(*args, **kwargs)

    return decorated


def setup_csrf(app):
    """Configure CSRF token to be available in all templates and responses."""

    @app.before_request
    def ensure_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = generate_csrf_token()

    @app.after_request
    def set_csrf_cookie(response):
        # Expose CSRF token to JavaScript via a custom header
        # (not a cookie — avoids the "double-submit cookie" confusion
        #  while staying secure because we check against session value)
        response.headers["X-CSRF-Token"] = session.get("csrf_token", "")
        return response


def rate_limit_config(app):
    """Configure rate limiting."""
    # Import here to avoid circular import issues
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=["200 per day", "50 per hour"],
            storage_uri=Config.RATELIMIT_STORAGE_URI,
        )
        return limiter
    except ImportError:
        logger.warning("flask-limiter not installed; rate limiting disabled.")
        return None
