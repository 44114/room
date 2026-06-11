"""
WebSocket event handlers using Flask-SocketIO.

Handles:
- Real-time text messaging
- User presence (join/leave notifications)
- Typing indicators
- File message broadcasting
"""

import logging
from datetime import datetime

from flask import session, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

from config import Config
from utils import get_db_connection, sanitize_plain_text, sanitize_html

logger = logging.getLogger(__name__)

# SocketIO will be initialized in app.py
socketio: SocketIO = None


def init_socketio(app):
    """Initialize SocketIO with the Flask app.

    Caller must have already called gevent.monkey.patch_all() before importing
    this module (see app.py).
    """
    global socketio

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="gevent",
        ping_timeout=30,
        ping_interval=15,
        max_http_buffer_size=Config.CHUNK_SIZE,
    )
    _register_events()
    return socketio


def _register_events():
    """Register all WebSocket event handlers."""

    @socketio.on("connect")
    def handle_connect():
        """Verify authentication on WebSocket connection."""
        if not session.get("user_id"):
            logger.warning("WebSocket connect rejected: not logged in")
            return False  # Reject connection

        room = "general"
        join_room(room)
        session["current_room"] = room

        emit("system_message", {
            "type": "join",
            "username": session.get("username"),
            "message": f"{session.get('username')} 进入了聊天室",
            "timestamp": datetime.utcnow().isoformat(),
        }, room=room)

        logger.info("User %s connected to room %s", session.get("username"), room)

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle user disconnect."""
        room = session.get("current_room", "general")
        emit("system_message", {
            "type": "leave",
            "username": session.get("username"),
            "message": f"{session.get('username')} 离开了聊天室",
            "timestamp": datetime.utcnow().isoformat(),
        }, room=room)

        leave_room(room)

    @socketio.on("send_message")
    def handle_message(data):
        """
        Handle incoming text message: sanitize, persist, broadcast.

        Expected data format: {"content": "message text"}
        """
        if not session.get("user_id"):
            emit("error", {"error": "未登录。"})
            return

        raw_content = data.get("content", "")
        if not raw_content or not raw_content.strip():
            return

        # Sanitize and truncate
        content = sanitize_plain_text(raw_content, max_length=10000)

        if not content:
            return

        user_id = session["user_id"]
        username = session["username"]
        room = session.get("current_room", "general")
        timestamp = datetime.utcnow()

        # Persist to database
        message_id = _save_message(user_id, content, None, room)

        # Broadcast to room
        message_data = {
            "id": message_id,
            "type": "text",
            "sender_id": user_id,
            "username": username,
            "content": content,
            "timestamp": timestamp.isoformat(),
        }
        emit("new_message", message_data, room=room)

    @socketio.on("send_file_message")
    def handle_file_message(data):
        """
        Handle file notification: after upload completes, notify the room.

        Expected data format: {"file_id": 123, "filename": "...", "file_size": ...}
        """
        if not session.get("user_id"):
            emit("error", {"error": "未登录。"})
            return

        file_id = data.get("file_id")
        filename = sanitize_html(data.get("filename", "unknown"))
        file_size = data.get("file_size", 0)

        if not file_id:
            return

        user_id = session["user_id"]
        username = session["username"]
        room = session.get("current_room", "general")
        timestamp = datetime.utcnow()

        # Persist
        message_id = _save_message(user_id, f"[文件] {filename}", file_id, room)

        message_data = {
            "id": message_id,
            "type": "file",
            "sender_id": user_id,
            "username": username,
            "content": f"[文件] {filename}",
            "file_id": file_id,
            "filename": filename,
            "file_size": file_size,
            "timestamp": timestamp.isoformat(),
        }
        emit("new_message", message_data, room=room)

    @socketio.on("typing")
    def handle_typing(data):
        """Broadcast typing indicator."""
        if not session.get("user_id"):
            return
        room = session.get("current_room", "general")
        emit("user_typing", {
            "username": session.get("username"),
            "typing": data.get("typing", False),
        }, room=room, include_self=False)


def _save_message(sender_id: int, content: str, file_id: int | None, room: str) -> int:
    """Persist a message to the database. Returns message_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO messages (sender_id, content, file_id, room)
                   VALUES (%s, %s, %s, %s)""",
                (sender_id, content, file_id, room),
            )
            message_id = cursor.lastrowid
        conn.commit()
        return message_id
    except Exception as e:
        conn.rollback()
        logger.error("Failed to save message: %s", e)
        return 0
    finally:
        conn.close()
