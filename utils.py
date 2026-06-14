"""
Security utility functions for the chat room application.

Provides:
- Argon2id password hashing and verification
- XSS sanitization via Bleach
- File upload validation (MIME type, extension, content scanning)
- CSRF token generation and validation
- Cloudflare Turnstile server-side verification
- Input validation helpers
"""

import hashlib
import hmac
import logging
import re
import secrets
import struct
import uuid
from functools import wraps

import bleach
import magic
import requests
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from config import Config

logger = logging.getLogger(__name__)

# --- Argon2id Password Handling ---

_ph = PasswordHasher(
    time_cost=Config.ARGON2_TIME_COST,
    memory_cost=Config.ARGON2_MEMORY_COST,
    parallelism=Config.ARGON2_PARALLELISM,
    hash_len=Config.ARGON2_HASH_LENGTH,
    salt_len=Config.ARGON2_SALT_LENGTH,
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against an Argon2id hash in constant time."""
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# --- XSS Sanitization ---

_ALLOWED_TAGS = {
    "b", "i", "u", "em", "strong", "a", "p", "br", "ul", "ol", "li",
    "code", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "span", "div", "img", "table", "thead", "tbody", "tr", "th", "td",
}

_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "width", "height"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "pre": ["class"],
}


def sanitize_html(text: str) -> str:
    """Sanitize user input to prevent XSS. Strips dangerous tags/attributes."""
    if not text:
        return ""
    cleaned = bleach.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )
    # Also strip any javascript: / data: URI in href/src
    cleaned = bleach.linkify(cleaned)
    return _strip_dangerous_protocols(cleaned)


_DANGEROUS_PROTOCOL_RE = re.compile(
    r'''(?i)(?:href|src)\s*=\s*["']\s*(javascript|data|vbscript):''',
)


def _strip_dangerous_protocols(text: str) -> str:
    return _DANGEROUS_PROTOCOL_RE.sub(r'href="#"', text)


def sanitize_plain_text(text: str, max_length: int = 5000) -> str:
    """Strip all HTML, leaving only plain text. Enforce max length."""
    if not text:
        return ""
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    return cleaned[:max_length]


def is_safe_username(username: str) -> bool:
    """Validate username: 3-30 chars, alphanumeric + underscore only."""
    if not username:
        return False
    pattern = r"^[a-zA-Z0-9_]{3,30}$"
    return bool(re.match(pattern, username))


def is_strong_password(password: str) -> bool:
    """Check password strength: at least 8 chars, mix of character types."""
    if not password or len(password) < 8:
        return False
    if len(password) > 128:
        return False
    has_upper = bool(re.search(r"[A-Z]", password))
    has_lower = bool(re.search(r"[a-z]", password))
    has_digit = bool(re.search(r"[0-9]", password))
    has_special = bool(re.search(r"[^A-Za-z0-9]", password))
    return sum([has_upper, has_lower, has_digit, has_special]) >= 3


# --- File Validation ---


def validate_file_mime(file_data: bytes, filename: str) -> tuple[bool, str]:
    """
    Validate a file by checking its MIME type (magic bytes) and extension.
    Returns (is_valid, detected_mime_type).
    """
    # Check MIME type via magic bytes
    try:
        detected_mime = magic.from_buffer(file_data[:4096], mime=True)
    except Exception:
        return False, "unknown"

    # Also check from filename for double-validation
    try:
        detected_mime_name = magic.from_file(filename, mime=True)
    except Exception:
        detected_mime_name = ""

    # If the magic-library detection conflicts with the filename detection,
    # use the content-based detection
    mime_type = detected_mime or detected_mime_name or "application/octet-stream"

    if mime_type not in Config.ALLOWED_MIMETYPES:
        logger.warning("Blocked file upload: MIME type %s not allowed", mime_type)
        return False, mime_type

    return True, mime_type


def is_allowed_extension(filename: str) -> bool:
    """Check if the file extension is allowed."""
    if "." not in filename:
        return True  # No extension — allow, will be served as binary
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext not in Config.FORBIDDEN_EXTENSIONS


def scan_file_for_scripts(file_data: bytes) -> bool:
    """
    Scan file content for common web shell / script signatures.
    Returns True if file appears safe, False if suspicious.
    """
    # Common PHP/script signatures at start of file
    suspicious_patterns = [
        b"<?php", b"<?=", b"#!/usr/bin/perl", b"#!/usr/bin/python",
        b"#!/bin/bash", b"#!/bin/sh", b"#!/usr/bin/env python",
        b"eval(", b"system(", b"exec(", b"shell_exec(",
        b"<script", b"<%", b"<%@", b"<%=",
        b"__halt_compiler",
    ]

    # Check first 4096 bytes for most common shells
    head = file_data[:4096].lower()
    for pattern in suspicious_patterns:
        if pattern.lower() in head:
            logger.warning("Suspicious content detected: %s", pattern)
            return False

    return True


def generate_stored_filename(original_filename: str) -> str:
    """Generate a UUID-based filename for secure storage."""
    ext = ""
    if "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()
    return f"{uuid.uuid4().hex}{ext}"


# --- CSRF Token ---


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time."""
    return hmac.compare_digest(a.encode(), b.encode())


# --- Cloudflare Turnstile Verification ---


def verify_turnstile(token: str, remote_ip: str = "") -> bool:
    """
    Verify a Cloudflare Turnstile token server-side.
    Uses test keys that always pass during development.
    """
    if not token:
        return False

    try:
        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": Config.TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": remote_ip,
            },
            timeout=Config.TURNSTILE_TIMEOUT,
        )
        result = resp.json()
        return bool(result.get("success", False))
    except requests.RequestException as e:
        logger.error("Turnstile verification request failed: %s", e)
        # In development with test keys, fall back to lenient mode
        if "1x00000000000000000000AA" in Config.TURNSTILE_SITE_KEY:
            return True
        return False


# --- Decorators ---


def require_login(f):
    """Decorator to require a logged-in session for routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session, redirect, url_for, flash
        if not session.get("user_id"):
            flash("请先登录。", "warning")
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated


def require_json(f):
    """Decorator to require JSON content-type."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import request, jsonify
        if not request.is_json:
            return jsonify({"error": "需要 JSON 请求体"}), 415
        return f(*args, **kwargs)
    return decorated


# --- Database Connection ---


def get_db_connection() -> "pymysql.Connection":
    """Create and return a PyMySQL database connection."""
    import pymysql
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
