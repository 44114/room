"""
Authentication blueprint — handles registration, login, logout,
password change, and account deletion.

All routes use parameterized SQL queries to prevent SQL injection.
All user input is sanitized for XSS prevention.
"""

import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, request, session, redirect, url_for, flash,
    render_template, jsonify, g,
)

from config import Config
from middleware import csrf_protect, validate_input, get_or_create_csrf_token
from utils import (
    get_db_connection,
    hash_password,
    verify_password,
    sanitize_plain_text,
    sanitize_html,
    is_safe_username,
    is_strong_password,
    require_login,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# --- Page Routes ---


@auth_bp.route("/register")
def register_page():
    """Render registration page."""
    csrf_token = get_or_create_csrf_token()
    return render_template(
        "register.html",
        csrf_token=csrf_token,
    )


@auth_bp.route("/login")
def login_page():
    """Render login page."""
    csrf_token = get_or_create_csrf_token()
    return render_template(
        "login.html",
        csrf_token=csrf_token,
    )


@auth_bp.route("/account")
@require_login
def account_page():
    """Render account management page."""
    csrf_token = get_or_create_csrf_token()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT username, created_at FROM users WHERE id = %s AND is_active = TRUE",
                (session["user_id"],),
            )
            user = cursor.fetchone()
    finally:
        conn.close()

    if not user:
        session.clear()
        flash("账号不存在或已被注销。", "error")
        return redirect(url_for("auth.login_page"))

    return render_template(
        "account.html",
        csrf_token=csrf_token,
        user=user,
    )


# --- API Routes ---


@auth_bp.route("/register", methods=["POST"])
@csrf_protect
@validate_input
def register():
    """Handle user registration."""
    data = g.get("clean_form") or g.get("clean_json") or {}

    username = sanitize_plain_text(data.get("username", "").strip())
    password = data.get("password", "")
    password_confirm = data.get("password_confirm", "")
    invite_code = data.get("invite_code", "").strip()

    # --- Validation ---
    errors = []

    if not is_safe_username(username):
        errors.append("用户名必须是3-30位字母、数字或下划线。")

    if password != password_confirm:
        errors.append("两次输入的密码不一致。")

    if not is_strong_password(password):
        errors.append("密码至少8位，需包含大写字母、小写字母、数字、特殊字符中的至少三种。")

    if not invite_code:
        errors.append("请输入邀请码。")

    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    # Verify invite code and create user in a single transaction
    # to prevent race conditions on invite code usage
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check username availability
            cursor.execute(
                "SELECT id FROM users WHERE username = %s",
                (username,),
            )
            if cursor.fetchone():
                return jsonify({"error": "用户名已被占用。"}), 409

            # Verify invite code within the transaction
            code_hash = hash_password(invite_code)
            cursor.execute(
                "SELECT id, code_hash FROM invite_codes WHERE used_by IS NULL FOR UPDATE"
            )
            unused = cursor.fetchall()

            code_valid = False
            for row in unused:
                if verify_password(invite_code, row["code_hash"]):
                    code_valid = True
                    break

            if not code_valid:
                return jsonify({"error": "邀请码无效或已被使用。"}), 400

            # Create user
            password_hash = hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash),
            )
            user_id = cursor.lastrowid

            # Mark invite code as used (atomically)
            cursor.execute(
                """UPDATE invite_codes SET used_by = %s, used_at = NOW()
                   WHERE used_by IS NULL
                   ORDER BY id LIMIT 1""",
                (user_id,),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Registration failed: %s", e)
        return jsonify({"error": "注册失败，请稍后重试。"}), 500
    finally:
        conn.close()

    # Auto-login
    _create_session(user_id, username, request)

    logger.info("User %s (id=%d) registered successfully.", username, user_id)
    return jsonify({"success": True, "redirect": url_for("chat_page")}), 201


@auth_bp.route("/login", methods=["POST"])
@csrf_protect
@validate_input
def login():
    """Handle user login."""
    data = g.get("clean_form") or g.get("clean_json") or {}

    username = sanitize_plain_text(data.get("username", "").strip())
    password = data.get("password", "")
    remember_me = data.get("remember_me") in ("true", "1", True, "on")

    errors = []
    if not username:
        errors.append("请输入用户名。")
    if not password:
        errors.append("请输入密码。")

    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    # Rate limiting: delay response to slow brute force
    import time
    time.sleep(0.5)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s AND is_active = TRUE",
                (username,),
            )
            user = cursor.fetchone()

        if not user:
            # Constant-time compare against a dummy hash to mask timing
            verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy")
            return jsonify({"error": "用户名或密码错误。"}), 401

        if not verify_password(password, user["password_hash"]):
            return jsonify({"error": "用户名或密码错误。"}), 401

    finally:
        conn.close()

    _create_session(user["id"], user["username"], request, remember_me)

    logger.info("User %s logged in.", username)
    return jsonify({"success": True, "redirect": url_for("chat_page")}), 200


@auth_bp.route("/logout", methods=["POST"])
@csrf_protect
def logout():
    """Handle user logout."""
    _destroy_session()
    flash("您已成功退出登录。", "info")
    return jsonify({"success": True, "redirect": url_for("auth.login_page")}), 200


@auth_bp.route("/change-password", methods=["POST"])
@require_login
@csrf_protect
@validate_input
def change_password():
    """Handle password change."""
    data = g.get("clean_form") or g.get("clean_json") or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    new_password_confirm = data.get("new_password_confirm", "")

    errors = []
    if not current_password:
        errors.append("请输入当前密码。")
    if new_password != new_password_confirm:
        errors.append("两次输入的新密码不一致。")
    if not is_strong_password(new_password):
        errors.append("新密码至少8位，需包含大写字母、小写字母、数字、特殊字符中的至少三种。")

    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash FROM users WHERE id = %s AND is_active = TRUE",
                (session["user_id"],),
            )
            user = cursor.fetchone()

        if not user:
            session.clear()
            return jsonify({"error": "账号不存在。"}), 404

        if not verify_password(current_password, user["password_hash"]):
            return jsonify({"error": "当前密码错误。"}), 401

        new_hash = hash_password(new_password)
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (new_hash, session["user_id"]),
            )

        conn.commit()
        logger.info("User %d changed password.", session["user_id"])
    except Exception as e:
        conn.rollback()
        logger.error("Password change failed: %s", e)
        return jsonify({"error": "修改密码失败，请重试。"}), 500
    finally:
        conn.close()

    return jsonify({"success": True, "message": "密码修改成功。"}), 200


@auth_bp.route("/delete-account", methods=["POST"])
@require_login
@csrf_protect
@validate_input
def delete_account():
    """Handle account deletion (soft delete)."""
    data = g.get("clean_form") or g.get("clean_json") or {}

    password = data.get("password", "")

    if not password:
        return jsonify({"error": "请输入密码以确认注销。"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash FROM users WHERE id = %s AND is_active = TRUE",
                (session["user_id"],),
            )
            user = cursor.fetchone()

        if not user:
            session.clear()
            return jsonify({"error": "账号不存在。"}), 404

        if not verify_password(password, user["password_hash"]):
            return jsonify({"error": "密码错误。"}), 401

        with conn.cursor() as cursor:
            # Soft delete: mark inactive
            cursor.execute(
                "UPDATE users SET is_active = FALSE WHERE id = %s",
                (session["user_id"],),
            )

        conn.commit()
        logger.info("User %d deleted account.", session["user_id"])
    except Exception as e:
        conn.rollback()
        logger.error("Account deletion failed: %s", e)
        return jsonify({"error": "注销账号失败，请重试。"}), 500
    finally:
        conn.close()

    _destroy_session()
    return jsonify({"success": True, "message": "账号已注销。", "redirect": url_for("auth.login_page")}), 200


@auth_bp.route("/check", methods=["GET"])
def check():
    """Return current login status."""
    if session.get("user_id"):
        return jsonify({
            "logged_in": True,
            "username": session.get("username"),
            "user_id": session.get("user_id"),
        })
    return jsonify({"logged_in": False})


# --- Helpers ---


def _verify_invite_code(code: str) -> bool:
    """Verify an invite code by comparing against stored Argon2id hashes."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, code_hash FROM invite_codes WHERE used_by IS NULL"
            )
            unused = cursor.fetchall()

        for row in unused:
            if verify_password(code, row["code_hash"]):
                return True
        return False
    finally:
        conn.close()


def _create_session(user_id: int, username: str, request, remember: bool = False) -> None:
    """Create and persist a user session with CSRF token."""
    session.clear()  # Regenerate session ID
    session["user_id"] = user_id
    session["username"] = username
    session["csrf_token"] = generate_csrf_token()
    session["logged_in_at"] = datetime.utcnow().isoformat()

    if remember:
        session.permanent = True
        _persist_session(user_id, session["csrf_token"], request)
    else:
        session.permanent = False

    session.modified = True


def _persist_session(user_id: int, csrf_token: str, request) -> None:
    """Store session record in database for remember-me."""
    conn = get_db_connection()
    try:
        session_id = session.get("_id", request.cookies.get("session", ""))
        expires = datetime.utcnow() + timedelta(days=30)
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO sessions (session_id, user_id, csrf_token, ip_address, user_agent, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE csrf_token = VALUES(csrf_token),
                                           expires_at = VALUES(expires_at)""",
                (
                    str(session_id), user_id, csrf_token,
                    request.remote_addr or "",
                    request.user_agent.string[:500] if request.user_agent else "",
                    expires,
                ),
            )
        conn.commit()
    except Exception as e:
        logger.warning("Failed to persist session: %s", e)
    finally:
        conn.close()


def _destroy_session() -> None:
    """Clear the current session."""
    session.clear()
