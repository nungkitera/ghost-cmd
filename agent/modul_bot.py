from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import os
import time
import gc

# --- KONFIGURASI WAKTU ---
SLEEP_SEBELUM_AKSI = 50
SLEEP_SESUDAH_AKSI = 20
SLEEP_JIKA_ERROR = 2 

def get_options(user_data_dir, profile_dir):
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_dir}")
    
    options.add_argument("--test-type")
    options.add_argument("--simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT'")
    options.add_argument("--disable-component-update")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    
    options.add_argument("--remote-allow-origins=*") 
    
    options.add_argument("--disable-gpu") 
    options.add_argument("--no-sandbox") 
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-infobars")
    options.add_argument("--window-size=500,500")
    options.add_argument("--disable-extensions")
    
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.exit_type": "Normal", 
        "profile.exited_cleanly": True
    })
    return options

def read_file_lines(path):
    if not os.path.exists(path): return []
    with open(path, 'r') as f: return [line.strip() for line in f if line.strip()]

def get_profiles_from_mapping(path):
    profiles = []
    base_docker_path = os.path.join(os.getcwd(), "chrome_profiles")
    
    lines = read_file_lines(path)
    for line in lines:
        if "|" in line:
            parts = line.split("|")
            original_path = parts[0].strip()
            name = parts[1].strip()
            
            folder_name = os.path.basename(original_path)
            if not folder_name: folder_name = name 
            
            final_path = os.path.join(base_docker_path, folder_name)
            
            profiles.append({
                "name": name,
                "user_data_dir": final_path,
                "profile_dir": "Default",
                "window_position": (0, 0)
            })
    return profiles

def process_single_link(driver, link, profile_name, status_dict):
    try:
        status_dict[profile_name] = f"Membuka: {link}..."
        
        driver.set_page_load_timeout(20)
        try:
            driver.get(link)
        except TimeoutException:
            status_dict[profile_name] = "Page load timeout (Lanjut cek elemen)..."
        except Exception:
            status_dict[profile_name] = "Gagal memuat URL -> SKIP"
            return False

        wait = WebDriverWait(driver, 10)

        try:
            trust = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'I trust the owner')]")))
            trust.click()
            status_dict[profile_name] = "Klik Trust"
            time.sleep(2)
        except: pass 

        try:
            open_ws = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Open Workspace')]")))
            open_ws.click()
            status_dict[profile_name] = "Klik Open"
            time.sleep(2)
        except: pass 

        try:
            status_dict[profile_name] = "Menunggu Iframe IDE..."
            wait.until(EC.visibility_of_element_located((
                By.CSS_SELECTOR, "iframe.the-iframe.is-loaded[src*='ide-start']"
            )))
            status_dict[profile_name] = "✅ Iframe Muncul! Lanjut..."
        except: 
            status_dict[profile_name] = "❌ Iframe Gak Muncul -> SKIP LINK"
            return False 

        status_dict[profile_name] = f"Idle {SLEEP_SEBELUM_AKSI}s..."
        time.sleep(SLEEP_SEBELUM_AKSI)
        
        try:
            driver.find_element(By.TAG_NAME, "body").click()
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys("c").key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
            status_dict[profile_name] = "Shortcut Terkirim!"
        except:
            status_dict[profile_name] = "Gagal kirim shortcut"
            
        time.sleep(SLEEP_SESUDAH_AKSI)
        status_dict[profile_name] = "✅ Selesai link ini."
        return True

    except Exception as e:
        status_dict[profile_name] = f"❌ Error System: {str(e)[:20]}..."
        time.sleep(SLEEP_JIKA_ERROR)
        return False
        
def worker(profile_name, user_data_dir, profile_dir, window_position, links, status_dict):
    if not links:
        status_dict[profile_name] = "Tidak ada link."
        return

    options = get_options(user_data_dir, profile_dir)
    driver = None
    try:
        status_dict[profile_name] = "Start Browser..."
        driver = webdriver.Chrome(options=options)
        
        if window_position: 
            driver.set_window_position(*window_position)

        putaran = 1
        while True: 
            status_dict[profile_name] = f"🔄 Masuk Putaran ke-{putaran}"
            for i, link in enumerate(links):
                status_dict[profile_name] = f"[P{putaran}] Link {i+1}..."
                
                gc.collect() 
                
                process_single_link(driver, link, profile_name, status_dict)
                
            status_dict[profile_name] = f"✅ Putaran {putaran} Done. Replay..."
            putaran += 1
            time.sleep(3) 
            
    except Exception as e:
        status_dict[profile_name] = f"CRITICAL: {e}"
    finally:
        if driver:
            try: driver.quit()
            except: pass
