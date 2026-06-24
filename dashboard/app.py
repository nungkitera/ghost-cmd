#!/usr/bin/env python3
"""
GHOST CMD - Dashboard Backend
Multi-agent control panel with local TXT storage
Cloudflare tunnel ready
"""

import os
import json
import time
import threading
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# ⚙️ CONFIG
# ==========================================
APP_DIR = Path(__file__).parent.absolute()
DATA_DIR = APP_DIR / "data"
SLOTS_DIR = DATA_DIR / "slots"
LOGS_DIR = DATA_DIR / "logs"

AUTH_KEY = "GHOST_SECRET_2026"
MAX_SLOTS = 192
CURRENT_GRID = 6

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
SLOTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ==========================================
# 🌐 FLASK SETUP
# ==========================================
app = Flask(__name__, 
    static_folder="static",
    template_folder="templates",
    static_url_path="/static"
)
CORS(app)

# ==========================================
# 📦 SLOT DATA MANAGER
# ==========================================
class SlotManager:
    def __init__(self):
        self.slots = {}
        self.lock = threading.Lock()
        self.last_hash = None  # Track data changes
        self.load_all_slots()
    
    def load_all_slots(self):
        """Load all slot data from JSON files"""
        with self.lock:
            self.slots = {}
            for i in range(1, MAX_SLOTS + 1):
                self.slots[i] = self.load_slot(i)
    
    def load_slot(self, slot_id):
        """Load single slot data"""
        slot_file = SLOTS_DIR / f"slot_{slot_id}.json"
        
        default = {
            "id": slot_id,
            "status": "- Kosong -",
            "ip": None,
            "emails": 0,
            "links": 0,
            "isLooping": False,
            "isOffline": True,
            "lastUpdate": None,
            "agent_url": None,
            "emails_file": "",
            "links_file": "",
        }
        
        if slot_file.exists():
            try:
                with open(slot_file, 'r') as f:
                    data = json.load(f)
                    default.update(data)
                    # Count emails and links
                    default["emails"] = len([l for l in data.get("emails_file", "").split("\n") if l.strip()])
                    default["links"] = len([l for l in data.get("links_file", "").split("\n") if l.strip()])
            except:
                pass
        
        return default
    
    def save_slot(self, slot_id, data):
        """Save slot data to JSON"""
        with self.lock:
            slot_file = SLOTS_DIR / f"slot_{slot_id}.json"
            data["lastUpdate"] = datetime.now().isoformat()
            with open(slot_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.slots[slot_id] = data
    
    def get_slot(self, slot_id):
        """Get slot data"""
        return self.slots.get(slot_id, {})
    
    def get_all_slots(self):
        """Get all slots"""
        return list(self.slots.values())
    
    def get_hash(self):
        """Get hash of current data to detect changes"""
        slots_json = json.dumps(self.get_all_slots(), sort_keys=True)
        import hashlib
        return hashlib.md5(slots_json.encode()).hexdigest()
    
    def has_changes(self):
        """Check if data has changed since last check"""
        current_hash = self.get_hash()
        changed = current_hash != self.last_hash
        self.last_hash = current_hash
        return changed
    
    def update_slot_status(self, slot_id, status, ip=None):
        """Update slot status from agent report"""
        slot = self.get_slot(slot_id)
        slot["status"] = status
        if ip:
            slot["ip"] = ip
        
        if "BUSY" in status:
            slot["isLooping"] = True
            slot["isOffline"] = False
        elif "IDLE" in status or "Connected" in status:
            slot["isLooping"] = False
            slot["isOffline"] = False
        else:
            slot["isOffline"] = True
        
        self.save_slot(slot_id, slot)

slot_manager = SlotManager()

# ==========================================
# 🔐 AUTH DECORATOR
# ==========================================
def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_key = request.headers.get('X-Auth-Key')
        if auth_key != AUTH_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ==========================================
# 📡 API ENDPOINTS
# ==========================================

@app.route('/')
def index():
    """Serve dashboard HTML"""
    return render_template('index.html')

@app.route('/api/status')
def status():
    """Get dashboard status"""
    slots = slot_manager.get_all_slots()
    
    online = sum(1 for s in slots if not s['isOffline'])
    busy = sum(1 for s in slots if s['isLooping'])
    total_data = sum(s['emails'] + s['links'] for s in slots)
    
    return jsonify({
        "online": online,
        "busy": busy,
        "data": total_data,
        "max_slots": MAX_SLOTS,
        "current_grid": CURRENT_GRID
    })

@app.route('/api/slots')
def get_slots():
    """Get all slots data"""
    return jsonify(slot_manager.get_all_slots())

@app.route('/api/slots/check')
def check_changes():
    """Check if slots data has changed (untuk smart refresh)"""
    # Reload dari disk
    slot_manager.load_all_slots()
    has_changes = slot_manager.has_changes()
    
    return jsonify({
        "changed": has_changes,
        "slots": slot_manager.get_all_slots() if has_changes else None
    })

@app.route('/api/slot/<int:slot_id>', methods=['GET', 'POST'])
@require_auth
def slot_handler(slot_id):
    """Get or update slot data"""
    if slot_id < 1 or slot_id > MAX_SLOTS:
        return jsonify({"error": "Invalid slot ID"}), 400
    
    if request.method == 'GET':
        return jsonify(slot_manager.get_slot(slot_id))
    
    elif request.method == 'POST':
        data = request.get_json()
        slot = slot_manager.get_slot(slot_id)
        
        if 'emails_file' in data:
            slot['emails_file'] = data['emails_file']
        if 'links_file' in data:
            slot['links_file'] = data['links_file']
        
        slot_manager.save_slot(slot_id, slot)
        return jsonify({"status": "saved"})

@app.route('/api/register', methods=['POST'])
@require_auth
def register_agent():
    """Register new agent (from agent.py)"""
    data = request.get_json()
    agent_url = data.get('url')
    agent_ip = data.get('ip')
    
    # Find available slot
    for slot_id in range(1, MAX_SLOTS + 1):
        slot = slot_manager.get_slot(slot_id)
        if slot['isOffline'] or slot['status'] == '- Kosong -':
            # Assign slot
            slot['agent_url'] = agent_url
            slot['ip'] = agent_ip
            slot['status'] = '🔌 WS CONNECTED'
            slot['isOffline'] = False
            
            # Load emails and links for this slot
            emails = slot['emails_file'].split('\n') if slot['emails_file'] else []
            links = slot['links_file'].split('\n') if slot['links_file'] else []
            
            slot_manager.save_slot(slot_id, slot)
            
            return jsonify({
                "slot": slot_id,
                "locker": {
                    "emails": [e.strip() for e in emails if e.strip()],
                    "links": [l.strip() for l in links if l.strip()]
                }
            }), 200
    
    return jsonify({"error": "No available slots"}), 503

@app.route('/api/report', methods=['POST'])
@require_auth
def report_status():
    """Receive status report from agent"""
    data = request.get_json()
    slot_id = data.get('slot')
    state = data.get('state', 'IDLE')
    msg = data.get('msg', '')
    
    slot_manager.update_slot_status(slot_id, state)
    
    # Log report
    log_file = LOGS_DIR / f"slot_{slot_id}.log"
    with open(log_file, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {state}: {msg}\n")
    
    return jsonify({"status": "received"})

@app.route('/api/ack', methods=['POST'])
@require_auth
def ack_slot():
    """Acknowledge slot registration"""
    data = request.get_json()
    slot_id = data.get('slot')
    
    slot = slot_manager.get_slot(slot_id)
    slot['status'] = '✅ READY'
    slot_manager.save_slot(slot_id, slot)
    
    return jsonify({"status": "ack_received"})

@app.route('/api/command/<int:slot_id>/<command>', methods=['POST'])
@require_auth
def send_command(slot_id, command):
    """Send command to agent"""
    slot = slot_manager.get_slot(slot_id)
    agent_url = slot.get('agent_url')
    
    if not agent_url:
        return jsonify({"error": "Agent not connected"}), 400
    
    endpoint_map = {
        'login': '/start/login',
        'loop': '/start/loop',
        'stop': '/stop',
        'sync': '/clean_ram',
    }
    
    endpoint = endpoint_map.get(command)
    if not endpoint:
        return jsonify({"error": "Unknown command"}), 400
    
    try:
        resp = requests.post(
            f"{agent_url}{endpoint}",
            headers={"X-Auth-Key": AUTH_KEY},
            timeout=10,
            verify=False
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs/<int:slot_id>')
@require_auth
def get_logs(slot_id):
    """Get logs for slot"""
    log_file = LOGS_DIR / f"slot_{slot_id}.log"
    
    if not log_file.exists():
        return jsonify({"logs": "No logs yet"})
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            logs = ''.join(lines[-50:])
        return jsonify({"logs": logs})
    except:
        return jsonify({"logs": "Error reading logs"})

@app.route('/api/bulk/upload', methods=['POST'])
@require_auth
def bulk_upload():
    """Bulk upload emails and links to multiple slots"""
    data = request.get_json()
    selected_slots = data.get('slots', [])
    emails = data.get('emails', '').split('\n')
    links = data.get('links', '').split('\n')
    
    emails = [e.strip() for e in emails if e.strip()]
    links = [l.strip() for l in links if l.strip()]
    
    if not emails or not links:
        return jsonify({"error": "No emails or links provided"}), 400
    
    emails_per_slot = len(emails) // len(selected_slots) if selected_slots else 0
    links_per_slot = len(links) // len(selected_slots) if selected_slots else 0
    
    for idx, slot_id in enumerate(selected_slots):
        start_e = idx * emails_per_slot
        end_e = start_e + emails_per_slot
        start_l = idx * links_per_slot
        end_l = start_l + links_per_slot
        
        slot = slot_manager.get_slot(slot_id)
        slot['emails_file'] = '\n'.join(emails[start_e:end_e])
        slot['links_file'] = '\n'.join(links[start_l:end_l])
        slot_manager.save_slot(slot_id, slot)
    
    return jsonify({"status": "uploaded", "slots": selected_slots})

@app.route('/api/mass/command/<command>', methods=['POST'])
@require_auth
def mass_command(command):
    """Send command to multiple slots"""
    data = request.get_json()
    slot_ids = data.get('slots', [])
    
    results = {}
    for slot_id in slot_ids:
        slot = slot_manager.get_slot(slot_id)
        agent_url = slot.get('agent_url')
        
        if not agent_url:
            results[slot_id] = "Not connected"
            continue
        
        endpoint_map = {
            'login': '/start/login',
            'loop': '/start/loop',
            'stop': '/stop',
            'sync': '/clean_ram',
        }
        
        endpoint = endpoint_map.get(command)
        if not endpoint:
            results[slot_id] = "Unknown command"
            continue
        
        try:
            resp = requests.post(
                f"{agent_url}{endpoint}",
                headers={"X-Auth-Key": AUTH_KEY},
                timeout=5,
                verify=False
            )
            results[slot_id] = "OK" if resp.status_code == 200 else "Failed"
        except:
            results[slot_id] = "Error"
    
    return jsonify({"results": results})

# ==========================================
# 🚀 MAIN
# ==========================================
if __name__ == '__main__':
    print("🚀 GHOST CMD Dashboard Starting on port 5000...")
    print(f"📊 Dashboard: http://0.0.0.0:5000")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )
