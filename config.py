"""
Sensitive configuration — all values read from environment variables.
Never hardcode credentials; never commit this file with real values.
"""

import os
import secrets


class Config:
    """Application configuration."""

    # Flask
    SECRET_KEY: str = os.environ.get("SECRET_KEY", secrets.token_hex(64))

    # MySQL
    MYSQL_HOST: str = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.environ.get("MYSQL_USER", "chatroom")
    MYSQL_PASSWORD: str = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DB: str = os.environ.get("MYSQL_DB", "chatroom")

    # Cloudflare Turnstile
    TURNSTILE_SITE_KEY: str = os.environ.get("TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    TURNSTILE_SECRET_KEY: str = os.environ.get(
        "TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA"
    )

    # Invite code — raw value from env, stored as Argon2id hash in DB
    INVITE_CODE: str = os.environ.get("INVITE_CODE", "changeme")

    # Mobile clients have poor Turnstile pass rates due to WebView fingerprinting.
    # Since invite codes already provide a strong anti-bot gate, Turnstile can
    # be exempted for mobile clients. Set to True to enforce Turnstile on mobile too.
    TURNSTILE_REQUIRED_FOR_MOBILE: bool = os.environ.get(
        "TURNSTILE_REQUIRED_FOR_MOBILE", "0"
    ) == "1"

    # Session security
    SESSION_COOKIE_SECURE: bool = False  # HTTP, not HTTPS
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME: int = 1800  # 30 minutes idle timeout

    # File upload
    MAX_CONTENT_LENGTH: int = 5 * 1024 * 1024  # 5 MB per chunk
    MAX_FILE_SIZE: int = 4 * 1024 * 1024 * 1024  # 4 GB total
    UPLOAD_FOLDER: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    CHUNK_SIZE: int = 5 * 1024 * 1024  # 5 MB per chunk

    # Allowed file MIME types (whitelist)
    ALLOWED_MIMETYPES: set = {
        # Images
        "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
        # Documents
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain", "text/csv", "text/markdown",
        # Archives
        "application/zip", "application/x-rar-compressed",
        "application/x-7z-compressed", "application/gzip",
        "application/x-tar",
        # Code (non-executable text)
        "application/json", "text/html", "text/css", "text/javascript",
        "application/xml",
        # Audio/Video
        "audio/mpeg", "audio/wav", "audio/ogg",
        "video/mp4", "video/webm",
    }

    # Forbidden file extensions (additional check)
    FORBIDDEN_EXTENSIONS: set = {
        "exe", "dll", "so", "dylib", "sh", "bash", "zsh",
        "php", "jsp", "asp", "aspx", "cgi", "pl", "py", "rb",
        "jar", "class", "war", "ear",
        "bat", "cmd", "ps1", "vbs", "msi",
        "htm", "html", "xhtml", "shtml",  # served as text/plain anyway
    }

    # Argon2id parameters
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_PARALLELISM: int = 4
    ARGON2_HASH_LENGTH: int = 32
    ARGON2_SALT_LENGTH: int = 16

    # Rate limiting
    RATELIMIT_ENABLED: bool = True
    RATELIMIT_STORAGE_URI: str = "memory://"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 9888
    DEBUG: bool = os.environ.get("FLASK_DEBUG", "0") == "1"
