/**
 * Chat Room Client — WebSocket messaging + chunked file upload/download
 *
 * Uses SocketIO for real-time messaging and HTTP for file chunk transfer.
 * File size limit: 4 GB total, 5 MB per chunk.
 */

(function () {
    'use strict';

    // --- Configuration ---
    var CHUNK_SIZE = 5 * 1024 * 1024;  // 5 MB
    var MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024;  // 4 GB

    // --- DOM Elements ---
    var messagesEl = document.getElementById('chat-messages');
    var messageInput = document.getElementById('message-input');
    var sendBtn = document.getElementById('send-btn');
    var fileUploadBtn = document.getElementById('file-upload-btn');
    var fileInput = document.getElementById('file-input');
    var uploadProgressEl = document.getElementById('upload-progress');
    var uploadFilenameEl = document.getElementById('upload-filename');
    var uploadPercentEl = document.getElementById('upload-percent');
    var progressFillEl = document.getElementById('progress-fill');
    var connectionStatusEl = document.getElementById('connection-status');
    var typingIndicatorEl = document.getElementById('typing-indicator');
    var onlineUsersList = document.getElementById('online-users-list');

    // --- SocketIO Connection ---
    var socket = io({
        transports: ['websocket'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 30000,
    });

    // --- Connection Event Handlers ---
    socket.on('connect', function () {
        connectionStatusEl.textContent = '🟢 已连接';
        connectionStatusEl.className = 'status-connected';
        addSystemMessage('已连接到聊天室');
    });

    socket.on('disconnect', function () {
        connectionStatusEl.textContent = '🔴 断开连接';
        connectionStatusEl.className = 'status-disconnected';
        addSystemMessage('与聊天室的连接已断开，正在重连...');
    });

    socket.on('connect_error', function () {
        connectionStatusEl.textContent = '🟡 连接中...';
        connectionStatusEl.className = 'status-disconnected';
    });

    // --- Message Handling ---
    socket.on('new_message', function (data) {
        if (data.type === 'text') {
            addChatMessage(data);
        } else if (data.type === 'file') {
            addFileMessage(data);
        }
        scrollToBottom();
    });

    socket.on('system_message', function (data) {
        addSystemMessage(data.message);
        if (data.type === 'join' || data.type === 'leave') {
            updateOnlineUsers(data);
        }
        scrollToBottom();
    });

    socket.on('user_typing', function (data) {
        if (data.typing) {
            typingIndicatorEl.textContent = data.username + ' 正在输入...';
        } else {
            typingIndicatorEl.textContent = '';
        }
    });

    socket.on('error', function (data) {
        addSystemMessage('错误: ' + (data.error || '未知错误'));
    });

    // --- Send Text Message ---
    function sendMessage() {
        var content = messageInput.value.trim();
        if (!content) return;

        if (socket.connected) {
            socket.emit('send_message', { content: content });
            messageInput.value = '';
            messageInput.style.height = 'auto';
        } else {
            addSystemMessage('未连接到服务器，无法发送消息');
        }
    }

    sendBtn.addEventListener('click', sendMessage);

    messageInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    messageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // --- Typing Indicator ---
    var typingTimeout;
    messageInput.addEventListener('input', function () {
        if (socket.connected) {
            socket.emit('typing', { typing: true });
            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(function () {
                socket.emit('typing', { typing: false });
            }, 2000);
        }
    });

    // --- File Upload ---
    fileUploadBtn.addEventListener('click', function () {
        fileInput.click();
    });

    fileInput.addEventListener('change', function () {
        var file = this.files[0];
        if (!file) return;

        if (file.size > MAX_FILE_SIZE) {
            alert('文件大小超过 4 GB 限制。');
            this.value = '';
            return;
        }

        uploadFile(file);
        this.value = '';
    });

    // Drag and drop
    document.addEventListener('dragover', function (e) {
        e.preventDefault();
    });

    document.addEventListener('drop', function (e) {
        e.preventDefault();
        var file = e.dataTransfer.files[0];
        if (file) {
            if (file.size > MAX_FILE_SIZE) {
                alert('文件大小超过 4 GB 限制。');
                return;
            }
            uploadFile(file);
        }
    });

    /**
     * Upload a file in chunks.
     * Flow: POST /files/upload/init -> POST /files/upload/chunk (N times) -> POST /files/upload/complete
     */
    async function uploadFile(file) {
        var totalChunks = Math.ceil(file.size / CHUNK_SIZE);

        // Show progress
        uploadProgressEl.style.display = 'block';
        uploadFilenameEl.textContent = file.name;
        uploadPercentEl.textContent = '0%';
        progressFillEl.style.width = '0%';

        try {
            // Step 1: Init upload session
            var initResp = await apiFetch('/files/upload/init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    file_size: file.size,
                    mime_type: file.type || 'application/octet-stream',
                    total_chunks: totalChunks,
                    chunk_size: CHUNK_SIZE,
                }),
            });

            var initResult = await initResp.json();
            if (!initResp.ok) {
                throw new Error(initResult.error || '初始化上传失败');
            }

            var fileId = initResult.file_id;
            var uploadId = initResult.upload_id;
            var chunkSize = initResult.chunk_size;

            // Step 2: Upload chunks sequentially
            for (var i = 0; i < totalChunks; i++) {
                var start = i * CHUNK_SIZE;
                var end = Math.min(start + CHUNK_SIZE, file.size);
                var chunk = file.slice(start, end);

                var formData = new FormData();
                formData.append('upload_id', uploadId);
                formData.append('file_id', fileId);
                formData.append('chunk_index', i);
                formData.append('chunk', chunk, file.name + '.part' + i);

                // Retry logic for each chunk
                var maxRetries = 3;
                var chunkOk = false;
                for (var retry = 0; retry < maxRetries; retry++) {
                    try {
                        var chunkResp = await fetch('/files/upload/chunk', {
                            method: 'POST',
                            headers: { 'X-CSRF-Token': CSRF_TOKEN },
                            body: formData,
                        });

                        if (chunkResp.ok) {
                            chunkOk = true;
                            break;
                        }
                        if (retry < maxRetries - 1) {
                            await sleep(1000 * (retry + 1));
                        }
                    } catch (err) {
                        if (retry < maxRetries - 1) {
                            await sleep(1000 * (retry + 1));
                        }
                    }
                }

                if (!chunkOk) {
                    throw new Error('上传分块 ' + (i + 1) + '/' + totalChunks + ' 失败');
                }

                // Update progress
                var pct = Math.round(((i + 1) / totalChunks) * 100);
                uploadPercentEl.textContent = pct + '%';
                progressFillEl.style.width = pct + '%';
            }

            // Step 3: Complete upload
            var completeResp = await apiFetch('/files/upload/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    upload_id: uploadId,
                    file_id: fileId,
                }),
            });

            var completeResult = await completeResp.json();
            if (!completeResp.ok) {
                throw new Error(completeResult.error || '完成上传失败');
            }

            // Success — notify room via WebSocket
            uploadPercentEl.textContent = '100%';
            progressFillEl.style.width = '100%';

            if (socket.connected) {
                socket.emit('send_file_message', {
                    file_id: fileId,
                    filename: file.name,
                    file_size: file.size,
                });
            }

            addSystemMessage('文件 "' + file.name + '" 上传成功 (' + formatFileSize(file.size) + ')');

        } catch (err) {
            addSystemMessage('文件上传失败: ' + err.message);
        } finally {
            // Hide progress after a delay
            setTimeout(function () {
                uploadProgressEl.style.display = 'none';
                progressFillEl.style.width = '0%';
            }, 3000);
        }
    }

    // --- File Download (chunked for large files) ---
    async function downloadFile(fileId, filename, fileSize) {
        try {
            addSystemMessage('开始下载: ' + filename);

            // For files smaller than 50 MB, download directly
            if (fileSize < 50 * 1024 * 1024) {
                window.location.href = '/files/download/' + fileId;
                return;
            }

            // For large files, use range requests
            var chunks = [];
            var downloaded = 0;
            var chunkSize = CHUNK_SIZE;

            while (downloaded < fileSize) {
                var end = Math.min(downloaded + chunkSize - 1, fileSize - 1);
                var rangeHeader = 'bytes=' + downloaded + '-' + end;

                var resp = await fetch('/files/download/' + fileId, {
                    headers: {
                        'Range': rangeHeader,
                    },
                });

                if (!resp.ok && resp.status !== 206) {
                    throw new Error('下载失败 (HTTP ' + resp.status + ')');
                }

                var data = await resp.arrayBuffer();
                chunks.push(data);
                downloaded += data.byteLength;

                var pct = Math.round((downloaded / fileSize) * 100);
                addSystemMessage('下载进度: ' + pct + '%');
            }

            // Combine chunks and trigger save
            var blob = new Blob(chunks);
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            addSystemMessage(filename + ' 下载完成');
        } catch (err) {
            addSystemMessage('文件下载失败: ' + err.message);
        }
    }

    // --- Message Rendering ---
    function addChatMessage(data) {
        var msgDiv = document.createElement('div');
        msgDiv.className = 'message';

        var initial = getInitial(data.username || '?');

        msgDiv.innerHTML =
            '<div class="message-avatar">' + escapeHtml(initial) + '</div>' +
            '<div class="message-body">' +
                '<div class="message-header">' +
                    '<span class="message-username">' + escapeHtml(data.username) + '</span>' +
                    '<span class="message-time">' + formatTime(data.timestamp) + '</span>' +
                '</div>' +
                '<div class="message-content">' + escapeHtml(data.content) + '</div>' +
            '</div>';

        messagesEl.appendChild(msgDiv);
    }

    function addFileMessage(data) {
        var msgDiv = document.createElement('div');
        msgDiv.className = 'message';

        var initial = getInitial(data.username || '?');
        var fileSizeStr = formatFileSize(data.file_size || 0);
        var filename = escapeHtml(data.filename || 'unknown');

        msgDiv.innerHTML =
            '<div class="message-avatar">' + escapeHtml(initial) + '</div>' +
            '<div class="message-body">' +
                '<div class="message-header">' +
                    '<span class="message-username">' + escapeHtml(data.username) + '</span>' +
                    '<span class="message-time">' + formatTime(data.timestamp) + '</span>' +
                '</div>' +
                '<div class="message-file">' +
                    '<span class="file-icon">📄</span>' +
                    '<div class="file-info">' +
                        '<div class="file-name" title="' + filename + '">' + filename + '</div>' +
                        '<div class="file-size">' + fileSizeStr + '</div>' +
                    '</div>' +
                    '<button class="file-download" data-file-id="' + data.file_id + '" ' +
                        'data-filename="' + filename + '" data-file-size="' + (data.file_size || 0) + '">' +
                        '下载</button>' +
                '</div>' +
            '</div>';

        // Attach download handler
        var downloadBtn = msgDiv.querySelector('.file-download');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', function () {
                var fid = parseInt(this.getAttribute('data-file-id'));
                var fname = this.getAttribute('data-filename');
                var fsize = parseInt(this.getAttribute('data-file-size'));
                downloadFile(fid, fname, fsize);
            });
        }

        messagesEl.appendChild(msgDiv);
    }

    function addSystemMessage(text) {
        var div = document.createElement('div');
        div.className = 'message-system';
        div.innerHTML = '<span>' + escapeHtml(text) + '</span>';
        messagesEl.appendChild(div);
    }

    function updateOnlineUsers(data) {
        // Simple update: broadcast includes username, we could maintain a list.
        // For now, the system messages already show join/leave events.
    }

    function scrollToBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // --- Helpers ---
    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    function getInitial(username) {
        return (username || '?').charAt(0).toUpperCase();
    }

    function formatTime(isoString) {
        if (!isoString) return '';
        var d = new Date(isoString);
        var h = String(d.getHours()).padStart(2, '0');
        var m = String(d.getMinutes()).padStart(2, '0');
        return h + ':' + m;
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        var units = ['B', 'KB', 'MB', 'GB'];
        var i = Math.floor(Math.log(bytes) / Math.log(1024));
        i = Math.min(i, units.length - 1);
        var val = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
        return val + ' ' + units[i];
    }

    function sleep(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }
})();
