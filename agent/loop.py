from multiprocessing import Process, Manager
import os
import time
import sys
import json
import psutil

try:
    from modul_bot import worker, get_profiles_from_mapping, read_file_lines
except ImportError:
    print("❌ Error: modul_bot.py tidak ditemukan!")
    sys.exit(1)

# ==========================================
# ⚙️ KONFIGURASI
# ==========================================
STATUS_FILE = "monitor.json"
MAX_BATCH_TIME = 43200 # 12 Jam

# ==========================================
# 🛠️ UTILS
# ==========================================
def force_kill_chrome():
    print("🧹 [CLEANUP] Scanning for stray Chrome processes...", flush=True)
    
    targets = ['chrome', 'chromedriver', 'chromium', 'google-chrome']
    my_pid = os.getpid()
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.pid == my_pid: continue
            
            if any(t in proc.info['name'].lower() for t in targets):
                try:
                    proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    time.sleep(2)
    clean_zombies()

def clean_zombies():
    try:
        for proc in psutil.process_iter(['pid', 'status']):
            if proc.info['status'] == psutil.STATUS_ZOMBIE:
                try: 
                    proc.wait(timeout=0)
                except: 
                    pass
    except: pass

def save_status(status_dict, time_remaining):
    try:
        data = {
            "time_remaining": time_remaining,
            "workers": dict(status_dict)
        }
        with open(STATUS_FILE + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(STATUS_FILE + ".tmp", STATUS_FILE)
    except: pass

# ==========================================
# 🚀 MAIN LOOP PROCESS
# ==========================================
if __name__ == "__main__":
    BASE_DIR = os.getcwd()
    MAPPING_FILE = os.path.join(BASE_DIR, "mapping_profil.txt")
    LINK_FILE = os.path.join(BASE_DIR, "link.txt")
    
    if os.path.exists(STATUS_FILE): os.remove(STATUS_FILE)

    print("🚀 [LOOP] Service Started. Monitoring via 'monitor.json'", flush=True)

    with Manager() as manager:
        status_dict = manager.dict()

        while True:
            force_kill_chrome()
            
            status_dict['SYSTEM'] = "Initializing Batch..."
            save_status(status_dict, MAX_BATCH_TIME)
            time.sleep(3) 

            if not os.path.exists(MAPPING_FILE) or not os.path.exists(LINK_FILE):
                status_dict['SYSTEM'] = "Waiting for Data Files..."
                save_status(status_dict, MAX_BATCH_TIME)
                time.sleep(10)
                continue

            user_profiles = get_profiles_from_mapping(MAPPING_FILE)
            all_links = read_file_lines(LINK_FILE)
            
            if not user_profiles or not all_links:
                status_dict['SYSTEM'] = "Data Empty (Profiles/Links Missing)"
                save_status(status_dict, MAX_BATCH_TIME)
                time.sleep(10)
                continue
            
            status_dict['SYSTEM'] = "Running"
            for p in user_profiles:
                status_dict[p['name']] = "Idle (Waiting Queue)"

            links_for_profiles = [[] for _ in user_profiles]
            for i, link in enumerate(all_links):
                links_for_profiles[i % len(user_profiles)].append(link)
            
            processes = []

            print(f"🔄 [LOOP] Starting Batch: {len(user_profiles)} Workers | {len(all_links)} Links", flush=True)

            for i, profile in enumerate(user_profiles):
                p = Process(target=worker, args=(
                    profile['name'],
                    profile['user_data_dir'],
                    profile['profile_dir'],
                    profile['window_position'],
                    links_for_profiles[i],
                    status_dict
                ))
                p.start()
                processes.append(p)
                time.sleep(1) 

            start_wait = time.time()
            
            while True:
                elapsed = int(time.time() - start_wait)
                sisa = MAX_BATCH_TIME - elapsed
                
                save_status(status_dict, sisa)
                
                if not any(p.is_alive() for p in processes):
                    status_dict['SYSTEM'] = "Batch Finished. Restarting..."
                    save_status(status_dict, 0)
                    print("✅ [LOOP] Batch Finished.", flush=True)
                    break
                
                if elapsed > MAX_BATCH_TIME:
                    print(f"⚠️ [LOOP] Batch Timeout ({MAX_BATCH_TIME}s). Killing workers...", flush=True)
                    status_dict['SYSTEM'] = "Time Limit Reached."
                    save_status(status_dict, 0)
                    
                    for p in processes:
                        if p.is_alive():
                            try:
                                p.terminate()
                                p.join(timeout=1)
                                if p.is_alive():
                                    p.kill()
                            except: pass
                    break
                
                time.sleep(2)

            processes = [] 
            force_kill_chrome()
            time.sleep(5)
