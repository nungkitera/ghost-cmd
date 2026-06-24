import os
import subprocess
import psutil
import time
import requests
import threading
import re 
import sys
import socket
import json
import urllib3
import glob
import shutil
from urllib.parse import urlparse
from flask import Flask, request, jsonify

# Matikan Warning SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==========================================
# ⚙️ CONFIG
# ==========================================
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://dashboard.jujulefek.qzz.io")
AUTH_KEY = "GHOST_SECRET_2026"

FILE_LOGIN = "login.py"
FILE_LOOP = "loop.py"
LOG_FILE = "bot_log.txt"
MAPPING_FILE = "mapping_profil.txt"

# --- PATH CONFIG ---
BASE_DIR = os.getcwd()
PROFILE_DIR = os.path.join(BASE_DIR, "chrome_profiles")

# --- RESOLUSI LAYAR ---
SCREEN_LOGIN = "1280x720x24" 
SCREEN_LOOP = "500x500x24"   

# GLOBAL VARIABLE UNTUK MENYIMPAN SLOT ID
CURRENT_SLOT = None 

# ==========================================
# 🌉 NETWORK BRIDGE & DNS BYPASS
# ==========================================
old_getaddrinfo = socket.getaddrinfo
DNS_MAP = {} 

def resolve_domain_dynamic():
    print("🌉 [BRIDGE] Memulai Resolusi DNS Dinamis...", flush=True)
    try:
        domain = urlparse(DASHBOARD_URL).netloc
        if domain and domain not in DNS_MAP:
            print(f"🔍 [BRIDGE] Mencari IP untuk: {domain}...", flush=True)
            api_url = f"https://dns.google/resolve?name={domain}"
            resp = requests.get(api_url, timeout=10, verify=False)
            data = resp.json()
            
            if 'Answer' in data:
                ip_address = data['Answer'][0]['data']
                DNS_MAP[domain] = ip_address
                print(f"✅ [BRIDGE] Rute Ditemukan: {domain} -> {ip_address}", flush=True)
    except Exception as e:
        print(f"❌ [BRIDGE] Error Resolve: {e}", flush=True)

def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in DNS_MAP:
        return old_getaddrinfo(DNS_MAP[host], port, family, type, proto, flags)
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo
resolve_domain_dynamic()

# ==========================================
# 📡 LAPORAN STATUS
# ==========================================
def report_status(state, msg=""):
    """Mengirim laporan ke Dashboard"""
    global CURRENT_SLOT
    
    if not CURRENT_SLOT:
        return
    
    payload = {
        "slot": CURRENT_SLOT,
        "state": state,
        "msg": msg
    }

    try:
        requests.post(
            f"{DASHBOARD_URL}/api/report",
            json=payload,
            headers={"X-Auth-Key": AUTH_KEY},
            timeout=10,
            verify=False
        )
    except Exception as e:
        print(f"[REPORT] Error: {e}", flush=True)

# ==========================================
# 📧 CREDENTIAL LOADER (NEW)
# ==========================================
def load_credentials():
    """
    ✅ NEW: Load credentials dari berbagai format:
    1. Plain email (dari email.txt)
    2. Email:password (dari credentials.json)
    """
    credentials = []
    
    # Priority 1: Check untuk credentials.json (dari format email:password)
    if os.path.exists('credentials.json'):
        try:
            with open('credentials.json', 'r') as f:
                credentials = json.load(f)
                print(f"✅ [CRED] Loaded {len(credentials)} credentials dari JSON", flush=True)
                return credentials
        except Exception as e:
            print(f"⚠️ [CRED] Error loading JSON: {e}", flush=True)
    
    # Priority 2: Plain email.txt (backward compatible)
    if os.path.exists('email.txt'):
        try:
            with open('email.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if ':' in line:
                        # Format: email:password
                        parts = line.split(':', 1)
                        credentials.append({
                            'email': parts[0].strip(),
                            'password': parts[1].strip()
                        })
                    else:
                        # Plain email only
                        credentials.append({
                            'email': line,
                            'password': ''
                        })
            
            print(f"✅ [CRED] Loaded {len(credentials)} credentials dari email.txt", flush=True)
            
            # Save ke JSON untuk next time
            if credentials and not os.path.exists('credentials.json'):
                try:
                    with open('credentials.json', 'w') as f:
                        json.dump(credentials, f, indent=2)
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ [CRED] Error loading email.txt: {e}", flush=True)
    
    return credentials

# ==========================================
# 🛠️ PROCESS MANAGER
# ==========================================

def run_and_monitor(cmd_list, task_name):
    """Menjalankan proses dan memonitor hingga selesai"""
    print(f"🚀 [TASK] Memulai: {task_name}", flush=True)
    
    state_name = f"BUSY_{task_name}" 
    report_status(state_name, f"Running {task_name}...")

    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"\n--- START {task_name} : {time.ctime()} ---\n")
            f.flush()
            
            process = subprocess.Popen(
                cmd_list, stdout=f, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid
            )
            process.wait() 
            
            f.write(f"\n--- END {task_name} : {time.ctime()} ---\n")
    
        print(f"✅ [TASK] {task_name} Selesai.", flush=True)
        report_status("IDLE", f"{task_name} Finished")
        
    except Exception as e:
        print(f"❌ [TASK] Error: {e}", flush=True)
        report_status("IDLE", f"Error: {str(e)}")

def check_process(script_name):
    for p in psutil.process_iter(['cmdline']):
        try:
            if p.info['cmdline'] and script_name in ' '.join(p.info['cmdline']):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def kill_processes():
    print("🛑 [CLEANUP] Killing active processes...", flush=True)
    targets = [FILE_LOGIN, FILE_LOOP, 'chrome', 'chromedriver', 'xvfb']
    my_pid = os.getpid()

    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            if p.pid == my_pid: continue
            
            cmd_str = ' '.join(p.info['cmdline']) if p.info['cmdline'] else ''
            name_str = p.info['name'].lower()
            
            if any(t in cmd_str for t in targets) or any(t in name_str for t in targets):
                try: 
                    p.kill()
                except: pass
        except: pass
             
    time.sleep(2)
    
    try:
        for lock_file in glob.glob('/tmp/.X*-lock'):
            os.remove(lock_file)
        if os.path.exists('/tmp/.X11-unix'):
            shutil.rmtree('/tmp/.X11-unix', ignore_errors=True)
            os.makedirs('/tmp/.X11-unix', exist_ok=True)
    except Exception as e:
        print(f"⚠️ Error cleanup: {e}", flush=True)

def clean_system():
    try:
        for p in psutil.process_iter(['status']):
            if p.info['status'] == psutil.STATUS_ZOMBIE:
                try: p.wait(timeout=0) 
                except: pass
    except: pass
    
    try:
        for cache_dir in glob.glob(os.path.join(PROFILE_DIR, '*/Default/Cache')):
            shutil.rmtree(cache_dir, ignore_errors=True)
    except: pass

    try: os.system("sync") 
    except: pass

# ==========================================
# 🔄 AUTO REGISTER
# ==========================================
def auto_register():
    global CURRENT_SLOT
    print("⏳ [INIT] Menyiapkan URL Bot...", flush=True)
    time.sleep(3)

    hf_host = os.environ.get("SPACE_HOST")
    
    if hf_host:
        bot_url = f"https://{hf_host}"
        print(f"✅ [INIT] Berjalan di Hugging Face! URL: {bot_url}", flush=True)
    else:
        bot_url = "http://localhost:7860"
        print(f"⚠️ [INIT] SPACE_HOST tidak ditemukan. Menggunakan fallback: {bot_url}", flush=True)

    try:
        my_ip = requests.get('https://api.ipify.org', timeout=10, verify=False).text.strip()
    except:
        my_ip = "Unknown IP"

    registered = False
    
    while not registered:
        try:
            print(f"📡 [INIT] Register ke Dashboard: {DASHBOARD_URL} ...", flush=True)
            resp = requests.post(
                f"{DASHBOARD_URL}/api/register", 
                json={"url": bot_url, "ip": my_ip}, 
                headers={"X-Auth-Key": AUTH_KEY}, 
                timeout=20, verify=False 
            )

            if resp.status_code == 200:
                data = resp.json()
                CURRENT_SLOT = data.get('slot')
                locker = data.get('locker', {})

                print(f"\n✅ [INIT] TERDAFTAR DI SLOT: {CURRENT_SLOT}", flush=True)
                
                # ✅ NEW: Handle both plain email dan email:password format
                format_type = locker.get('format_type', 'plain_email')
                
                if format_type == 'email_password':
                    # Email:password format - save ke credentials.json
                    credentials = locker.get('credentials', [])
                    with open('credentials.json', 'w') as f:
                        json.dump(credentials, f, indent=2)
                    
                    # Also save emails untuk backward compatibility
                    emails = locker.get('emails', [])
                    with open('email.txt', 'w') as f:
                        f.write("\n".join(emails) + "\n")
                    
                    print(f"✅ [INIT] Saved {len(credentials)} credentials (email:password format)", flush=True)
                
                else:
                    # Plain email format
                    emails = locker.get('emails', [])
                    with open('email.txt', 'w') as f:
                        f.write("\n".join(emails) + "\n")
                    
                    print(f"✅ [INIT] Saved {len(emails)} emails (plain format)", flush=True)
                
                os.system("sed -i '/^$/d' email.txt")

                ack_success = False
                for i in range(5): 
                    try:
                        ack_resp = requests.post(
                            f"{DASHBOARD_URL}/api/ack", 
                            json={"slot": CURRENT_SLOT}, 
                            headers={"X-Auth-Key": AUTH_KEY}, 
                            timeout=10, verify=False
                        )
                        if ack_resp.status_code == 200:
                            print("✅ [ACK] Sinkronisasi Berhasil!", flush=True)
                            ack_success = True
                            break 
                    except:
                        time.sleep(1)
                
                if not ack_success:
                    print("💀 [FATAL] Gagal ACK. Ulangi Register...", flush=True)
                    CURRENT_SLOT = None
                    continue 

                registered = True
                return True

            elif resp.status_code == 503:
                print("⛔ [INIT] PANEL PENUH! Retry 10s...", flush=True)
        except Exception as e:
            print(f"❌ [INIT] Gagal koneksi: {e}", flush=True)
            resolve_domain_dynamic()
        
        if not registered: time.sleep(10)

# ==========================================
# 🤖 AUTOMATION FLOW
# ==========================================
def start_automatic_flow():
    """Flow Otomatis: Register -> Cek Data -> Login -> Loop"""
    
    print("\n🔹 [AUTO] STEP 1: Melakukan Registrasi...", flush=True)
    is_registered = auto_register()
    
    if not is_registered:
        print("❌ [AUTO] Registrasi gagal.")
        return

    report_status("IDLE", "Registered. Cooldown 10s...")
    print(f"⏳ [AUTO] STEP 2: Menunggu 10 detik...", flush=True)
    time.sleep(10)

    # PENGECEKAN DATA KOSONG
    has_valid_data = False
    try:
        emails_count = 0
        links_count = 0
        if os.path.exists('email.txt'):
            with open('email.txt', 'r') as f: emails_count = len([line for line in f if line.strip()])
        if os.path.exists('link.txt'):
            with open('link.txt', 'r') as f: links_count = len([line for line in f if line.strip()])
            
        if emails_count > 0 and links_count > 0:
            has_valid_data = True
    except Exception as e:
        print(f"⚠️ [AUTO] Error cek data: {e}", flush=True)

    # JIKA KOSONG: TETAP IDLE
    if not has_valid_data:
        print("⚠️ [AUTO] Data Kosong. Bot standby.", flush=True)
        report_status("IDLE", "Data Empty. Standby")
        return

    # RUN LOGIN.PY
    print("\n🔹 [AUTO] STEP 3: Data terdeteksi. Running login.py...", flush=True)
    if not check_process(FILE_LOGIN) and not check_process(FILE_LOOP):
        cmd_login = (
            f"xvfb-run -a --server-args='-screen 0 {SCREEN_LOGIN}' "
            f"{sys.executable} {FILE_LOGIN}"
        )
        run_and_monitor(cmd_login, "LOGIN")
    else:
        print("⚠️ [AUTO] Proses lain sedang jalan.")
        report_status("IDLE", "Login Skipped (Busy)")

    # RUN LOOP.PY
    print("\n🔹 [AUTO] STEP 4: Login selesai. Running loop.py...", flush=True)
    if not check_process(FILE_LOOP):
        cmd_loop = (
            f"xvfb-run -a --server-args='-screen 0 {SCREEN_LOOP}' "
            f"{sys.executable} -u {FILE_LOOP}"
        )
        run_and_monitor(cmd_loop, "LOOP")
    else:
        print("⚠️ [AUTO] Loop sudah jalan.")

# ==========================================
# 🌐 API ENDPOINTS
# ==========================================

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>GHOST CMD Agent</title></head>
    <body style="text-align:center">
        <h1>🚀 GHOST CMD Agent</h1>
        <p>Slot: <b id="slot">-</b></p>
        <p>Status: <b id="status">IDLE</b></p>
        <p style="font-size:12px; color:#666;">Format: <b id="format">-</b></p>
    </body>
    <script>
        setInterval(async () => {
            try {
                const res = await fetch('/status');
                const data = await res.json();
                document.getElementById('slot').innerText = data.slot || '-';
                document.getElementById('status').innerText = data.state || 'IDLE';
                document.getElementById('format').innerText = data.format_type || '-';
            } catch(e) {}
        }, 2000);
    </script>
    </html>
    """

@app.before_request
def auth():
    if request.endpoint == 'index' or request.endpoint == 'status':
        return
    if request.headers.get("X-Auth-Key") != AUTH_KEY:
        return jsonify({"error": "Unauthorized"}), 401

@app.route('/status', methods=['GET'])
def status():
    state = "IDLE"
    if check_process(FILE_LOGIN): state = "BUSY_LOGIN"
    if check_process(FILE_LOOP): state = "BUSY_LOOP"
    
    # ✅ NEW: Include format type di status
    format_type = "email_password" if os.path.exists('credentials.json') else "plain_email"
    
    return jsonify({
        "slot": CURRENT_SLOT,
        "login": check_process(FILE_LOGIN),
        "loop": check_process(FILE_LOOP),
        "state": state,
        "format_type": format_type,
        "credentials_count": len(load_credentials())
    })

@app.route('/start/login', methods=['POST'])
def menu_1():
    if check_process(FILE_LOGIN): return jsonify({"msg": "Login sudah jalan!", "status": "busy"})
    if check_process(FILE_LOOP): return jsonify({"msg": "Loop sedang jalan!", "status": "busy"})
    
    cmd = (
        f"xvfb-run -a --server-args='-screen 0 {SCREEN_LOGIN}' "
        f"{sys.executable} {FILE_LOGIN}" 
    )
    
    threading.Thread(target=run_and_monitor, args=(cmd, "LOGIN"), daemon=True).start()
    return jsonify({"msg": "Login Started", "status": "ok"})

@app.route('/start/loop', methods=['POST'])
def menu_2():
    if check_process(FILE_LOOP): return jsonify({"msg": "Loop sudah jalan!", "status": "busy"})
    if check_process(FILE_LOGIN): return jsonify({"msg": "Login sedang jalan!", "status": "busy"})

    cmd = (
        f"xvfb-run -a --server-args='-screen 0 {SCREEN_LOOP}' "
        f"{sys.executable} -u {FILE_LOOP}" 
    )
    
    threading.Thread(target=run_and_monitor, args=(cmd, "LOOP"), daemon=True).start()
    return jsonify({"msg": "Loop Started", "status": "ok"})

@app.route('/logs', methods=['GET'])
def menu_3():
    if not os.path.exists(LOG_FILE): return jsonify({"logs": "No Logs."})
    try:
        raw = subprocess.check_output(['tail', '-n', '50', LOG_FILE]).decode('utf-8', errors='ignore')
        return jsonify({"logs": re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', raw)})
    except Exception as e: return jsonify({"logs": str(e)})

@app.route('/stop', methods=['POST'])
def menu_4():
    kill_processes()
    clean_system()
    open(LOG_FILE, 'w').close()
    if CURRENT_SLOT: report_status("IDLE", "Stopped by Admin")
    return jsonify({"msg": "Stopped & Cleaned"})

@app.route('/clean_ram', methods=['POST'])
def menu_7():
    clean_system()
    mem = psutil.virtual_memory()
    return jsonify({"msg": "RAM Optimized", "free": f"{mem.available // 1048576} MB"})

# ==========================================
# 🖼️ MAIN
# ==========================================
if __name__ == '__main__':
    threading.Thread(target=start_automatic_flow, daemon=True).start()
    print("🚀 Agent Flask API running on port 7860...")
    app.run(host='0.0.0.0', port=7860, debug=False, threaded=True)
