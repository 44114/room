"""
Database models and schema initialization for the chat room.

Uses raw SQL with parameterized queries for maximum control and security.
"""

import logging

import pymysql

from config import Config
from utils import get_db_connection, hash_password

logger = logging.getLogger(__name__)

# -- DDL Statements --

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    INDEX idx_username (username),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_INVITE_CODES_TABLE = """
CREATE TABLE IF NOT EXISTS invite_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code_hash VARCHAR(255) NOT NULL UNIQUE,
    used_by INT NULL,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_code_hash (code_hash),
    INDEX idx_used_by (used_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    content TEXT NULL,
    file_id INT NULL,
    room VARCHAR(50) DEFAULT 'general',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_room_created (room, created_at),
    INDEX idx_sender_id (sender_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    uploader_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL UNIQUE,
    file_size BIGINT NOT NULL DEFAULT 0,
    mime_type VARCHAR(100) DEFAULT 'application/octet-stream',
    chunk_count INT DEFAULT 0,
    upload_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uploader_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_uploader_id (uploader_id),
    INDEX idx_upload_complete (upload_complete)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    csrf_token VARCHAR(128) NOT NULL,
    ip_address VARCHAR(45) DEFAULT '',
    user_agent VARCHAR(512) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

ALL_TABLES = [
    ("users", CREATE_USERS_TABLE),
    ("invite_codes", CREATE_INVITE_CODES_TABLE),
    ("messages", CREATE_MESSAGES_TABLE),
    ("files", CREATE_FILES_TABLE),
    ("sessions", CREATE_SESSIONS_TABLE),
]


def init_db() -> None:
    """Create all tables and seed the invite code if needed."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for table_name, ddl in ALL_TABLES:
                cursor.execute(ddl)
                logger.info("Ensured table %s exists.", table_name)

        # Seed the invite code from config (store as Argon2id hash)
        seed_invite_code(conn)

        conn.commit()
        logger.info("Database initialization complete.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed_invite_code(conn: pymysql.Connection) -> None:
    """Insert the invite code hash if it doesn't exist yet."""
    code_hash = hash_password(Config.INVITE_CODE)
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM invite_codes WHERE code_hash = %s",
            (code_hash,),
        )
        if cursor.fetchone() is None:
            # Remove any old unused codes to keep the table clean
            cursor.execute("DELETE FROM invite_codes WHERE used_by IS NULL")
            cursor.execute(
                "INSERT INTO invite_codes (code_hash) VALUES (%s)",
                (code_hash,),
            )
            logger.info("Seeded invite code.")


def get_db_schema_sql() -> str:
    """Return the full SQL schema as a string (for .sql export)."""
    statements = [
        "-- Chat Room Database Schema",
        f"-- Generated for MySQL/MariaDB",
        "",
        "CREATE DATABASE IF NOT EXISTS chatroom",
        "    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        "",
        "USE chatroom;",
        "",
    ]
    for _, ddl in ALL_TABLES:
        # Strip CREATE TABLE IF NOT EXISTS -> CREATE TABLE for clean export
        clean = ddl.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
        statements.append(clean.strip() + ";\n")

    return "\n".join(statements)
