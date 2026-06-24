#!/bin/bash

# ==========================================
# 🚀 GHOST CMD - AGENT INSTALLER
# ==========================================
# Auto-install, update, dan restart agent
# Usage: sudo bash install.sh

set -e

echo "🚀 GHOST CMD Agent Installer"
echo "======================================"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ Script harus dijalankan dengan sudo!"
   exit 1
fi

# ==========================================
# 1️⃣ SETUP VARIABLES
# ==========================================
AGENT_DIR="/opt/ghost-cmd/agent"
REPO_URL="https://github.com/umnodqib/ghost-cmd.git"
SERVICE_NAME="ghost-agent"
PYTHON_CMD=$(which python3 || which python)

echo "📦 Python: $PYTHON_CMD"
echo "📁 Agent Dir: $AGENT_DIR"

# ==========================================
# 2️⃣ CREATE/UPDATE AGENT DIRECTORY
# ==========================================
if [ ! -d "$AGENT_DIR" ]; then
    echo "📥 Clone repository..."
    mkdir -p /opt/ghost-cmd
    cd /opt/ghost-cmd
    git clone "$REPO_URL" .
else
    echo "🔄 Update repository..."
    cd "$AGENT_DIR"
    git pull origin main
fi

cd "$AGENT_DIR"
echo "✅ Repository ready at $AGENT_DIR"

# ==========================================
# 3️⃣ INSTALL PYTHON DEPENDENCIES
# ==========================================
echo "📦 Installing Python dependencies..."

if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install --upgrade pip -q
    $PYTHON_CMD -m pip install -r requirements.txt -q
    echo "✅ Dependencies installed"
else
    echo "⚠️ requirements.txt not found, skipping pip install"
fi

# ==========================================
# 4️⃣ CONFIGURE ENVIRONMENT
# ==========================================
echo "⚙️ Configuring environment..."

# Create .env file if not exists
if [ ! -f "$AGENT_DIR/.env" ]; then
    echo "📝 Creating .env file..."
    read -p "📡 Enter Dashboard URL [https://dashboard.jujulefek.qzz.io]: " DASHBOARD_URL
    DASHBOARD_URL="${DASHBOARD_URL:-https://dashboard.jujulefek.qzz.io}"
    
    cat > "$AGENT_DIR/.env" << EOF
DASHBOARD_URL=$DASHBOARD_URL
AUTH_KEY=GHOST_SECRET_2026
EOF
    echo "✅ .env created"
else
    echo "✅ .env already exists"
    cat "$AGENT_DIR/.env"
fi

# ==========================================
# 5️⃣ CREATE SYSTEMD SERVICE
# ==========================================
echo "🔧 Setting up systemd service..."

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=GHOST CMD Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$AGENT_DIR
EnvironmentFile=$AGENT_DIR/.env
ExecStart=$PYTHON_CMD $AGENT_DIR/agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload
echo "✅ Systemd service created"

# ==========================================
# 6️⃣ CREATE DIRECTORIES
# ==========================================
echo "📁 Creating required directories..."
mkdir -p "$AGENT_DIR/chrome_profiles"
mkdir -p "$AGENT_DIR/logs"
chmod -R 755 "$AGENT_DIR"
echo "✅ Directories ready"

# ==========================================
# 7️⃣ START/RESTART SERVICE
# ==========================================
echo "🚀 Starting agent service..."

if systemctl is-active --quiet $SERVICE_NAME; then
    echo "🔄 Restarting $SERVICE_NAME..."
    systemctl restart $SERVICE_NAME
else
    echo "▶️ Starting $SERVICE_NAME..."
    systemctl start $SERVICE_NAME
    systemctl enable $SERVICE_NAME
fi

# Wait untuk service start
sleep 2

# Check status
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ Service is running!"
else
    echo "⚠️ Service might still be starting, check with: sudo systemctl status $SERVICE_NAME"
fi

# ==========================================
# 8️⃣ DISPLAY INFO
# ==========================================
echo ""
echo "======================================"
echo "✅ GHOST CMD Agent Installed!"
echo "======================================"
echo ""
echo "📋 Commands:"
echo "  Start:    sudo systemctl start $SERVICE_NAME"
echo "  Stop:     sudo systemctl stop $SERVICE_NAME"
echo "  Restart:  sudo systemctl restart $SERVICE_NAME"
echo "  Status:   sudo systemctl status $SERVICE_NAME"
echo "  Logs:     sudo journalctl -u $SERVICE_NAME -f"
echo "  Update:   cd $AGENT_DIR && sudo bash install.sh"
echo ""
echo "📊 Agent running on: http://localhost:7860"
echo "📡 Dashboard: $(grep DASHBOARD_URL $AGENT_DIR/.env | cut -d= -f2)"
echo ""
echo "🎯 Next step: Monitor logs dengan 'sudo journalctl -u $SERVICE_NAME -f'"
echo "======================================"
