#!/usr/bin/env bash
# ================================================================
#  Chat Room — Interactive One-Click Deployment Script
# ================================================================
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/44114/room/main/setup.sh -o setup.sh
#    bash setup.sh
#
#  Works on: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+, Fedora 36+, Arch Linux
# ================================================================
set -euo pipefail

# ── Color helpers ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
ask()   { echo -ne "${CYAN}[?]${NC}    $* "; }
header(){ echo -e "\n${BOLD}${BLUE}═══ $* ═══${NC}\n"; }

# ── Root check ─────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (or with sudo)."
    err "Please run: sudo bash setup.sh"
    exit 1
fi

# ── OS Detection ───────────────────────────────────────────────
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID:-}"
    elif [[ -f /etc/redhat-release ]]; then
        OS_ID="rhel"
    else
        err "Unable to detect OS. Unsupported distribution."
        exit 1
    fi

    case "$OS_ID" in
        ubuntu|debian)              PKG_MGR="apt";;
        centos|rhel|rocky|almalinux|fedora) PKG_MGR="dnf";;
        arch)                       PKG_MGR="pacman";;
        *) warn "Unrecognized OS: $OS_ID. Attempting to continue with apt..."; PKG_MGR="apt";;
    esac
    ok "Detected OS: $OS_ID ($OS_VERSION) — using $PKG_MGR"
}

# ── Dependency installation ────────────────────────────────────
install_system_deps() {
    header "Installing System Dependencies"

    if [[ -n "${PROXY_URL:-}" ]]; then
        export http_proxy="$PROXY_URL"
        export https_proxy="$PROXY_URL"
        export HTTP_PROXY="$PROXY_URL"
        export HTTPS_PROXY="$PROXY_URL"
        info "Using proxy: $PROXY_URL"
    fi

    case "$PKG_MGR" in
        apt)
            info "Running apt update..."
            apt-get update -qq
            info "Installing packages (python3, venv, mysql-server, libmagic, git)..."
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                python3 python3-pip python3-venv \
                mysql-server libmagic1 git nginx curl
            ;;
        dnf)
            info "Installing packages (python3, mysql-server, libmagic, git)..."
            dnf install -y -q python3 python3-pip python3-virtualenv \
                mysql-server file-devel git nginx curl
            ;;
        pacman)
            info "Installing packages (python, mysql, libmagic, git)..."
            pacman -Sy --noconfirm --quiet python python-pip python-virtualenv \
                mariadb file git nginx curl
            ;;
    esac
    ok "System dependencies installed."
}

# ── MySQL setup ─────────────────────────────────────────────────
setup_mysql() {
    header "Database Setup"

    # Ensure MySQL is running
    case "$PKG_MGR" in
        apt)       systemctl enable --now mysql 2>/dev/null || true;;
        dnf)       systemctl enable --now mysqld 2>/dev/null || true;;
        pacman)    systemctl enable --now mariadb 2>/dev/null || true;;
    esac

    # Prompt for DB credentials
    ask "MySQL root password (leave blank to generate random):"
    read -r MYSQL_ROOT_PW
    if [[ -z "$MYSQL_ROOT_PW" ]]; then
        MYSQL_ROOT_PW=$(tr -dc 'A-Za-z0-9!@#$%^&*' < /dev/urandom | head -c 20)
        info "Generated random MySQL root password: $MYSQL_ROOT_PW"
    fi

    ask "Chat room database name [chatroom]:"
    read -r DB_NAME; DB_NAME="${DB_NAME:-chatroom}"

    ask "Chat room database user [chatroom]:"
    read -r DB_USER; DB_USER="${DB_USER:-chatroom}"

    ask "Chat room database password (leave blank to generate random):"
    read -r DB_PASS
    if [[ -z "$DB_PASS" ]]; then
        DB_PASS=$(tr -dc 'A-Za-z0-9!@#$%^&*' < /dev/urandom | head -c 24)
        info "Generated random database password: $DB_PASS"
    fi

    # Attempt to create DB and user
    info "Creating database and user..."

    _mysql_exec() {
        mysql -u root ${MYSQL_ROOT_PW:+-p"$MYSQL_ROOT_PW"} -e "$1" 2>/dev/null
    }

    if ! _mysql_exec "SELECT 1;" > /dev/null 2>&1; then
        # Try without password (fresh install)
        if mysql -u root -e "SELECT 1;" > /dev/null 2>&1; then
            MYSQL_ROOT_PW=""
            _mysql_exec() { mysql -u root -e "$1" 2>/dev/null; }
        else
            err "Cannot connect to MySQL as root. Please check credentials."
            err "Try: sudo mysql -u root"
            return 1
        fi
    fi

    _mysql_exec "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    _mysql_exec "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    _mysql_exec "GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';"
    _mysql_exec "FLUSH PRIVILEGES;"

    ok "Database '$DB_NAME' and user '$DB_USER' created."

    # Save for later
    MYSQL_ROOT_PW_SAVED="$MYSQL_ROOT_PW"
}

# ── Project deployment ──────────────────────────────────────────
deploy_project() {
    header "Deploying Chat Room Server"

    ask "Installation directory [/opt/chatroom]:"
    read -r INSTALL_DIR; INSTALL_DIR="${INSTALL_DIR:-/opt/chatroom}"

    if [[ -d "$INSTALL_DIR" ]] && [[ "$MODE" != "uninstall" ]]; then
        warn "Directory $INSTALL_DIR already exists."
        ask "Overwrite? (y/N):"
        read -r OVERWRITE
        if [[ ! "$OVERWRITE" =~ ^[Yy] ]]; then
            err "Aborted by user."
            exit 0
        fi
        rm -rf "$INSTALL_DIR"
    fi

    # Clone
    info "Cloning repository..."
    if [[ -n "${PROXY_URL:-}" ]]; then
        git config --global http.proxy "$PROXY_URL"
        git config --global https.proxy "$PROXY_URL"
    fi
    git clone --depth 1 https://github.com/44114/room.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    # Virtual environment
    info "Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate

    # Install Python deps (with proxy if set)
    if [[ -n "${PROXY_URL:-}" ]]; then
        pip install --proxy "$PROXY_URL" --quiet -r requirements.txt
    else
        pip install --quiet -r requirements.txt
    fi

    # Ask about reverse proxy configuration
    echo ""
    ask "Will this server be behind Nginx with HTTPS? (Y/n):"
    read -r USE_HTTPS
    USE_HTTPS="${USE_HTTPS:-y}"
    if [[ "$USE_HTTPS" =~ ^[Yy]$ ]]; then
        ALIAS_PROTO="https"
        ALIAS_PRT="443"
    else
        ALIAS_PROTO="http"
        ALIAS_PRT="9888"
        warn "Running without HTTPS — session cookies will be transmitted in plaintext."
    fi

    # Create upload directory
    mkdir -p uploads && chmod 750 uploads

    # Generate secrets
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))")
    INVITE_CODE_GEN=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)

    # Create .env
    cat > .env <<EOF
# Chat Room Server Configuration
SECRET_KEY=$SECRET_KEY
ALIAS_PROTOCOL=$ALIAS_PROTO
ALIAS_PORT=$ALIAS_PRT
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=$DB_NAME
MYSQL_USER=$DB_USER
MYSQL_PASSWORD=$DB_PASS
INVITE_CODE=$INVITE_CODE_GEN
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
FLASK_DEBUG=0
EOF
    ok ".env file created."

    # Import schema
    info "Importing database schema..."
    if [[ -n "${MYSQL_ROOT_PW_SAVED:-}" ]]; then
        mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$INSTALL_DIR/schema.sql"
    else
        mysql -u "$DB_USER" "$DB_NAME" < "$INSTALL_DIR/schema.sql"
    fi
    ok "Database schema imported."

    ok "Chat Room server deployed to $INSTALL_DIR"
    info "Invite code: $INVITE_CODE_GEN  (share this with users)"
}

# ── room-admin deployment ───────────────────────────────────────
deploy_admin() {
    header "Deploying Admin Panel"

    ask "Admin panel installation directory [/opt/chatroom-admin]:"
    read -r ADMIN_DIR; ADMIN_DIR="${ADMIN_DIR:-/opt/chatroom-admin}"

    if [[ -d "$ADMIN_DIR" ]]; then
        warn "Directory $ADMIN_DIR already exists."
        ask "Overwrite? (y/N):"
        read -r OVERWRITE
        if [[ ! "$OVERWRITE" =~ ^[Yy] ]]; then
            warn "Skipping admin panel installation."
            return
        fi
        rm -rf "$ADMIN_DIR"
    fi

    info "Cloning room-admin repository..."
    git clone --depth 1 https://github.com/44114/room-admin.git "$ADMIN_DIR"
    cd "$ADMIN_DIR"

    info "Setting up Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    if [[ -n "${PROXY_URL:-}" ]]; then
        pip install --proxy "$PROXY_URL" --quiet -r requirements.txt
    else
        pip install --quiet -r requirements.txt
    fi

    # Generate admin .env
    ADMIN_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))")

    cat > .env <<EOF
# Admin Panel Configuration
SECRET_KEY=$ADMIN_SECRET_KEY
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=$DB_NAME
MYSQL_USER=$DB_USER
MYSQL_PASSWORD=$DB_PASS
ADMIN_PORT=9889
FLASK_DEBUG=0
EOF
    ok "Admin panel deployed to $ADMIN_DIR"
    ok "Admin panel .env created."
    warn "IMPORTANT: Before exposing the admin panel, visit http://127.0.0.1:9889/auth/setup to create the admin account!"
}

# ── systemd services ────────────────────────────────────────────
install_systemd() {
    header "Configuring systemd Services"

    # ── Chat Room service ──────────────────────────────────────
    cat > /etc/systemd/system/chatroom.service <<EOF
[Unit]
Description=Chat Room Server
After=network.target mysql.service mysqld.service mariadb.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/gunicorn -k gevent -w 4 -b 0.0.0.0:9888 app:create_app\(\)
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # ── Admin panel service ────────────────────────────────────
    if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
        cat > /etc/systemd/system/chatroom-admin.service <<EOF
[Unit]
Description=Chat Room Admin Panel
After=network.target mysql.service mysqld.service mariadb.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$ADMIN_DIR
EnvironmentFile=$ADMIN_DIR/.env
ExecStart=$ADMIN_DIR/venv/bin/gunicorn -w 2 -b 127.0.0.1:9889 app:create_app\(\)
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    fi

    systemctl daemon-reload
    systemctl enable chatroom
    systemctl start chatroom

    if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
        systemctl enable chatroom-admin
        systemctl start chatroom-admin
    fi

    ok "systemd services installed and started."
    info "Useful commands:"
    info "  systemctl status chatroom"
    if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
        info "  systemctl status chatroom-admin"
    fi
    info "  journalctl -u chatroom -f"
}

# ── Uninstall ───────────────────────────────────────────────────
do_uninstall() {
    header "Uninstalling Chat Room"

    echo ""
    warn "This will remove all project files and systemd services."
    warn "Database and uploaded files will NOT be deleted."
    echo ""
    ask "Are you sure you want to uninstall? (yes/N):"
    read -r CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        info "Uninstall cancelled."
        exit 0
    fi

    # Stop and disable services
    systemctl stop chatroom 2>/dev/null || true
    systemctl disable chatroom 2>/dev/null || true
    rm -f /etc/systemd/system/chatroom.service

    if systemctl is-active --quiet chatroom-admin 2>/dev/null; then
        systemctl stop chatroom-admin 2>/dev/null || true
        systemctl disable chatroom-admin 2>/dev/null || true
        rm -f /etc/systemd/system/chatroom-admin.service
    fi

    systemctl daemon-reload

    # Remove install directories
    ask "Chat room install directory to remove [/opt/chatroom]:"
    read -r REMOVE_DIR; REMOVE_DIR="${REMOVE_DIR:-/opt/chatroom}"
    if [[ -d "$REMOVE_DIR" ]]; then
        ask "Also remove uploaded files in $REMOVE_DIR/uploads? (y/N):"
        read -r REMOVE_UPLOADS
        if [[ "$REMOVE_UPLOADS" =~ ^[Yy]$ ]]; then
            rm -rf "$REMOVE_DIR"
        else
            # Keep uploads
            find "$REMOVE_DIR" -mindepth 1 -not -name 'uploads' -not -path '*/uploads/*' -exec rm -rf {} + 2>/dev/null || true
            rm -rf "$REMOVE_DIR" 2>/dev/null || warn "Could not fully remove $REMOVE_DIR (uploads may be preserved)"
        fi
        ok "Removed $REMOVE_DIR"
    fi

    ask "Admin panel directory to remove [/opt/chatroom-admin]:"
    read -r REMOVE_ADMIN; REMOVE_ADMIN="${REMOVE_ADMIN:-/opt/chatroom-admin}"
    if [[ -d "$REMOVE_ADMIN" ]]; then
        rm -rf "$REMOVE_ADMIN"
        ok "Removed $REMOVE_ADMIN"
    fi

    # Clear git proxy settings
    if [[ -n "${PROXY_URL:-}" ]]; then
        git config --global --unset http.proxy 2>/dev/null || true
        git config --global --unset https.proxy 2>/dev/null || true
    fi

    echo ""
    ok "Uninstall complete."
    info "Database and its data were preserved."
    info "To remove the database manually: mysql -u root -e 'DROP DATABASE $DB_NAME;'"
}

# ── Main ────────────────────────────────────────────────────────
main() {
    clear
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║      💬  Chat Room — Deployment Script       ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${NC}"

    # ── Mode ───────────────────────────────────────────────────
    echo "What would you like to do?"
    echo "  [1] Install"
    echo "  [2] Uninstall"
    echo ""
    ask "Choose [1/2]:"
    read -r MODE_CHOICE

    case "$MODE_CHOICE" in
        2|uninstall|Uninstall) MODE="uninstall"; do_uninstall; exit 0;;
        *)                    MODE="install";;
    esac

    # ── Proxy ──────────────────────────────────────────────────
    echo ""
    ask "Do you need to use a proxy for downloads? (y/N):"
    read -r USE_PROXY
    if [[ "$USE_PROXY" =~ ^[Yy]$ ]]; then
        ask "Proxy URL (e.g. http://127.0.0.1:7890):"
        read -r PROXY_URL
        if [[ -n "$PROXY_URL" ]]; then
            info "Proxy set to: $PROXY_URL"
        else
            warn "No proxy URL provided — continuing without proxy."
            PROXY_URL=""
        fi
    fi

    # ── Detect OS and install system deps ──────────────────────
    detect_os
    install_system_deps

    # ── MySQL ──────────────────────────────────────────────────
    setup_mysql

    # ── Admin panel ────────────────────────────────────────────
    echo ""
    ask "Also install the Admin Panel (room-admin)? Recommended: yes (Y/n):"
    read -r INSTALL_ADMIN
    INSTALL_ADMIN="${INSTALL_ADMIN:-y}"

    # ── Boot ───────────────────────────────────────────────────
    echo ""
    ask "Enable automatic startup on boot (systemd)? (Y/n):"
    read -r AUTOBOOT
    AUTOBOOT="${AUTOBOOT:-y}"

    # ── Deploy ─────────────────────────────────────────────────
    deploy_project

    if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
        deploy_admin
    fi

    # ── systemd ────────────────────────────────────────────────
    if [[ "$AUTOBOOT" =~ ^[Yy]$ ]]; then
        install_systemd
    else
        header "Manual Startup"
        info "To start the chat room server:"
        info "  cd $INSTALL_DIR && source venv/bin/activate && python app.py"
        if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
            info "To start the admin panel:"
            info "  cd $ADMIN_DIR && source venv/bin/activate && python app.py"
        fi
    fi

    # ── Summary ────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}${GREEN}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║         ✅  Installation Complete!           ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "${BOLD}─── Chat Room Server ─────────────────────────────${NC}"
    echo "  URL:       http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'YOUR_IP'):9888"
    echo "  Invite:    $INVITE_CODE_GEN"
    echo "  Directory: $INSTALL_DIR"
    echo "  Service:   systemctl status chatroom"
    echo ""

    if [[ "$INSTALL_ADMIN" =~ ^[Yy]$ ]]; then
        echo -e "${BOLD}─── Admin Panel ──────────────────────────────────${NC}"
        echo "  URL:       http://127.0.0.1:9889"
        echo "  Setup:     http://127.0.0.1:9889/auth/setup"
        echo "  Directory: ${ADMIN_DIR:-/opt/chatroom-admin}"
        echo -e "  ${RED}⚠  IMPORTANT: Set admin password BEFORE exposing to network!${NC}"
        echo "  Service:   systemctl status chatroom-admin"
        echo ""
    fi

    echo -e "${BOLD}─── Database ─────────────────────────────────────${NC}"
    echo "  Host:       127.0.0.1:3306"
    echo "  Database:   $DB_NAME"
    echo "  User:       $DB_USER"
    echo "  Password:   $DB_PASS"
    echo ""

    if [[ "$AUTOBOOT" =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓${NC} Services will start automatically on boot."
    fi

    echo -e "${YELLOW}⚠  Next step: configure Nginx reverse proxy + Let's Encrypt HTTPS for production use.${NC}"
    echo -e "${YELLOW}   See README.md for detailed instructions.${NC}"
    echo ""
}

main
