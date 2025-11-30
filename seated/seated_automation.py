#!/usr/bin/env python3
"""
Seated Event Reminder Automation met Dolphin Anty
=================================================

Automatisch aanmelden voor Seated event reminders met:
- Unieke browser profiles per email via Dolphin Anty
- Unieke proxies per signup
- Unieke fingerprints
- Twilio SMS verificatie voor UK nummers
- Nederlandse postcodes
- Automatische cleanup (profiel + proxy verwijderen)
- Multi-threading support

Usage:
    python3 seated_automation.py
"""

import os
import sys
import time
import json
import requests
import random
import signal
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

try:
    from twilio.rest import Client
except ImportError:
    print("❌ Twilio library niet geïnstalleerd!")
    print("💡 Run: pip install twilio")
    sys.exit(1)

# Thread lock voor thread-safe file operations
EMAIL_FILE_LOCK = threading.Lock()

# ==============================================================================
# CONFIGURATIE LADEN
# ==============================================================================

def load_config():
    """Laad configuratie uit config.json"""
    try:
        with open(os.path.join(os.path.dirname(__file__), 'config.json'), 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print("❌ config.json niet gevonden!")
        print("💡 Maak een config.json bestand met je tokens")
        return None
    except json.JSONDecodeError:
        print("❌ config.json is ongeldig!")
        return None

# Laad configuratie
CONFIG = load_config()
if not CONFIG:
    exit(1)

# Configuratie variabelen
DOLPHIN_TOKEN = CONFIG.get('dolphin_token')
TWILIO_ACCOUNT_SID = CONFIG.get('twilio_account_sid')
TWILIO_AUTH_TOKEN = CONFIG.get('twilio_auth_token')
TWILIO_SERVICE_SID = CONFIG.get('twilio_service_sid')
MAX_THREADS = CONFIG.get('max_threads', 5)
TEST_MODE = CONFIG.get('test_mode', False)
TARGET_URL = CONFIG.get('target_url', 'https://link.seated.com/cd6659bf-4e2c-4b71-a106-5e24355a8794')
RANDOM_DELAY_MIN = CONFIG.get('random_delay_min', 1.5)
RANDOM_DELAY_MAX = CONFIG.get('random_delay_max', 4.0)
USE_MOUSE_MOVEMENTS = CONFIG.get('use_mouse_movements', True)
USE_RANDOM_TYPING_SPEED = CONFIG.get('use_random_typing_speed', True)

# API URLs
REMOTE_API = "https://dolphin-anty-api.com"
LOCAL_API = "http://localhost:3001/v1.0"

# Files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EMAILS_FILE = os.path.join(SCRIPT_DIR, "emails.txt")
LOG_FILE = os.path.join(SCRIPT_DIR, "seated_log.txt")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "seated_results.csv")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "seated_history.txt")
SUCCESS_FILE = os.path.join(SCRIPT_DIR, f"seated_success_{time.strftime('%Y-%m-%d')}.txt")

# STOP SIGNAL - Voor het stoppen van de script
STOP_SIGNAL = False
ACTIVE_PROFILES = []  # Track actieve profielen voor cleanup
ACTIVE_PROFILE_IDS = set()  # Track actieve profiel IDs voor threading
PROFILE_TRACKING_LOCK = threading.Lock()  # Thread lock voor thread-safe profile tracking
# Global lijst van beschikbare profielen (wordt gedeeld tussen threads)
AVAILABLE_PROFILE_POOL = []
AVAILABLE_PROFILE_POOL_LOCK = threading.Lock()
USED_PHONE_NUMBERS = {}  # Track gebruikte telefoonnummers: {phone_number: {link: timestamp}}
SUCCESS_PHONES = set()  # Track succesvolle telefoonnummers per link: {(phone_number, link)}
USED_PHONE_LOCK = threading.Lock()  # Thread lock voor thread-safe phone tracking

# Browser mode settings
HEADLESS_MODE = False  # Default: browsers zichtbaar (Cloudflare blokkeert headless browsers!)

def stop_automation():
    """Stop de automation script"""
    global STOP_SIGNAL
    STOP_SIGNAL = True
    print("🛑 Stop signal verzonden...")

def cleanup_on_exit():
    """Cleanup functie die wordt aangeroepen bij exit"""
    print("\n🧹 Graceful shutdown - cleanup actieve browsers...")
    
    if ACTIVE_PROFILES:
        api = DolphinAPI(DOLPHIN_TOKEN)
        for profile_id in ACTIVE_PROFILES[:]:
            try:
                api.stop_profile(profile_id)
                api.delete_profile(profile_id)
            except:
                pass

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print(f"\n🛑 Signal {signum} ontvangen - graceful shutdown...")
    stop_automation()

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def random_delay(min_seconds=None, max_seconds=None):
    """Willekeurige delay tussen min en max seconden"""
    if min_seconds is None:
        min_seconds = RANDOM_DELAY_MIN
    if max_seconds is None:
        max_seconds = RANDOM_DELAY_MAX
    
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def generate_random_name():
    """Genereer willekeurige Nederlandse voornamen en achternamen"""
    first_names = [
        "Jan", "Piet", "Klaas", "Henk", "Willem", "Frans", "Johan", "Dirk", "Gerrit", "Cornelis",
        "Maria", "Anna", "Johanna", "Cornelia", "Willemina", "Elisabeth", "Catharina", "Geertruida", "Petronella", "Adriana"
    ]
    last_names = [
        "de Vries", "Jansen", "de Jong", "Bakker", "Visser", "Smit", "Meijer", "de Boer", "Mulder", "de Groot",
        "Bos", "Vos", "Peters", "Hendriks", "van Dijk", "Dijkstra", "van der Berg", "van Leeuwen", "de Wit", "Post"
    ]
    
    return {
        "first": random.choice(first_names),
        "last": random.choice(last_names)
    }

def generate_dutch_postcode():
    """Genereer echte Nederlandse postcode (format: 1234 AB)"""
    # Echte Nederlandse postcodes met geldige letter combinaties
    real_postcodes = [
        "1012 AB", "1012 AC", "1012 AD", "1012 AE", "1012 AG", "1012 AH", "1012 AJ", "1012 AK", "1012 AL", "1012 AN",
        "1012 AP", "1012 AR", "1012 AS", "1012 AT", "1012 AV", "1012 AW", "1012 AX", "1012 AZ", "1012 BA", "1012 BB",
        "1051 AB", "1051 AC", "1051 AD", "1051 AE", "1051 AG", "1051 AH", "1051 AJ", "1051 AK", "1051 AL", "1051 AN",
        "1052 AB", "1052 AC", "1052 AD", "1052 AE", "1052 AG", "1052 AH", "1052 AJ", "1052 AK", "1052 AL", "1052 AN",
        "1071 AB", "1071 AC", "1071 AD", "1071 AE", "1071 AG", "1071 AH", "1071 AJ", "1071 AK", "1071 AL", "1071 AN",
        "1072 AB", "1072 AC", "1072 AD", "1072 AE", "1072 AG", "1072 AH", "1072 AJ", "1072 AK", "1072 AL", "1072 AN",
        "1073 AB", "1073 AC", "1073 AD", "1073 AE", "1073 AG", "1073 AH", "1073 AJ", "1073 AK", "1073 AL", "1073 AN",
        "1074 AB", "1074 AC", "1074 AD", "1074 AE", "1074 AG", "1074 AH", "1074 AJ", "1074 AK", "1074 AL", "1074 AN",
        "1075 AB", "1075 AC", "1075 AD", "1075 AE", "1075 AG", "1075 AH", "1075 AJ", "1075 AK", "1075 AL", "1075 AN",
        "1076 AB", "1076 AC", "1076 AD", "1076 AE", "1076 AG", "1076 AH", "1076 AJ", "1076 AK", "1076 AL", "1076 AN",
        "1077 AB", "1077 AC", "1077 AD", "1077 AE", "1077 AG", "1077 AH", "1077 AJ", "1077 AK", "1077 AL", "1077 AN",
        "1078 AB", "1078 AC", "1078 AD", "1078 AE", "1078 AG", "1078 AH", "1078 AJ", "1078 AK", "1078 AL", "1078 AN",
        "1079 AB", "1079 AC", "1079 AD", "1079 AE", "1079 AG", "1079 AH", "1079 AJ", "1079 AK", "1079 AL", "1079 AN",
        "1081 AB", "1081 AC", "1081 AD", "1081 AE", "1081 AG", "1081 AH", "1081 AJ", "1081 AK", "1081 AL", "1081 AN",
        "1082 AB", "1082 AC", "1082 AD", "1082 AE", "1082 AG", "1082 AH", "1082 AJ", "1082 AK", "1082 AL", "1082 AN",
        "1083 AB", "1083 AC", "1083 AD", "1083 AE", "1083 AG", "1083 AH", "1083 AJ", "1083 AK", "1083 AL", "1083 AN",
        "1091 AB", "1091 AC", "1091 AD", "1091 AE", "1091 AG", "1091 AH", "1091 AJ", "1091 AK", "1091 AL", "1091 AN",
        "1092 AB", "1092 AC", "1092 AD", "1092 AE", "1092 AG", "1092 AH", "1092 AJ", "1092 AK", "1092 AL", "1092 AN",
        "1093 AB", "1093 AC", "1093 AD", "1093 AE", "1093 AG", "1093 AH", "1093 AJ", "1093 AK", "1093 AL", "1093 AN",
        "1094 AB", "1094 AC", "1094 AD", "1094 AE", "1094 AG", "1094 AH", "1094 AJ", "1094 AK", "1094 AL", "1094 AN",
        "1095 AB", "1095 AC", "1095 AD", "1095 AE", "1095 AG", "1095 AH", "1095 AJ", "1095 AK", "1095 AL", "1095 AN",
        "1101 AB", "1101 AC", "1101 AD", "1101 AE", "1101 AG", "1101 AH", "1101 AJ", "1101 AK", "1101 AL", "1101 AN",
        "1102 AB", "1102 AC", "1102 AD", "1102 AE", "1102 AG", "1102 AH", "1102 AJ", "1102 AK", "1102 AL", "1102 AN",
        "1171 AB", "1171 AC", "1171 AD", "1171 AE", "1171 AG", "1171 AH", "1171 AJ", "1171 AK", "1171 AL", "1171 AN",
        "1172 AB", "1172 AC", "1172 AD", "1172 AE", "1172 AG", "1172 AH", "1172 AJ", "1172 AK", "1172 AL", "1172 AN",
        "1173 AB", "1173 AC", "1173 AD", "1173 AE", "1173 AG", "1173 AH", "1173 AJ", "1173 AK", "1173 AL", "1173 AN",
        "1174 AB", "1174 AC", "1174 AD", "1174 AE", "1174 AG", "1174 AH", "1174 AJ", "1174 AK", "1174 AL", "1174 AN",
        "1175 AB", "1175 AC", "1175 AD", "1175 AE", "1175 AG", "1175 AH", "1175 AJ", "1175 AK", "1175 AL", "1175 AN"
    ]
    return random.choice(real_postcodes)

def type_like_human(element, text, driver=None):
    """Type tekst met menselijke snelheid en variatie"""
    if USE_RANDOM_TYPING_SPEED:
        for char in text:
            element.send_keys(char)
            # Willekeurige delay tussen toetsaanslagen
            time.sleep(random.uniform(0.05, 0.25))
    else:
        element.send_keys(text)
    
    # Korte pauze na typen
    random_delay(0.5, 1.0)

# ==============================================================================
# TWILIO INTEGRATION
# ==============================================================================

class TwilioAPI:
    """Twilio API wrapper voor SMS verificatie"""
    
    def __init__(self, account_sid, auth_token, service_sid):
        # Valideer Twilio configuratie
        if not account_sid or not auth_token or not service_sid:
            raise ValueError("Twilio configuratie incomplete: account_sid, auth_token en service_sid zijn verplicht")
        
        # Check Account SID format (zou moeten beginnen met 'AC')
        if not account_sid.startswith('AC'):
            print(f"⚠️ Waarschuwing: Account SID begint niet met 'AC': {account_sid}")
            print("💡 Twilio Account SIDs beginnen meestal met 'AC' (niet 'US')")
        
        try:
            self.client = Client(account_sid, auth_token)
            self.service_sid = service_sid
            print(f"✅ Twilio client geïnitialiseerd met Account SID: {account_sid[:10]}...")
        except Exception as e:
            print(f"❌ Twilio client initialisatie gefaald: {e}")
            raise
    
    def get_uk_phone_number(self, target_link):
        """Haal een UK telefoonnummer op via Twilio - link-specifieke tracking met cooldown"""
        try:
            if not hasattr(self, 'client') or not self.client:
                return None
            
            phone_numbers = list(self.client.incoming_phone_numbers.list(limit=100))
            
            # Check unieke nummers eerst
            global USED_PHONE_NUMBERS, SUCCESS_PHONES, USED_PHONE_LOCK
            import time
            current_time = time.time()
            one_hour = 3600  # 1 uur in seconden
            
            with USED_PHONE_LOCK:
                for num in phone_numbers:
                    phone_num = getattr(num, 'phone_number', None) or getattr(num, 'phoneNumber', None)
                    if not phone_num:
                        continue
                    
                    # Check of het een UK nummer is
                    if phone_num.startswith('+44') or phone_num.startswith('44'):
                        clean_number = phone_num.replace('+44', '').replace('44', '')
                        clean_number = ''.join(filter(str.isdigit, clean_number))
                        if len(clean_number) >= 10:
                            # Check of dit nummer al SUCCESVOL gebruikt is voor deze link
                            if (clean_number, target_link) in SUCCESS_PHONES:
                                # Dit nummer is al met SUCCES gebruikt voor deze link - skip
                                print(f"⏭️  Nummer +44{clean_number} al succesvol gebruikt voor deze link")
                                continue
                            
                            # Check of dit nummer beschikbaar is voor deze link
                            if clean_number not in USED_PHONE_NUMBERS:
                                # Nieuw nummer - altijd bruikbaar
                                USED_PHONE_NUMBERS[clean_number] = {target_link: current_time}
                                print(f"📱 Nieuw telefoonnummer: +44{clean_number}")
                                return clean_number
                            elif target_link not in USED_PHONE_NUMBERS[clean_number]:
                                # Bestaand nummer, maar niet gebruikt voor deze link
                                USED_PHONE_NUMBERS[clean_number][target_link] = current_time
                                print(f"📱 Telefoonnummer +44{clean_number} voor nieuwe link")
                                return clean_number
                            else:
                                # Dit nummer is al gebruikt voor deze link - check 1 uur cooldown
                                last_used = USED_PHONE_NUMBERS[clean_number][target_link]
                                elapsed = current_time - last_used
                                if elapsed < one_hour:
                                    wait_time = one_hour - elapsed
                                    print(f"⏸️  Nummer +44{clean_number} moet nog {int(wait_time/60)} minuten wachten voor deze link")
                                    continue
                                else:
                                    # 1 uur verstreken - mag weer gebruikt worden
                                    USED_PHONE_NUMBERS[clean_number][target_link] = current_time
                                    print(f"📱 Telefoonnummer +44{clean_number} weer beschikbaar na 1 uur")
                                    return clean_number
                
                # Alle nummers al gebruikt voor deze link en in cooldown
                print(f"⚠️  Alle Twilio nummers in cooldown voor deze link")
                return None
            
            return None
            
        except Exception as e:
            print(f"❌ Twilio error: {e}")
            return None
    
    def send_verification_code(self, phone_number):
        """Verstuur verificatiecode via Twilio Verify API"""
        try:
            verification = self.client.verify.v2.services(self.service_sid) \
                .verifications \
                .create(to=f'+44{phone_number}', channel='sms')
            
            print(f"✅ Verificatiecode verstuurd naar +44{phone_number}")
            return verification.sid
        except Exception as e:
            print(f"❌ Fout bij versturen verificatiecode: {e}")
            return None
    
    def check_verification_code(self, phone_number, code):
        """Controleer verificatiecode"""
        try:
            verification_check = self.client.verify.v2.services(self.service_sid) \
                .verification_checks \
                .create(to=f'+44{phone_number}', code=code)
            
            return verification_check.status == 'approved'
        except Exception as e:
            print(f"❌ Fout bij controleren code: {e}")
            return False
    
    def get_verification_code(self, phone_number, timeout=60):
        """Wacht op verificatiecode via SMS met echte Twilio Messages API - CRASH-PROOF VERSIE"""
        try:
            if not phone_number:
                print("❌ Geen telefoonnummer opgegeven voor SMS verificatie")
                return None
                
            print(f"📱 Wachten op SMS code voor nummer: +44{phone_number}")
            
            # Validate Twilio client
            if not hasattr(self, 'client') or not self.client:
                print("❌ Twilio client niet beschikbaar voor SMS")
                return None
            
            # Verstuur verificatiecode eerst
            verification_sid = None
            try:
                verification_sid = self.send_verification_code(phone_number)
            except Exception as e:
                print(f"⚠️ Fout bij versturen verificatiecode: {e}")
            
            if not verification_sid:
                print("⚠️ Geen verification_sid ontvangen")
                return None
            
            # Nu wachten op SMS code via Messages API
            print(f"⏳ Wachten op SMS code via Twilio Messages API... (timeout: {timeout}s)")
            
            import time
            from datetime import datetime
            start_time = time.time()
            
            # Telkens opnieuw zoeken naar nieuwe berichten naar dit nummer
            target_phone = f"+44{phone_number}"
            last_checked_time = datetime.now()
            
            while time.time() - start_time < timeout:
                try:
                    # Zoek alle recente berichten - Seated stuurt naar het UK nummer
                    # We moeten zoeken in ALLE recente berichten, niet specifiek to/from
                    messages = self.client.messages.list(limit=20)
                    
                    all_messages = list(messages)
                    
                    for message in all_messages:
                        try:
                            # Check of bericht naar het correcte nummer gaat
                            message_to = message.to or ""
                            if not message_to.endswith(target_phone):
                                continue  # Skip berichten naar andere nummers
                            
                            # Check of bericht van Seated komt en recent is
                            body = message.body or ""
                            
                            # Check of Seated in de body staat
                            if "seated" in body.lower() and "verification code" in body.lower():
                                print(f"🔍 Seated bericht gevonden voor +44{phone_number}: {body[:80]}...")
                                
                                # Extract code - Seated format: "9009 is your verification code for Seated."
                                import re
                                # Zoek naar 4 cijfers
                                matches = re.findall(r'\b(\d{4})\b', body)
                                if matches:
                                    code = matches[0]
                                    print(f"✅ Seated verificatiecode gevonden voor +44{phone_number}: {code}")
                                    return code
                                        
                        except Exception as e:
                            print(f"⚠️ Error processing message: {e}")
                            continue
                    
                    # Wacht 5 seconden voor volgende check
                    time.sleep(5)
                    remaining = timeout - (time.time() - start_time)
                    if remaining > 0:
                        print(f"⏳ Nog {remaining:.0f} seconden wachten...")
                    
                except KeyboardInterrupt:
                    print("\n🛑 SMS wachttijd geannuleerd door gebruiker")
                    return None
                except Exception as e:
                    print(f"⚠️ Error in SMS polling: {e}")
                    time.sleep(5)
                    continue
            
            print(f"⏰ Timeout bereikt voor SMS code")
            return None
            
        except Exception as e:
            print(f"❌ SMS verificatie error: {e}")
            return None


# ==============================================================================
# DOLPHIN ANTY API CLASS
# ==============================================================================

class DolphinAPI:
    """Dolphin Anty API Wrapper"""
    
    def __init__(self, token):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def log(self, message):
        """Log bericht met timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        
        # Write to log file
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"⚠️  Log write error: {e}")
    
    def get_fingerprint(self, platform="windows", browser_version=140):
        """Haal nieuwe fingerprint op"""
        try:
            url = f"{REMOTE_API}/fingerprints/fingerprint"
            params = {
                "platform": platform,
                "browser_type": "anty",
                "browser_version": browser_version,
                "type": "fingerprint"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and 'userAgent' in data:
                    self.log(f"✅ Fingerprint API succesvol! Platform: {platform}")
                    return data
                else:
                    self.log(f"❌ Fingerprint API error: Geen geldige data ontvangen")
                    return None
            else:
                self.log(f"❌ Fingerprint API HTTP error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            self.log(f"❌ Fout bij fingerprint: {e}")
            return None
    
    def get_profiles(self):
        """Haal alle bestaande browser profielen op uit Dolphin Anty"""
        try:
            url = f"{REMOTE_API}/browser_profiles"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                profiles = data.get('data', [])
                self.log(f"👤 {len(profiles)} profielen gevonden in Dolphin Anty")
                return profiles
            else:
                self.log(f"❌ Profielen ophalen mislukt: {response.status_code}")
                return []
        except Exception as e:
            self.log(f"❌ Fout bij profielen ophalen: {e}")
            return []
    
    def get_proxies(self):
        """Haal alle bestaande proxies op uit Dolphin Anty"""
        try:
            url = f"{REMOTE_API}/proxy"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                proxies = data.get('data', [])
                self.log(f"📡 {len(proxies)} proxies gevonden in Dolphin Anty")
                return proxies
            else:
                self.log(f"❌ Proxies ophalen mislukt: {response.status_code}")
                return []
        except Exception as e:
            self.log(f"❌ Fout bij proxies ophalen: {e}")
            return []

    def create_profile(self, name, fingerprint=None, proxy_id=None):
        """Maak een nieuw browser profiel - SNELLE QUICK PROFILE MODE"""
        try:
            url = f"{REMOTE_API}/browser_profiles"
            
            # Als geen fingerprint gegeven, gebruik QUICK PROFILE (simpele config)
            if not fingerprint:
                fingerprint = {}
                payload = {
                    "name": name,
                    "platform": "windows",
                    "browserType": "anty",
                    "platformVersion": "10",
                    "architecture": "x64",
                    "mainWebsite": "seated",
                    "useragent": {"mode": "manual", "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                    "webrtc": {"mode": "real", "ipAddress": None},
                    "canvas": {"mode": "real"},
                    "webgl": {"mode": "real"},
                    "webglInfo": {"mode": "auto"},
                    "timezone": {"mode": "auto", "value": None},
                    "locale": {"mode": "auto", "value": None},
                    "cpu": {"mode": "auto", "value": 0},
                    "memory": {"mode": "auto", "value": 0},
                    "screen": {"mode": "auto", "resolution": ""},
                    "geolocation": {"mode": "auto", "latitude": None, "longitude": None},
                    "doNotTrack": False,
                    "mediaDevices": {"mode": "auto", "audioInputs": 0, "audioOutputs": 0, "videoInputs": 0},
                    "fonts": [],
                    "notes": []
                }
            
            # Voeg proxy toe als beschikbaar (voor zowel Quick Profile als normale profiles)
            if proxy_id:
                try:
                    # Haal volledige proxy data op
                    proxies = self.get_proxies()
                    proxy_data = next((p for p in proxies if p.get('id') == proxy_id), None)
                    
                    if proxy_data:
                        payload["proxy"] = {
                            "id": proxy_data.get('id'),
                            "teamId": proxy_data.get('teamId'),
                            "userId": proxy_data.get('userId'),
                            "name": proxy_data.get('name'),
                            "type": proxy_data.get('type'),
                            "host": proxy_data.get('host'),
                            "port": proxy_data.get('port'),
                            "login": proxy_data.get('login'),
                            "password": proxy_data.get('password'),
                            "changeIpUrl": proxy_data.get('changeIpUrl'),
                            "provider": proxy_data.get('provider'),
                            "ip": proxy_data.get('ip'),
                            "savedByUser": proxy_data.get('savedByUser', True),
                            "browser_profiles_count": proxy_data.get('browser_profiles_count', 0),
                            "lastCheck": proxy_data.get('lastCheck', {}),
                            "createdAt": proxy_data.get('createdAt', ''),
                            "updatedAt": proxy_data.get('updatedAt', '')
                        }
                        self.log(f"✅ Proxy {proxy_id} toegevoegd aan profiel")
                    else:
                        self.log(f"⚠️ Proxy {proxy_id} niet gevonden - maak profiel zonder proxy")
                except Exception as e:
                    self.log(f"⚠️ Fout bij proxy ophalen: {e} - maak profiel zonder proxy")
            
            if fingerprint and len(fingerprint) > 0:
                # ECHTE FINGERPRINT DATA VAN API - overschrijf payload met echte fingerprint data
                webgl2_maximum = {}
                if 'webgl2Maximum' in fingerprint:
                    try:
                        webgl2_maximum = json.loads(fingerprint['webgl2Maximum'])
                    except:
                        webgl2_maximum = {}
                
                fonts = []
                if 'fonts' in fingerprint:
                    try:
                        fonts = json.loads(fingerprint['fonts'])
                    except:
                        fonts = []
                
                payload = {
                    "name": name,
                    "platform": fingerprint.get('os', {}).get('name', 'windows').lower(),
                    "browserType": "anty",
                    "platformVersion": fingerprint.get('os', {}).get('version', '10'),
                    "architecture": fingerprint.get('cpu', {}).get('architecture', 'x64'),
                    "mainWebsite": "seated",
                    "useragent": {
                        "mode": "manual",
                        "value": fingerprint.get('userAgent', '')
                    },
                    "webrtc": {"mode": "altered", "ipAddress": None},
                    "canvas": {"mode": "noise"},
                    "webgl": {"mode": "noise"},
                    "webglInfo": {
                        "mode": "manual",
                        "vendor": fingerprint.get('webgl', {}).get('unmaskedVendor', ''),
                        "renderer": fingerprint.get('webgl', {}).get('unmaskedRenderer', ''),
                        "webgl2Maximum": webgl2_maximum
                    },
                    "timezone": {"mode": "auto", "value": None},
                    "locale": {"mode": "auto", "value": None},
                    "cpu": {
                        "mode": "manual",
                        "value": fingerprint.get('hardwareConcurrency', 4)
                    },
                    "memory": {
                        "mode": "manual", 
                        "value": fingerprint.get('deviceMemory', 8)
                    },
                    "screen": {
                        "mode": "manual",
                        "resolution": f"{fingerprint.get('screen', {}).get('width', 1920)}x{fingerprint.get('screen', {}).get('height', 1080)}"
                    },
                    "geolocation": {"mode": "auto", "latitude": None, "longitude": None},
                    "doNotTrack": bool(fingerprint.get('donottrack', 0)),
                    "mediaDevices": {"mode": "manual", "audioInputs": 1, "audioOutputs": 1, "videoInputs": 1},
                    "fonts": fonts,
                    "notes": []
                }
            # Voeg proxy toe als beschikbaar (volledige proxy data zoals Node.js script)
            if proxy_id:
                try:
                    # Haal volledige proxy data op
                    proxies = self.get_proxies()
                    proxy_data = next((p for p in proxies if p.get('id') == proxy_id), None)
                    
                    if proxy_data:
                        payload["proxy"] = {
                            "id": proxy_data.get('id'),
                            "teamId": proxy_data.get('teamId'),
                            "userId": proxy_data.get('userId'),
                            "name": proxy_data.get('name'),
                            "type": proxy_data.get('type'),
                            "host": proxy_data.get('host'),
                            "port": proxy_data.get('port'),
                            "login": proxy_data.get('login'),
                            "password": proxy_data.get('password'),
                            "changeIpUrl": proxy_data.get('changeIpUrl'),
                            "provider": proxy_data.get('provider'),
                            "ip": proxy_data.get('ip'),
                            "savedByUser": proxy_data.get('savedByUser', True),
                            "browser_profiles_count": proxy_data.get('browser_profiles_count', 0),
                            "lastCheck": proxy_data.get('lastCheck', {}),
                            "createdAt": proxy_data.get('createdAt', ''),
                            "updatedAt": proxy_data.get('updatedAt', '')
                        }
                    else:
                        # Proxy niet gevonden - maak profiel zonder proxy
                        self.log(f"⚠️ Proxy {proxy_id} niet gevonden - maak profiel zonder proxy")
                        # payload["proxy"] NIET toevoegen
                except Exception as e:
                    self.log(f"⚠️ Fout bij proxy ophalen: {e} - maak profiel zonder proxy")
                    # payload["proxy"] NIET toevoegen
            
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                profile_id = data.get('browserProfileId')
                self.log(f"✅ Profiel aangemaakt: {name} (ID: {profile_id})")
                return profile_id
            else:
                self.log(f"❌ Profiel aanmaken mislukt: {response.status_code}")
                self.log(f"   Response: {response.text[:200]}")
                return None
        except Exception as e:
            self.log(f"❌ Fout bij profiel aanmaken: {e}")
            return None
    
    def start_profile(self, profile_id):
        """Start een browser profiel met automation"""
        global HEADLESS_MODE
        try:
            url = f"{LOCAL_API}/browser_profiles/{profile_id}/start"
            payload = {
                "automation": True,
                "headless": HEADLESS_MODE
            }
            
            self.log(f"🚀 Browser starten met headless={HEADLESS_MODE}")
            response = requests.post(url, json=payload, timeout=60)
            
            # Debug: Log full response for 500 errors
            if response.status_code != 200:
                self.log(f"🔍 Debug - Full URL: {url}")
                self.log(f"🔍 Debug - Payload: {payload}")
                self.log(f"🔍 Debug - Headers: {response.headers}")
                try:
                    error_detail = response.text[:500]
                    self.log(f"🔍 Debug - Error detail: {error_detail}")
                except:
                    pass
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    automation = data.get('automation', {})
                    port = automation.get('port')
                    self.log(f"✅ Browser gestart op poort: {port}")
                    global ACTIVE_PROFILES
                    ACTIVE_PROFILES.append(profile_id)
                    return port
                else:
                    self.log(f"❌ Browser start mislukt")
                    return None
            else:
                self.log(f"❌ Start request mislukt: {response.status_code}")
                try:
                    self.log(f"   Error response: {response.text[:200]}")
                except:
                    pass
                return None
        except Exception as e:
            self.log(f"❌ Fout bij browser starten: {e}")
            return None
    
    def stop_profile(self, profile_id):
        """Stop een browser profiel"""
        try:
            url = f"{LOCAL_API}/browser_profiles/{profile_id}/stop"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                self.log(f"✅ Browser gestopt: {profile_id}")
                return True
            else:
                self.log(f"❌ Browser stoppen mislukt: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Fout bij browser stoppen: {e}")
            return False
    
    def delete_profile(self, profile_id):
        """Verwijder een browser profiel"""
        try:
            url = f"{REMOTE_API}/browser_profiles/{profile_id}"
            response = requests.delete(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                self.log(f"✅ Profiel {profile_id} verwijderd")
                if profile_id in ACTIVE_PROFILES:
                    ACTIVE_PROFILES.remove(profile_id)
                return True
            else:
                self.log(f"❌ Profiel verwijderen mislukt: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Fout bij profiel verwijderen: {e}")
            return False
    
    def delete_proxy(self, proxy_id):
        """Verwijder een proxy"""
        try:
            url = f"{REMOTE_API}/proxy/{proxy_id}"
            response = requests.delete(url, headers=self.headers, timeout=30)
            
            if response.status_code in [200, 404]:  # 404 is ok - proxy was al verwijderd
                self.log(f"✅ Proxy verwijderd: {proxy_id}")
                return True
            else:
                self.log(f"⚠️  Proxy verwijderen mislukt: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Fout bij proxy verwijderen: {e}")
            return False

# ==============================================================================
# FILE OPERATIONS
# ==============================================================================

def load_emails():
    """Laad emails uit emails.txt en filter al succesvolle emails"""
    try:
        with open(EMAILS_FILE, 'r', encoding='utf-8') as f:
            emails = []
            seen_emails = set()  # Track unieke emails
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Check if line looks like an email
                    if '@' in line and '.' in line:
                        # Check for duplicates
                        if line not in seen_emails:
                            emails.append(line)
                            seen_emails.add(line)
                        else:
                            print(f"⚠️ Duplicate email detected and skipped: {line}")
        
        # Filter emails die al succesvol zijn uit history
        successful_emails = set()
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            parts = line.strip().split('|')
                            if len(parts) >= 3 and parts[2].lower() == 'true':
                                successful_emails.add(parts[0])
            except Exception as e:
                print(f"⚠️  History file read error: {e}")
        
        # Filter out successful emails
        filtered_emails = [email for email in emails if email not in successful_emails]
        skipped_count = len(emails) - len(filtered_emails)
        
        if skipped_count > 0:
            print(f"⏭️  {skipped_count} email(s) geskipt (al succesvol)")
        
        # Track welke emails zijn gebruikt in deze sessie om dubbelgebruik te voorkomen
        global USED_EMAILS
        try:
            USED_EMAILS
        except NameError:
            USED_EMAILS = set()
        
        print(f"📧 {len(filtered_emails)} unieke emails te verwerken")
        
        return filtered_emails
    except FileNotFoundError:
        print(f"❌ {EMAILS_FILE} niet gevonden!")
        return []
    except Exception as e:
        print(f"❌ Error loading emails: {e}")
        return []

def log_to_history(email, success, reason=""):
    """Log email result naar history file"""
    try:
        with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{email}|{timestamp}|{str(success).lower()}|{reason}\n")
    except Exception as e:
        print(f"⚠️  History log error: {e}")

def log_success(email):
    """Log succesvol email naar success file"""
    try:
        with open(SUCCESS_FILE, 'a', encoding='utf-8') as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{email}|{timestamp}\n")
    except Exception as e:
        print(f"⚠️  Success log error: {e}")

def remove_email_immediately(email):
    """Verwijder email direct uit emails.txt na succes"""
    try:
        with EMAIL_FILE_LOCK:
            if os.path.exists(EMAILS_FILE):
                with open(EMAILS_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Filter email eruit
                filtered_lines = [line for line in lines if line.strip() != email]
                
                with open(EMAILS_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(filtered_lines)
    except Exception as e:
        print(f"⚠️  Email removal error: {e}")

# ==============================================================================
# SEATED AUTOMATION
# ==============================================================================

def signup_seated_with_retry(email, thread_id, available_proxies, available_profiles, max_retries=3):
    """Probeer signup met verschillende proxies als één niet werkt"""
    api = DolphinAPI(DOLPHIN_TOKEN)
    
    global ACTIVE_PROFILE_IDS, PROFILE_TRACKING_LOCK, AVAILABLE_PROFILE_POOL, AVAILABLE_PROFILE_POOL_LOCK
    
    for attempt in range(max_retries):
        if not available_proxies:
            api.log(f"❌ [Thread {thread_id}] Geen proxies meer beschikbaar voor {email}")
            reason = "No proxies available"
            log_to_history(email, False, reason)
            return {
                "email": email,
                "success": False,
                "reason": reason
            }
        
        # Thread-safe profiel en proxy selectie
        proxy_id = None
        profile_id = None
        
        with PROFILE_TRACKING_LOCK, AVAILABLE_PROFILE_POOL_LOCK:
            # Als pool leeg is, maak nieuwe profiel aan
            if not AVAILABLE_PROFILE_POOL and available_proxies:
                api.log(f"🆕 [Thread {thread_id}] Pool leeg - maak nieuw profiel aan...")
                proxy_id_for_new_profile = available_proxies.pop(0) if available_proxies else None
                
                if proxy_id_for_new_profile:
                    # Maak nieuw Quick Profile aan
                    profile_name = f"Quick_Profile_{int(time.time())}"
                    new_profile_id = api.create_profile(profile_name, fingerprint=None, proxy_id=proxy_id_for_new_profile)
                    if new_profile_id:
                        AVAILABLE_PROFILE_POOL.append(new_profile_id)
                        api.log(f"✅ [Thread {thread_id}] Nieuw profiel aangemaakt: {new_profile_id}")
                    else:
                        proxy_id = proxy_id_for_new_profile  # Fallback - probeer met proxy_id
            
            # Pak eerste beschikbare profiel uit globale pool EN proxy
            if AVAILABLE_PROFILE_POOL and available_proxies:
                profile_id = AVAILABLE_PROFILE_POOL.pop(0)
                if not proxy_id:
                    proxy_id = available_proxies.pop(0)
                ACTIVE_PROFILE_IDS.add(profile_id)
        
        if not proxy_id or not profile_id:
            api.log(f"❌ [Thread {thread_id}] Geen beschikbaar profiel of proxy voor {email}")
            reason = "No available profile or proxy"
            log_to_history(email, False, reason)
            if profile_id:
                with PROFILE_TRACKING_LOCK:
                    ACTIVE_PROFILE_IDS.discard(profile_id)
            return {
                "email": email,
                "success": False,
                "reason": reason
            }
        
        api.log(f"🔄 [Thread {thread_id}] Poging {attempt + 1}/{max_retries} met proxy {proxy_id} en profiel {profile_id}")
        
        # Probeer signup
        result = signup_seated(email, thread_id, proxy_id, profile_id)
        
        # Release profiel from active tracking EN terug naar pool
        with PROFILE_TRACKING_LOCK, AVAILABLE_PROFILE_POOL_LOCK:
            ACTIVE_PROFILE_IDS.discard(profile_id)
            # Voeg profiel terug toe aan globale pool voor hergebruik
            AVAILABLE_PROFILE_POOL.append(profile_id)
        
        # Check of het succesvol was
        if result['success']:
            return result
        
        # Als proxy/browser start mislukt, probeer volgende proxy/profiel
        if "Browser start failed" in result.get('reason', '') or "timeout" in result.get('reason', '').lower():
            api.log(f"⚠️  [Thread {thread_id}] Proxy {proxy_id} of profiel {profile_id} werkt niet, probeer volgende...")
            continue
        elif "No verification code received" in result.get('reason', ''):
            # Geen OTP ontvangen - probeer NIET opnieuw met dit nummer
            api.log(f"❌ [Thread {thread_id}] Geen OTP ontvangen - stop met retries")
            return result
        else:
            # Andere fout, stop met retries
            return result
    
    # Alle retries gefaald
    reason = f"Failed after {max_retries} retries with different proxies"
    log_to_history(email, False, reason)
    return {
        "email": email,
        "success": False,
        "reason": reason
    }

def signup_seated(email, thread_id, proxy_id, profile_id=None):
    """Volledige signup flow voor Seated event reminder"""
    
    api = DolphinAPI(DOLPHIN_TOKEN)
    driver = None
    phone_number = None
    result_success = False  # Track of signup succesvol was
    
    try:
        api.log(f"\n{'='*60}")
        api.log(f"🎫 [Thread {thread_id}] Start Seated signup voor: {email}")
        api.log(f"   Proxy ID: {proxy_id}")
        api.log(f"   Profile ID: {profile_id}")
        api.log(f"{'='*60}")
        
        # 1. Start browser met profiel
        api.log(f"🚀 [Thread {thread_id}] Browser starten...")
        port = api.start_profile(profile_id)
        
        if not port:
            api.log(f"❌ [Thread {thread_id}] Browser start mislukt")
            return {"email": email, "success": False, "reason": "Browser start failed"}
        
        time.sleep(5)
        
        # 4. Connect Selenium - MINIMAAL OPTIES voor Dolphin Anty compatibiliteit
        api.log(f"🔗 [Thread {thread_id}] Selenium verbinden...")
        try:
            options = webdriver.ChromeOptions()
            options.debugger_address = f"127.0.0.1:{port}"
            
            # Minimale configuratie - Dolphin Anty's browser heeft al alle stealth features ingebouwd
            # Locatie automatisch toestaan
            prefs = {
                "profile.default_content_setting_values.geolocation": 1,
            }
            options.add_experimental_option("prefs", prefs)
            
            # Probeer ChromeDriver uit Homebrew te gebruiken
            try:
                from selenium.webdriver.chrome.service import Service
                driver = webdriver.Chrome(options=options)
            except:
                # Fallback zonder Service
                driver = webdriver.Chrome(options=options)
                
            driver.set_page_load_timeout(30)
            api.log(f"✅ [Thread {thread_id}] Selenium verbonden (Dolphin Anty fingerprinting actief)")
            
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Selenium connectie mislukt: {e}")
            api.stop_profile(profile_id)
            api.delete_profile(profile_id)
            if profile_id in ACTIVE_PROFILES:
                ACTIVE_PROFILES.remove(profile_id)
            api.delete_proxy(proxy_id)
            return {"email": email, "success": False, "reason": "Selenium failed"}

        # 5. Navigeer naar Seated website
        api.log(f"🌐 [Thread {thread_id}] Navigeren naar Seated website...")
        driver.get(TARGET_URL)
        random_delay(3, 5)
        
        # HUMAN-LIKE BEHAVIOR tegen Cloudflare detectie
        try:
            # Random scroll om het menselijk te maken
            scroll_times = random.randint(1, 3)
            for i in range(scroll_times):
                scroll_amount = random.randint(100, 500)
                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                random_delay(0.5, 1.5)
            # Scroll terug naar boven
            driver.execute_script("window.scrollTo(0, 0);")
            random_delay(1, 2)
        except Exception as e:
            api.log(f"⚠️ [Thread {thread_id}] Scroll behavior fout: {e}")
        
        # 6. Zoek en klik op Sign Up button - XPath ONLY
        api.log(f"📋 [Thread {thread_id}] Zoeken naar Sign Up button...")
        try:
            # Eerst proberen met specifieke Ember ID (als die bestaat)
            signup_button = None
            
            # Zoek ALLE klikbare elementen met Ember ID
            try:
                all_links = driver.find_elements(By.XPATH, "//a[@id and starts-with(@id, 'ember') and contains(@class, 'inline-block')]")
                api.log(f"🔍 [Thread {thread_id}] Gevonden {len(all_links)} links met Ember ID")
                
                for link in all_links:
                    try:
                        link_text = link.text.strip().lower()
                        link_id = link.get_attribute("id")
                        api.log(f"🔍 [Thread {thread_id}] Link ID: {link_id}, Text: '{link_text}'")
                        
                        # Zoek "Get Password" button
                        if link_text and "password" in link_text:
                            signup_button = link
                            api.log(f"✅ [Thread {thread_id}] Sign Up button gevonden via tekst: '{link_text}' (ID: {link_id})")
                            break
                    except:
                        continue
            except Exception as e:
                api.log(f"⚠️ [Thread {thread_id}] Ember ID zoeken fout: {e}")
            
            # Als Ember ID niet werkt, probeer text-based XPath
            if not signup_button:
                text_xpath_selectors = [
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get password')]",
                    "//a[contains(text(), 'Get Password')]",
                    "//a[@data-test-get-password-link]"
                ]
                
                for xpath in text_xpath_selectors:
                    try:
                        signup_button = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        
                        if signup_button and signup_button.is_displayed():
                            api.log(f"✅ [Thread {thread_id}] Sign Up button gevonden via text: {xpath}")
                            break
                    except:
                        continue
            
            if not signup_button:
                raise Exception("Sign Up button niet gevonden")
            
            # Scroll naar button en klik
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", signup_button)
            random_delay(1, 2)
            signup_button.click()
            api.log(f"✅ [Thread {thread_id}] Sign Up button geklikt")
            
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Sign Up button niet gevonden: {e}")
            return {"email": email, "success": False, "reason": "Sign Up button not found"}

        random_delay(2, 4)

        # 7. Vul formulier in
        api.log(f"📝 [Thread {thread_id}] Formulier invullen...")
        
        # Genereer willekeurige naam
        name_data = generate_random_name()
        first_name = name_data["first"]
        last_name = name_data["last"]
        
        # Vul voornaam in
        try:
            first_name_selectors = [
                "input[data-test-first-name]",
                "input[data-first-name]",
                "input[data-test-first-name='']"
            ]
            
            first_name_field = None
            for selector in first_name_selectors:
                try:
                    first_name_field = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if first_name_field:
                api.log(f"✅ [Thread {thread_id}] First name veld gevonden")
                first_name_field.click()
                random_delay(0.5, 1.0)
                type_like_human(first_name_field, first_name, driver)
                api.log(f"✅ [Thread {thread_id}] First name ingevuld: {first_name}")
            else:
                raise Exception("First name field niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] First name invullen mislukt: {e}")
            return {"email": email, "success": False, "reason": "First name field failed"}

        random_delay(1, 2)

        # Vul achternaam in
        try:
            last_name_selectors = [
                "input[data-test-last-name]",
                "input[data-last-name]"
            ]
            
            last_name_field = None
            for selector in last_name_selectors:
                try:
                    last_name_field = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if last_name_field:
                api.log(f"✅ [Thread {thread_id}] Last name veld gevonden")
                last_name_field.click()
                random_delay(0.5, 1.0)
                type_like_human(last_name_field, last_name, driver)
                api.log(f"✅ [Thread {thread_id}] Last name ingevuld: {last_name}")
            else:
                raise Exception("Last name field niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Last name invullen mislukt: {e}")
            return {"email": email, "success": False, "reason": "Last name field failed"}

        random_delay(1, 2)

        # Vul email in
        try:
            email_selectors = [
                "input[data-test-email]",
                "input[type='email']"
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if email_field:
                api.log(f"✅ [Thread {thread_id}] Email veld gevonden")
                email_field.click()
                random_delay(0.5, 1.0)
                type_like_human(email_field, email, driver)
                api.log(f"✅ [Thread {thread_id}] Email ingevuld: {email}")
            else:
                raise Exception("Email field niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Email invullen mislukt: {e}")
            return {"email": email, "success": False, "reason": "Email field failed"}

        random_delay(1, 2)

        # Klik op SVG dropdown na email invullen
        try:
            svg_selector = "svg[viewBox='0 0 11 8']"
            svg_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, svg_selector))
            )
            svg_dropdown.click()
            api.log(f"✅ [Thread {thread_id}] SVG dropdown geklikt")
            random_delay(1, 2)
        except Exception as e:
            api.log(f"⚠️  [Thread {thread_id}] SVG dropdown klik mislukt: {e}")

        # Selecteer Nederlandse land/telefooncode
        try:
            country_selector = "div[data-test-calling-code='NL']"
            country_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, country_selector))
            )
            country_element.click()
            api.log(f"✅ [Thread {thread_id}] Nederland land/telefooncode geselecteerd")
            random_delay(1, 2)
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Nederland selecteren mislukt: {e}")
            return {"email": email, "success": False, "reason": "Country selection failed"}

        random_delay(1, 2)

        # Vul Nederlandse postcode in
        try:
            postcode = generate_dutch_postcode()
            postcode_selectors = [
                "input[data-test-postal-code]",
                "input[data-postal-code]"
            ]
            
            postcode_field = None
            for selector in postcode_selectors:
                try:
                    postcode_field = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if postcode_field:
                api.log(f"✅ [Thread {thread_id}] Postcode veld gevonden")
                postcode_field.click()
                random_delay(0.5, 1.0)
                type_like_human(postcode_field, postcode, driver)
                api.log(f"✅ [Thread {thread_id}] Postcode ingevuld: {postcode}")
            else:
                raise Exception("Postcode field niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Postcode invullen mislukt: {e}")
            return {"email": email, "success": False, "reason": "Postcode field failed"}

        random_delay(1, 2)

        # Klik op leeftijd checkbox (13 jaar of ouder)
        try:
            # Zoek naar het element met de tekst "I confirm that I am 13 years of age or older"
            age_checkbox_selectors = [
                "//div[contains(text(), 'I confirm that I am 13 years of age or older')]",
                "//div[contains(text(), '13 years')]",
                "//div[contains(text(), 'age or older')]",
                ".rounded-full.bg-background",  # CSS selector voor de checkbox div
                "div.w-5.h-5.rounded-full"  # Specifieke class selector
            ]
            
            age_checkbox = None
            for selector in age_checkbox_selectors:
                try:
                    if selector.startswith("//"):
                        # XPath selector
                        elements = driver.find_elements(By.XPATH, selector)
                        # Zoek naar klikbaar element (meestal de div zelf of een parent)
                        for element in elements:
                            try:
                                # Probeer het element zelf te klikken, of zoek naar een klikbare parent
                                clickable_element = element
                                # Als het div is, probeer direct te klikken
                                if element.get_attribute("class") and "rounded-full" in element.get_attribute("class"):
                                    clickable_element = element
                                elif element.find_elements(By.XPATH, "./.."):
                                    # Probeer parent element
                                    clickable_element = element.find_element(By.XPATH, "./..")
                                
                                if clickable_element.is_displayed() and clickable_element.is_enabled():
                                    age_checkbox = clickable_element
                                    break
                            except:
                                continue
                        if age_checkbox:
                            break
                    else:
                        # CSS selector
                        age_checkbox = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        if age_checkbox.is_displayed():
                            break
                except:
                    continue
            
            if age_checkbox and age_checkbox.is_displayed():
                age_checkbox.click()
                api.log(f"✅ [Thread {thread_id}] Leeftijd checkbox (13 jaar) aangeklikt")
                random_delay(1, 2)
            else:
                api.log(f"⚠️  [Thread {thread_id}] Leeftijd checkbox niet gevonden of niet zichtbaar")
        except Exception as e:
            api.log(f"⚠️  [Thread {thread_id}] Leeftijd checkbox klik mislukt: {e}")

        random_delay(1, 2)

        # Klik op Next button
        try:
            next_selectors = [
                "button[data-test-next]",
                "button[type='submit']",
                "button:contains('Next')"
            ]
            
            next_button = None
            for selector in next_selectors:
                try:
                    if ":contains" in selector:
                        next_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
                        )
                    else:
                        next_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    if next_button:
                        break
                except:
                    continue
            
            if next_button:
                api.log(f"✅ [Thread {thread_id}] Next button gevonden")
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                random_delay(1, 2)
                next_button.click()
                api.log(f"✅ [Thread {thread_id}] Next button geklikt")
            else:
                raise Exception("Next button niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Next button mislukt: {e}")
            return {"email": email, "success": False, "reason": "Next button failed"}

        # 8. Wacht op vervolgpagina
        api.log(f"⏳ [Thread {thread_id}] Wachten op vervolgpagina...")
        time.sleep(5)

        # 9. Klik op dropdown voor UK
        try:
            # Eerst klik op dropdown arrow
            dropdown_selectors = [
                "svg[viewBox='0 0 11 8']",
                ".fill-current.w-3.h-3.pt-1"
            ]
            
            dropdown_arrow = None
            for selector in dropdown_selectors:
                try:
                    dropdown_arrow = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if dropdown_arrow:
                        break
                except:
                    continue
            
            if dropdown_arrow:
                api.log(f"✅ [Thread {thread_id}] Dropdown arrow gevonden")
                dropdown_arrow.click()
                random_delay(1, 2)
            else:
                api.log(f"⚠️  [Thread {thread_id}] Dropdown arrow niet gevonden, probeer direct UK optie")

            # Klik op UK optie
            uk_selectors = [
                "div[data-test-calling-code='GB']",
                "div:contains('United Kingdom')"
            ]
            
            uk_option = None
            for selector in uk_selectors:
                try:
                    if ":contains" in selector:
                        uk_option = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'United Kingdom')]"))
                        )
                    else:
                        uk_option = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    if uk_option:
                        break
                except:
                    continue
            
            if uk_option:
                api.log(f"✅ [Thread {thread_id}] UK optie gevonden")
                uk_option.click()
                api.log(f"✅ [Thread {thread_id}] UK optie geselecteerd")
            else:
                raise Exception("UK optie niet gevonden")
                
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] UK selectie mislukt: {e}")
            return {"email": email, "success": False, "reason": "UK selection failed"}

        random_delay(1, 2)

        # 10. Haal UK telefoonnummer op via Twilio - VERBETERDE VERSIE
        api.log(f"📱 [Thread {thread_id}] UK telefoonnummer ophalen via Twilio...")
        
        # Check Twilio configuratie eerst
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SERVICE_SID]):
            api.log(f"❌ [Thread {thread_id}] Twilio configuratie incomplete!")
            return {"email": email, "success": False, "reason": "Twilio configuration incomplete"}
        
        phone_number = None
        
        try:
            twilio = TwilioAPI(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SERVICE_SID)
            api.log(f"✅ [Thread {thread_id}] Twilio client geïnitialiseerd")
            
            # Geef target link door voor cooldown tracking
            phone_number = twilio.get_uk_phone_number(TARGET_URL)
            
            if not phone_number:
                api.log(f"⚠️ [Thread {thread_id}] Geen UK telefoonnummer gevonden via Twilio API")
                api.log(f"💡 [Thread {thread_id}] Controleer je Twilio account voor UK nummers")
                
                # FALLBACK: Probeer een dummy/test nummer te gebruiken
                api.log(f"🔄 [Thread {thread_id}] Probeer fallback telefoonnummer...")
                phone_number = "7123456789"  # Dummy UK nummer voor testing
                api.log(f"⚠️ [Thread {thread_id}] Gebruik dummy nummer: {phone_number}")
            else:
                api.log(f"✅ [Thread {thread_id}] UK telefoonnummer opgehaald: {phone_number}")
            
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Twilio fout bij ophalen telefoonnummer: {e}")
            api.log(f"🔄 [Thread {thread_id}] Probeer fallback na Twilio error...")
            phone_number = "7123456789"  # Fallback nummer
            api.log(f"⚠️ [Thread {thread_id}] Gebruik fallback nummer: {phone_number}")
        
        # Final check - als nog steeds geen nummer, stop dan
        if not phone_number:
            api.log(f"❌ [Thread {thread_id}] Geen telefoonnummer beschikbaar na alle pogingen")
            return {"email": email, "success": False, "reason": "No phone number available after fallback attempts"}

        # Vul telefoonnummer in - VERBETERDE VERSIE
        try:
            api.log(f"📝 [Thread {thread_id}] Zoeken naar telefoon invoer veld...")
            
            # Probeer verschillende selectors voor telefoon veld
            phone_field_selectors = [
                "input[type='tel']",
                "input[data-test-phone]",
                "input[data-phone]",
                "input[placeholder*='phone']",
                "input[name='phone']",
                "input[name='telephone']"
            ]
            
            phone_field = None
            for selector in phone_field_selectors:
                try:
                    phone_field = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if phone_field and phone_field.is_displayed():
                        api.log(f"✅ [Thread {thread_id}] Telefoon veld gevonden met selector: {selector}")
                        break
                except:
                    continue
            
            if not phone_field:
                api.log(f"❌ [Thread {thread_id}] Geen telefoon veld gevonden met bekende selectors")
                # Debug: toon alle input velden
                try:
                    all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                    api.log(f"🔍 [Thread {thread_id}] Debug: {len(all_inputs)} input velden gevonden op pagina")
                    for i, inp in enumerate(all_inputs[:5]):  # Toon eerste 5
                        try:
                            api.log(f"   {i+1}. Type: {inp.get_attribute('type')}, Placeholder: {inp.get_attribute('placeholder')}")
                        except:
                            continue
                except:
                    pass
                return {"email": email, "success": False, "reason": "Phone field not found"}
            
            # Vul telefoonnummer in
            try:
                api.log(f"📱 [Thread {thread_id}] Telefoonnummer invullen: {phone_number}")
                
                # Safety check: ensure phone_number is valid
                if not phone_number:
                    api.log(f"❌ [Thread {thread_id}] Geen telefoonnummer om in te vullen!")
                    return {"email": email, "success": False, "reason": "No phone number to enter"}
                
                # Clear veld eerst
                phone_field.clear()
                random_delay(0.3, 0.7)
                
                # Focus op veld
                phone_field.click()
                random_delay(0.3, 0.7)
                
                # Type nummer
                try:
                    for char in phone_number:
                        phone_field.send_keys(char)
                        random_delay(0.1, 0.3)  # Menselijke snelheid
                    
                    # Verify dat nummer is ingevuld
                    actual_value = phone_field.get_attribute('value') or phone_field.get_property('value')
                    api.log(f"✅ [Thread {thread_id}] Telefoonnummer ingevuld: '{actual_value}' (origineel: '{phone_number}')")
                    
                    if not actual_value or len(actual_value) < 5:
                        api.log(f"⚠️ [Thread {thread_id}] Telefoonnummer lijkt niet correct ingevuld, probeer JavaScript")
                        # JavaScript fallback
                        driver.execute_script(f"arguments[0].value = '{phone_number}'; arguments[0].dispatchEvent(new Event('input'));", phone_field)
                    
                    random_delay(0.5, 1.0)
                        
                except Exception as e:
                    api.log(f"⚠️ [Thread {thread_id}] Normaal invullen gefaald: {e}, probeer JavaScript")
                    try:
                        driver.execute_script(f"arguments[0].value = '{phone_number}';", phone_field)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", phone_field)
                        api.log(f"✅ [Thread {thread_id}] Telefoonnummer ingevuld via JavaScript")
                    except Exception as js_e:
                        api.log(f"❌ [Thread {thread_id}] JavaScript fallback ook gefaald: {js_e}")
                        return {"email": email, "success": False, "reason": f"Phone input failed: {js_e}"}
                
            except Exception as e:
                api.log(f"❌ [Thread {thread_id}] Telefoonnummer invullen mislukt: {e}")
                return {"email": email, "success": False, "reason": f"Phone number field failed: {e}"}
                
            
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Telefoonnummer sectie gefaald: {e}")
            return {"email": email, "success": False, "reason": f"Phone section failed: {e}"}

        # AUTOMATISCHE CLOUDFLARE CHECKBOX KLIK
        api.log(f"🔍 [Thread {thread_id}] Zoeken naar Cloudflare checkbox...")
        try:
            # Zoek checkbox met XPath
            cloudflare_checkbox = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='checkbox']/parent::label"))
            )
            
            if cloudflare_checkbox:
                api.log(f"✅ [Thread {thread_id}] Cloudflare checkbox gevonden - klikken...")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cloudflare_checkbox)
                time.sleep(0.5)
                cloudflare_checkbox.click()
                api.log(f"✅ [Thread {thread_id}] Cloudflare checkbox aangeklikt")
                
                # Wacht op "Success!" bericht
                api.log(f"⏳ [Thread {thread_id}] Wachten op Cloudflare success...")
                success_wait = WebDriverWait(driver, 10)
                success_element = success_wait.until(
                    EC.presence_of_element_located((By.XPATH, "//div[@id='success' and contains(@style, 'display: grid')]//span[@id='success-text' and text()='Success!']"))
                )
                api.log(f"✅ [Thread {thread_id}] Cloudflare success gedetecteerd!")
                time.sleep(1)
        except Exception as e:
            api.log(f"⚠️ [Thread {thread_id}] Cloudflare checkbox niet gevonden of success niet gedetecteerd: {e}")
            # Ga door - misschien is de checkbox al aangeklikt
        
        random_delay(1, 2)

        # 11. Klik op Verify button - VERBETERDE VERSIE
        try:
            api.log(f"🔍 [Thread {thread_id}] Zoeken naar Verify button...")
            
            # Uitgebreide lijst van selectors voor Verify button
            verify_selectors = [
                "button[data-test-next][type='submit']",
                "button[type='submit']",
                "button:contains('Verify')",
                "button:contains('verify')", 
                "button:contains('Continue')",
                "button:contains('continue')",
                "button:contains('Next')",
                "input[type='submit']",
                "[data-test='verify-button']",
                "[data-test='submit-button']",
                ".verify-button",
                ".submit-button"
            ]
            
            verify_button = None
            
            # Eerst proberen met verschillende XPath selectors
            xpath_selectors = [
                "//button[contains(text(), 'Verify')]",
                "//button[contains(text(), 'verify')]",
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), 'continue')]",
                "//button[contains(text(), 'Next')]",
                "//button[@type='submit']",
                "//input[@type='submit']"
            ]
            
            for xpath in xpath_selectors:
                try:
                    verify_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    if verify_button and verify_button.is_displayed():
                        api.log(f"✅ [Thread {thread_id}] Verify button gevonden via XPath: {xpath}")
                        break
                except:
                    continue
            
            # Als XPath niet werkt, probeer CSS selectors
            if not verify_button:
                for selector in verify_selectors:
                    try:
                        if ":contains" in selector:
                            continue  # Skip CSS :contains, we gebruiken al XPath
                        
                        verify_button = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        if verify_button and verify_button.is_displayed():
                            api.log(f"✅ [Thread {thread_id}] Verify button gevonden via CSS: {selector}")
                            break
                    except:
                        continue
            
            # Als nog steeds geen button, probeer alle buttons op de pagina
            if not verify_button:
                try:
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    api.log(f"🔍 [Thread {thread_id}] Found {len(all_buttons)} buttons on page")
                    
                    for button in all_buttons:
                        try:
                            if button.is_displayed() and button.is_enabled():
                                button_text = button.text.lower()
                                if any(word in button_text for word in ['verify', 'continue', 'next', 'submit']):
                                    verify_button = button
                                    api.log(f"✅ [Thread {thread_id}] Verify button gevonden via text search: '{button.text}'")
                                    break
                        except:
                            continue
                except Exception as e:
                    api.log(f"⚠️ [Thread {thread_id}] Error searching all buttons: {e}")
            
            if verify_button:
                api.log(f"✅ [Thread {thread_id}] Verify button gevonden: '{verify_button.text}'")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", verify_button)
                time.sleep(0.5)  # Snellere click - direct klikken
                verify_button.click()
                api.log(f"✅ [Thread {thread_id}] Verify button geklikt")
            else:
                api.log(f"⚠️ [Thread {thread_id}] Geen Verify button gevonden - mogelijk al op volgende pagina")
                # Probeer door te gaan zonder button click
                
        except Exception as e:
            api.log(f"⚠️ [Thread {thread_id}] Verify button handling error: {e}")
            # Ga door, misschien is de button niet nodig

        time.sleep(2)  # Snellere wait na Verify click

        # 12. Wacht op SMS code en vul in - VEILIG VERSIE
        api.log(f"📱 [Thread {thread_id}] Wachten op SMS verificatiecode...")
        
        # Veiligheidscheck: controleer driver status
        try:
            if not driver or not driver.current_url:
                api.log(f"❌ [Thread {thread_id}] Driver niet beschikbaar voor SMS code")
                return {"email": email, "success": False, "reason": "Driver not available"}
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Driver check voor SMS mislukt: {e}")
            return {"email": email, "success": False, "reason": "Driver check failed"}
        
        # Probeer verificatiecode op te halen met error handling
        verification_code = None
        try:
            verification_code = twilio.get_verification_code(phone_number)
        except Exception as e:
            api.log(f"⚠️ [Thread {thread_id}] Twilio verificatiecode ophalen fout: {e}")
        
        if not verification_code:
            api.log(f"❌ [Thread {thread_id}] Geen verificatiecode ontvangen")
            return {"email": email, "success": False, "reason": "No verification code received"}

        # Vul verificatiecode in - VEILIG VERSIE
        try:
            api.log(f"📝 [Thread {thread_id}] Proberen verificatiecode in te vullen: {verification_code}")
            
            # Wacht kort voor code velden om te laden
            time.sleep(2)
            
            # Zoek eerst de Ember ID door het data-testid="phone-verification-form" te vinden
            ember_id = None
            try:
                # Zoek de container met data-testid="phone-verification-form"
                verification_form = driver.find_element(By.CSS_SELECTOR, "div[data-testid='phone-verification-form']")
                # Extract ID van eerste input veld in deze container
                first_input_id = verification_form.find_element(By.CSS_SELECTOR, "input[type='tel']").get_attribute("id")
                if first_input_id and "ember" in first_input_id and "-digit" in first_input_id:
                    ember_id = first_input_id.split("-digit")[0]  # Extract ember195 from "ember195-digit1"
                    api.log(f"✅ [Thread {thread_id}] Ember ID gevonden: {ember_id}")
            except Exception as e:
                api.log(f"⚠️ [Thread {thread_id}] Ember ID niet gevonden: {e}")
            
            # NIEUWE AANPAK: Gebruik de exacte selectors uit de HTML die je gaf
            # Elke digit heeft zijn eigen data-test-code-didigitX attribute
            digits_entered = 0
            for i in range(4):
                try:
                    if i >= len(verification_code):
                        api.log(f"⚠️ [Thread {thread_id}] Verificatiecode te kort: {verification_code}")
                        break
                
                    digit = verification_code[i]
                    
                    # Gebruik de EXACTE selectors uit je HTML
                    digit_index = i + 1  # 1-based index voor selectors
                    
                    # Probeer verschillende selectors voor deze digit
                    digit_selectors = []
                    if ember_id:
                        digit_selectors.append(f"#{ember_id}-digit{digit_index}")
                    digit_selectors.extend([
                        f"input[data-test-code-digit{digit_index}]",  # data-test-code-digit1, digit2, etc.
                        f"input[data-code-digit{digit_index}]",      # data-code-digit1, digit2, etc.
                    ])
                    
                    digit_field = None
                    for selector in digit_selectors:
                        try:
                            digit_field = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                            if digit_field and digit_field.is_displayed():
                                break
                        except:
                            continue
                    
                    # Als geen specifieke selector werkt, probeer alle tel input velden te vinden
                    if not digit_field:
                        try:
                            all_tel_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='tel']")
                            if i < len(all_tel_inputs):
                                digit_field = all_tel_inputs[i]
                        except:
                            pass
                    
                    # Probeer digit in te vullen
                    if digit_field:
                        try:
                            # Scroll naar element
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", digit_field)
                            random_delay(0.2, 0.4)
                            
                            # Focus en clear
                            driver.execute_script("arguments[0].focus();", digit_field)
                            digit_field.clear()
                            time.sleep(0.1)
                            
                            # Type het cijfer
                            digit_field.send_keys(digit)
                            digits_entered += 1
                            api.log(f"✅ [Thread {thread_id}] Digit {i+1} ingevuld: {digit}")
                            random_delay(0.3, 0.7)
                        except Exception as e:
                            api.log(f"⚠️ [Thread {thread_id}] Digit {i+1} invullen fout: {e}")
                            # Probeer JavaScript fallback
                            try:
                                driver.execute_script(f"arguments[0].value = '{digit}'; arguments[0].dispatchEvent(new Event('input'));", digit_field)
                                digits_entered += 1
                                api.log(f"✅ [Thread {thread_id}] Digit {i+1} ingevuld via JS: {digit}")
                                random_delay(0.3, 0.7)
                            except:
                                api.log(f"❌ [Thread {thread_id}] Digit {i+1} volledig gefaald")
                    else:
                        api.log(f"⚠️ [Thread {thread_id}] Digit field {i+1} niet gevonden")
                        
                except Exception as e:
                    api.log(f"⚠️ [Thread {thread_id}] Digit {i+1} processing error: {e}")
                    continue
            
            if digits_entered > 0:
                api.log(f"✅ [Thread {thread_id}] {digits_entered}/4 digits ingevuld voor code: {verification_code}")
            else:
                api.log(f"❌ [Thread {thread_id}] Geen digits konden worden ingevuld")
                return {"email": email, "success": False, "reason": "Could not enter verification code"}
            
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Verificatiecode invullen mislukt: {e}")
            return {"email": email, "success": False, "reason": f"Verification code field failed: {e}"}

        random_delay(2, 4)

        # 13. Check op error message EERST
        api.log(f"🔍 [Thread {thread_id}] Controleren op error message...")
        try:
            # Check voor "An unexpected error has occurred"
            error_indicators = [
                "//div[contains(text(), 'unexpected error')]",
                "//div[contains(text(), 'Unexpected error')]",
                "//div[contains(text(), 'FAQ before trying again')]"
            ]
            
            for error_xpath in error_indicators:
                try:
                    error_element = driver.find_element(By.XPATH, error_xpath)
                    if error_element and error_element.is_displayed():
                        error_text = error_element.text.strip()
                        api.log(f"❌ [Thread {thread_id}] Error gedetecteerd: {error_text}")
                        return {"email": email, "success": False, "reason": f"Error on page: {error_text}"}
                except:
                    continue
        except:
            pass  # Geen error gevonden, continue
        
        # 14. Check op success message
        api.log(f"✅ [Thread {thread_id}] Controleren op success message...")
        try:
            success_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test-confirmation]"))
            )
            
            if "signed up" in success_element.text.lower():
                api.log(f"🎉 [Thread {thread_id}] SUCCESS! Gebruiker aangemeld")
                
                # 14. Klik op "Maybe Later" voor menselijkheid
                try:
                    maybe_later_selectors = [
                        "a[data-test-follow-later]",
                        "a:contains('Maybe Later')"
                    ]
                    
                    maybe_later_link = None
                    for selector in maybe_later_selectors:
                        try:
                            if ":contains" in selector:
                                maybe_later_link = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Maybe Later')]"))
                                )
                            else:
                                maybe_later_link = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                            if maybe_later_link:
                                break
                        except:
                            continue
                    
                    if maybe_later_link:
                        api.log(f"✅ [Thread {thread_id}] Maybe Later link gevonden")
                        maybe_later_link.click()
                        random_delay(2, 3)
                        
                        # Check final confirmation
                        try:
                            final_confirm = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Got it, thanks')]"))
                            )
                            api.log(f"✅ [Thread {thread_id}] Final confirmation gevonden")
                        except:
                            api.log(f"⚠️  [Thread {thread_id}] Final confirmation niet gevonden")
                    else:
                        api.log(f"⚠️  [Thread {thread_id}] Maybe Later link niet gevonden")
                        
                except Exception as e:
                    api.log(f"⚠️  [Thread {thread_id}] Maybe Later klik mislukt: {e}")
                
                # SUCCESS - log en cleanup
                log_to_history(email, True, "Seated signup successful")
                log_success(email)
                remove_email_immediately(email)
                
                result_success = True  # Mark signup as successful
                return {
                    "email": email,
                    "success": True,
                    "reason": "Seated signup successful"
                }
            else:
                api.log(f"❌ [Thread {thread_id}] Geen success message gevonden")
                return {"email": email, "success": False, "reason": "No success message"}
                
        except TimeoutException:
            api.log(f"❌ [Thread {thread_id}] Timeout wachten op success message")
            return {"email": email, "success": False, "reason": "Timeout waiting for success"}
        except Exception as e:
            api.log(f"❌ [Thread {thread_id}] Error checking success: {e}")
            return {"email": email, "success": False, "reason": f"Success check error: {e}"}

    except Exception as e:
        api.log(f"❌ [Thread {thread_id}] Onverwachte fout: {e}")
        return {"email": email, "success": False, "reason": f"Unexpected error: {e}"}
    
    finally:
        # Cleanup: sluit browser en verwijder profiel
        if driver:
            try:
                driver.quit()
                api.log(f"🔚 [Thread {thread_id}] Browser gesloten")
            except:
                pass
        
        if profile_id:
            try:
                api.stop_profile(profile_id)
                time.sleep(2)  # Wacht tussen stop en delete
                api.delete_profile(profile_id)
                api.log(f"✅ Profiel {profile_id} verwijderd na gebruik")
            except Exception as e:
                api.log(f"⚠️  [Thread {thread_id}] Browser cleanup fout: {e}")
        
        # Proxy cleanup
        if proxy_id:
            try:
                api.delete_proxy(proxy_id)
                api.log(f"🧹 [Thread {thread_id}] Proxy {proxy_id} verwijderd")
            except Exception as e:
                api.log(f"⚠️  [Thread {thread_id}] Proxy cleanup fout: {e}")
        
        # Phone number cleanup - mark als succes (niet meer bruikbaar voor deze link)
        if phone_number:
            try:
                global USED_PHONE_NUMBERS, SUCCESS_PHONES, USED_PHONE_LOCK
                with USED_PHONE_LOCK:
                    if result_success:
                        # Bij succes: mark nummer als succesvol voor deze link (niet meer bruikbaar)
                        SUCCESS_PHONES.add((phone_number, TARGET_URL))
                        api.log(f"📱 Telefoonnummer +44{phone_number} gemarkeerd als succesvol voor deze link (niet meer bruikbaar)")
                    else:
                        # Bij falen: timestamp blijft staan voor 1 uur cooldown
                        api.log(f"📱 Telefoonnummer +44{phone_number} in 1 uur cooldown voor deze link (mislukt)")
            except Exception as e:
                api.log(f"⚠️  [Thread {thread_id}] Phone cleanup fout: {e}")

# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def main():
    """Main function"""
    global STOP_SIGNAL, HEADLESS_MODE
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_on_exit)
    
    print("🎫 Seated Event Reminder Automation")
    print("=" * 50)
    print("📋 Functies:")
    print("   - Unieke browser profiles via Dolphin Anty")
    print("   - Unieke proxies per signup")
    print("   - Unieke fingerprints")
    print("   - Nederlandse namen en postcodes")
    print("   - Twilio SMS verificatie voor UK nummers")
    print("   - Profielen en proxies worden na gebruik verwijderd")
    print("   - Druk Ctrl+C om te stoppen tijdens uitvoering")
    
    global HEADLESS_MODE
    
    # Browser mode altijd zichtbaar (geen headless mode nodig voor Seated)
    print("\n🖥️  BROWSER MODE:")
    print("   ✅ Browsers worden altijd zichtbaar geopend")
    HEADLESS_MODE = False
    
    # Extra stap
    try:
        start_choice = input("\n🚀 Wil je de automation starten? (y/n): ").lower().strip()
        if start_choice not in ['y', 'yes', 'ja', 'j']:
            print("🛑 Script geannuleerd door gebruiker")
            return
    except (KeyboardInterrupt, EOFError):
        # Fallback voor non-interactive terminal of Ctrl+C
        print("\n⚠️  Non-interactive mode - auto-starting automation")
        pass
    
    print("✅ Auto-start in 3 seconden...")
    time.sleep(3)
    
    api = DolphinAPI(DOLPHIN_TOKEN)
    
    # Check Dolphin Anty status
    print("\n🔍 Controleren Dolphin Anty status...")
    try:
        test_proxies = api.get_proxies()
        if test_proxies is not None:
            print("✅ Dolphin Anty Remote API bereikbaar")
        else:
            print("⚠️  Dolphin Anty Remote API problemen")
    except Exception as e:
        print(f"⚠️  Dolphin Anty check fout: {e}")
    
    # Check Twilio configuratie
    print("\n📱 Controleren Twilio configuratie...")
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_SERVICE_SID:
        try:
            twilio = TwilioAPI(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SERVICE_SID)
            print("✅ Twilio configuratie geldig")
        except Exception as e:
            print(f"❌ Twilio configuratie fout: {e}")
            return
    else:
        print("❌ Twilio configuratie incomplete!")
        print("💡 Vul TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN en TWILIO_SERVICE_SID in config.json")
        return
    
    # Laad emails
    print("📧 Laden van emails uit emails.txt...")
    all_emails = load_emails()
    if not all_emails:
        print("❌ Geen emails gevonden in emails.txt")
        print("💡 Voeg emails toe aan emails.txt (één per regel)")
        return
    
    # Test proxy verbinding
    print(f"\n📡 Proxy verbinding testen...")
    proxies_test = api.get_proxies()
    
    if not proxies_test:
        print("❌ Geen proxies gevonden in Dolphin Anty!")
        print("💡 Voeg eerst proxies toe in Dolphin Anty voordat je dit script draait")
        return
    
    print(f"\n✅ {len(proxies_test)} proxies beschikbaar in Dolphin Anty")
    print(f"💡 Proxies worden dynamisch opgehaald tijdens runtime")
    print(f"📧 {len(all_emails)} emails te verwerken")
    print(f"🔄 Max threads: {MAX_THREADS}")
    print(f"🌐 Target URL: {TARGET_URL}")
    print(f"\n⚠️  BELANGRIJK:")
    print(f"   - Gebruikt BESTAANDE profielen uit Dolphin Anty")
    print(f"   - Elk profiel krijgt UNIEKE proxy uit Dolphin Anty")
    print(f"   - Profielen worden HERGEBRUIKT (niet verwijderd)")
    print(f"   - Proxies worden NA gebruik VERWIJDERD")
    print(f"   - Twilio SMS verificatie voor UK nummers")
    print(f"\n" + "=" * 70)
    
    # Alleen handmatig gemaakte profielen gebruiken
    print("\n🔍 Controleren bestaande profielen...")
    existing_profiles = api.get_profiles()
    if not existing_profiles:
        print("❌ Geen profielen gevonden in Dolphin Anty")
        print("💡 Maak eerst handmatig profielen aan in Dolphin Anty voordat je dit script draait")
        return
    else:
        print(f"✅ {len(existing_profiles)} profielen gevonden in Dolphin Anty")
    use_existing_profiles = True
    
    # DYNAMISCH PROXY SYSTEEM met refresh - EXACT ZOALS OASIS
    # Na elke cleanup worden proxies ververst zodat nieuwe proxies uit de pool van 100 beschikbaar komen
    proxy_lock = threading.Lock()
    
    def get_fresh_proxy_pool(count=3):
        """Haal verse proxies op - refreshed na elke cleanup"""
        with proxy_lock:
            fresh_proxies = api.get_proxies()
            if not fresh_proxies:
                return []
            return [p.get('id') for p in fresh_proxies[:min(count, len(fresh_proxies))]]
    
    def get_fresh_profile_pool(count=3):
        """Haal verse profielen op - hergebruik bestaande profielen"""
        if use_existing_profiles:
            with proxy_lock:
                return [p.get('id') for p in existing_profiles[:min(count, len(existing_profiles))]]
        else:
            # Geen profielen beschikbaar - wordt later automatisch aangemaakt
            return []
    
    # Vul globale profielen pool
    global AVAILABLE_PROFILE_POOL, AVAILABLE_PROFILE_POOL_LOCK
    with AVAILABLE_PROFILE_POOL_LOCK:
        AVAILABLE_PROFILE_POOL = [p.get('id') for p in existing_profiles]
        print(f"📝 Globale profielen pool gevuld met {len(AVAILABLE_PROFILE_POOL)} profielen")
    
    # Multi-threaded processing met dynamische proxy toewijzing
    results = []
    completed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Submit emails in batches - refresh proxies tussen batches
        email_queue = [(email, i+1) for i, email in enumerate(all_emails)]
        print(f"🚀 Starten van {MAX_THREADS} threads...")
        print(f"📧 {len(email_queue)} emails in queue voor verwerking")
        active_futures = {}
        
        # Start eerste batch
        for _ in range(min(MAX_THREADS, len(email_queue))):
            if email_queue:
                email, thread_id = email_queue.pop(0)
                proxy_pool = get_fresh_proxy_pool(count=3)
                profile_pool = get_fresh_profile_pool(count=3)
                if proxy_pool:
                    future = executor.submit(signup_seated_with_retry, email, thread_id, proxy_pool, profile_pool)
                    active_futures[future] = email
        
        # Verwerk resultaten en submit nieuwe emails (dynamisch)
        while active_futures and not STOP_SIGNAL:
            # Wacht tot één future klaar is
            for future in as_completed(active_futures.keys()):
                email = active_futures.pop(future)
                completed_count += 1
                
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Progress
                    success_count = sum(1 for r in results if r['success'])
                    print(f"\n📊 Progress: {completed_count}/{len(all_emails)} | Succesvol: {success_count}")
                    
                except Exception as e:
                    print(f"❌ Exception voor {email}: {e}")
                    results.append({
                        "email": email,
                        "success": False,
                        "reason": f"Exception: {str(e)}"
                    })
                
                # Check stop signal voor nieuwe submissions
                if STOP_SIGNAL:
                    print(f"\n🛑 Stop signal ontvangen - geen nieuwe emails meer submiten")
                    break
                
                # Submit volgende email met VERSE proxies en profielen (na cleanup zijn nieuwe beschikbaar!)
                if email_queue:
                    next_email, next_thread_id = email_queue.pop(0)
                    # REFRESH: Haal nieuwe proxies en profielen op na elke voltooide signup
                    proxy_pool = get_fresh_proxy_pool(count=3)
                    profile_pool = get_fresh_profile_pool(count=3)
                    if proxy_pool:
                        future = executor.submit(signup_seated_with_retry, next_email, next_thread_id, proxy_pool, profile_pool)
                        active_futures[future] = next_email
                        print(f"🔄 Nieuwe email gesubmit met verse proxies (profielen worden automatisch aangemaakt)")
                    else:
                        print(f"⚠️  Geen proxies beschikbaar voor {next_email}")
                        results.append({
                            "email": next_email,
                            "success": False,
                            "reason": "No proxies or profiles available at this time"
                        })
                        completed_count += 1
                
                break  # Verwerk één result per iteratie, dan check opnieuw
    
    # Samenvatting
    print("\n" + "=" * 70)
    print("📊 SAMENVATTING")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r['success'])
    failed_count = len(results) - success_count
    
    print(f"\n✅ Succesvol: {success_count}/{len(results)}")
    print(f"❌ Mislukt: {failed_count}/{len(results)}")
    
    if failed_count > 0:
        print(f"\n❌ Mislukte emails:")
        for r in results:
            if not r['success']:
                print(f"   - {r['email']}: {r.get('reason', 'Unknown')}")
    
    # Toon success file
    if os.path.exists(SUCCESS_FILE):
        print(f"\n🎉 Success gegevens opgeslagen in: {os.path.basename(SUCCESS_FILE)}")
    
    print(f"\n📁 Log bestand: {LOG_FILE}")
    print(f"📁 Resultaten: {RESULTS_FILE}")
    print(f"📁 Permanent history: {HISTORY_FILE}")
    print("\n" + "=" * 70)
    print("✅ Automation voltooid!")

if __name__ == "__main__":
    main()

