#!/usr/bin/env python3
"""
Chat Room Application — Main Entry Point

Python Flask + MySQL + WebSocket 即时通讯聊天室

Usage:
    # Set required environment variables, then:
    python app.py
"""

# !! Monkey-patch must happen BEFORE any other imports that touch ssl/socket !!
from gevent.monkey import patch_all
patch_all()

import logging
import os
import sys

from flask import Flask, render_template, session, redirect, url_for, flash

from config import Config
from models import init_db
from middleware import setup_security_headers, setup_csrf, rate_limit_config
from auth import auth_bp
from files import files_bp
from chat import init_socketio

# --- Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# --- App Factory ---


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # --- Flask Config ---
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_HTTPONLY"] = Config.SESSION_COOKIE_HTTPONLY
    app.config["SESSION_COOKIE_SAMESITE"] = Config.SESSION_COOKIE_SAMESITE
    app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = Config.PERMANENT_SESSION_LIFETIME

    # --- Security Middleware ---
    setup_security_headers(app)
    setup_csrf(app)

    # --- Rate Limiting ---
    limiter = rate_limit_config(app)

    # --- Register Blueprints ---
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)

    # --- Error Handlers ---

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html" if _template_exists("404.html") else error_response(404, "页面不存在")), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html" if _template_exists("403.html") else error_response(403, "无权访问")), 403

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Internal server error")
        return render_template("500.html" if _template_exists("500.html") else error_response(500, "服务器错误")), 500

    @app.errorhandler(413)
    def too_large(e):
        return {"error": "请求体过大。"}, 413

    # --- Public Config Endpoint (for mobile/third-party clients) ---

    @app.route("/config")
    def public_config():
        """Return non-sensitive configuration needed by clients.
        The Turnstile site key IS public — it appears in the web page HTML.
        The secret key remains server-side only, never exposed."""
        from flask import jsonify
        return jsonify({
            "turnstile_site_key": Config.TURNSTILE_SITE_KEY,
            "turnstile_required_for_mobile": Config.TURNSTILE_REQUIRED_FOR_MOBILE,
            "max_file_size": Config.MAX_FILE_SIZE,
            "chunk_size": Config.CHUNK_SIZE,
            "allowed_mimetypes": sorted(Config.ALLOWED_MIMETYPES),
        })

    # --- Main Routes ---

    @app.route("/")
    def index():
        """Redirect to chat if logged in, otherwise to login."""
        if session.get("user_id"):
            return redirect(url_for("chat_page"))
        return redirect(url_for("auth.login_page"))

    @app.route("/chat")
    def chat_page():
        """Main chat interface — login required."""
        if not session.get("user_id"):
            flash("请先登录。", "warning")
            return redirect(url_for("auth.login_page"))
        return render_template("chat.html")

    return app


def error_response(code, message):
    """Simple error response."""
    return f"<h1>{code}</h1><p>{message}</p>"


def _template_exists(name):
    """Check if a template file exists."""
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    return os.path.exists(os.path.join(template_dir, name))


# --- Main ---

if __name__ == "__main__":
    # Verify required environment variables
    required_vars = ["MYSQL_PASSWORD", "SECRET_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        logger.warning(
            "未设置以下环境变量，将使用默认值（仅用于开发）：%s",
            ", ".join(missing),
        )
        logger.warning(
            "生产环境请设置：MYSQL_HOST MYSQL_USER MYSQL_PASSWORD MYSQL_DB "
            "TURNSTILE_SITE_KEY TURNSTILE_SECRET_KEY INVITE_CODE SECRET_KEY"
        )

    app = create_app()

    # Initialize database
    try:
        init_db()
        logger.info("数据库初始化完成。")
    except Exception as e:
        logger.error("数据库初始化失败：%s", e)
        logger.error("请确保 MySQL 服务已启动，并设置了正确的凭据。")
        sys.exit(1)

    # Initialize SocketIO
    socketio = init_socketio(app)

    logger.info("聊天室服务启动在 http://%s:%d", Config.HOST, Config.PORT)

    socketio.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
