<p align="center">
  <a href="#english">English</a> |
  <a href="#%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87">简体中文</a> |
  <a href="#%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87">繁體中文</a>
</p>

---

<a id="english"></a>

# 💬 Chat Room — Real-Time Instant Messaging

A secure, lightweight web-based instant messaging chat room built with **Python Flask**, **MySQL**, and vanilla **HTML/CSS/JavaScript**. Features real-time messaging via WebSocket, chunked file transfers up to 4 GB, Cloudflare Turnstile human verification, and Argon2id password hashing.

> 🤖 **Developed with assistance from [Claude Code](https://claude.ai/code) (Anthropic)**

---

## ✨ Features

- **User Authentication** — Register with invite code + Cloudflare Turnstile verification; login with "Remember Me" support
- **Real-Time Chat** — WebSocket (SocketIO) for instant text messaging with typing indicators
- **File Sharing** — Chunked upload/download up to 4 GB per file (5 MB chunks), drag-and-drop support
- **Account Management** — Change password, delete account (soft-delete), secure logout
- **Security First** — Argon2id password hashing, CSRF protection, XSS sanitization, SQL injection prevention, file content scanning
- **Minimal & Fast** — No heavy frontend frameworks; vanilla JS with clean modern CSS

## 🛠 Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask 3.x |
| WebSocket | Flask-SocketIO + gevent |
| Database | MySQL 8.0+ / MariaDB 10.11+ |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Password Hashing | Argon2id (argon2-cffi) |
| XSS Prevention | Bleach |
| MIME Detection | python-magic |
| Human Verification | Cloudflare Turnstile |
| Rate Limiting | Flask-Limiter |

## 📦 Quick Start

### Prerequisites

- Python 3.10+
- MySQL 8.0+ or MariaDB 10.11+
- `libmagic` system library

```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv mysql-server libmagic1

# macOS
brew install python mysql libmagic
```

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/44114/room.git && cd room

# 2. Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Create environment configuration
cp .env.example .env
# Edit .env with your actual credentials

# 4. Create the database and import schema
sudo mysql -u root
CREATE DATABASE chatroom CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'chatroom'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON chatroom.* TO 'chatroom'@'localhost';
FLUSH PRIVILEGES;
EXIT;

mysql -u chatroom -p chatroom < schema.sql

# 5. Run the application
python app.py
```

The application will start at **http://0.0.0.0:9888**.

### Production Deployment (gunicorn)

```bash
source venv/bin/activate
gunicorn -k gevent -w 4 -b 0.0.0.0:9888 app:create_app()
```

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Required | Description |
|----------|:--------:|-------------|
| `SECRET_KEY` | ✅ | Flask session signing key (generate with `secrets.token_hex(64)`) |
| `MYSQL_PASSWORD` | ✅ | MySQL database password |
| `INVITE_CODE` | ✅ | Invite code required for registration |
| `MYSQL_HOST` | | MySQL host (default: `127.0.0.1`) |
| `MYSQL_PORT` | | MySQL port (default: `3306`) |
| `MYSQL_USER` | | MySQL user (default: `chatroom`) |
| `MYSQL_DB` | | Database name (default: `chatroom`) |
| `TURNSTILE_SITE_KEY` | | Cloudflare Turnstile site key |
| `TURNSTILE_SECRET_KEY` | | Cloudflare Turnstile secret key |
| `FLASK_DEBUG` | | Set to `1` for development mode |

> **Note:** Turnstile defaults to Cloudflare's test keys in development (always pass).

## 📁 Project Structure

```
room/
├── app.py                  # Flask entry point (port 9888)
├── config.py               # Environment-based configuration
├── requirements.txt        # Python dependencies
├── models.py               # Database models & initialization
├── auth.py                 # Authentication blueprint
├── chat.py                 # WebSocket event handlers
├── files.py                # Chunked file upload/download
├── middleware.py            # CSRF, security headers, rate limiting
├── utils.py                # Security utilities (Argon2id, XSS, MIME)
├── schema.sql              # Database schema
├── .env.example            # Environment variables template
├── templates/
│   ├── base.html           # Base layout & CSRF handling
│   ├── register.html       # Registration page
│   ├── login.html          # Login page
│   ├── chat.html           # Main chat interface
│   └── account.html        # Account management
├── static/
│   ├── css/style.css       # Application styles
│   └── js/
│       ├── auth.js         # Auth form logic
│       ├── chat.js         # WebSocket client + file handler
│       └── account.js      # Account management logic
└── uploads/                # File storage (outside web root)
```

## 🔒 Security

| Threat | Mitigation |
|--------|-----------|
| **SQL Injection** | 100% parameterized queries (PyMySQL `%s` placeholders) |
| **XSS** | Bleach HTML sanitization, CSP headers, `textContent` DOM rendering, Jinja2 auto-escaping |
| **CSRF** | Double-submit token pattern, `SameSite=Lax`, constant-time comparison |
| **Password Attacks** | Argon2id hashing, brute-force rate limiting, timing-attack resistant verification |
| **File Upload Attacks** | MIME validation via magic bytes, script signature scanning, UUID file naming, forbidden extension blocklist |
| **Session Hijacking** | `HttpOnly` + `SameSite` cookies, session regeneration on login, 30-min idle timeout |
| **Path Traversal** | UUID validation on upload IDs, database-driven file resolution |
| **RCE** | No `eval()`/`exec()`, files stored outside web root |

## 📡 API Overview

### REST Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/auth/register` | No | Register (invite code + Turnstile) |
| `POST` | `/auth/login` | No | Login (Turnstile + remember me) |
| `POST` | `/auth/logout` | Yes | Logout |
| `GET` | `/auth/check` | Any | Check login status |
| `POST` | `/auth/change-password` | Yes | Change password |
| `POST` | `/auth/delete-account` | Yes | Delete account (soft-delete) |
| `POST` | `/files/upload/init` | Yes | Initialize chunked upload |
| `POST` | `/files/upload/chunk` | Yes | Upload a file chunk |
| `POST` | `/files/upload/complete` | Yes | Finalize upload |
| `GET` | `/files/download/<id>` | Yes | Download file (Range support) |
| `GET` | `/files/info/<id>` | Yes | File metadata |

### WebSocket Events

**Client → Server:**
- `send_message` — Send a text message
- `send_file_message` — Notify room of uploaded file
- `typing` — Typing indicator

**Server → Client:**
- `new_message` — New message (text or file)
- `system_message` — System notifications (join/leave)
- `user_typing` — Other user typing status

## 🗄 Database

See [`schema.sql`](schema.sql) for the full DDL. Five tables:

| Table | Purpose |
|-------|---------|
| `users` | User accounts (Argon2id password hashes) |
| `invite_codes` | Hashed invite codes (one-time use) |
| `messages` | Chat message history |
| `files` | Uploaded file metadata |
| `sessions` | Persistent sessions ("Remember Me") |

## 📄 License

This project is provided for educational and personal use.

---

<a id="简体中文"></a>

# 💬 聊天室 — 即时通讯

一个安全、轻量的网页版即时通讯聊天室，基于 **Python Flask**、**MySQL** 和原生 **HTML/CSS/JavaScript** 构建。支持 WebSocket 实时消息、最大 4 GB 分块文件传输、Cloudflare Turnstile 人机验证以及 Argon2id 密码哈希。

> 🤖 **本项目由 [Claude Code](https://claude.ai/code) (Anthropic) 辅助开发**

## ✨ 功能

- **用户认证** — 邀请码 + Cloudflare Turnstile 人机验证注册；支持"记住我"登录
- **实时聊天** — 基于 WebSocket (SocketIO) 即时消息，支持输入状态提示
- **文件共享** — 分块上传/下载最大 4 GB 文件 (每块 5 MB)，支持拖放
- **账号管理** — 修改密码、注销账号 (软删除)、安全退出
- **安全优先** — Argon2id 密码哈希、CSRF 防护、XSS 清洗、SQL 注入防护、文件内容扫描
- **轻量高速** — 无重型前端框架，原生 JS + 现代 CSS

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+, Flask 3.x |
| WebSocket | Flask-SocketIO + gevent |
| 数据库 | MySQL 8.0+ / MariaDB 10.11+ |
| 前端 | HTML5, CSS3, 原生 JavaScript |
| 密码哈希 | Argon2id (argon2-cffi) |
| XSS 防护 | Bleach |
| MIME 检测 | python-magic |
| 人机验证 | Cloudflare Turnstile |
| 速率限制 | Flask-Limiter |

## 📦 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+ 或 MariaDB 10.11+
- `libmagic` 系统库

```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv mysql-server libmagic1
```

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/44114/room.git && cd room

# 2. 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 创建环境配置
cp .env.example .env
# 编辑 .env 填入真实凭据

# 4. 创建数据库并导入表结构
sudo mysql -u root
CREATE DATABASE chatroom CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'chatroom'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON chatroom.* TO 'chatroom'@'localhost';
FLUSH PRIVILEGES;
EXIT;

mysql -u chatroom -p chatroom < schema.sql

# 5. 启动应用
python app.py
```

应用将在 **http://0.0.0.0:9888** 启动。

## ⚙️ 环境变量

复制 `.env.example` 为 `.env` 并配置：

| 变量 | 必需 | 说明 |
|------|:----:|------|
| `SECRET_KEY` | ✅ | Flask 会话签名密钥 |
| `MYSQL_PASSWORD` | ✅ | MySQL 数据库密码 |
| `INVITE_CODE` | ✅ | 注册所需邀请码 |
| `TURNSTILE_SITE_KEY` | | Turnstile 站点密钥 (开发可用测试密钥) |
| `TURNSTILE_SECRET_KEY` | | Turnstile 密钥 |
| `FLASK_DEBUG` | | 设为 `1` 启用调试模式 |

## 🔒 安全措施

| 威胁 | 缓解措施 |
|------|---------|
| **SQL 注入** | 100% 参数化查询 |
| **XSS** | Bleach 清洗 + CSP 头 + textContent DOM 构建 |
| **CSRF** | 双重提交 Token + SameSite=Lax + 恒定时间比较 |
| **密码攻击** | Argon2id 哈希 + 速率限制 + 时序攻击防护 |
| **文件上传攻击** | Magic bytes MIME 验证 + 脚本扫描 + UUID 命名 + 扩展名黑名单 |
| **会话劫持** | HttpOnly + SameSite Cookie + 登录重建会话 + 30分钟超时 |
| **RCE** | 禁用 eval()/exec() + 文件存于 Web 根外 |

---

<a id="繁體中文"></a>

# 💬 聊天室 — 即時通訊

一個安全、輕量的網頁版即時通訊聊天室，基於 **Python Flask**、**MySQL** 和原生 **HTML/CSS/JavaScript** 建構。支援 WebSocket 即時訊息、最大 4 GB 分塊檔案傳輸、Cloudflare Turnstile 人機驗證以及 Argon2id 密碼雜湊。

> 🤖 **本專案由 [Claude Code](https://claude.ai/code) (Anthropic) 輔助開發**

## ✨ 功能

- **使用者認證** — 邀請碼 + Cloudflare Turnstile 人機驗證註冊；支援「記住我」登入
- **即時聊天** — 基於 WebSocket (SocketIO) 即時訊息，支援輸入狀態提示
- **檔案分享** — 分塊上傳/下載最大 4 GB 檔案 (每塊 5 MB)，支援拖放
- **帳號管理** — 修改密碼、註銷帳號 (軟刪除)、安全登出
- **安全優先** — Argon2id 密碼雜湊、CSRF 防護、XSS 清理、SQL 注入防護、檔案內容掃描
- **輕量高速** — 無重型前端框架，原生 JS + 現代 CSS

## 🛠 技術棧

| 層級 | 技術 |
|------|------|
| 後端 | Python 3.10+, Flask 3.x |
| WebSocket | Flask-SocketIO + gevent |
| 資料庫 | MySQL 8.0+ / MariaDB 10.11+ |
| 前端 | HTML5, CSS3, 原生 JavaScript |
| 密碼雜湊 | Argon2id (argon2-cffi) |
| XSS 防護 | Bleach |
| MIME 檢測 | python-magic |
| 人機驗證 | Cloudflare Turnstile |
| 速率限制 | Flask-Limiter |

## 📦 快速開始

### 環境要求

- Python 3.10+
- MySQL 8.0+ 或 MariaDB 10.11+
- `libmagic` 系統函式庫

```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv mysql-server libmagic1
```

### 安裝步驟

```bash
# 1. 複製儲存庫
git clone https://github.com/44114/room.git && cd room

# 2. 建立虛擬環境並安裝依賴
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 建立環境設定
cp .env.example .env
# 編輯 .env 填入真實憑據

# 4. 建立資料庫並匯入表結構
sudo mysql -u root
CREATE DATABASE chatroom CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'chatroom'@'localhost' IDENTIFIED BY '你的密碼';
GRANT ALL PRIVILEGES ON chatroom.* TO 'chatroom'@'localhost';
FLUSH PRIVILEGES;
EXIT;

mysql -u chatroom -p chatroom < schema.sql

# 5. 啟動應用
python app.py
```

應用將在 **http://0.0.0.0:9888** 啟動。

## ⚙️ 環境變數

複製 `.env.example` 為 `.env` 並設定：

| 變數 | 必要 | 說明 |
|------|:----:|------|
| `SECRET_KEY` | ✅ | Flask 工作階段簽名金鑰 |
| `MYSQL_PASSWORD` | ✅ | MySQL 資料庫密碼 |
| `INVITE_CODE` | ✅ | 註冊所需邀請碼 |
| `TURNSTILE_SITE_KEY` | | Turnstile 站點金鑰 (開發可用測試金鑰) |
| `TURNSTILE_SECRET_KEY` | | Turnstile 密鑰 |
| `FLASK_DEBUG` | | 設為 `1` 啟用除錯模式 |

## 🔒 安全措施

| 威脅 | 緩解措施 |
|------|---------|
| **SQL 注入** | 100% 參數化查詢 |
| **XSS** | Bleach 清理 + CSP 標頭 + textContent DOM 建構 |
| **CSRF** | 雙重提交 Token + SameSite=Lax + 恆定時間比較 |
| **密碼攻擊** | Argon2id 雜湊 + 速率限制 + 時序攻擊防護 |
| **檔案上傳攻擊** | Magic bytes MIME 驗證 + 指令碼掃描 + UUID 命名 + 副檔名黑名單 |
| **工作階段劫持** | HttpOnly + SameSite Cookie + 登入重建工作階段 + 30分鐘逾時 |
| **RCE** | 禁用 eval()/exec() + 檔案存於 Web 根外 |

---

<p align="center">
  <sub>🤖 Developed with <a href="https://claude.ai/code">Claude Code</a> (Anthropic) · 2026</sub>
</p>
