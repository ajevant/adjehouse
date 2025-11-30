#!/usr/bin/env python3
"""
Laylo RSVP Automation
=====================
Automates RSVP signup for Laylo events using Dolphin browser profiles.
"""

import sys
import os
import json
import time
import random
import csv
import requests
from pathlib import Path

# Add parent directory to path to import dolphin_base
# Handle both normal execution and PyInstaller EXE execution
if getattr(sys, 'frozen', False):
    # Running as EXE - add the directory where the EXE's extracted files are
    base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
    sys.path.insert(0, str(base_path))
    # Also try the directory where EXE is located (for bundled data files)
    exe_dir = Path(sys.executable).parent
    sys.path.insert(0, str(exe_dir))
else:
    # Running as script - add parent directory
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dolphin_base import DolphinAutomation
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class LayloAutomation(DolphinAutomation):
    """Laylo-specific automation extending DolphinAutomation base"""
    
    def __init__(self, config_file):
        """Initialize with config file"""
        # Load config
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.site_config = json.load(f)
        
        # Debug: Print config structure (hide sensitive data)
        dolphin_config_raw = self.site_config.get('dolphin', {})
        if dolphin_config_raw:
            token_present = bool(dolphin_config_raw.get('token', ''))
            print(f"📋 Config loaded from: {config_path}")
            print(f"📋 Dolphin token present: {token_present}")
            if not token_present:
                print(f"⚠️  Warning: Dolphin token not found in config!")
                print(f"   Config structure: {list(self.site_config.keys())}")
                print(f"   Dolphin keys: {list(dolphin_config_raw.keys())}")
        else:
            print(f"⚠️  Warning: No 'dolphin' section found in config!")
            print(f"   Config structure: {list(self.site_config.keys())}")
        
        # Transform config to match dolphin_base.py expectations
        # dolphin_base expects 'dolphin_token', 'dolphin_remote_api_url', and 'dolphin_api_url' (local)
        dolphin_config = {}
        if dolphin_config_raw:
            if 'token' in dolphin_config_raw:
                dolphin_config['dolphin_token'] = dolphin_config_raw['token']
            if 'remote_api_url' in dolphin_config_raw:
                dolphin_config['dolphin_remote_api_url'] = dolphin_config_raw['remote_api_url']
            elif 'api_url' in dolphin_config_raw:
                # Fallback: if only api_url is set and it's not localhost, use it as remote
                api_url = dolphin_config_raw['api_url']
                if 'localhost' not in api_url and '127.0.0.1' not in api_url:
                    dolphin_config['dolphin_remote_api_url'] = api_url
            if 'local_api_url' in dolphin_config_raw:
                dolphin_config['dolphin_api_url'] = dolphin_config_raw['local_api_url']
            elif 'api_url' in dolphin_config_raw:
                # Fallback: if only api_url is set and it's localhost, use it as local
                api_url = dolphin_config_raw['api_url']
                if 'localhost' in api_url or '127.0.0.1' in api_url:
                    dolphin_config['dolphin_api_url'] = api_url
        
        # Debug: print config being passed to base class
        print(f"🔍 Dolphin config being passed: token={'***' if dolphin_config.get('dolphin_token') else 'MISSING'}, remote_api_url={dolphin_config.get('dolphin_remote_api_url', 'NOT SET')}, local_api_url={dolphin_config.get('dolphin_api_url', 'NOT SET')}")
        
        # Initialize base class with dolphin config
        super().__init__(dolphin_config)
        
        # Debug: verify what was set
        print(f"🔍 Base class initialized: remote_api_url={self.remote_api_url}, local_api_url={self.local_api_url}, token={'***' if self.dolphin_token else 'MISSING'}")
        
        self.site_url = self.site_config.get('site_url', '')
        automation_config = self.site_config.get('automation', {})
        # Ensure threads is an integer (handle string conversion if needed)
        threads_value = automation_config.get('threads', 1)
        self.threads = int(threads_value) if threads_value else 1
        self.max_retries = automation_config.get('max_retries', 3)
        self.timeout = automation_config.get('timeout_seconds', 60)
        self.config_path = config_path
        
        # Debug: verify threads was read correctly
        print(f"🔍 Config loaded - threads: {self.threads} (type: {type(self.threads)}), automation section: {automation_config}")
        
        # Determine base directory for files (same directory as config)
        # Always use config directory (which should be in dist/ when running as script)
        base_dir = config_path.parent
        
        # Ensure directory exists (create if needed)
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Debug: show which directory is being used
        print(f"🔍 Using base directory for files: {base_dir}")
        
        # Load emails from CSV file
        files_config = self.site_config.get('files', {})
        emails_csv = base_dir / files_config.get('emails', 'emails.csv')
        self.emails_csv = emails_csv
        
        # Load emails and filter out already entered ones
        all_emails_data = self._load_emails_from_csv(emails_csv)
        
        # Only use emails that haven't been entered yet (entered = "nee" or empty)
        self.emails = [row['email'] for row in all_emails_data if row.get('entered', '').lower() not in ['ja', 'yes', 'done', 'completed']]
        
        completed_count = len(all_emails_data) - len(self.emails)
        if completed_count > 0:
            print(f"⏭️  Skipping {completed_count} already entered emails")
        if len(self.emails) < len(all_emails_data):
            print(f"📧 {len(self.emails)} emails remaining to process (out of {len(all_emails_data)} total)")
        
        # Load proxy strings from file (lazy loading - create on demand)
        proxies_file = base_dir / files_config.get('proxies', 'proxies.txt')
        self.proxies_file = proxies_file  # Store for later cleanup
        self.proxy_strings = self._load_from_file(proxies_file, "proxies")
        
        if self.proxy_strings:
            print(f"📡 Loaded {len(self.proxy_strings)} proxy strings (will create on demand)")
        else:
            self.proxy_strings = []
            print(f"⚠️  No proxies loaded from {proxies_file}")
        
        # Load Discord webhook URL
        discord_config = self.site_config.get('discord', {})
        self.discord_webhook = discord_config.get('finished_webhook', '')
        
        # Track which proxy strings have been used
        self.used_proxy_strings = set()
        # Track which proxy string was used for each profile (for cleanup)
        self.profile_proxy_string_map = {}  # {profile_id: proxy_string}
        self.profile_proxy_map = {}  # {profile_id: proxy_data}
    
    def create_profile(self, proxy_data=None, name_prefix='LAYLO'):
        """Override create_profile to use lazy proxy creation"""
        # Use our custom proxy getter that creates on demand
        if not proxy_data:
            proxy_data, proxy_string = self._get_or_create_proxy()
            # Store proxy string for cleanup later
            self.profile_proxy_string_map[proxy_data.get('id')] = proxy_string
        
        # Call parent create_profile with the proxy
        profile = super().create_profile(proxy_data=proxy_data, name_prefix=name_prefix)
        
        # Store mapping between profile and proxy for cleanup
        if profile and proxy_data:
            self.profile_proxy_map[profile['id']] = proxy_data
            # Also store proxy string if we have it
            if proxy_data.get('id') in self.profile_proxy_string_map:
                self.profile_proxy_string_map[profile['id']] = self.profile_proxy_string_map[proxy_data.get('id')]
                del self.profile_proxy_string_map[proxy_data.get('id')]  # Remove duplicate entry
        
        return profile
    
    def _process_single_item(self, site_config, data_item, task_number):
        """
        Override to use lazy proxy creation - proxies are created on demand
        """
        profile = None
        driver = None
        
        try:
            # Create profile - our overridden create_profile will handle proxy creation
            profile = self.create_profile(proxy_data=None, name_prefix=f'LAYLO{task_number}')
            if not profile:
                return False
            
            # Create driver
            driver = self.create_driver(profile['id'])
            if not driver:
                return False
            
            # Run site-specific automation
            success = self._execute_site_automation(driver, site_config, data_item, task_number)
            
            # Get proxy info for cleanup
            profile_id = profile['id'] if profile else None
            proxy_data = self.profile_proxy_map.get(profile_id) if profile_id else None
            proxy_string = self.profile_proxy_string_map.get(profile_id) if profile_id else None
            
            # Use base class cleanup method (handles profile and proxy deletion)
            if profile:
                # Use base class cleanup with proxy string file removal
                self._cleanup_profile_and_proxy(
                    profile=profile,
                    proxy=proxy_data,
                    success=success,
                    proxy_string=proxy_string,
                    proxies_file=str(self.proxies_file) if hasattr(self, 'proxies_file') and self.proxies_file else None
                )
            
            # Clean up tracking dictionaries
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
            # Always cleanup driver
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            # Base class cleanup already handles stopping/deleting in _cleanup_profile_and_proxy
            # No additional cleanup needed here
    
    def _get_or_create_proxy(self):
        """Get an unused proxy or create a new one from proxy_strings if needed
        Returns: (proxy_data, proxy_string) tuple where proxy_string can be None if using existing proxy
        """
        # First, try to get an existing unused proxy
        unused_proxy = self.get_random_unused_proxy()
        if unused_proxy:
            return unused_proxy, None  # No proxy string for existing proxies
        
        # No unused proxies available, create a new one from proxy_strings
        if not self.proxy_strings:
            raise Exception("No proxy strings available and no unused proxies found")
        
        # Find a proxy string that hasn't been used yet
        available_strings = [s for s in self.proxy_strings if s not in self.used_proxy_strings]
        
        if not available_strings:
            # All proxy strings have been used, try to reuse them
            print(f"⚠️  All proxy strings used, reusing proxies...")
            available_strings = self.proxy_strings
        
        # Pick a random proxy string
        proxy_string = random.choice(available_strings)
        self.used_proxy_strings.add(proxy_string)
        
        # Parse and create the proxy
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
            
            print(f"📡 Creating new proxy: {parts[0]}:{parts[1]}...")
            created_proxy = self.create_proxy(proxy_data)
            print(f"✅ Proxy created: {created_proxy.get('id')}")
            return created_proxy, proxy_string
            
        except Exception as e:
            print(f"❌ Failed to create proxy from string: {e}")
            # Remove from used set so we can try again
            self.used_proxy_strings.discard(proxy_string)
            raise
    
    # _remove_proxy_string_from_file is now in base class (dolphin_base.py)
    # No need to override unless custom behavior is needed
    
    def _load_from_file(self, file_path, file_type):
        """Load lines from a text file, skipping empty lines and comments"""
        lines = []
        
        if not file_path.exists():
            print(f"⚠️ {file_type.capitalize()} file not found: {file_path}")
            return lines
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    # Skip empty lines and comments (lines starting with #)
                    if line and not line.startswith('#'):
                        lines.append(line)
            
            print(f"✅ Loaded {len(lines)} {file_type} from {file_path.name}")
            return lines
            
        except Exception as e:
            print(f"❌ Error loading {file_type} from {file_path}: {e}")
            return lines
    
    def _load_emails_from_csv(self, csv_file):
        """Load emails from CSV file with entered status"""
        emails_data = []
        
        if not csv_file.exists():
            # If CSV doesn't exist, try to load from old emails.txt and convert
            txt_file = csv_file.parent / 'emails.txt'
            if txt_file.exists():
                print(f"📝 Converting emails.txt to emails.csv...")
                all_emails = self._load_from_file(txt_file, "emails")
                # Create CSV from txt file
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['email', 'entered', 'timestamp'])  # Header
                    for email in all_emails:
                        writer.writerow([email, 'nee', ''])  # All new emails
                print(f"✅ Created emails.csv with {len(all_emails)} emails")
                return [{'email': email, 'entered': 'nee', 'timestamp': ''} for email in all_emails]
            else:
                print(f"⚠️ Emails CSV file not found: {csv_file}")
                return emails_data
        
        try:
            with open(csv_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = row.get('email', '').strip()
                    if email and '@' in email:
                        emails_data.append({
                            'email': email,
                            'entered': row.get('entered', 'nee').strip().lower(),
                            'timestamp': row.get('timestamp', '').strip()
                        })
            
            print(f"✅ Loaded {len(emails_data)} emails from {csv_file.name}")
            return emails_data
            
        except Exception as e:
            print(f"❌ Error loading emails from CSV: {e}")
            return emails_data
    
    def _mark_email_entered(self, email):
        """Mark an email as entered in the CSV file - writes immediately to disk"""
        try:
            if not self.emails_csv.exists():
                print(f"⚠️ CSV file not found: {self.emails_csv}")
                return
            
            # Read all rows
            rows = []
            fieldnames = None
            with open(self.emails_csv, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or ['email', 'entered', 'timestamp']
                for row in reader:
                    if row.get('email', '').strip().lower() == email.lower():
                        # Update this email's status
                        row['entered'] = 'ja'
                        row['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"💾 Marking {email} as entered - updating CSV immediately...")
                    rows.append(row)
            
            # Write back to CSV with immediate flush
            with open(self.emails_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                # Force flush to disk immediately
                f.flush()
                os.fsync(f.fileno())  # Force OS to write to disk
            
            print(f"✅ CSV updated: {email} marked as entered")
            
        except Exception as e:
            print(f"⚠️ Error marking email as entered: {e}")
    
    def _send_discord_notification(self, email, success=True):
        """Send Discord webhook notification when signup is finished"""
        if not self.discord_webhook:
            return
        
        try:
            if success:
                message = {
                    "content": f"✅ **Laylo Signup Finished**\n📧 Email: `{email}`\n🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "username": "Laylo Automation"
                }
            else:
                message = {
                    "content": f"❌ **Laylo Signup Failed**\n📧 Email: `{email}`\n🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "username": "Laylo Automation"
                }
            
            response = requests.post(self.discord_webhook, json=message, timeout=10)
            if response.status_code == 204:
                print(f"📢 Discord notification sent for {email}")
            else:
                print(f"⚠️ Discord webhook returned status {response.status_code}")
        
        except Exception as e:
            print(f"⚠️ Error sending Discord notification: {e}")
    
    def _execute_site_automation(self, driver, site_config, data_item, task_number):
        """
        Execute Laylo RSVP automation
        data_item: email address string
        """
        email = data_item
        print(f"\n🎯 [TASK-{task_number}] Starting Laylo RSVP for {email}")
        
        try:
            # Step 1: Navigate to site
            print(f"[TASK-{task_number}] 📍 Navigating to site...")
            driver.get(self.site_url)
            
            # Wait for page load with human-like behavior
            time.sleep(random.uniform(2, 4))
            
            # Simulate human behavior on page load
            self.human_scroll(driver, scroll_count=random.randint(2, 4))
            self.random_mouse_movement(driver)
            self.simulate_akamai_behavior(driver, duration=random.uniform(2, 4))
            
            # Step 2: Wait for and click EMAIL toggle button
            print(f"[TASK-{task_number}] 📧 Looking for EMAIL toggle button...")
            
            # Multiple selectors to try (voor robuustheid)
            email_toggle_selectors = [
                "button[aria-label='RSVP by EMAIL']",
                "button[value='EMAIL']",
                "button.MuiToggleButton[value='EMAIL']",
                "button[aria-label*='EMAIL']",
                "button[type='button'][value='EMAIL']"
            ]
            
            email_toggle = None
            for selector in email_toggle_selectors:
                try:
                    email_toggle = WebDriverWait(driver, self.timeout).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if email_toggle and email_toggle.is_displayed():
                        print(f"[TASK-{task_number}] ✅ Found EMAIL toggle with selector: {selector}")
                        break
                except TimeoutException:
                    continue
            
            if not email_toggle:
                # Fallback: try to find by text content and attributes
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        aria_label = btn.get_attribute('aria-label') or ''
                        value = btn.get_attribute('value') or ''
                        if 'EMAIL' in aria_label.upper() or value == 'EMAIL':
                            if btn.is_displayed():
                                email_toggle = btn
                                break
                except Exception as e:
                    print(f"[TASK-{task_number}] ⚠️ Fallback search error: {e}")
                    pass
            
            if not email_toggle:
                raise Exception("Could not find EMAIL toggle button")
            
            # Human-like click on EMAIL toggle
            print(f"[TASK-{task_number}] 🖱️ Clicking EMAIL toggle button...")
            
            # Scroll to element first
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", email_toggle)
            time.sleep(random.uniform(0.3, 0.6))
            
            self.human_click(driver, email_toggle)
            
            # Wait a bit after clicking toggle
            time.sleep(random.uniform(0.5, 1.5))
            
            # Step 3: Find and fill email input
            print(f"[TASK-{task_number}] ✉️ Looking for email input field...")
            
            email_input_selectors = [
                "input[name='email']",
                "input[id*='email']",
                "input[placeholder*='email' i]",
                "input[placeholder*='Your email']",
                "input[type='email']",
                "input[type='text'][name='email']"
            ]
            
            email_input = None
            for selector in email_input_selectors:
                try:
                    email_input = WebDriverWait(driver, self.timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if email_input and email_input.is_displayed():
                        print(f"[TASK-{task_number}] ✅ Found email input with selector: {selector}")
                        break
                except TimeoutException:
                    continue
            
            if not email_input:
                # Fallback: find by placeholder text
                try:
                    inputs = driver.find_elements(By.TAG_NAME, "input")
                    for inp in inputs:
                        placeholder = inp.get_attribute('placeholder') or ''
                        name = inp.get_attribute('name') or ''
                        if 'email' in placeholder.lower() or 'email' in name.lower():
                            email_input = inp
                            break
                except:
                    pass
            
            if not email_input:
                raise Exception("Could not find email input field")
            
            # Human-like typing in email field
            print(f"[TASK-{task_number}] ⌨️ Filling email address...")
            
            # Scroll to element
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", email_input)
            time.sleep(random.uniform(0.3, 0.6))
            
            # Click on input first
            self.human_click(driver, email_input)
            time.sleep(random.uniform(0.2, 0.4))
            
            # Clear any existing value
            email_input.clear()
            time.sleep(random.uniform(0.1, 0.2))
            
            # Type email with human-like behavior
            self.human_type(email_input, email)
            
            # Trigger input/change events
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", email_input)
            
            time.sleep(random.uniform(0.5, 1.0))
            
            # Step 4: Find and click RSVP submit button
            print(f"[TASK-{task_number}] 📤 Looking for RSVP submit button...")
            
            rsvp_button_selectors = [
                "button[type='submit'][name='rsvp']",
                "button.laylo-rsvp-submit-button",
                "button[alt='Confirm RSVP']",
                "button[title='Confirm RSVP']",
                "button.MuiButton-contained[name='rsvp']",
                "button[type='submit']"
            ]
            
            rsvp_button = None
            for selector in rsvp_button_selectors:
                try:
                    rsvp_button = WebDriverWait(driver, self.timeout).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if rsvp_button and rsvp_button.is_displayed():
                        # Check if button text contains RSVP
                        button_text = rsvp_button.text or ''
                        if 'RSVP' in button_text.upper():
                            print(f"[TASK-{task_number}] ✅ Found RSVP button with selector: {selector}")
                            break
                        else:
                            rsvp_button = None
                            continue
                except TimeoutException:
                    continue
            
            if not rsvp_button:
                # Fallback: find by text content using XPath
                try:
                    rsvp_button = driver.find_element(By.XPATH, "//button[contains(text(), 'RSVP')]")
                    if rsvp_button and rsvp_button.is_displayed():
                        print(f"[TASK-{task_number}] ✅ Found RSVP button via XPath")
                except:
                    # Try all buttons
                    try:
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        for btn in buttons:
                            if not btn.is_displayed():
                                continue
                            text = btn.text or ''
                            alt = btn.get_attribute('alt') or ''
                            title = btn.get_attribute('title') or ''
                            name = btn.get_attribute('name') or ''
                            if 'RSVP' in text.upper() or 'Confirm RSVP' in alt or 'Confirm RSVP' in title or name == 'rsvp':
                                rsvp_button = btn
                                print(f"[TASK-{task_number}] ✅ Found RSVP button via text/attribute search")
                                break
                    except Exception as e:
                        print(f"[TASK-{task_number}] ⚠️ Fallback search error: {e}")
                        pass
            
            if not rsvp_button:
                raise Exception("Could not find RSVP submit button")
            
            # Human-like click on RSVP button
            print(f"[TASK-{task_number}] 🖱️ Clicking RSVP submit button...")
            
            # Scroll to element first
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", rsvp_button)
            time.sleep(random.uniform(0.3, 0.6))
            
            self.human_click(driver, rsvp_button)
            
            # Step 5: Wait for success confirmation
            print(f"[TASK-{task_number}] ⏳ Waiting for confirmation page...")
            
            # Custom wait function for text content
            def check_confirmation(driver):
                try:
                    # Check for h6 elements with "Check your email" text
                    h6_elements = driver.find_elements(By.TAG_NAME, "h6")
                    for h6 in h6_elements:
                        text = h6.text or ''
                        if 'Check your email' in text or 'check your email' in text.lower():
                            return True
                    
                    # Try XPath search
                    try:
                        confirmation = driver.find_element(By.XPATH, "//h6[contains(text(), 'Check your email')]")
                        if confirmation and confirmation.is_displayed():
                            return True
                    except:
                        pass
                    
                    # Also check page source for confirmation text
                    page_source = driver.page_source
                    if 'check your email' in page_source.lower():
                        return True
                    
                    return False
                except:
                    return False
            
            # Wait up to timeout for confirmation
            confirmation_found = False
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                if check_confirmation(driver):
                    confirmation_found = True
                    break
                time.sleep(1)
                
                # Also check if page changed (redirect happened)
                current_url = driver.current_url
                if current_url != self.site_url:
                    # Page redirected, check for confirmation on new page
                    time.sleep(random.uniform(2, 4))
                    if check_confirmation(driver):
                        confirmation_found = True
                        break
            
            if confirmation_found:
                print(f"[TASK-{task_number}] ✅ SUCCESS! Confirmation page detected - RSVP completed for {email}")
                
                # Mark email as entered in CSV
                self._mark_email_entered(email)
                
                # Send Discord notification
                self._send_discord_notification(email, success=True)
                
                # Small human-like behavior before finishing
                time.sleep(random.uniform(1, 2))
                self.random_mouse_movement(driver)
                
                return True
            else:
                print(f"[TASK-{task_number}] ⚠️ Warning: Could not confirm success, but continuing...")
                # Still return True as button was clicked successfully
                # Mark as entered anyway since button was clicked
                self._mark_email_entered(email)
                
                # Send Discord notification (assume success since button was clicked)
                self._send_discord_notification(email, success=True)
                
                return True
                
        except Exception as e:
            print(f"[TASK-{task_number}] ❌ Error during RSVP: {e}")
            import traceback
            traceback.print_exc()
            
            # Send Discord notification for failure
            self._send_discord_notification(email, success=False)
            
            return False
    
    def run(self):
        """Run the Laylo automation"""
        print(f"\n🚀 Starting Laylo RSVP Automation")
        print(f"📧 Emails: {len(self.emails)}")
        print(f"🧵 Threads: {self.threads}")
        print(f"🌐 Site: {self.site_url}\n")
        
        if not self.emails:
            print("❌ No emails provided in config!")
            return
        
        # Run automation using base class method
        site_config = {
            'name': 'Laylo',
            'url': self.site_url
        }
        
        # Set proxies to empty list since we use lazy loading
        self.proxies = []
        
        # Run automation - will use our overridden create_profile with lazy proxy creation
        self.run_automation(site_config, self.emails, threads=self.threads)


def main():
    """Main entry point"""
    # Get config file path - handle both script and EXE execution
    if getattr(sys, 'frozen', False):
        # Running as EXE - always look in directory where EXE is located
        # This allows users to put the EXE anywhere and it will use that directory
        exe_dir = Path(sys.executable).parent
        config_dir = exe_dir / 'signups' / 'laylo'
        
        # Create directory structure if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / 'laylo_config.json'
        
        # If config doesn't exist in standard location, check bundled data as fallback
        if not config_file.exists() and hasattr(sys, '_MEIPASS'):
            bundled_config = Path(sys._MEIPASS) / 'signups' / 'laylo' / 'laylo_config.json'
            if bundled_config.exists():
                # Copy from bundled data to EXE directory
                print(f"📋 Copying config from bundled data to: {config_file}")
                import shutil
                shutil.copy2(bundled_config, config_file)
    else:
        # Running as script - always look in dist/signups/laylo/ (not in source signups/)
        script_dir = Path(__file__).parent.parent.parent  # Go up from signups/laylo/ to project root
        config_dir = script_dir / 'dist' / 'signups' / 'laylo'
        config_dir.mkdir(parents=True, exist_ok=True)  # Create if doesn't exist
        config_file = config_dir / 'laylo_config.json'
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        print("Please create laylo_config.json with your settings.")
        print(f"   Expected location: {config_file}")
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            print(f"   For EXE, place it at: {exe_dir / 'signups' / 'laylo' / 'laylo_config.json'}")
            print(f"   The directory will be created automatically if it doesn't exist.")
        return
    
    try:
        automation = LayloAutomation(str(config_file))
        automation.run()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

