#!/usr/bin/env python3
"""
Zach Bryan Presale Signup Automation
=====================================
Automates registration for zachbryanpresale.com using Dolphin browser profiles.
Includes IMAP email OTP extraction.
"""

import sys
import os
import json
import time
import random
import csv
import re
import imaplib
import email
import requests
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from email.header import decode_header

# Add parent directory to path to import dolphin_base
# Handle both normal execution and PyInstaller EXE execution
if getattr(sys, 'frozen', False):
    # Running as EXE - add the directory where the EXE's extracted files are
    base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
    sys.path.insert(0, str(base_path))
    # Also try the directory where EXE is located (for bundled data files)
    exe_dir = Path(sys.executable).parent
    sys.path.insert(0, str(exe_dir))
    # Also try parent of current file location (for when loaded from signups/)
    if hasattr(sys, '_MEIPASS'):
        # In PyInstaller, dolphin_base should be in _MEIPASS root
        pass  # Already added above
else:
    # Running as script - add parent directory
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dolphin_base import DolphinAutomation
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class IMAPHelper:
    """Helper class for IMAP email OTP extraction for AEG Presents concerts"""
    
    def __init__(self, imap_config: Dict[str, Any]):
        self.email = imap_config.get('email', '')
        self.password = imap_config.get('password', '')
        self.server = imap_config.get('server', 'imap.gmail.com')
        self.port = imap_config.get('port', 993)
        self.folder = imap_config.get('folder', 'INBOX')
        self.sender = imap_config.get('sender', 'concerts@events.aegpresents.com')
        self.subject_phrase = imap_config.get('subject_phrase', 'Your One-Time Passcode')
        self.timeout = imap_config.get('code_timeout_seconds', 60)
        self.poll_interval = imap_config.get('code_poll_interval', 10)
        
        # OTP Cache: {target_email: {'code': code, 'timestamp': datetime, 'email_id': email_id}}
        self.otp_cache = {}
        self.otp_cache_lock = threading.Lock()
        self.scanned_email_ids = set()  # Track welke emails we al gescand hebben
        
        # Background scanner control
        self.scanner_running = False
        self.scanner_thread = None
        
        # Start background scanner immediately
        self.start_background_otp_scanner(scan_interval=10)
    
    def start_background_otp_scanner(self, scan_interval: int = 10):
        """Start background thread that scans OTP emails every 10 seconds"""
        if self.scanner_running:
            return
        
        self.scanner_running = True
        self.scanner_thread = threading.Thread(
            target=self._background_otp_scanner,
            args=(scan_interval,),
            daemon=True,
            name="AEGOTPScanner"
        )
        self.scanner_thread.start()
        print(f"🔄 OTP background scanner gestart (scant elke {scan_interval}s voor {self.sender})...")
    
    def stop_background_otp_scanner(self):
        """Stop background OTP scanner"""
        self.scanner_running = False
        if self.scanner_thread:
            self.scanner_thread.join(timeout=5)
        print("🛑 OTP background scanner gestopt")
    
    def _background_otp_scanner(self, scan_interval: int):
        """Background proces dat continu OTP emails scant en cached"""
        while self.scanner_running:
            try:
                # Scan alle OTP emails van vandaag
                since_date = datetime.now().strftime('%d-%b-%Y')
                
                with imaplib.IMAP4_SSL(self.server, self.port) as M:
                    M.login(self.email, self.password)
                    
                    # FORCE REFRESH: Close and reopen mailbox
                    try:
                        M.close()
                    except:
                        pass
                    M.select(self.folder)
                    
                    # Search voor alle emails van vandaag van sender
                    search_criteria = f'FROM "{self.sender}" SINCE "{since_date}"'
                    
                    try:
                        status, messages = M.search(None, search_criteria)
                    except:
                        # Fallback zonder FROM filter
                        search_criteria = f'SINCE "{since_date}"'
                        status, messages = M.search(None, search_criteria)
                    
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        new_cached_count = 0
                        
                        # Process newest first
                        for email_id in reversed(email_ids):
                            if not self.scanner_running:
                                break
                            
                            email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                            
                            # Skip als we deze email al gescand hebben
                            with self.otp_cache_lock:
                                if email_id_str in self.scanned_email_ids:
                                    continue
                            
                            try:
                                status, msg_data = M.fetch(email_id, '(RFC822)')
                                if status != 'OK' or not msg_data:
                                    continue
                                
                                msg = email.message_from_bytes(msg_data[0][1])
                                
                                # Check sender
                                from_header = self.decode_str(msg.get('From', ''))
                                if self.sender.lower() not in from_header.lower():
                                    continue
                                
                                # Get recipient emails
                                to_header = self.decode_str(msg.get('To', ''))
                                cc_header = self.decode_str(msg.get('Cc', ''))
                                bcc_header = self.decode_str(msg.get('Bcc', ''))
                                
                                all_recipient_emails = []
                                for header in [to_header, cc_header, bcc_header]:
                                    if header:
                                        # Extract emails from header
                                        email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', header)
                                        all_recipient_emails.extend(email_matches)
                                
                                if not all_recipient_emails:
                                    continue
                                
                                # Get HTML body
                                html_body = self.get_html_body(msg)
                                if not html_body:
                                    continue
                                
                                # Extract OTP: "Your One-Time Passcode: <strong>CODE</strong>"
                                otp_code = None
                                
                                # Try strong tag first
                                strong_match = re.search(
                                    r'Your One-Time Passcode:\s*<strong>\s*([A-Z0-9]{4})\s*</strong>',
                                    html_body,
                                    re.IGNORECASE
                                )
                                
                                if strong_match:
                                    otp_code = strong_match.group(1).strip()
                                
                                # Fallback: look for 4-character alphanumeric code
                                if not otp_code:
                                    fallback_match = re.search(
                                        r'Your One-Time Passcode:\s*([A-Z0-9]{4})',
                                        html_body,
                                        re.IGNORECASE
                                    )
                                    if fallback_match:
                                        otp_code = fallback_match.group(1).strip()
                                
                                # Cache OTP voor alle recipients
                                if otp_code and len(otp_code) == 4:
                                    with self.otp_cache_lock:
                                        # Mark email as scanned
                                        self.scanned_email_ids.add(email_id_str)
                                        
                                        # Cache voor alle recipients
                                        for recipient in all_recipient_emails:
                                            recipient_normalized = recipient.lower().strip()
                                            # Normalize Gmail addresses
                                            if '@gmail.com' in recipient_normalized:
                                                recipient_normalized = recipient_normalized.replace('.', '').split('@')[0] + '@gmail.com'
                                            
                                            # Only cache if not already cached or cache is older
                                            should_cache = True
                                            if recipient_normalized in self.otp_cache:
                                                cached_entry = self.otp_cache[recipient_normalized]
                                                cached_timestamp = cached_entry.get('timestamp')
                                                if cached_timestamp:
                                                    age_seconds = (datetime.now() - cached_timestamp).total_seconds()
                                                    if age_seconds < 300:  # Keep if less than 5 min old
                                                        should_cache = False
                                            
                                            if should_cache:
                                                self.otp_cache[recipient_normalized] = {
                                                    'code': otp_code,
                                                    'timestamp': datetime.now(),
                                                    'email_id': email_id_str
                                                }
                                                new_cached_count += 1
                                                
                                                # Mark email as read
                                                try:
                                                    M.store(email_id, '+FLAGS', '\\Seen')
                                                except:
                                                    pass
                                
                            except Exception as e:
                                # Silently skip errors
                                continue
                        
                        if new_cached_count > 0:
                            print(f"✅ [OTP Scanner] {new_cached_count} nieuwe OTP code(s) gecached van {self.sender}")
                    
            except Exception as e:
                # Silently handle errors in background scanner
                pass
            
            # Wait before next scan
            if self.scanner_running:
                time.sleep(scan_interval)
    
    def decode_str(self, s):
        """Decode email header string"""
        if not s:
            return ""
        try:
            decoded, encoding = decode_header(str(s))[0]
            if isinstance(decoded, bytes):
                return decoded.decode(encoding or 'utf-8', errors='ignore')
            return str(decoded)
        except:
            return str(s)
    
    def get_html_body(self, msg):
        """Extract HTML content from email message"""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            return payload.decode('utf-8', errors='ignore')
                    except:
                        pass
        else:
            try:
                if msg.get_content_type() == "text/html":
                    payload = msg.get_payload(decode=True)
                    if payload:
                        return payload.decode('utf-8', errors='ignore')
            except:
                pass
        return None
    
    def extract_otp_from_email(self, target_email: str) -> Optional[str]:
        """Extract OTP code from email - check eerst cache, dan IMAP"""
        if not target_email:
            return None
        
        # EERST CHECK CACHE (veel sneller!)
        target_email_normalized = target_email.lower().strip()
        
        # Normalize Gmail addresses for cache lookup (dots don't matter)
        if '@gmail.com' in target_email_normalized:
            target_email_normalized = target_email_normalized.replace('.', '').split('@')[0] + '@gmail.com'
        
        with self.otp_cache_lock:
            if target_email_normalized in self.otp_cache:
                cached_entry = self.otp_cache[target_email_normalized]
                code = cached_entry.get('code')
                timestamp = cached_entry.get('timestamp')
                if code and timestamp:
                    # Check if code is still fresh (max 10 minuten oud)
                    age_seconds = (datetime.now() - timestamp).total_seconds()
                    if age_seconds < 600:  # 10 minuten
                        print(f"      ✅ OTP GEVONDEN IN CACHE! Code: {code} (gecached {int(age_seconds)}s geleden)")
                        # Remove from cache after use (one-time use)
                        del self.otp_cache[target_email_normalized]
                        return code
                    else:
                        # Cache entry is too old, remove it
                        del self.otp_cache[target_email_normalized]
        
        # GEEN OTP IN CACHE - scan IMAP (met force refresh)
        try:
            print(f"      🔐 IMAP verbinden met {self.server}:{self.port}...")
            with imaplib.IMAP4_SSL(self.server, self.port) as M:
                M.login(self.email, self.password)
                
                elapsed = 0
                start_time = datetime.now()
                
                while elapsed < self.timeout:
                    # FORCE REFRESH: Close and reopen mailbox
                    try:
                        M.close()
                    except:
                        pass
                    M.select(self.folder)
                    
                    # Search for emails from sender to target_email
                    since_date = (datetime.now() - timedelta(minutes=10)).strftime('%d-%b-%Y')
                    search_criteria = f'FROM "{self.sender}" TO "{target_email}" SINCE "{since_date}"'
                    
                    try:
                        status, messages = M.search(None, search_criteria)
                    except:
                        # Fallback without TO filter
                        search_criteria = f'FROM "{self.sender}" SINCE "{since_date}"'
                        status, messages = M.search(None, search_criteria)
                    
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        
                        # Process newest first
                        for email_id in reversed(email_ids):
                            try:
                                status, msg_data = M.fetch(email_id, '(RFC822)')
                                if status != 'OK':
                                    continue
                                
                                msg = email.message_from_bytes(msg_data[0][1])
                                
                                # Check recipient
                                to_header = self.decode_str(msg.get('To', ''))
                                if target_email.lower() not in to_header.lower():
                                    continue
                                
                                # Check sender
                                from_header = self.decode_str(msg.get('From', ''))
                                if self.sender.lower() not in from_header.lower():
                                    continue
                                
                                # Get HTML body
                                html_body = self.get_html_body(msg)
                                if not html_body:
                                    continue
                                
                                # Extract OTP
                                otp_code = None
                                
                                # Try strong tag first
                                strong_match = re.search(
                                    r'Your One-Time Passcode:\s*<strong>\s*([A-Z0-9]{4})\s*</strong>',
                                    html_body,
                                    re.IGNORECASE
                                )
                                
                                if strong_match:
                                    otp_code = strong_match.group(1).strip()
                                
                                # Fallback: look for 4-character code
                                if not otp_code:
                                    fallback_match = re.search(
                                        r'Your One-Time Passcode:\s*([A-Z0-9]{4})',
                                        html_body,
                                        re.IGNORECASE
                                    )
                                    if fallback_match:
                                        otp_code = fallback_match.group(1).strip()
                                
                                if otp_code and len(otp_code) == 4:
                                    print(f"      ✅ Extracted OTP: {otp_code}")
                                    
                                    # Mark email as read
                                    try:
                                        M.store(email_id, '+FLAGS', '\\Seen')
                                    except:
                                        pass
                                    
                                    return otp_code
                                    
                            except Exception as e:
                                continue
                    
                    # Wait before next check
                    time.sleep(self.poll_interval)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    if elapsed < self.timeout:
                        print(f"      ⏳ Waiting for OTP email... ({int(elapsed)}s/{self.timeout}s)")
                
                print(f"      ❌ OTP email not found after {self.timeout} seconds")
                return None
                
        except Exception as e:
            print(f"      ❌ IMAP error: {e}")
            return None


class ZachBryanAutomation(DolphinAutomation):
    """Zach Bryan-specific automation extending DolphinAutomation base"""
    
    def __init__(self, config_file):
        """Initialize with config file"""
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.site_config = json.load(f)
        
        # Transform config to match dolphin_base.py expectations
        dolphin_config_raw = self.site_config.get('dolphin', {})
        dolphin_config = {}
        if dolphin_config_raw:
            if 'token' in dolphin_config_raw:
                dolphin_config['dolphin_token'] = dolphin_config_raw['token']
            if 'remote_api_url' in dolphin_config_raw:
                dolphin_config['dolphin_remote_api_url'] = dolphin_config_raw['remote_api_url']
            if 'api_url' in dolphin_config_raw:
                api_url = dolphin_config_raw['api_url']
                if 'localhost' in api_url or '127.0.0.1' in api_url:
                    dolphin_config['dolphin_api_url'] = api_url
                else:
                    dolphin_config['dolphin_remote_api_url'] = api_url
        
        super().__init__(dolphin_config)
        
        self.site_url = self.site_config.get('site_url', '')
        automation_config = self.site_config.get('automation', {})
        self.threads = int(automation_config.get('threads', 5))
        self.timeout = automation_config.get('timeout_seconds', 45)
        self.config_path = config_path
        
        # Determine base directory for files
        base_dir = config_path.parent
        
        # Load accounts from CSV
        files_config = self.site_config.get('files', {})
        accounts_csv = base_dir / files_config.get('accounts', 'emails.csv')
        self.accounts_csv = accounts_csv
        
        # Load accounts
        self.accounts = self._load_accounts_from_csv(accounts_csv)
        
        # Load proxies
        proxies_file = base_dir / files_config.get('proxies', 'proxies.txt')
        self.proxies_file = proxies_file
        self.proxy_strings = self._load_from_file(proxies_file, "proxies")
        
        # Initialize IMAP helper
        imap_config = self.site_config.get('imap', {})
        if imap_config:
            self.imap_helper = IMAPHelper(imap_config)
        else:
            self.imap_helper = None
        
        # Discord webhook
        discord_config = self.site_config.get('discord', {})
        self.discord_webhook = discord_config.get('finished_webhook', '')
        
        # Track proxies
        self.used_proxy_strings = set()
        self.profile_proxy_string_map = {}
        self.profile_proxy_map = {}
    
    def _load_accounts_from_csv(self, csv_file):
        """Load accounts from CSV file"""
        accounts = []
        
        if not csv_file.exists():
            print(f"⚠️ Accounts CSV file not found: {csv_file}")
            return accounts
        
        try:
            with open(csv_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = row.get('email', '').strip()
                    if email and '@' in email:
                        accounts.append({
                            'email': email,
                            'first_name': row.get('first_name', '').strip(),
                            'last_name': row.get('last_name', '').strip(),
                            'phone_number': row.get('phone_number', '').strip(),
                            'registered': row.get('registered', 'false').strip().lower() == 'true'
                        })
            
            # Filter out already registered
            unregistered = [acc for acc in accounts if not acc['registered']]
            print(f"📧 Loaded {len(unregistered)} unregistered accounts (out of {len(accounts)} total)")
            return unregistered
            
        except Exception as e:
            print(f"❌ Error loading accounts from CSV: {e}")
            return accounts
    
    def _load_from_file(self, file_path, file_type):
        """Load lines from a text file"""
        lines = []
        
        if not file_path.exists():
            print(f"⚠️ {file_type.capitalize()} file not found: {file_path}")
            return lines
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        lines.append(line)
            
            print(f"✅ Loaded {len(lines)} {file_type} from {file_path.name}")
            return lines
            
        except Exception as e:
            print(f"❌ Error loading {file_type} from {file_path}: {e}")
            return lines
    
    def _mark_account_registered(self, email):
        """Mark an account as registered in CSV"""
        try:
            if not self.accounts_csv.exists():
                return
            
            rows = []
            fieldnames = None
            with open(self.accounts_csv, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or ['email', 'first_name', 'last_name', 'phone_number', 'registered', 'timestamp']
                for row in reader:
                    if row.get('email', '').strip().lower() == email.lower():
                        row['registered'] = 'true'
                        row['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    rows.append(row)
            
            with open(self.accounts_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            print(f"✅ Marked {email} as registered")
            
        except Exception as e:
            print(f"⚠️ Error marking account as registered: {e}")
    
    def _generate_uk_phone(self):
        """Generate UK phone number in format +44 7XXX XXXXXX"""
        # UK mobile numbers start with +44 7
        area = random.randint(100, 999)
        number = random.randint(100000, 999999)
        return f"+44 7{area} {number:06d}"
    
    def _generate_name(self, is_first=True):
        """Generate random first or last name"""
        first_names = ['James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles',
                      'Emma', 'Olivia', 'Sophia', 'Isabella', 'Charlotte', 'Amelia', 'Mia', 'Harper', 'Evelyn', 'Abigail']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
                     'Wilson', 'Anderson', 'Taylor', 'Thomas', 'Hernandez', 'Moore', 'Martin', 'Jackson', 'Thompson', 'White']
        
        if is_first:
            return random.choice(first_names)
        else:
            return random.choice(last_names)
    
    def create_profile(self, proxy_data=None, name_prefix='ZACHBRYAN'):
        """Override create_profile to use lazy proxy creation"""
        if not proxy_data:
            proxy_data, proxy_string = self._get_or_create_proxy()
            if proxy_data:
                self.profile_proxy_string_map[proxy_data.get('id')] = proxy_string
        
        profile = super().create_profile(proxy_data=proxy_data, name_prefix=name_prefix)
        
        if profile and proxy_data:
            self.profile_proxy_map[profile['id']] = proxy_data
            if proxy_data.get('id') in self.profile_proxy_string_map:
                self.profile_proxy_string_map[profile['id']] = self.profile_proxy_string_map[proxy_data.get('id')]
                del self.profile_proxy_string_map[proxy_data.get('id')]
        
        return profile
    
    def _get_or_create_proxy(self):
        """Get an unused proxy or create a new one"""
        unused_proxy = self.get_random_unused_proxy()
        if unused_proxy:
            return unused_proxy, None
        
        if not self.proxy_strings:
            raise Exception("No proxy strings available")
        
        available_strings = [s for s in self.proxy_strings if s not in self.used_proxy_strings]
        if not available_strings:
            available_strings = self.proxy_strings
        
        proxy_string = random.choice(available_strings)
        self.used_proxy_strings.add(proxy_string)
        
        try:
            parts = proxy_string.strip().split(':')
            if len(parts) != 4:
                raise Exception(f"Invalid proxy format: {proxy_string}")
            
            proxy_data = {
                'type': 'http',
                'host': parts[0],
                'port': int(parts[1]),
                'login': parts[2],
                'password': parts[3],
                'name': f"Proxy-{parts[0]}-{parts[1]}"
            }
            
            created_proxy = self.create_proxy(proxy_data)
            return created_proxy, proxy_string
            
        except Exception as e:
            self.used_proxy_strings.discard(proxy_string)
            raise
    
    def _process_single_item(self, site_config, data_item, task_number):
        """Process a single account signup"""
        profile = None
        driver = None
        
        try:
            account = data_item
            email = account['email']
            
            # Create profile
            profile = self.create_profile(proxy_data=None, name_prefix=f'ZACHBRYAN{task_number}')
            if not profile:
                return False
            
            # Create driver
            driver = self.create_driver(profile['id'])
            if not driver:
                return False
            
            # Run automation
            success = self._execute_site_automation(driver, site_config, account, task_number)
            
            # Cleanup
            profile_id = profile['id'] if profile else None
            proxy_data = self.profile_proxy_map.get(profile_id) if profile_id else None
            proxy_string = self.profile_proxy_string_map.get(profile_id) if profile_id else None
            
            if profile:
                self._cleanup_profile_and_proxy(
                    profile=profile,
                    proxy=proxy_data,
                    success=success,
                    proxy_string=proxy_string,
                    proxies_file=str(self.proxies_file) if hasattr(self, 'proxies_file') and self.proxies_file else None
                )
            
            if profile_id and profile_id in self.profile_proxy_map:
                del self.profile_proxy_map[profile_id]
            if profile_id and profile_id in self.profile_proxy_string_map:
                del self.profile_proxy_string_map[profile_id]
            
            return success
            
        except Exception as e:
            print(f"❌ Error in automation process: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def _execute_site_automation(self, driver, site_config, account, task_number):
        """Execute Zach Bryan registration automation"""
        email = account['email']
        first_name = account.get('first_name') or self._generate_name(is_first=True)
        last_name = account.get('last_name') or self._generate_name(is_first=False)
        phone_number = account.get('phone_number') or self._generate_uk_phone()
        
        print(f"\n🎯 [TASK-{task_number}] Starting Zach Bryan registration for {email}")
        
        try:
            # Step 1: Open Gmail and scroll
            print(f"[TASK-{task_number}] 📧 Opening Gmail...")
            driver.get("https://www.gmail.com")
            time.sleep(random.uniform(2, 4))
            self.human_scroll(driver, scroll_count=random.randint(2, 4))
            time.sleep(random.uniform(1, 2))
            
            # Step 2: Open new tab and navigate to zachbryanpresale.com
            print(f"[TASK-{task_number}] 🌐 Opening zachbryanpresale.com in new tab...")
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(self.site_url)
            time.sleep(random.uniform(2, 4))
            
            # Step 3: Scroll down naturally
            print(f"[TASK-{task_number}] 📜 Scrolling down...")
            self.human_scroll(driver, scroll_count=random.randint(5, 8))
            time.sleep(random.uniform(1, 2))
            
            # Step 4: Click REGISTER button
            print(f"[TASK-{task_number}] 🖱️ Clicking REGISTER button...")
            register_button = WebDriverWait(driver, self.timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.reggie-button-fullwidth.reggie-venues__button-text_showid50"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", register_button)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, register_button)
            time.sleep(random.uniform(2, 4))
            
            # Step 5: Wait for form and make natural movements
            print(f"[TASK-{task_number}] ⏳ Waiting for form to load...")
            time.sleep(random.uniform(2, 4))
            self.random_mouse_movement(driver)
            self.human_scroll(driver, scroll_count=random.randint(2, 3))
            
            # Step 6: Fill phone number
            print(f"[TASK-{task_number}] 📱 Filling phone number: {phone_number}")
            phone_input = WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#mobilePhone"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", phone_input)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, phone_input)
            time.sleep(random.uniform(0.2, 0.4))
            phone_input.clear()
            self.human_type(phone_input, phone_number)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Step 7: Fill first name
            print(f"[TASK-{task_number}] ✏️ Filling first name: {first_name}")
            first_name_input = WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#nameFirst"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", first_name_input)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, first_name_input)
            time.sleep(random.uniform(0.2, 0.4))
            first_name_input.clear()
            self.human_type(first_name_input, first_name)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Step 8: Fill last name
            print(f"[TASK-{task_number}] ✏️ Filling last name: {last_name}")
            last_name_input = WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#nameLast"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", last_name_input)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, last_name_input)
            time.sleep(random.uniform(0.2, 0.4))
            last_name_input.clear()
            self.human_type(last_name_input, last_name)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Step 9: Fill email
            print(f"[TASK-{task_number}] ✉️ Filling email: {email}")
            email_input = WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#email"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", email_input)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, email_input)
            time.sleep(random.uniform(0.2, 0.4))
            email_input.clear()
            self.human_type(email_input, email)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Step 10: Scroll to checkbox
            print(f"[TASK-{task_number}] 📜 Scrolling to checkbox...")
            self.human_scroll(driver, scroll_count=random.randint(3, 4))
            
            # Step 11: Click marketing checkbox
            print(f"[TASK-{task_number}] ☑️ Clicking marketing checkbox...")
            checkbox = WebDriverWait(driver, self.timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#optInMarketing"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", checkbox)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, checkbox)
            time.sleep(random.uniform(1, 2))
            
            # Step 12: Click Continue button
            print(f"[TASK-{task_number}] 🖱️ Clicking Continue button...")
            continue_button = WebDriverWait(driver, self.timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.c-button[type='submit'][value='Continue']"))
            )
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", continue_button)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, continue_button)
            time.sleep(random.uniform(2, 4))
            
            # Step 13: Wait for verification page
            print(f"[TASK-{task_number}] ⏳ Waiting for verification page...")
            verification_input1 = WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#verificationChar1"))
            )
            
            # Step 14: Extract OTP from email
            print(f"[TASK-{task_number}] 📧 Extracting OTP from email...")
            if not self.imap_helper:
                raise Exception("IMAP helper not initialized")
            
            otp_code = self.imap_helper.extract_otp_from_email(email)
            
            if not otp_code or len(otp_code) != 4:
                raise Exception(f"Invalid OTP code: {otp_code}")
            
            # Step 15: Fill OTP code in 4 inputs
            print(f"[TASK-{task_number}] 🔢 Filling OTP code: {otp_code}")
            for i in range(4):
                char = otp_code[i]
                selector = f"#verificationChar{i + 1}"
                
                otp_input = WebDriverWait(driver, self.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", otp_input)
                time.sleep(random.uniform(0.2, 0.4))
                self.human_click(driver, otp_input)
                time.sleep(random.uniform(0.1, 0.2))
                otp_input.clear()
                self.human_type(otp_input, char)
                time.sleep(random.uniform(0.2, 0.4))
            
            # Step 16: Wait for Verify button to be enabled
            print(f"[TASK-{task_number}] ⏳ Waiting for Verify button to be enabled...")
            time.sleep(random.uniform(1, 2))
            
            verify_button = WebDriverWait(driver, self.timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.c-button.reggie-button-fullwidth.center-text:not([disabled])"))
            )
            
            # Step 17: Click Verify button
            print(f"[TASK-{task_number}] 🖱️ Clicking Verify button...")
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", verify_button)
            time.sleep(random.uniform(0.3, 0.6))
            self.human_click(driver, verify_button)
            time.sleep(random.uniform(4, 6))
            
            # Step 18: Check for success
            print(f"[TASK-{task_number}] ✅ Checking for success...")
            page_source = driver.page_source
            if "We'll send you a presale code" in page_source or "presale code" in page_source.lower():
                print(f"[TASK-{task_number}] ✅ SUCCESS! Registration completed for {email}")
                
                # Mark as registered
                self._mark_account_registered(email)
                
                # Send Discord notification
                if self.discord_webhook:
                    try:
                        message = {
                            "content": f"✅ **Zach Bryan Registration Finished**\n📧 Email: `{email}`\n🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                            "username": "Zach Bryan Automation"
                        }
                        requests.post(self.discord_webhook, json=message, timeout=10)
                    except:
                        pass
                
                return True
            else:
                print(f"[TASK-{task_number}] ⚠️ Success message not found, but continuing...")
                # Still mark as registered if we got this far
                self._mark_account_registered(email)
                return True
                
        except Exception as e:
            print(f"[TASK-{task_number}] ❌ Error during registration: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """Run the Zach Bryan automation"""
        print(f"\n🚀 Starting Zach Bryan Presale Registration Automation")
        print(f"📧 Accounts: {len(self.accounts)}")
        print(f"🧵 Threads: {self.threads}")
        print(f"🌐 Site: {self.site_url}\n")
        
        if not self.accounts:
            print("❌ No accounts provided in config!")
            return
        
        try:
            site_config = {
                'name': 'Zach Bryan',
                'url': self.site_url
            }
            
            self.proxies = []
            self.run_automation(site_config, self.accounts, threads=self.threads)
        finally:
            # Stop IMAP scanner when done
            if self.imap_helper:
                self.imap_helper.stop_background_otp_scanner()


def main():
    """Main entry point"""
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        config_dir = exe_dir / 'signups' / 'zachbryan'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / 'zachbryan_config.json'
        
        if not config_file.exists() and hasattr(sys, '_MEIPASS'):
            bundled_config = Path(sys._MEIPASS) / 'signups' / 'zachbryan' / 'zachbryan_config.json'
            if bundled_config.exists():
                import shutil
                shutil.copy2(bundled_config, config_file)
    else:
        script_dir = Path(__file__).parent.parent.parent
        config_dir = script_dir / 'dist' / 'signups' / 'zachbryan'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / 'zachbryan_config.json'
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        print("Please create zachbryan_config.json with your settings.")
        return
    
    automation = None
    try:
        automation = ZachBryanAutomation(str(config_file))
        automation.run()
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure IMAP scanner is stopped
        if automation and automation.imap_helper:
            automation.imap_helper.stop_background_otp_scanner()


if __name__ == "__main__":
    main()

