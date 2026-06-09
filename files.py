"""
File handling blueprint — chunked upload and download.

Supports:
- Chunked upload up to 4 GB total (5 MB per chunk)
- Chunked download with HTTP Range support
- MIME type validation and file content scanning
- Auth check on all downloads
"""

import hashlib
import logging
import os
import uuid

from flask import (
    Blueprint, request, session, jsonify, send_file, Response,
    current_app, g,
)

from config import Config
from middleware import csrf_protect, validate_input
from utils import (
    get_db_connection,
    require_login,
    validate_file_mime,
    is_allowed_extension,
    scan_file_for_scripts,
    generate_stored_filename,
    sanitize_html,
)

logger = logging.getLogger(__name__)

files_bp = Blueprint("files", __name__, url_prefix="/files")

# Ensure upload directory exists
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


@files_bp.route("/upload/init", methods=["POST"])
@require_login
@csrf_protect
@validate_input
def upload_init():
    """
    Initialize a chunked file upload session.
    Client sends filename, file_size, mime_type, total_chunks, and chunk_size.
    """
    data = g.get("clean_json") or {}

    filename = sanitize_html(data.get("filename", "").strip())
    file_size = int(data.get("file_size", 0))
    mime_type = data.get("mime_type", "application/octet-stream")
    total_chunks = int(data.get("total_chunks", 0))
    chunk_size = int(data.get("chunk_size", Config.CHUNK_SIZE))

    # Validation
    errors = []
    if not filename:
        errors.append("文件名为空。")
    if file_size <= 0:
        errors.append("文件大小无效。")
    if file_size > Config.MAX_FILE_SIZE:
        errors.append(f"文件大小超过限制 ({Config.MAX_FILE_SIZE // (1024**3)} GB)。")
    if total_chunks <= 0:
        errors.append("分块数量无效。")
    if chunk_size > Config.MAX_CONTENT_LENGTH:
        errors.append("分块大小超出限制。")
    if not is_allowed_extension(filename):
        errors.append("文件类型不允许。")

    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    # Create file record
    stored_name = generate_stored_filename(filename)
    upload_id = uuid.uuid4().hex

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO files
                   (uploader_id, filename, stored_name, file_size, mime_type, chunk_count, upload_complete)
                   VALUES (%s, %s, %s, %s, %s, %s, FALSE)""",
                (session["user_id"], filename, stored_name, file_size, mime_type, total_chunks),
            )
            file_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Upload init failed: %s", e)
        return jsonify({"error": "初始化上传失败。"}), 500
    finally:
        conn.close()

    # Create temp directory for chunks
    chunk_dir = os.path.join(Config.UPLOAD_FOLDER, upload_id)
    os.makedirs(chunk_dir, exist_ok=True)

    logger.info(
        "Upload initiated: file=%s, size=%d, chunks=%d, upload_id=%s",
        filename, file_size, total_chunks, upload_id,
    )

    return jsonify({
        "success": True,
        "file_id": file_id,
        "upload_id": upload_id,
        "chunk_size": chunk_size,
    }), 201


@files_bp.route("/upload/chunk", methods=["POST"])
@require_login
@csrf_protect
def upload_chunk():
    """
    Receive a file chunk.
    Expects multipart form data: chunk_index (int), upload_id (str), file_id (int),
    and the chunk data as a file.
    """
    upload_id = request.form.get("upload_id", "")
    file_id = request.form.get("file_id", "")
    chunk_index = request.form.get("chunk_index", "")

    if not upload_id or not file_id or chunk_index == "":
        return jsonify({"error": "缺少上传参数。"}), 400

    # Validate upload_id is a hex UUID (prevents path traversal)
    import re
    if not re.match(r'^[a-f0-9]{32}$', upload_id):
        return jsonify({"error": "上传ID无效。"}), 400

    try:
        file_id = int(file_id)
        chunk_index = int(chunk_index)
    except (ValueError, TypeError):
        return jsonify({"error": "参数类型错误。"}), 400

    # Verify file record belongs to this user and is not complete
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, uploader_id, stored_name, chunk_count FROM files WHERE id = %s",
                (file_id,),
            )
            file_record = cursor.fetchone()

        if not file_record:
            return jsonify({"error": "文件记录不存在。"}), 404

        if file_record["uploader_id"] != session["user_id"]:
            return jsonify({"error": "无权上传此文件。"}), 403

        if chunk_index < 0 or chunk_index >= file_record["chunk_count"]:
            return jsonify({"error": "分块索引无效。"}), 400
    finally:
        conn.close()

    # Get chunk data
    if "chunk" not in request.files:
        return jsonify({"error": "未找到文件分块。"}), 400

    chunk_file = request.files["chunk"]
    chunk_data = chunk_file.read()

    if len(chunk_data) > Config.MAX_CONTENT_LENGTH:
        return jsonify({"error": "分块大小超出限制。"}), 400

    # Validate first chunk
    if chunk_index == 0:
        is_valid, detected_mime = validate_file_mime(chunk_data, file_record["stored_name"])
        if not is_valid:
            # Clean up
            _cleanup_upload(upload_id, file_id)
            return jsonify({"error": f"文件类型不允许 ({detected_mime})。"}), 400

        if not scan_file_for_scripts(chunk_data):
            _cleanup_upload(upload_id, file_id)
            return jsonify({"error": "文件内容包含不安全代码。"}), 400

    # Write chunk to disk
    chunk_dir = os.path.join(Config.UPLOAD_FOLDER, upload_id)
    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:06d}")

    try:
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
    except IOError as e:
        logger.error("Failed to write chunk: %s", e)
        return jsonify({"error": "写入分块失败。"}), 500

    return jsonify({
        "success": True,
        "chunk_index": chunk_index,
        "received_size": len(chunk_data),
    }), 200


@files_bp.route("/upload/complete", methods=["POST"])
@require_login
@csrf_protect
@validate_input
def upload_complete():
    """
    Finalize a chunked upload: reassemble chunks, verify file, mark complete.
    """
    data = g.get("clean_json") or {}
    upload_id = data.get("upload_id", "")
    file_id = data.get("file_id", "")

    if not upload_id or not file_id:
        return jsonify({"error": "缺少上传参数。"}), 400

    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        return jsonify({"error": "文件ID无效。"}), 400

    # Verify ownership
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, uploader_id, filename, stored_name, file_size, chunk_count FROM files WHERE id = %s",
                (file_id,),
            )
            file_record = cursor.fetchone()

        if not file_record:
            return jsonify({"error": "文件记录不存在。"}), 404

        if file_record["uploader_id"] != session["user_id"]:
            return jsonify({"error": "无权完成此上传。"}), 403
    finally:
        conn.close()

    # Reassemble chunks
    chunk_dir = os.path.join(Config.UPLOAD_FOLDER, upload_id)
    final_path = os.path.join(Config.UPLOAD_FOLDER, file_record["stored_name"])

    try:
        total_size = 0
        with open(final_path, "wb") as outfile:
            for i in range(file_record["chunk_count"]):
                chunk_path = os.path.join(chunk_dir, f"chunk_{i:06d}")
                if not os.path.exists(chunk_path):
                    return jsonify({"error": f"缺少分块 {i}。"}), 400

                with open(chunk_path, "rb") as infile:
                    chunk_data = infile.read()
                    outfile.write(chunk_data)
                    total_size += len(chunk_data)

        if total_size != file_record["file_size"]:
            os.remove(final_path)
            return jsonify({
                "error": f"文件大小不匹配 (期望 {file_record['file_size']}, 实际 {total_size})。"
            }), 400

        # Mark upload complete
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE files SET upload_complete = TRUE WHERE id = %s",
                    (file_id,),
                )
            conn.commit()
        finally:
            conn.close()

        # Clean up chunk directory
        import shutil
        shutil.rmtree(chunk_dir, ignore_errors=True)

        logger.info("Upload complete: file_id=%d, size=%d", file_id, total_size)

        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": file_record["filename"],
            "file_size": total_size,
        }), 200

    except Exception as e:
        logger.error("Upload complete failed: %s", e)
        return jsonify({"error": "完成上传失败。"}), 500


@files_bp.route("/download/<int:file_id>", methods=["GET"])
@require_login
def download_file(file_id):
    """
    Download a file with Range support for chunked downloads.
    Only logged-in users may download.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, uploader_id, filename, stored_name, file_size, mime_type, upload_complete
                   FROM files WHERE id = %s""",
                (file_id,),
            )
            file_record = cursor.fetchone()

        if not file_record:
            return jsonify({"error": "文件不存在。"}), 404

        if not file_record["upload_complete"]:
            return jsonify({"error": "文件尚未上传完成。"}), 404
    finally:
        conn.close()

    file_path = os.path.join(Config.UPLOAD_FOLDER, file_record["stored_name"])

    if not os.path.exists(file_path):
        logger.error("File record %d exists but file is missing on disk: %s", file_id, file_path)
        return jsonify({"error": "文件数据丢失。"}), 500

    # Handle Range requests for chunked download
    range_header = request.headers.get("Range")
    if range_header:
        return _stream_range_response(file_path, file_record, range_header)

    # Full download (for smaller files)
    return send_file(
        file_path,
        mimetype=file_record["mime_type"],
        as_attachment=True,
        download_name=file_record["filename"],
        conditional=True,
    )


def _stream_range_response(file_path, file_record, range_header):
    """Handle HTTP Range requests for chunked downloads."""
    file_size = file_record["file_size"]

    try:
        range_type, range_value = range_header.replace(" ", "").split("=")
        start_str, end_str = range_value.split("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except (ValueError, AttributeError):
        return jsonify({"error": "无效的 Range 头。"}), 416

    if start >= file_size or end >= file_size or start > end:
        return jsonify({"error": "Range 超出文件大小。"}), 416

    length = end - start + 1

    def generate_chunks():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            chunk_size = Config.CHUNK_SIZE
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    response = Response(
        generate_chunks(),
        status=206,
        mimetype=file_record["mime_type"],
        direct_passthrough=True,
    )
    response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    response.headers["Content-Length"] = str(length)
    response.headers["Accept-Ranges"] = "bytes"
    # Sanitize filename to prevent HTTP response splitting (strip CR/LF)
    safe_filename = file_record["filename"].replace("\r", "").replace("\n", "")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{safe_filename}"'
    )
    return response


@files_bp.route("/info/<int:file_id>", methods=["GET"])
@require_login
def file_info(file_id):
    """Get file metadata."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, filename, file_size, mime_type, upload_complete, created_at
                   FROM files WHERE id = %s""",
                (file_id,),
            )
            f = cursor.fetchone()

        if not f:
            return jsonify({"error": "文件不存在。"}), 404
    finally:
        conn.close()

    return jsonify(f), 200


# --- Helpers ---


def _cleanup_upload(upload_id: str, file_id: int) -> None:
    """Clean up a failed upload."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM files WHERE id = %s", (file_id,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    import shutil
    chunk_dir = os.path.join(Config.UPLOAD_FOLDER, upload_id)
    shutil.rmtree(chunk_dir, ignore_errors=True)
