#!/bin/bash
# GHOST CMD - Dashboard Installer
# Run once on main server
set -e

echo "🚀 GHOST CMD Dashboard Installer"
echo "=================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root: sudo bash install.sh"
    exit 1
fi

# ==========================================
# 1. System Update
# ==========================================
echo "📦 Updating system packages..."
apt-get update && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv git curl wget

# ==========================================
# 2. Setup Python Environment
# ==========================================
echo "🐍 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ==========================================
# 3. Setup Data Directories
# ==========================================
echo "📁 Creating data directories..."
mkdir -p data/slots
mkdir -p data/logs
mkdir -p static

# ==========================================
# 4. Cloudflare Tunnel Setup (Official Method)
# ==========================================
echo "🌐 Setting up Cloudflare Tunnel..."

# Install cloudflared via official repository
if ! command -v cloudflared &> /dev/null; then
    echo "📦 Adding Cloudflare official repository..."
    mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg | tee /usr/share/keyrings/cloudflare-public-v2.gpg >/dev/null
    
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main' | tee /etc/apt/sources.list.d/cloudflared.list
    
    apt-get update && apt-get install -y cloudflared
    echo "✅ cloudflared installed successfully"
else
    echo "✅ cloudflared already installed"
fi

# Input Tunnel Token
echo ""
echo "🔑 Masukkan Cloudflare Tunnel Token kamu"
echo "Cara mendapatkan token:"
echo "1. Login ke https://dash.cloudflare.com"
echo "2. Pilih Zero Trust → Networks → Tunnels"
echo "3. Create tunnel atau pilih tunnel yang sudah ada"
echo "4. Pilih 'Cloudflared connector' → Copy token"
echo ""
read -p "Paste Token di sini: " TUNNEL_TOKEN

if [ -z "$TUNNEL_TOKEN" ]; then
    echo "❌ Token tidak boleh kosong!"
    exit 1
fi

# Install Cloudflare Tunnel as systemd service
echo "🔧 Installing Cloudflare Tunnel service..."
cloudflared service install "$TUNNEL_TOKEN"
echo "✅ Tunnel service installed (cloudflared)"

# ==========================================
# 5. Create Systemd Service for Dashboard
# ==========================================
echo "⚙️ Creating GHOST Dashboard systemd service..."

cat > /etc/systemd/system/ghost-dashboard.service <<EOF
[Unit]
Description=GHOST CMD Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python3 app.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ghost-dashboard.service

# ==========================================
# 6. Start Services
# ==========================================
echo "🚀 Starting services..."
systemctl start ghost-dashboard.service
systemctl start cloudflared

sleep 3

# ==========================================
# 7. Final Message
# ==========================================
echo ""
echo "✅ Installation Complete!"
echo "=================================="
echo "📊 Local Dashboard : http://localhost:5000"
echo "🌐 Public URL      : https://dashboard.jujulefek.qzz.io"
echo "🔑 Auth Key        : GHOST_SECRET_2026"
echo ""
echo "🔧 Service Management:"
echo "   systemctl status ghost-dashboard"
echo "   systemctl status cloudflared"
echo ""
echo "🔄 Restart commands:"
echo "   systemctl restart ghost-dashboard"
echo "   systemctl restart cloudflared"
echo ""
echo "📋 View Logs:"
echo "   journalctl -u ghost-dashboard -f"
echo "   journalctl -u cloudflared -f"
echo ""
echo "🎉 Selamat! Dashboard kamu sudah aktif."
