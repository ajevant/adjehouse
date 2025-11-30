#!/usr/bin/env python3
"""
Portugal FPF Registration Automation
====================================
Automates registration for Portugal FPF using Dolphin browser profiles.
Includes IMAP email verification code handling.
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
import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from email.header import decode_header
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

# Add parent directory to path to import dolphin_base
if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
    sys.path.insert(0, str(base_path))
    exe_dir = Path(sys.executable).parent
    sys.path.insert(0, str(exe_dir))
else:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dolphin_base import DolphinAutomation
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException, NoSuchElementException, NoSuchWindowException, InvalidSessionIdException

# Capsolver/Turnstile code verwijderd - we gebruiken direct refresh in plaats daarvan


def random_delay(min_seconds: float, max_seconds: float) -> None:
    """Sleep for a random duration between the given bounds (geoptimaliseerd: 50% sneller)."""
    # Verklein alle delays met 50% voor sneller script
    time.sleep(random.uniform(min_seconds * 0.5, max_seconds * 0.5))


class IMAPHelper:
    """Helper class for IMAP email verification code extraction"""
    
    def __init__(self, imap_config: Dict[str, Any]):
        self.email = imap_config.get('email', '')
        self.password = imap_config.get('password', '')
        self.server = imap_config.get('server', 'imap.gmail.com')
        self.port = imap_config.get('port', 993)
        self.folder = imap_config.get('folder', 'INBOX')
        self.subject_phrase = imap_config.get('subject_phrase', 'Código de verificação')
        self.timeout = imap_config.get('code_timeout_seconds', 600)  # 10 minuten (mails kunnen delayed zijn)
        self.poll_interval = imap_config.get('code_poll_interval', 3)  # 3 seconden is redelijk (niet te snel, niet te langzaam)
        
        # OTP Cache: {target_email: {'code': code, 'timestamp': datetime, 'email_id': email_id}}
        self.otp_cache = {}
        self.otp_cache_lock = threading.Lock()
        self.scanned_email_ids = set()  # Track welke emails we al gescand hebben
        
        # Background scanner control
        self.scanner_running = False
        self.scanner_thread = None
    
    def start_background_otp_scanner(self, scan_interval: int = 120):
        """Start background thread that scans OTP emails every 2 minutes (default)"""
        if self.scanner_running:
            return
        
        self.scanner_running = True
        self.scanner_thread = threading.Thread(
            target=self._background_otp_scanner,
            args=(scan_interval,),
            daemon=True,
            name="OTPScanner"
        )
        self.scanner_thread.start()
        print(f"🔄 OTP background scanner gestart (scant elke {scan_interval}s)...")
    
    def stop_background_otp_scanner(self):
        """Stop background OTP scanner"""
        self.scanner_running = False
        if self.scanner_thread:
            self.scanner_thread.join(timeout=5)
        print("🛑 OTP background scanner gestopt")
    
    def _background_otp_scanner(self, scan_interval: int):
        """Background proces dat continu OTP emails scant en cached (zoals fan number scanner)"""
        while self.scanner_running:
            try:
                # Scan alle OTP emails van vandaag
                since_date = datetime.now().strftime('%d-%b-%Y')  # Alleen vandaag
                expected_sender = "no-reply@fpf.pt"
                expected_subject = "Código de verificação"
                
                with imaplib.IMAP4_SSL(self.server, self.port) as M:
                    M.login(self.email, self.password)
                    M.select(self.folder)
                    
                    # Search voor alle emails van vandaag - GEEN FROM filter (sender kan variëren)
                    # We filteren op subject "Código de verificação" in Python
                    search_criteria = f'SINCE "{since_date}"'
                    
                    try:
                        status, messages = M.search(None, search_criteria)
                    except UnicodeEncodeError:
                        # Fallback zonder subject filter
                        search_criteria = f'FROM "{expected_sender}" SINCE "{since_date}"'
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
                                
                                # Get headers
                                from_header = self.decode_str(msg.get('From', ''))
                                subject = self.decode_str(msg.get('Subject', ''))
                                to_header = self.decode_str(msg.get('To', ''))
                                cc_header = self.decode_str(msg.get('Cc', ''))
                                bcc_header = self.decode_str(msg.get('Bcc', ''))
                                
                                # Filter ALLEEN op subject (sender kan variëren, maar subject blijft hetzelfde)
                                if expected_subject.lower() not in subject.lower():
                                    continue
                                
                                # Extract recipient emails
                                def extract_emails(header_text):
                                    if not header_text:
                                        return []
                                    emails = []
                                    email_pattern = r'<([^>]+@[^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                                    matches = re.finditer(email_pattern, header_text)
                                    for match in matches:
                                        email_addr = match.group(1) or match.group(2)
                                        if email_addr:
                                            emails.append(email_addr.lower().strip())
                                    return emails
                                
                                all_recipient_emails = []
                                all_recipient_emails.extend(extract_emails(to_header))
                                all_recipient_emails.extend(extract_emails(cc_header))
                                all_recipient_emails.extend(extract_emails(bcc_header))
                                
                                if not all_recipient_emails:
                                    continue
                                
                                # Extract OTP code from email body
                                html_body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/html":
                                            payload = part.get_payload(decode=True)
                                            if payload:
                                                html_body = payload.decode('utf-8', errors='ignore')
                                                break
                                else:
                                    if msg.get_content_type() == "text/html":
                                        payload = msg.get_payload(decode=True)
                                        if payload:
                                            html_body = payload.decode('utf-8', errors='ignore')
                                
                                # Extract code from HTML body
                                code = None
                                if html_body:
                                    try:
                                        from lxml import html as lxml_html
                                        doc = lxml_html.fromstring(html_body)
                                        xpath_patterns = [
                                            '//span[contains(text(), "O seu código é")]',
                                            '//span[contains(text(), "código é")]',
                                            '//div[contains(@id, "avWBGd")]//span[contains(text(), "código")]',
                                            '//span[contains(., "código")]',
                                        ]
                                        for xpath in xpath_patterns:
                                            try:
                                                elements = doc.xpath(xpath)
                                                if elements:
                                                    for elem in elements:
                                                        text = elem.text_content() if hasattr(elem, 'text_content') else str(elem)
                                                        match = re.search(r'código é:\s*(\d+)', text, re.IGNORECASE)
                                                        if match:
                                                            code = match.group(1).strip()
                                                            if len(code) >= 5:
                                                                break
                                            except:
                                                continue
                                    except:
                                        pass
                                
                                # Fallback: regex patterns
                                if not code:
                                    code_patterns = [
                                        r'<span[^>]*>O seu código é:\s*(\d+)\s*</span>',
                                        r'O seu código é:\s*(\d+)',
                                        r'código é:\s*(\d+)',
                                        r'código:\s*(\d+)',
                                    ]
                                    search_body = html_body if html_body else self.get_body_text(msg)
                                    for pattern in code_patterns:
                                        match = re.search(pattern, search_body, re.IGNORECASE)
                                        if match:
                                            code = match.group(1).strip()
                                            if len(code) >= 5:
                                                break
                                
                                # Cache OTP voor alle recipients
                                if code and len(code) >= 5:
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
                                                    'code': code,
                                                    'timestamp': datetime.now(),
                                                    'email_id': email_id_str
                                                }
                                                new_cached_count += 1
                                
                            except Exception as e:
                                # Silently skip errors
                                continue
                        
                        if new_cached_count > 0:
                            print(f"✅ [OTP Scanner] {new_cached_count} nieuwe OTP code(s) gecached")
                    
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
    
    def get_body_text(self, msg):
        """Extract text from email body"""
        text = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='ignore')
                            # Simple HTML to text conversion (keep it simple)
                            text += body
                    except:
                        pass
                elif content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            text += payload.decode('utf-8', errors='ignore')
                    except:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    text = payload.decode('utf-8', errors='ignore')
            except:
                pass
        return text
    
    def extract_verification_code(self, target_email: str, start_time: datetime) -> Optional[str]:
        """Extract verification code from email - check eerst cache, dan IMAP"""
        import time as time_module
        
        if not target_email:
            print("      ❌ Fout: target_email is leeg bij aanroep extract_verification_code!")
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
                        print(f"      ⏳ Cache entry verouderd, opnieuw scannen...")
            else:
                # Debug: log wat er wel in de cache zit om te zien waarom we missen
                # (alleen de keys loggen om privacy te bewaken, en alleen als er iets in zit)
                if self.otp_cache:
                    pass # print(f"      ℹ️ Cache miss voor {target_email_normalized}. Beschikbaar in cache: {list(self.otp_cache.keys())}")
        
        # GEEN OTP IN CACHE - scan IMAP (met cache update)
        try:
            print(f"      🔐 IMAP verbinden met {self.server}:{self.port}...")
            with imaplib.IMAP4_SSL(self.server, self.port) as M:
                print(f"      🔐 IMAP login met {self.email}...")
                M.login(self.email, self.password)
                print(f"      ✓ IMAP login succesvol")
                
                M.select(self.folder)
                print(f"      ✓ Folder {self.folder} geselecteerd")
                
                expected_sender = "no-reply@fpf.pt"
                expected_subject = "Código de verificação"
                
                print(f"      🔍 Zoeken naar email met titel '{expected_subject}' van {expected_sender} naar {target_email}...")
                
                elapsed = 0
                poll_count = 0
                
                # Start with faster polling for first 30 seconds (email usually arrives quickly)
                fast_poll_interval = 1.0  # Poll elke 1 seconde (snel voor snelle OTP detectie)
                normal_poll_interval = 2.0  # Normale poll interval (2 seconden is redelijk snel)
                fast_poll_duration = 30  # Use fast polling for first 30 seconds
                
                while elapsed < self.timeout:
                    poll_count += 1
                    
                    # Use faster polling for first 30 seconds
                    current_poll_interval = fast_poll_interval if elapsed < fast_poll_duration else normal_poll_interval
                    
                    # Refresh inbox periodiek om cache te doorbreken (niet bij elke poll - te veel overhead)
                    try:
                        # Refresh elke 3 polls (sneller dan elke 5, maar niet te veel overhead)
                        if poll_count % 3 == 1 or elapsed < 10:
                            print(f"      🔄 Refreshing inbox (poll #{poll_count})...")
                        # Refresh inbox: close + reopen folder selectie (doorbreekt cache)
                        try:
                            M.close()
                        except:
                            pass
                        M.select(self.folder)  # Fresh folder selection = ziet nieuwe emails direct!
                    except Exception as e:
                        # Als refresh faalt, probeer volledige reconnect
                        try:
                            M.logout()
                            M.login(self.email, self.password)
                            M.select(self.folder)
                        except:
                            pass  # Als alles faalt, ga gewoon door
                    
                    # Only print every 3rd poll to reduce spam (maar toch snel pollen)
                    if poll_count % 3 == 1 or elapsed < 10:
                        print(f"      🔄 Poll #{poll_count} (elapsed: {elapsed}s/{self.timeout}s, poll elke {current_poll_interval:.1f}s)...")
                    
                    # Optimized search: filter op TO recipient en subject DIRECT in IMAP search (veel sneller!)
                    # Check alleen vandaag (OTP wordt direct verzonden)
                    since_date = datetime.now().strftime('%d-%b-%Y')  # Alleen vandaag!
                    
                    # GEEN FROM filter meer - sender kan variëren! Alleen op SUBJECT filteren in Python
                    # We halen alle emails van vandaag op en filteren dan op subject "Código de verificação"
                    search_criteria = f'SINCE "{since_date}"'
                    
                    try:
                        try:
                            status, messages = M.search(None, search_criteria)
                        except UnicodeEncodeError as e:
                            # Fallback (zou niet nodig moeten zijn zonder subject/to)
                            if poll_count == 1:
                                print(f"      ⚠️ IMAP encoding error: {e}")
                            status, messages = M.search(None, search_criteria)
                        
                        if status != 'OK' or not messages[0]:
                            # Als geen email gevonden, refresh inbox opnieuw en probeer nog een keer
                            if poll_count % 3 == 1 or elapsed < 10:
                                print(f"      📭 Nog geen emails gevonden, refreshing inbox en opnieuw proberen...")
                            try:
                                M.close()
                                M.select(self.folder)  # Refresh inbox
                            except:
                                pass
                            
                            # Probeer nog een keer met refreshed inbox
                            status, messages = M.search(None, search_criteria)
                            if status != 'OK' or not messages[0]:
                                # Als nog steeds niets, wacht en ga door naar volgende poll
                                if poll_count % 3 == 1 or elapsed < 10:
                                    print(f"      📭 Nog steeds geen emails gevonden, wachten...")
                                time_module.sleep(current_poll_interval)
                                elapsed += current_poll_interval
                                continue
                        
                        email_ids = messages[0].split()
                        if poll_count % 3 == 1 or elapsed < 10:
                            print(f"      📧 {len(email_ids)} email(s) gevonden, check nieuwste eerst...")
                        
                        # Get all emails sorted by UID (newest last in IMAP, so reverse)
                        # Process from newest to oldest (reverse order) - STOP BIJ EERSTE MATCH!
                        sorted_email_ids = list(reversed(email_ids))
                        
                        # Process emails from newest to oldest - STOP DIRECT bij eerste OTP!
                        for email_id in sorted_email_ids:
                            try:
                                status, msg_data = M.fetch(email_id, '(RFC822)')
                                if status != 'OK':
                                    continue
                                
                                msg = email.message_from_bytes(msg_data[0][1])
                                
                                # Get headers
                                from_header = self.decode_str(msg.get('From', ''))
                                to_header = self.decode_str(msg.get('To', ''))
                                cc_header = self.decode_str(msg.get('Cc', ''))
                                bcc_header = self.decode_str(msg.get('Bcc', ''))
                                subject = self.decode_str(msg.get('Subject', ''))
                                
                                # Filter ALLEEN op subject (sender kan variëren, maar subject blijft hetzelfde)
                                if expected_subject.lower() not in subject.lower():
                                    continue
                                
                                # Extract email addresses from To/Cc/Bcc headers (voor dubbele check)
                                def extract_emails(header_text):
                                    """Extract all email addresses from header text"""
                                    if not header_text:
                                        return []
                                    emails = []
                                    # Find all email patterns: <email@domain.com> or email@domain.com
                                    email_pattern = r'<([^>]+@[^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                                    matches = re.finditer(email_pattern, header_text)
                                    for match in matches:
                                        email = match.group(1) or match.group(2)
                                        if email:
                                            emails.append(email.lower().strip())
                                    return emails
                                
                                # Extract email addresses from headers
                                all_recipient_emails = []
                                all_recipient_emails.extend(extract_emails(to_header))
                                all_recipient_emails.extend(extract_emails(cc_header))
                                all_recipient_emails.extend(extract_emails(bcc_header))
                                
                                # Normalize target email (lowercase, strip, remove dots for Gmail comparison)
                                target_email_lower = target_email.lower().strip()
                                target_email_normalized = target_email_lower.replace('.', '').split('@')[0] if '@gmail.com' in target_email_lower else target_email_lower
                                
                                # Check if target email matches any recipient (with Gmail dot-ignoring)
                                email_matches = False
                                for recipient in all_recipient_emails:
                                    recipient_normalized = recipient.replace('.', '').split('@')[0] if '@gmail.com' in recipient else recipient
                                    # Exact match or Gmail dot-normalized match
                                    if (target_email_lower == recipient.lower() or 
                                        (target_email_normalized == recipient_normalized and 
                                         ('@gmail.com' in target_email_lower and '@gmail.com' in recipient.lower()))):
                                        email_matches = True
                                        break
                                
                                if not email_matches:
                                    continue  # Skip silently if recipient doesn't match
                                
                                print(f"      ✅ OTP email gevonden! Van: {from_header[:50]}..., To: {to_header[:50]}..., Subject: '{subject}'")
                                
                                # Extract verification code from email body
                                # OOK CACHEN voor andere email adressen die hetzelfde nodig hebben!
                                body = self.get_body_text(msg)
                                
                                # Also try to get HTML body specifically for better pattern matching
                                html_body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/html":
                                            payload = part.get_payload(decode=True)
                                            if payload:
                                                html_body = payload.decode('utf-8', errors='ignore')
                                                break
                                else:
                                    if msg.get_content_type() == "text/html":
                                        payload = msg.get_payload(decode=True)
                                        if payload:
                                            html_body = payload.decode('utf-8', errors='ignore')
                                
                                # Use HTML body if available, otherwise use text body
                                search_body = html_body if html_body else body
                                
                                print(f"      🔍 Zoeken naar verificatie code in email body...")
                                
                                # Try multiple patterns to find the verification code
                                if html_body:
                                    try:
                                        from lxml import html as lxml_html
                                        doc = lxml_html.fromstring(html_body)
                                        
                                        # Try the specific XPath first: //*[@id="avWBGd-1427"]/div[1]/table/tbody/tr/td/table/tbody/tr[2]/td/table/tbody/tr/td/div[2]/span
                                        # But the ID is dynamic, so try pattern matching
                                        xpath_patterns = [
                                            '//span[contains(text(), "O seu código é")]',
                                            '//span[contains(text(), "código é")]',
                                            '//div[contains(@id, "avWBGd")]//span[contains(text(), "código")]',
                                            '//span[contains(., "código")]',
                                        ]
                                        
                                        for xpath in xpath_patterns:
                                            try:
                                                elements = doc.xpath(xpath)
                                                if elements:
                                                    for elem in elements:
                                                        text = elem.text_content() if hasattr(elem, 'text_content') else str(elem)
                                                        match = re.search(r'código é:\s*(\d+)', text, re.IGNORECASE)
                                                        if match:
                                                            code = match.group(1).strip()
                                                            if len(code) >= 5:
                                                                # Cache voor alle recipients in deze email
                                                                with self.otp_cache_lock:
                                                                    for recipient in all_recipient_emails:
                                                                        recipient_normalized = recipient.lower().strip()
                                                                        # Normalize Gmail addresses (dots don't matter)
                                                                        if '@gmail.com' in recipient_normalized:
                                                                            recipient_normalized = recipient_normalized.replace('.', '').split('@')[0] + '@gmail.com'
                                                                        self.otp_cache[recipient_normalized] = {
                                                                            'code': code,
                                                                            'timestamp': datetime.now(),
                                                                            'email_id': email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                                                                        }
                                                                print(f"      ✅ OTP GEVONDEN! Code: {code}")
                                                                return code  # DIRECT STOPPEN!
                                            except:
                                                continue
                                    except Exception as e:
                                        print(f"      ⚠️ XPath parsing error: {e}")
                                
                                # Look for code pattern in HTML: <span>O seu código é: 89582 </span>
                                # Or in text: "O seu código é: 75557" or similar
                                code_patterns = [
                                    r'<span[^>]*>O seu código é:\s*(\d+)\s*</span>',  # HTML span pattern (most specific)
                                    r'O seu código é:\s*(\d+)',  # Text pattern
                                    r'código é:\s*(\d+)',
                                    r'código:\s*(\d+)',
                                    r'verification code:\s*(\d+)',
                                    r'code:\s*(\d+)',
                                    r'(\d{5,6})',  # Fallback: 5-6 digit code (last resort)
                                ]
                                
                                for pattern in code_patterns:
                                    match = re.search(pattern, search_body, re.IGNORECASE)
                                    if match:
                                        code = match.group(1).strip()
                                        if len(code) >= 5:  # Valid code should be at least 5 digits
                                            # Cache voor alle recipients in deze email
                                            with self.otp_cache_lock:
                                                for recipient in all_recipient_emails:
                                                    recipient_normalized = recipient.lower().strip()
                                                    # Normalize Gmail addresses (dots don't matter)
                                                    if '@gmail.com' in recipient_normalized:
                                                        recipient_normalized = recipient_normalized.replace('.', '').split('@')[0] + '@gmail.com'
                                                    self.otp_cache[recipient_normalized] = {
                                                        'code': code,
                                                        'timestamp': datetime.now(),
                                                        'email_id': email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                                                    }
                                            print(f"      ✅ OTP GEVONDEN! Code: {code}")
                                            return code  # DIRECT STOPPEN - geen verdere emails checken!
                                
                                # Als geen code gevonden in deze email, ga door naar volgende
                                # (maar we hebben al gecheckt of het de juiste email is, dus dit zou niet moeten gebeuren)
                            
                            except Exception as e:
                                print(f"      ⚠️ Fout bij verwerken van email {email_id}: {e}")
                                import traceback
                                traceback.print_exc()
                                continue  # Try next email
                    
                    except Exception as e:
                        print(f"      ⚠️ Fout bij IMAP search: {e}")
                        time_module.sleep(current_poll_interval)
                        elapsed += current_poll_interval
                        continue
                    
                    # Wait before next poll
                    if elapsed < self.timeout - current_poll_interval:
                        time_module.sleep(current_poll_interval)
                    elapsed += current_poll_interval
                
                print(f"      ⚠️ Geen verificatie code gevonden binnen {self.timeout} seconden na {poll_count} polls")
                return None
                
        except Exception as e:
            print(f"      ❌ IMAP error: {e}")
            import traceback
            traceback.print_exc()
            return None


class PortugalFPFAutomation(DolphinAutomation):
    """Portugal FPF-specific automation extending DolphinAutomation base"""
    
    def __init__(self, config_file):
        """Initialize with config file"""
        # Load config
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.site_config = json.load(f)
        
        # Auto-migrate config: add missing new fields
        self._migrate_config(config_path)
        
        print(f"📋 Config loaded from: {config_path}")
        
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
        
        # Initialize base class
        super().__init__(dolphin_config)
        
        self.site_url = self.site_config.get('site_url', '')
        automation_config = self.site_config.get('automation', {})
        self.threads = int(automation_config.get('threads', 1))
        self.timeout_seconds = automation_config.get('timeout_seconds', 45)
        self.default_password = automation_config.get('default_password', '#Sara3105')
        
        # Stop mechanism: threading.Event to signal threads to stop
        self.stop_event = threading.Event()
        self.stop_keyboard_thread = None
        
        # Event to signal when a fan number is found (for immediate signup start)
        self.fan_number_found_event = threading.Event()
        
        # IMAP helper and config
        imap_config = self.site_config.get('imap', {})
        self.imap_helper = IMAPHelper(imap_config)
        self.imap_config = imap_config
        self.imap_email = imap_config.get('email', '')
        self.imap_password = imap_config.get('password', '')
        
        # Start background OTP scanner (elke 10 seconden voor snelle detectie)
        otp_scan_interval = imap_config.get('otp_scan_interval', 10)  # Default 10 seconden
        self.imap_helper.start_background_otp_scanner(scan_interval=otp_scan_interval)
        
        # Capsolver/Turnstile code verwijderd - we gebruiken direct refresh
        
        # Files
        files_config = self.site_config.get('files', {})
        config_dir = config_path.parent
        self.accounts_file = config_dir / files_config.get('accounts', 'accounts.csv')
        self.proxies_file = config_dir / files_config.get('proxies', 'proxies.txt')
        
        # Load proxy strings from file (lazy loading)
        self.proxy_strings = self._load_from_file(self.proxies_file, 'proxies')
        self.used_proxy_strings = set()
        # Track which proxy string was used for each profile (for cleanup)
        self.profile_proxy_string_map = {}  # {profile_id: proxy_string}
        self.profile_proxy_map = {}  # {profile_id: proxy_data}
        
        # Used phone numbers tracking (to ensure unique phone numbers)
        self.used_phone_numbers = set()
        
        # Profile activity tracking for automatic cleanup
        self.profile_last_activity = {}  # {profile_id: timestamp}
        self.profile_cleaner_running = True
        
        # CSV lock for thread-safe operations (prevent data loss from concurrent writes)
        self.csv_lock = threading.Lock()
        
        # Start background fan number scanner in a daemon thread
        self.fan_number_scanner_running = True
        self.fan_number_scanner_thread = threading.Thread(
            target=self._background_fan_number_scanner,
            daemon=True,
            name="FanNumberScanner"
        )
        self.fan_number_scanner_thread.start()
        
        # Start background profile cleaner in a daemon thread
        self.profile_cleaner_thread = threading.Thread(
            target=self._background_profile_cleaner,
            daemon=True,
            name="ProfileCleaner"
        )
        self.profile_cleaner_thread.start()
        print("🔄 Achtergrond profiel cleaner gestart (verwijdert inactieve profielen na 15 minuten)")
        
        # Start background signup processor (direct signups starten wanneer fan_number wordt gevonden)
        self.signup_processor_running = True
        self.signup_processor_thread = threading.Thread(
            target=self._background_signup_processor,
            daemon=True,
            name="SignupProcessor"
        )
        self.signup_processor_thread.start()
        print("🔄 Achtergrond signup processor gestart (start direct signups wanneer fan_number wordt gevonden)")
    
    def _migrate_config(self, config_path):
        """Auto-migrate config: add missing new fields with defaults"""
        updated = False
        config = self.site_config
        
        # Ensure automation section exists
        if 'automation' not in config:
            config['automation'] = {}
            updated = True
        
        automation = config['automation']
        
        # Add new fields if missing
        if 'auto_restart_runs' not in automation:
            automation['auto_restart_runs'] = 1
            updated = True
        
        if 'cleanup_on_start' not in automation:
            automation['cleanup_on_start'] = True
            updated = True
        
        if 'force_cleanup_completed' not in automation:
            automation['force_cleanup_completed'] = False
            updated = True
        
        # Save updated config if changed
        if updated:
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                print(f"✅ Config automatisch bijgewerkt met nieuwe velden: auto_restart_runs, cleanup_on_start, force_cleanup_completed")
            except Exception as e:
                print(f"⚠️  Kon config niet automatisch bijwerken: {e}")
        print("🔄 Achtergrond fan number scanner gestart (scant continu welkomstmails)")
    
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
            
            return lines
            
        except Exception as e:
            print(f"❌ Error loading {file_type} from {file_path}: {e}")
            return lines
    
    def create_profile(self, proxy_data=None, name_prefix='PORTUGAL_FPF'):
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
    
    def generate_phone_number(self) -> str:
        """Generate a unique 9-digit Portuguese mobile phone number starting with 21"""
        # Portuguese mobile numbers: 9 digits total, starting with 21 (area code for Lisbon)
        # Format: 21XXXXXXX (21 is the area code for Lisbon region)
        
        while True:
            # Generate remaining 7 random digits after "21"
            remaining_digits = ''.join([str(random.randint(0, 9)) for _ in range(7)])
            
            # Combine: 21 + 7 digits = 9 digits total
            number = '21' + remaining_digits
            
            if number not in self.used_phone_numbers:
                self.used_phone_numbers.add(number)
                return number
    
    def generate_birthdate(self) -> str:
        """Generate a random birthdate (older than 20 years, minimum 21 years old)"""
        # Generate year ensuring person is always 21+ years old
        # We use (current_year - 21) - 1 to ensure at least 21 years old regardless of month/day
        current_year = datetime.now().year
        max_birth_year = current_year - 22  # Born in 2003 = 22+ years old in 2025 (safe)
        min_birth_year = current_year - 45  # Max 45 years old
        year = random.randint(min_birth_year, max_birth_year)
        month = random.randint(1, 12)
        # Days depend on month
        if month in [1, 3, 5, 7, 8, 10, 12]:
            max_day = 31
        elif month in [4, 6, 9, 11]:
            max_day = 30
        else:  # February
            max_day = 28
        day = random.randint(1, max_day)
        return f"{year}-{month:02d}-{day:02d}"
    
    def generate_nif(self) -> str:
        """Generate a valid Portuguese NIF (tax identification number)
        Format: 9 digits, starts with 1-3 or 5-9
        """
        # NIF starts with 1-3 or 5-9 (4 is reserved for companies)
        first_digit = random.choice(['1', '2', '3', '5', '6', '7', '8', '9'])
        # Generate remaining 7 digits
        remaining = ''.join([str(random.randint(0, 9)) for _ in range(7)])
        # Calculate check digit (simplified - real validation is more complex)
        # For now, just generate a random last digit
        check_digit = random.randint(0, 9)
        nif = first_digit + remaining + str(check_digit)
        return nif
    
    def generate_portuguese_city(self) -> tuple:
        """Generate a random Portuguese city with address and postal code
        Returns: (city, address, postal_code, house_number)
        """
        portuguese_cities = [
            ("Lisboa", "Rua da Prata", "1100-000", "1100-299"),
            ("Porto", "Rua de Cedofeita", "4050-000", "4300-999"),
            ("Braga", "Avenida da Liberdade", "4700-000", "4700-999"),
            ("Coimbra", "Rua Ferreira Borges", "3000-000", "3000-999"),
            ("Faro", "Rua de Santo António", "8000-000", "8000-999"),
            ("Évora", "Rua 5 de Outubro", "7000-000", "7000-999"),
            ("Setúbal", "Avenida Luísa Todi", "2900-000", "2900-999"),
            ("Aveiro", "Rua da República", "3800-000", "3800-999"),
            ("Leiria", "Rua Barão de Viamonte", "2400-000", "2400-999"),
            ("Viseu", "Rua Formosa", "3500-000", "3500-999"),
            ("Amadora", "Avenida de Timor", "2700-000", "2700-999"),
            ("Almada", "Rua Capitão Leitão", "2800-000", "2800-999"),
            ("Sintra", "Rua Visconde de Monserrate", "2710-000", "2710-999"),
            ("Cascais", "Avenida Marginal", "2750-000", "2750-999"),
            ("Gondomar", "Rua 25 de Abril", "4420-000", "4420-999"),
            ("Guimarães", "Rua de Santa Maria", "4800-000", "4800-999"),
            ("Funchal", "Avenida Arriaga", "9000-000", "9000-999"),
        ]
        
        city_info = random.choice(portuguese_cities)
        city, street_prefix, postcode_start, postcode_end = city_info
        
        # Generate random house number (1-500)
        house_number = random.randint(1, 500)
        
        # Generate street variations
        street_suffixes = ["", " nº", " Nº", " N"]
        street = street_prefix + random.choice(street_suffixes)
        
        # Generate postal code (format: XXXX-XXX, 7 digits)
        # Parse postcode range
        start_num = int(postcode_start.split('-')[0])
        end_num = int(postcode_end.split('-')[0])
        postcode_first = random.randint(start_num, min(end_num, start_num + 100))
        
        # Second part (3 digits)
        postcode_second = random.randint(0, 999)
        postal_code = f"{postcode_first:04d}-{postcode_second:03d}"
        
        # Full address with house number
        address = f"{street} {house_number}"
        
        return (city, address, postal_code, str(house_number))
    
    def generate_portuguese_first_name(self) -> str:
        """Generate a random Portuguese first name"""
        first_names = [
            "João", "Francisco", "Miguel", "António", "José", "Pedro", "Luís", "Rafael",
            "Ricardo", "André", "Tiago", "Daniel", "Nuno", "Carlos", "Paulo",
            "Ana", "Maria", "Beatriz", "Catarina", "Inês", "Mariana", "Matilde",
            "Sofia", "Carolina", "Francisca", "Leonor", "Margarida", "Laura", "Rita", "Joana"
        ]
        return random.choice(first_names)
    
    def generate_portuguese_last_name(self) -> str:
        """Generate a random Portuguese last name"""
        last_names = [
            "Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues",
            "Martins", "Jesus", "Sousa", "Fernandes", "Gonçalves", "Gomes", "Lopes",
            "Marques", "Alves", "Almeida", "Ribeiro", "Pinto", "Carvalho", "Teixeira",
            "Moreira", "Correia", "Mendes", "Nunes", "Soares", "Vieira", "Monteiro",
            "Cardoso", "Rocha", "Neves", "Coelho", "Cruz", "Pires", "Ramos"
        ]
        return random.choice(last_names)
    
    def generate_password(self) -> str:
        """Generate a random password with variation"""
        length = random.randint(10, 16)  # Vary length between 10-16
        # Vary character sets for more realistic passwords
        use_special = random.choice([True, True, False])  # 2/3 chance of special chars
        use_numbers = random.choice([True, True, True, False])  # 3/4 chance of numbers
        use_uppercase = True  # Always use uppercase
        
        chars = "abcdefghijklmnopqrstuvwxyz"
        if use_uppercase:
            chars += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if use_numbers:
            chars += "0123456789"
        if use_special:
            chars += "!@#$%^&*"
        
        password = ''.join(random.choice(chars) for _ in range(length))
        # Ensure at least one uppercase and one number if required
        if use_uppercase and not any(c.isupper() for c in password):
            password = password[0].upper() + password[1:]
        if use_numbers and not any(c.isdigit() for c in password):
            idx = random.randint(0, len(password)-1)
            password = password[:idx] + random.choice("0123456789") + password[idx+1:]
        
        return password
    
    def _wait_for_element(self, driver, selector_type: str, selector: str, timeout: int = None) -> Optional[Any]:
        """Wait for element to be present (geoptimaliseerd: kortere timeouts)"""
        # Check if driver is still alive first
        try:
            _ = driver.current_url
        except Exception:
            print("      ❌ Browser lijkt gesloten te zijn tijdens wachten")
            return None

        if timeout is None:
            # Iets veiliger: 1/2 timeout, min 5 sec (was 1/3 en 3) - voorkomt te snel falen bij trage laadtijden
            timeout = max(5, self.timeout_seconds // 2)
        else:
            # Ook verklein expliciete timeouts iets minder agressief
            timeout = max(3, timeout // 2 + 2)
        
        try:
            wait = WebDriverWait(driver, timeout)
            if selector_type == "xpath":
                return wait.until(EC.presence_of_element_located((By.XPATH, selector)))
            elif selector_type == "id":
                return wait.until(EC.presence_of_element_located((By.ID, selector)))
            elif selector_type == "css":
                return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        except TimeoutException:
            return None
    
    def _check_for_ip_ban(self, driver) -> bool:
        """Check if IP address has been banned"""
        try:
            # Check if driver is still valid
            try:
                driver.current_url  # Quick check if driver is still valid
            except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
                error_msg = str(e).lower()
                if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg or 'disconnected' in error_msg:
                    # Browser is closed, can't check for IP ban
                    return False  # Return False (no ban detected) since we can't check
            
            page_source = driver.page_source.lower()
            page_text = driver.page_source
            
            # Check for IP ban message
            ban_indicators = [
                'your ip address has been banned',
                'ip address has been banned',
                'has been banned by automated security',
                'automated message',
                'help.me@fpf.pt'
            ]
            
            # Check if all key phrases are present (more reliable)
            has_automated_message = 'automated message' in page_source
            has_ip_banned = 'ip address has been banned' in page_source or 'has been banned' in page_source
            has_security_systems = 'automated security systems' in page_source or 'security systems' in page_source
            
            if has_automated_message and has_ip_banned:
                print(f"      ⚠️ IP BAN gedetecteerd: 'Automated message - Your IP address has been banned'")
                return True  # Returns True for IP ban, caller should return "IP_BANNED_RETRY"
            
            # Also check for any ban indicator
            for indicator in ban_indicators:
                if indicator in page_source:
                    print(f"      ⚠️ IP BAN indicator gevonden: {indicator}")
                    return True
            
            return False
            
        except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
            error_msg = str(e).lower()
            if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg or 'disconnected' in error_msg:
                # Browser is closed, can't check for IP ban - silently return False
                return False
            print(f"      ⚠️ Fout bij IP ban check: {e}")
            return False
        except Exception as e:
            print(f"      ⚠️ Fout bij IP ban check: {e}")
            return False
    
    def _check_and_handle_captcha(self, driver, task_number: int) -> bool:
        """Check for CAPTCHA on homepage and refresh if detected"""
        try:
            # Check if driver is still valid
            try:
                driver.current_url  # Quick check if driver is still valid
            except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
                error_msg = str(e).lower()
                if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg or 'disconnected' in error_msg:
                    print(f"[{task_number}] ⚠️ Browser gesloten, kan CAPTCHA niet checken")
                    return False
            
            # Wait a bit for page to load
            random_delay(0.5, 1.0)
            
            # Check for IP ban first
            if self._check_for_ip_ban(driver):
                print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                return "IP_BANNED_RETRY"
            
            # Check for CAPTCHA/Turnstile indicators
            try:
            page_source = driver.page_source.lower()
            current_url = driver.current_url.lower()
            except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
                error_msg = str(e).lower()
                if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg or 'disconnected' in error_msg:
                    print(f"[{task_number}] ⚠️ Browser gesloten tijdens CAPTCHA check")
                    return False
                raise
            
            # Check for CAPTCHA/Turnstile indicators
            captcha_indicators = [
                'cf-turnstile', 'turnstile', 'challenges.cloudflare.com',
                'recaptcha', 'hcaptcha', 'captcha', 'challenge',
                'cloudflare', 'just a moment', 'checking your browser'
            ]
            
            has_captcha = False
            for indicator in captcha_indicators:
                if indicator in page_source or indicator in current_url:
                    has_captcha = True
                    print(f"      🔍 CAPTCHA indicator gevonden: {indicator}")
                    break
            
            # Also check for CAPTCHA iframes
            try:
                captcha_iframes = driver.find_elements(By.CSS_SELECTOR, 
                    'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="captcha"], '
                    'iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], '
                    'iframe[name*="captcha"], .cf-turnstile iframe')
                if captcha_iframes:
                    has_captcha = True
                    print(f"      🔍 CAPTCHA iframe gevonden")
            except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
                error_msg = str(e).lower()
                if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg or 'disconnected' in error_msg:
                    return False
            except:
                pass
            
            # If CAPTCHA detected, refresh immediately
            if has_captcha:
                print(f"[{task_number}] ⚠️ CAPTCHA gedetecteerd, direct refreshen...")
                try:
                    driver.refresh()
                    random_delay(0.5, 1.0)
                    print(f"[{task_number}] ✅ Pagina gerefreshed, CAPTCHA zou nu weg moeten zijn")
                    return True
                except Exception as e:
                    print(f"[{task_number}] ⚠️ Fout bij refreshen: {e}")
                    return True
            
            return True  # No CAPTCHA detected, continue
            
        except Exception as e:
            print(f"[{task_number}] ⚠️ Fout bij CAPTCHA check: {e}")
            return True  # Continue on error
    
    
    def _apply_stealth_headers(self, driver):
        """Apply realistic HTTP headers via CDP to bypass Cloudflare detection"""
        try:
            # Set realistic headers via CDP
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': driver.execute_script('return navigator.userAgent;'),
                'acceptLanguage': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7'
            })
            
            # Enable network domain for header manipulation
            driver.execute_cdp_cmd('Network.enable', {})
            
            # Set extra headers via JavaScript (for requests)
            header_script = """
            // Override fetch to add realistic headers
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                if (args[1]) {
                    args[1].headers = args[1].headers || {};
                    args[1].headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8';
                    args[1].headers['Accept-Language'] = 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7';
                    args[1].headers['Accept-Encoding'] = 'gzip, deflate, br';
                    args[1].headers['DNT'] = '1';
                    args[1].headers['Connection'] = 'keep-alive';
                    args[1].headers['Upgrade-Insecure-Requests'] = '1';
                    args[1].headers['Sec-Fetch-Dest'] = 'document';
                    args[1].headers['Sec-Fetch-Mode'] = 'navigate';
                    args[1].headers['Sec-Fetch-Site'] = 'none';
                    args[1].headers['Sec-Fetch-User'] = '?1';
                }
                return originalFetch.apply(this, args);
            };
            return true;
            """
            driver.execute_script(header_script)
            
        except Exception as e:
            print(f"      ⚠️ Fout bij toepassen stealth headers: {e}")
    
    def _simulate_human_scroll(self, driver):
        """Simulate human-like scrolling behavior"""
        try:
            # Random scroll down and up (human behavior)
            scroll_amount = random.randint(200, 500)
            scroll_steps = random.randint(3, 6)
            
            for i in range(scroll_steps):
                # Scroll down
                driver.execute_script(f"window.scrollBy(0, {scroll_amount // scroll_steps});")
                random_delay(0.3, 0.6)
            
            # Sometimes scroll back up a bit
            if random.random() > 0.5:
                scroll_back = random.randint(50, 150)
                driver.execute_script(f"window.scrollBy(0, -{scroll_back});")
                random_delay(0.2, 0.4)
            
            # Scroll back to top (or near top)
            driver.execute_script("window.scrollTo(0, 0);")
            random_delay(0.5, 1.0)
            
        except Exception as e:
            # Silent fail - not critical
            pass
    
    def _simulate_hover_before_click(self, driver, element):
        """Simulate hover over element before clicking (human behavior)"""
        try:
            # Hover over element
            actions = ActionChains(driver)
            actions.move_to_element(element)
            actions.perform()
            random_delay(0.2, 0.5)
        except:
            # Fallback: just wait
            random_delay(0.2, 0.5)
    
    def _click_cookie_accept(self, driver) -> bool:
        """Click the cookie accept button"""
        try:
            # Wait for cookie banner - prioritize CSS selectors (more human-like)
            cookie_selectors = [
                ("css", "button[aria-label='Aceite tudo']"),  # Most specific CSS
                ("css", "button[data-cky-tag='accept-button']"),  # CSS by data attribute
                ("css", "button.cky-btn-accept"),  # CSS by class
                ("xpath", "//button[contains(text(), 'Aceite tudo')]"),  # XPath fallback only
            ]
            
            for selector_type, selector in cookie_selectors:
                element = self._wait_for_element(driver, selector_type, selector, timeout=5)
                if element:
                    random_delay(0.3, 0.6)
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                    random_delay(0.2, 0.4)
                    # Simulate hover before clicking (human behavior)
                    self._simulate_hover_before_click(driver, element)
                    self.human_click(driver, element)
                    print("      ✓ Cookie banner geaccepteerd")
                    random_delay(0.5, 1.0)  # Sneller na click
                    return True
            
            print("      ⚠️ Cookie banner niet gevonden, doorgaan...")
            random_delay(1.0, 2.0)  # Wait anyway before continuing
            return True  # Continue even if cookie banner not found
        except Exception as e:
            print(f"      ⚠️ Cookie accept error: {e}")
            random_delay(1.0, 2.0)
            return True  # Continue anyway
    
    def _click_register_button(self, driver) -> bool:
        """Click the register button on the homepage"""
        try:
            # Prioritize CSS selectors (more human-like and faster)
            register_selectors = [
                ("id", "IndexFinalCta"),  # Try ID first, then find button child
                ("css", "button.btn.btn-primary[data-ember-action]"),  # Most specific CSS
                ("css", "#IndexFinalCta button.btn-primary"),  # CSS with ID parent
                ("css", "button[data-ember-action]"),  # CSS by attribute
                ("xpath", "//button[contains(text(), 'Registar')]"),  # XPath fallback only
            ]
            
            # Try loop om zeker te zijn dat we de knop vinden als de pagina traag laadt
            start_time = time.time()
            max_search_time = 15  # Zoek maximaal 15 seconden naar de knop (was 10, nu langer)
            
            # Eerste keer printen dat we zoeken
            print(f"      🔍 Zoeken naar registratie button (max {max_search_time}s)...")
            
            while time.time() - start_time < max_search_time:
                for selector_type, selector in register_selectors:
                    # Gebruik expliciete timeout van 2s per selector check (snel doorheen loopen)
                    # Maar in _wait_for_element wordt dit minimaal 3s
                    
                    # Special handling for ID selector - find button child
                    if selector_type == "id" and selector == "IndexFinalCta":
                        try:
                            parent = self._wait_for_element(driver, "id", "IndexFinalCta", timeout=8)
                            if parent:
                                # Find first button child using CSS
                                element = parent.find_element(By.CSS_SELECTOR, "button")
                                if element:
                                    random_delay(0.3, 0.6)
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                    random_delay(0.2, 0.4)
                                    self.human_click(driver, element)
                                    print("      ✓ Registratie button geklikt")
                                    random_delay(0.5, 1.0)
                                    return True
                        except:
                            pass
                    else:
                        element = self._wait_for_element(driver, selector_type, selector, timeout=8)
                        if element:
                            random_delay(0.3, 0.6)
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                            random_delay(0.2, 0.4)
                            # Simulate hover before clicking (human behavior)
                            self._simulate_hover_before_click(driver, element)
                            self.human_click(driver, element)
                            print("      ✓ Registratie button geklikt")
                            random_delay(0.5, 1.0)
                            return True
                
                # Als geen selector werkte, wacht even en probeer opnieuw (pagina laadt misschien nog)
                time.sleep(0.5)
            
            print("      ❌ Registratie button niet gevonden met alle selectors")
            return False
        except Exception as e:
            print(f"      ❌ Register button error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _fill_email_and_submit(self, driver, email: str) -> bool:
        """Fill email field and submit - klik eerst op email veld, vul dan in, klik dan op button"""
        try:
            print(f"      📧 Wachten op email veld...")
            # Wait for email field to be present and visible
            email_element = self._wait_for_element(driver, "id", "email")
            if not email_element:
                print("      ❌ Email field niet gevonden")
                return False
            
            print(f"      📧 Email veld gevonden, klikken op veld...")
            random_delay(0.5, 1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", email_element)
            random_delay(0.3, 0.6)
            
            # Click on email field first (human-like behavior)
            try:
                email_element.click()
                random_delay(0.2, 0.4)
            except:
                # If click fails, try JavaScript click
                driver.execute_script("arguments[0].click();", email_element)
                random_delay(0.2, 0.4)
            
            # Clear any existing value
            try:
                email_element.clear()
                random_delay(0.2, 0.4)
            except:
                driver.execute_script("arguments[0].value = '';", email_element)
                random_delay(0.2, 0.4)
            
            # Type email letter by letter
            print(f"      📧 Email invullen: {email}")
            self.human_type(email_element, email, driver)
            print(f"      ✓ Email ingevuld: {email}")
            random_delay(1.0, 1.5)
            
            # Wait for and click "Enviar código de verificação" button
            print(f"      🔘 Zoeken naar 'Enviar código de verificação' button...")
            continue_element = self._wait_for_element(driver, "id", "continue")
            if not continue_element:
                print("      ❌ Continue button niet gevonden")
                return False
            
            # Verify button text/aria-label matches "Enviar código de verificação"
            try:
                button_text = continue_element.get_attribute("aria-label") or continue_element.text
                if "Enviar código" in button_text or "Enviar" in button_text:
                    print(f"      ✓ Correct button gevonden: {button_text}")
                else:
                    print(f"      ⚠️ Button text: {button_text}")
            except:
                pass
            
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", continue_element)
            random_delay(0.5, 1.0)
            self.human_click(driver, continue_element)
            print("      ✓ 'Enviar código de verificação' button geklikt")
            
            # Wait a bit for potential error message to appear
            random_delay(1.5, 2.5)
            
            # Check for error message: "Já existe um utilizador associado ao email pretendido."
            # Check multiple times as error might appear with delay
            error_detected = False
            error_text_found = ""
            for check_attempt in range(5):  # Increased to 5 checks for better detection
            try:
                    # Check page source for error text (exact match and variations)
                page_text = driver.page_source.lower()
                    error_patterns = [
                        "já existe um utilizador associado ao email pretendido",
                        "já existe um utilizador associado ao email",
                        "utilizador associado ao email pretendido",
                        "utilizador associado ao email",
                        "já existe um utilizador",
                        "email já existe",
                        "email já está em uso"
                    ]
                    
                    for pattern in error_patterns:
                        if pattern in page_text:
                            # Extract surrounding text for confirmation
                            idx = page_text.find(pattern)
                            context = page_text[max(0, idx-50):min(len(page_text), idx+len(pattern)+50)]
                            error_text_found = context
                            print(f"      ⚠️ Email bestaat al: '{pattern}' gevonden in pagina (check {check_attempt + 1})")
                            error_detected = True
                            break
                    
                    if error_detected:
                        break
                    
                    # Also check for error elements/divs that might contain the message
                    try:
                        error_elements = driver.find_elements(By.CSS_SELECTOR, 
                            "[class*='error'], [class*='Error'], [id*='error'], [id*='Error'], [role='alert'], "
                            "[class*='message'], [class*='Message'], [class*='alert'], [class*='Alert']")
                        for elem in error_elements:
                            try:
                                elem_text = elem.text.lower()
                                if elem_text:  # Only check if element has text
                                    for pattern in error_patterns:
                                        if pattern in elem_text:
                                            error_text_found = elem_text[:200]
                                            print(f"      ⚠️ Email bestaat al (gevonden in error element): {elem_text[:100]}")
                                            error_detected = True
                                            break
                                    if error_detected:
                                        break
                            except:
                                continue
                        if error_detected:
                            break
            except:
                pass
                    
                    # Check for toast/notification messages
                    try:
                        toast_elements = driver.find_elements(By.CSS_SELECTOR, 
                            "[class*='toast'], [class*='Toast'], [class*='notification'], [class*='Notification'], "
                            "[class*='message'], [class*='Message'], [class*='snackbar'], [class*='Snackbar']")
                        for elem in toast_elements:
                            try:
                                elem_text = elem.text.lower()
                                if elem_text:  # Only check if element has text
                                    for pattern in error_patterns:
                                        if pattern in elem_text:
                                            error_text_found = elem_text[:200]
                                            print(f"      ⚠️ Email bestaat al (gevonden in toast): {elem_text[:100]}")
                                            error_detected = True
                                            break
                                    if error_detected:
                                        break
                            except:
                                continue
                        if error_detected:
                            break
                    except:
                        pass
                    
                    # Check body text directly
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                        for pattern in error_patterns:
                            if pattern in body_text:
                                error_text_found = body_text[max(0, body_text.find(pattern)-50):min(len(body_text), body_text.find(pattern)+len(pattern)+50)]
                                print(f"      ⚠️ Email bestaat al (gevonden in body text): '{pattern}'")
                                error_detected = True
                                break
                        if error_detected:
                            break
                    except:
                        pass
                    
                    # If no error found yet, wait a bit more before next check
                    if check_attempt < 4:
                        random_delay(0.5, 1.0)
                except Exception as e:
                    # Continue checking even if one check fails
                    if check_attempt < 4:
                        random_delay(0.3, 0.6)
                    pass
            
            if error_detected:
                print("      ⏭️ Dit account wordt overgeslagen (email bestaat al)")
                return "SKIP_EMAIL_EXISTS"  # Special return value to indicate skip
            
            # Wait for next page to load (OTP input page)
            print(f"      ⏳ Wachten op vervolg pagina (OTP invoer)...")
            random_delay(1.0, 2.0)
            
            # Wait for OTP input field to appear (indicates next page loaded)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "emailVerificationCodeInput"))
                )
                print("      ✓ Vervolg pagina geladen (OTP invoer veld zichtbaar)")
            except:
                print("      ⚠️ OTP invoer veld nog niet zichtbaar, maar doorgaan...")
            
            return True
            
        except Exception as e:
            print(f"      ❌ Email submit error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _wait_for_verification_code(self, email: str, start_time: datetime) -> Optional[str]:
        """Wait for and extract verification code from email"""
        if not email or not email.strip():
            print(f"      ❌ Email is leeg, kan verificatie code niet ophalen")
            return None
        print(f"      📧 Wachten op verificatie code voor {email}...")
        code = self.imap_helper.extract_verification_code(email, start_time)
        return code
    
    def _wait_for_fan_number(self, target_email: str, start_time: datetime, timeout: int = 600) -> Optional[str]:
        """Wait for and extract fan number from welcome email"""
        print(f"      📧 Wachten op welkomstmail voor {target_email}...")
        try:
            # Use IMAP helper for consistency
            from email.header import decode_header
            import email.utils as email_utils  # Avoid name conflict with parameter
            
            imap_config = self.imap_config
            server = imap_config.get('server', 'imap.gmail.com')
            port = imap_config.get('port', 993)
            imap_email = self.imap_email
            imap_password = self.imap_password
            folder = imap_config.get('folder', 'INBOX')
            
            def decode_str(s):
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
            
            with imaplib.IMAP4_SSL(server, port) as M:
                M.login(imap_email, imap_password)
                M.select(folder)
                
                # Search for welcome email - ALLEEN op subject filteren (niet op sender, net zoals OTP)
                subject_phrase = "Bem-vindo ao Portugal+!"
                # Alleen vandaag (welkomstmail wordt direct verzonden)
                since_date = datetime.now().strftime('%d-%b-%Y')
                
                # GEEN FROM filter - alleen op subject filteren in Python (net zoals OTP)
                # GEEN SUBJECT filter in IMAP search (encoding issues met Portugese karakters)
                # We halen alle emails van vandaag op en filteren dan op subject in Python
                search_criteria = f'SINCE "{since_date}"'
                
                print(f"      🔍 Zoeken naar welkomstmail voor {target_email} vanaf {since_date}...")
                print(f"      🔍 Subject: {subject_phrase} (geen sender filter, net zoals OTP)")
                
                elapsed = 0
                poll_interval = 3  # Shorter interval for faster checks
                poll_count = 0
                
                while elapsed < timeout:
                    poll_count += 1
                    print(f"      🔄 Poll #{poll_count} (verstreken: {elapsed}s/{timeout}s)...")
                    
                    try:
                        status, messages = M.search(None, search_criteria)
                    except Exception as e:
                        print(f"      ⚠️ IMAP search encoding error: {e}")
                        time.sleep(poll_interval)
                        elapsed += poll_interval
                        continue
                    
                    if status != 'OK':
                        print(f"      ⚠️ IMAP search returned status: {status}")
                    
                    if status != 'OK' or not messages[0]:
                        if poll_count % 3 == 1 or elapsed < 10:
                            print(f"      📭 Nog geen emails gevonden, wachten...")
                        time.sleep(poll_interval)
                        elapsed += poll_interval
                        continue
                    
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        print(f"      📧 {len(email_ids)} email(s) gevonden met subject '{subject_phrase}', controleren...")
                        
                        # Process newest email first (geen wachten op oude emails!)
                        for email_id in reversed(email_ids):
                            status, msg_data = M.fetch(email_id, '(RFC822)')
                            
                            if status != 'OK' or not msg_data:
                                print(f"      ⚠️ Kon email {email_id} niet fetchen")
                                continue
                            
                            email_body = msg_data[0][1]
                            msg = email.message_from_bytes(email_body)
                            
                            # Get headers
                            from_header = decode_str(msg.get('From', ''))
                            subject = decode_str(msg.get('Subject', ''))
                            to_header = decode_str(msg.get('To', ''))
                            
                            # Filter ALLEEN op subject (net zoals OTP - sender kan variëren)
                            if subject_phrase.lower() not in subject.lower():
                                continue  # Skip emails without correct subject
                            
                            # Check if email is voor het juiste email adres (belangrijk!)
                            # IMAP TO filter werkt soms niet goed, check ook handmatig
                            email_recipients = [to_header]
                            # Ook check CC en BCC
                            cc_header = decode_str(msg.get('Cc', ''))
                            if cc_header:
                                email_recipients.append(cc_header)
                            bcc_header = decode_str(msg.get('Bcc', ''))
                            if bcc_header:
                                email_recipients.append(bcc_header)
                            
                            # Check of target_email in recipients staat
                            recipients_str = ' '.join(email_recipients)
                            if target_email.lower() not in recipients_str.lower():
                                if poll_count % 5 == 1:  # Niet te veel loggen
                                    print(f"      ⏭️ Email is niet voor {target_email} (aan: {to_header}), overslaan...")
                                continue  # Skip emails that aren't for this account
                            
                            print(f"      ✓ Match! Welkomstmail gevonden voor {target_email} (Van: {from_header}, Subject: {subject})")
                            
                            # Get HTML body
                            html_body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/html":
                                        html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                if msg.get_content_type() == "text/html":
                                    html_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
                            if html_body:
                                print(f"      🔍 Zoeken naar fan number in email body...")
                                # Extract fan number using regex patterns
                                try:
                                    import re
                                    
                                    # Look for fan number in email body - exact patterns from HTML
                                    # Patterns: "Your fan number is: 646623" or "És o fã nº 646623"
                                    fan_patterns = [
                                        r'Your fan number is:\s*(\d+)',  # English: "Your fan number is: 646623"
                                        r'És o fã n[º°o]\s*(\d+)',  # Portuguese: "És o fã nº 646623" (met º, °, of o)
                                        r'És o fã nº\s*(\d+)',  # Portuguese met nº specifiek
                                        r'fan number is:\s*(\d+)',  # Fallback: "fan number is: 646623"
                                        r'fã n[º°o]\s*(\d+)',  # Fallback: "fã nº 646623"
                                        r'n[º°o]\s*(\d+)',  # Just "nº 646623" (korter pattern)
                                        r'(\d{6})',  # Fallback: 6-digit number (fan numbers zijn meestal 6 cijfers)
                                    ]
                                    
                                    # Also get text body for fallback
                                    body = ""
                                    if msg.is_multipart():
                                        for part in msg.walk():
                                            if part.get_content_type() == "text/plain":
                                                payload = part.get_payload(decode=True)
                                                if payload:
                                                    body = payload.decode('utf-8', errors='ignore')
                                                    break
                                    else:
                                        if msg.get_content_type() == "text/plain":
                                            payload = msg.get_payload(decode=True)
                                            if payload:
                                                body = payload.decode('utf-8', errors='ignore')
                                    
                                    # Try HTML body first
                                    for pattern in fan_patterns:
                                        match = re.search(pattern, html_body, re.IGNORECASE)
                                        if match:
                                            fan_number = match.group(1).strip()
                                            print(f"      ✓ Fannummer gevonden via HTML pattern ({pattern}): {fan_number}")
                                            # Direct opslaan in CSV
                                            self.update_account_status(target_email, fan_number=fan_number)
                                            print(f"      💾 Fan number opgeslagen in CSV: {fan_number}")
                                            return fan_number
                                    
                                    # Fallback: try text body if HTML didn't work
                                    if body:
                                        for pattern in fan_patterns:
                                            match = re.search(pattern, body, re.IGNORECASE)
                                            if match:
                                                fan_number = match.group(1).strip()
                                                print(f"      ✓ Fannummer gevonden in text body ({pattern}): {fan_number}")
                                                # Direct opslaan in CSV
                                                self.update_account_status(target_email, fan_number=fan_number)
                                                print(f"      💾 Fan number opgeslagen in CSV: {fan_number}")
                                                return fan_number
                                    
                                    print(f"      ⚠️ Geen fan number patroon gevonden in email body")
                                    
                                except Exception as e:
                                    print(f"      ⚠️ Error parsing email HTML: {e}")
                                    import traceback
                                    traceback.print_exc()
                    
                    else:
                        if status == 'OK':
                            print(f"      📭 Geen emails gevonden in deze poll")
                        else:
                            print(f"      ⚠️ IMAP search error: {status}")
                    
                    # Wait before next poll
                    if elapsed < timeout - poll_interval:
                        print(f"      ⏳ Wachten {poll_interval}s voordat opnieuw wordt gezocht...")
                        time.sleep(poll_interval)
                    elapsed += poll_interval
                
                print(f"      ⚠️ Geen welkomstmail gevonden binnen {timeout} seconden na {poll_count} polls")
                return None
                
        except Exception as e:
            print(f"      ❌ Error checking email for fan number: {e}")
            return None
    
    def _wait_for_fan_number_quick(self, target_email: str, start_time: datetime, timeout: int = 30) -> Optional[str]:
        """Quick check for fan number with shorter timeout (for when browser is already open)"""
        # Reuse the same logic but with shorter timeout
        return self._wait_for_fan_number(target_email, start_time, timeout=timeout)
    
    def _check_existing_emails_for_fan_number(self, target_email: str) -> Optional[str]:
        """Direct check in existing emails for fan number (no waiting/timeout, just 1 check)"""
        print(f"      🔍 Direct checken in oude emails voor {target_email}...")
        try:
            from email.header import decode_header
            import email.utils as email_utils
            import re
            
            imap_config = self.imap_config
            server = imap_config.get('server', 'imap.gmail.com')
            port = imap_config.get('port', 993)
            imap_email = self.imap_email
            imap_password = self.imap_password
            folder = imap_config.get('folder', 'INBOX')
            
            def decode_str(s):
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
            
            with imaplib.IMAP4_SSL(server, port) as M:
                M.login(imap_email, imap_password)
                M.select(folder)
                
                # Search for welcome emails in the past 30 days (check old emails)
                # ALLEEN op subject filteren (niet op sender, net zoals OTP)
                subject_phrase = "Bem-vindo ao Portugal+!"
                # Check last 30 days for old emails
                since_date = (datetime.now() - timedelta(days=30)).strftime('%d-%b-%Y')
                # GEEN FROM filter - alleen op subject filteren in Python
                search_criteria = f'SINCE "{since_date}"'
                
                print(f"      🔍 Zoeken naar welkomstmail voor {target_email} vanaf {since_date}...")
                print(f"      🔍 Subject: {subject_phrase} (geen sender filter, net zoals OTP)")
                status, messages = M.search(None, search_criteria)
                
                if status != 'OK':
                    print(f"      ⚠️ IMAP search returned status: {status}")
                    return None
                
                if not messages[0]:
                    print(f"      📭 Geen emails gevonden")
                    return None
                
                email_ids = messages[0].split()
                print(f"      📧 {len(email_ids)} email(s) gevonden, filteren op subject '{subject_phrase}'...")
                
                # Process newest email first
                for email_id in reversed(email_ids):
                    status, msg_data = M.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK' or not msg_data:
                        continue
                    
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)
                    
                    # Get headers
                    from_header = decode_str(msg.get('From', ''))
                    subject = decode_str(msg.get('Subject', ''))
                    
                    # Filter ALLEEN op subject (net zoals OTP - sender kan variëren)
                    if subject_phrase.lower() not in subject.lower():
                        continue
                    
                    print(f"      ✓ Welkomstmail gevonden: {subject}")
                    
                    # Get HTML body
                    html_body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/html":
                                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                    else:
                        if msg.get_content_type() == "text/html":
                            html_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    if html_body:
                        # Extract fan number using regex patterns
                        fan_patterns = [
                            r'Your fan number is:\s*(\d+)',
                            r'És o fã n[º°]\s*(\d+)',
                            r'És o fã nº\s*(\d+)',
                            r'fan number is:\s*(\d+)',
                            r'fã n[º°]\s*(\d+)',
                            r'fã nº\s*(\d+)',
                            r'n[º°]\s*(\d+)',
                        ]
                        
                        for pattern in fan_patterns:
                            match = re.search(pattern, html_body, re.IGNORECASE)
                            if match:
                                fan_number = match.group(1).strip()
                                print(f"      ✓ Fan number gevonden: {fan_number}")
                                return fan_number
                        
                        # Fallback: try text body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode('utf-8', errors='ignore')
                                        break
                        else:
                            if msg.get_content_type() == "text/plain":
                                payload = msg.get_payload(decode=True)
                                if payload:
                                    body = payload.decode('utf-8', errors='ignore')
                        
                        if body:
                            for pattern in fan_patterns:
                                match = re.search(pattern, body, re.IGNORECASE)
                                if match:
                                    fan_number = match.group(1).strip()
                                    print(f"      ✓ Fan number gevonden in text: {fan_number}")
                                    return fan_number
                
                print(f"      ⚠️ Geen fan number gevonden in emails")
                return None
                
        except Exception as e:
            print(f"      ❌ Error checking existing emails: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _background_fan_number_scanner(self):
        """Achtergrond proces dat continu welkomstmails scant en fan numbers in CSV zet (EXACT zoals OTP scanner)"""
        scan_interval = 10  # Scan elke 10 seconden (net zoals OTP scanner voor snelle detectie)
        scan_count = 0
        
        # Track welke emails we al gescand hebben (net zoals OTP scanner)
        if not hasattr(self, '_fan_scanned_email_ids'):
            self._fan_scanned_email_ids = set()
        scanned_email_ids = self._fan_scanned_email_ids
        
        print("✅ [Background Fan Scanner] Thread gestart en actief")
        
        while self.fan_number_scanner_running:
            try:
                scan_count += 1
                print(f"🔍 [Background Fan Scanner] Scan #{scan_count}: Welkomstmails scannen voor fan numbers...")
                
                # Get IMAP config (EXACT zoals OTP scanner)
                imap_config = self.imap_config
                server = imap_config.get('server', 'imap.gmail.com')
                port = imap_config.get('port', 993)
                imap_email = self.imap_email
                imap_password = self.imap_password
                folder = imap_config.get('folder', 'INBOX')
                
                # Subject phrase (EXACT zoals OTP scanner)
                subject_phrase = "Bem-vindo ao Portugal+!"
                
                # Helper function voor decode (EXACT zoals OTP scanner)
                def decode_str(s):
                    if not s:
                        return ""
                    try:
                        from email.header import decode_header
                        decoded, encoding = decode_header(str(s))[0]
                        if isinstance(decoded, bytes):
                            return decoded.decode(encoding or 'utf-8', errors='ignore')
                        return str(decoded)
                    except:
                        return str(s)
                
                # Search criteria: ALLEEN vandaag (EXACT zoals OTP scanner)
                since_date = datetime.now().strftime('%d-%b-%Y')  # Alleen vandaag
                search_criteria = f'SINCE "{since_date}"'
                
                with imaplib.IMAP4_SSL(server, port) as M:
                    M.login(imap_email, imap_password)
                    M.select(folder)
                    
                    # Search voor alle emails van vandaag - GEEN FROM filter (EXACT zoals OTP scanner)
                    # We filteren op subject "Bem-vindo ao Portugal+!" in Python
                    try:
                        status, messages = M.search(None, search_criteria)
                    except UnicodeEncodeError:
                        # Fallback zonder datum filter (EXACT zoals OTP scanner)
                        search_criteria = 'ALL'
                    status, messages = M.search(None, search_criteria)
                    
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        print(f"🔍 [Background Fan Scanner] {len(email_ids)} email(s) gevonden, filteren op subject '{subject_phrase}'...")
                        
                        new_fan_numbers_found = 0
                        
                        # Process newest first (EXACT zoals OTP scanner)
                        for email_id in reversed(email_ids):
                            if not self.fan_number_scanner_running:
                                break
                            
                            email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                            
                            # Skip als we deze email al gescand hebben (EXACT zoals OTP scanner)
                            if email_id_str in scanned_email_ids:
                                continue
                            
                            try:
                                status, msg_data = M.fetch(email_id, '(RFC822)')
                                if status != 'OK' or not msg_data:
                                    continue
                                
                                msg = email.message_from_bytes(msg_data[0][1])
                                
                                # Get headers (EXACT zoals OTP scanner)
                                from_header = decode_str(msg.get('From', ''))
                                subject = decode_str(msg.get('Subject', ''))
                                to_header = decode_str(msg.get('To', ''))
                                cc_header = decode_str(msg.get('Cc', ''))
                                bcc_header = decode_str(msg.get('Bcc', ''))
                                
                                # Filter ALLEEN op subject (EXACT zoals OTP scanner - sender kan variëren)
                                if subject_phrase.lower() not in subject.lower():
                                    continue
                                
                                # Extract recipient emails (EXACT zoals OTP scanner)
                                def extract_emails(header_text):
                                    if not header_text:
                                        return []
                                    emails = []
                                    email_pattern = r'<([^>]+@[^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                                    matches = re.finditer(email_pattern, header_text)
                                    for match in matches:
                                        email_addr = match.group(1) or match.group(2)
                                        if email_addr:
                                            emails.append(email_addr.lower().strip())
                                    return emails
                                
                                all_recipient_emails = []
                                all_recipient_emails.extend(extract_emails(to_header))
                                all_recipient_emails.extend(extract_emails(cc_header))
                                all_recipient_emails.extend(extract_emails(bcc_header))
                                
                                if not all_recipient_emails:
                                    continue
                                
                                # Get HTML body for fan number extraction (EXACT zoals OTP scanner)
                                html_body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/html":
                                            payload = part.get_payload(decode=True)
                                            if payload:
                                                html_body = payload.decode('utf-8', errors='ignore')
                                                break
                                else:
                                    if msg.get_content_type() == "text/html":
                                        payload = msg.get_payload(decode=True)
                                        if payload:
                                            html_body = payload.decode('utf-8', errors='ignore')
                                
                                # Extract fan number (verbeterde patterns zoals OTP scanner)
                                fan_number = None
                                if html_body:
                                    # Try XPath first (zoals OTP scanner)
                                    try:
                                        from lxml import html as lxml_html
                                        doc = lxml_html.fromstring(html_body)
                                        xpath_patterns = [
                                            '//span[contains(text(), "fã")]',
                                            '//span[contains(text(), "fan")]',
                                            '//div[contains(text(), "fã")]',
                                            '//div[contains(text(), "fan")]',
                                        ]
                                        for xpath in xpath_patterns:
                                            try:
                                                elements = doc.xpath(xpath)
                                                if elements:
                                                    for elem in elements:
                                                        text = elem.text_content() if hasattr(elem, 'text_content') else str(elem)
                                                        # Try to find number in text
                                                        match = re.search(r'fã\s*n[º°]?\s*:?\s*(\d+)', text, re.IGNORECASE)
                                                        if not match:
                                                            match = re.search(r'fan\s*number\s*:?\s*(\d+)', text, re.IGNORECASE)
                                        if match:
                                            fan_number = match.group(1).strip()
                                                            if len(fan_number) >= 5:  # Fan numbers zijn meestal 6+ cijfers
                                            break
                                            except:
                                                continue
                                    except:
                                        pass
                                
                                # Fallback: regex patterns (EXACT zoals OTP scanner)
                                if not fan_number:
                                    fan_patterns = [
                                        r'És o fã\s*n[º°]?\s*:?\s*(\d+)',
                                        r'fã\s*n[º°]?\s*:?\s*(\d+)',
                                        r'fan\s*number\s*:?\s*(\d+)',
                                        r'Your fan number is:\s*(\d+)',
                                        r'n[º°]\s*:?\s*(\d+)',
                                    ]
                                    # Get text body as fallback
                                    text_body = ""
                                    if msg.is_multipart():
                                        for part in msg.walk():
                                            if part.get_content_type() == "text/plain":
                                                payload = part.get_payload(decode=True)
                                                if payload:
                                                    text_body = payload.decode('utf-8', errors='ignore')
                                                    break
                                    else:
                                        if msg.get_content_type() == "text/plain":
                                            payload = msg.get_payload(decode=True)
                                            if payload:
                                                text_body = payload.decode('utf-8', errors='ignore')
                                    
                                    search_body = html_body if html_body else text_body
                                        for pattern in fan_patterns:
                                        match = re.search(pattern, search_body, re.IGNORECASE)
                                            if match:
                                                fan_number = match.group(1).strip()
                                            if len(fan_number) >= 5:  # Fan numbers zijn meestal 6+ cijfers
                                                break
                                
                                # Update CSV for all recipients (EXACT zoals OTP scanner cached voor alle recipients)
                                if fan_number and len(fan_number) >= 5:
                                    # Mark email as scanned (EXACT zoals OTP scanner)
                                    scanned_email_ids.add(email_id_str)
                                    
                                    # Update CSV voor alle recipients die het nodig hebben
                                    for recipient_email in all_recipient_emails:
                                        recipient_normalized = recipient_email.lower().strip()
                                        # Normalize Gmail addresses (zoals OTP scanner)
                                        if '@gmail.com' in recipient_normalized:
                                            recipient_normalized = recipient_normalized.replace('.', '').split('@')[0] + '@gmail.com'
                                        
                                        # Check if this email is in our CSV and needs fan_number
                                        if self.accounts_file.exists():
                                            with open(self.accounts_file, 'r', encoding='utf-8', newline='') as f:
                                                reader = csv.DictReader(f)
                                                for row in reader:
                                                    csv_email = row.get('email', '').lower().strip()
                                                    # Normalize Gmail addresses
                                                    if '@gmail.com' in csv_email:
                                                        csv_email = csv_email.replace('.', '').split('@')[0] + '@gmail.com'
                                                    
                                                    if csv_email == recipient_normalized:
                                                        current_fan_number = row.get('fan_number', '').strip()
                                                        signup_done = row.get('signup', '').lower() == 'ja'
                                                        
                                                        # Only update if fan_number not set and signup not done
                                                        if (not current_fan_number or current_fan_number.lower() == 'nee') and not signup_done:
                                                            # Update fan_number en verwijder skip_reason
                                                            self.update_account_status(recipient_email, fan_number=fan_number, skip_reason='')
                                                            new_fan_numbers_found += 1
                                                            print(f"✅ [Background Fan Scanner] Fan number {fan_number} toegevoegd aan CSV voor {recipient_email}")
                                                            print(f"✅ [Background Fan Scanner] Skip_reason verwijderd - account kan nu worden verwerkt voor signup")
                                                            # Signal signup processor to immediately start signup
                                                            self.fan_number_found_event.set()
                                                            print(f"🚀 [Background Fan Scanner] Signaal verzonden - signup start direct voor {recipient_email}")
                                    break
                                
                                # Continue processing alle emails (EXACT zoals OTP scanner)
                            
                            except Exception as e:
                                # Silently skip errors (EXACT zoals OTP scanner)
                                continue
                        
                        if new_fan_numbers_found > 0:
                            print(f"✅ [Background Fan Scanner] {new_fan_numbers_found} nieuwe fan number(s) gevonden en bijgewerkt in CSV")
                        else:
                            print(f"ℹ️ [Background Fan Scanner] Scan #{scan_count} voltooid: {len(email_ids)} email(s) gescand, geen nieuwe fan numbers gevonden")
                    else:
                        if status != 'OK':
                            print(f"⚠️ [Background Fan Scanner] IMAP search error: {status}")
                        else:
                            print(f"ℹ️ [Background Fan Scanner] Scan #{scan_count} voltooid: Geen emails gevonden")
                
            except Exception as e:
                print(f"❌ [Background Fan Scanner] Fout bij scannen fan numbers: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait before next scan
            if self.fan_number_scanner_running:
                print(f"⏳ [Background Fan Scanner] Wachten {scan_interval} seconden tot volgende scan...")
                time.sleep(scan_interval)
            else:
                print("🛑 [Background Fan Scanner] Scanner gestopt")
                break
    
    def _background_signup_processor(self):
        """Achtergrond proces dat continu monitort op nieuwe signup accounts en ze direct verwerkt"""
        check_interval = 2  # Check elke 2 seconden voor snelle reactie
        processed_emails = set()  # Track welke emails momenteel worden verwerkt (wordt periodiek gereset)
        last_periodic_check = time.time()
        periodic_check_interval = 10  # Elke 10 seconden periodieke check
        
        def get_signup_accounts():
            """Helper functie om signup accounts op te halen uit CSV"""
            new_signup_accounts = []
            try:
                if self.accounts_file.exists():
                    with open(self.accounts_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                            signup_done = row.get('signup', '').lower() == 'ja'
                            if account_made and not signup_done:
                                fan_number = row.get('fan_number', '').strip()
                                if fan_number and fan_number.lower() != 'nee' and fan_number:
                                    email = row.get('email', '').strip()
                                    if email and email not in processed_emails:
                                        new_signup_accounts.append(row)
            except Exception as e:
                print(f"⚠️ [Background Signup] Fout bij ophalen signup accounts: {e}")
            return new_signup_accounts
        
        def start_signup_processing(accounts):
            """Helper functie om signup processing te starten"""
            if not accounts:
                return
            
            print(f"🚀 [Background Signup] {len(accounts)} nieuwe signup account(s) gevonden, direct starten...")
            for acc in accounts:
                email = acc.get('email', 'N/A')
                fan_num = acc.get('fan_number', 'N/A')
                print(f"   📝 [Background Signup] Start signup voor {email} (fan_number={fan_num})")
                processed_emails.add(email)  # Markeer als verwerkt
            
            # Start signup processing in a separate thread
            def run_signups():
                try:
                    # Calculate available threads for signups
                    signup_threads = max(1, self.threads - 10)
                    # Ignore stop_event for background signups - they should always run when fan_number is found
                    self.run_automation(
                        site_config=self.site_config,
                        data_list=accounts,
                        threads=min(signup_threads, len(accounts)),
                        ignore_stop_event=True  # Background signups should always run
                    )
                    # Na voltooiing, verwijder emails uit processed_emails als signup nog niet voltooid is
                    # (zodat ze opnieuw kunnen worden geprobeerd als ze falen)
                    time.sleep(5)  # Wacht even zodat CSV is bijgewerkt
                    for acc in accounts:
                        email = acc.get('email', '').strip()
                        if email:
                            # Check of signup is voltooid
                            try:
                                if self.accounts_file.exists():
                                    with open(self.accounts_file, 'r', encoding='utf-8') as f:
                                        reader = csv.DictReader(f)
                                        for row in reader:
                                            if row.get('email', '').strip().lower() == email.lower():
                                                signup_done = row.get('signup', '').lower() == 'ja'
                                                if not signup_done:
                                                    # Signup niet voltooid, verwijder uit processed zodat retry mogelijk is
                                                    processed_emails.discard(email)
                                                break
                            except:
                                pass
                except Exception as e:
                    print(f"❌ [Background Signup] Error in signup execution: {e}")
                    import traceback
                    traceback.print_exc()
                    # Bij error, verwijder emails uit processed zodat retry mogelijk is
                    for acc in accounts:
                        email = acc.get('email', '').strip()
                        if email:
                            processed_emails.discard(email)
            
            # Start in background thread (don't wait)
            signup_thread = threading.Thread(target=run_signups, daemon=True, name=f"SignupProcessor-{len(accounts)}")
            signup_thread.start()
        
        while self.signup_processor_running:
            try:
                current_time = time.time()
                should_check = False
                
                # Check if fan_number_found_event is set (signaal van background scanner)
                if self.fan_number_found_event.is_set():
                    self.fan_number_found_event.clear()
                    should_check = True
                    print(f"🔔 [Background Signup] Fan number event getriggerd, direct checken...")
                
                # Periodieke check (elke 10 seconden)
                elif current_time - last_periodic_check >= periodic_check_interval:
                    should_check = True
                    last_periodic_check = current_time
                    print(f"🔄 [Background Signup] Periodieke check voor nieuwe signup accounts...")
                
                if should_check:
                    new_signup_accounts = get_signup_accounts()
                    if new_signup_accounts:
                        start_signup_processing(new_signup_accounts)
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"⚠️ [Background Signup] Fout in signup processor: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(check_interval)
    
    def _background_profile_cleaner(self):
        """Achtergrond proces dat inactieve profielen verwijdert na 15 minuten inactiviteit"""
        check_interval = 60  # Check elke minuut
        inactivity_threshold = 15 * 60  # 15 minuten in seconden
        
        while self.profile_cleaner_running:
            try:
                current_time = time.time()
                
                # Check alle profielen in activity tracking
                profiles_to_remove = []
                for profile_id, last_activity in list(self.profile_last_activity.items()):
                    inactivity_duration = current_time - last_activity
                    
                    if inactivity_duration >= inactivity_threshold:
                        # Check of dit profiel nog nodig is in CSV
                        profile_still_needed = False
                        should_delete = False
                        
                        if self.accounts_file.exists():
                            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    csv_profile_id = row.get('profile_id', '').strip()
                                    if csv_profile_id == str(profile_id):
                                        account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                                        signup_done = row.get('signup', '').lower() == 'ja'
                                        
                                        # Profiel is nog nodig als:
                                        # - Account niet gemaakt (nog in gebruik voor account creation)
                                        # - Account gemaakt maar signup niet gedaan EN fan_number bestaat (wacht op signup completion)
                                        if not account_made:
                                            profile_still_needed = True
                                            break
                                        elif account_made and not signup_done:
                                            fan_number = row.get('fan_number', '').strip()
                                            if fan_number and fan_number.lower() != 'nee':
                                                # Heeft fan_number, kan signup doen - profiel is nog nodig
                                                profile_still_needed = True
                                                break
                                            else:
                                                # Geen fan_number EN inactief 15+ minuten
                                                # Dit profiel wacht op fan_number maar is inactief - kan worden verwijderd
                                                # (nieuw profiel wordt gemaakt wanneer fan_number wordt gevonden)
                                                should_delete = True
                                                break
                                        elif account_made and signup_done:
                                            # Volledig afgerond - kan worden verwijderd (wordt al door andere cleanup gedaan, maar doen we hier ook)
                                            should_delete = True
                                            break
                        
                        # Verwijder profiel als het niet meer nodig is of als het moet worden verwijderd
                        if should_delete or not profile_still_needed:
                            # Check of profiel nog actief is (gestart)
                            try:
                                profile = self.get_profile_by_id(profile_id)
                                if profile:
                                    # Profiel bestaat nog, probeer te stoppen en verwijderen
                                    profiles_to_remove.append(profile_id)
                            except:
                                # Profiel bestaat niet meer of kan niet worden opgehaald, skip
                                if profile_id in self.profile_last_activity:
                                    del self.profile_last_activity[profile_id]
                                continue
                
                # Verwijder inactieve profielen
                if profiles_to_remove:
                    print(f"🗑️  [Profile Cleaner] {len(profiles_to_remove)} inactief profiel(en) gevonden (15+ minuten inactief), verwijderen...")
                    for profile_id in profiles_to_remove:
                        try:
                            # Stop profiel eerst
                            self.stop_profile(profile_id)
                            
                            # Verwijder profiel
                            self.delete_profile(profile_id)
                            
                            # Cleanup tracking
                            if profile_id in self.profile_last_activity:
                                del self.profile_last_activity[profile_id]
                            if profile_id in self.profile_proxy_map:
                                del self.profile_proxy_map[profile_id]
                            if profile_id in self.profile_proxy_string_map:
                                del self.profile_proxy_string_map[profile_id]
                            
                            print(f"✅ [Profile Cleaner] Profiel {profile_id} verwijderd (15+ minuten inactief)")
                        except Exception as e:
                            print(f"⚠️  [Profile Cleaner] Fout bij verwijderen profiel {profile_id}: {e}")
                
            except Exception as e:
                print(f"⚠️  [Profile Cleaner] Fout bij profiel cleanup: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait before next check
            if self.profile_cleaner_running:
                time.sleep(check_interval)
    
    def _fill_verification_code(self, driver, code: str) -> bool:
        """Fill verification code and submit - klik eerst op OTP veld, vul dan in, klik dan op Confirmar button"""
        try:
            print(f"      🔐 Wachten op verificatie code veld...")
            # Wait for verification code input field to be present and visible
            code_element = self._wait_for_element(driver, "id", "emailVerificationCodeInput")
            if not code_element:
                print("      ❌ Verificatie code field niet gevonden")
                return False
            
            print(f"      🔐 Verificatie code veld gevonden, klikken op veld...")
            random_delay(0.5, 1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", code_element)
            random_delay(0.3, 0.6)
            
            # Click on OTP field first (human-like behavior)
            try:
                code_element.click()
                random_delay(0.2, 0.4)
            except:
                # If click fails, try JavaScript click
                driver.execute_script("arguments[0].click();", code_element)
                random_delay(0.2, 0.4)
            
            # Clear any existing value
            try:
                code_element.clear()
                random_delay(0.2, 0.4)
            except:
                driver.execute_script("arguments[0].value = '';", code_element)
                random_delay(0.2, 0.4)
            
            # Type code
            print(f"      🔐 Verificatie code invullen: {code}")
            self.human_type(code_element, code, driver)
            print(f"      ✓ Verificatie code ingevuld: {code}")
            random_delay(1.0, 1.5)
            
            # Wait for and click "Confirmar" button
            print(f"      🔘 Zoeken naar 'Confirmar' button...")
            confirm_element = self._wait_for_element(driver, "id", "continue")
            if not confirm_element:
                print("      ❌ Confirm button niet gevonden")
                return False
            
            # Verify button text/aria-label matches "Confirmar"
            try:
                button_text = confirm_element.get_attribute("aria-label") or confirm_element.text
                if "Confirmar" in button_text or "Confirm" in button_text:
                    print(f"      ✓ Correct button gevonden: {button_text}")
                else:
                    print(f"      ⚠️ Button text: {button_text}")
            except:
                pass
            
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", confirm_element)
            random_delay(0.5, 1.0)
            self.human_click(driver, confirm_element)
            print("      ✓ 'Confirmar' button geklikt")
            
            # Wait for next page to load (password form page)
            print(f"      ⏳ Wachten op vervolg pagina (wachtwoord formulier)...")
            random_delay(2.0, 3.0)
            
            # Wait for password field to appear (indicates next page loaded)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "newPassword"))
                )
                print("      ✓ Vervolg pagina geladen (wachtwoord veld zichtbaar)")
            except:
                print("      ⚠️ Wachtwoord veld nog niet zichtbaar, maar doorgaan...")
            
            return True
            
        except Exception as e:
            print(f"      ❌ Verification code error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _fill_password_form(self, driver, password: str) -> bool:
        """Fill password and confirm password"""
        try:
            # Wait for password fields
            password_element = self._wait_for_element(driver, "id", "newPassword")
            if not password_element:
                print("      ❌ Password field niet gevonden")
                return False
            
            random_delay(0.5, 1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", password_element)
            random_delay(0.3, 0.6)
            
            # Type password
            self.human_type(password_element, password, driver)
            print("      ✓ Password ingevuld")
            random_delay(0.8, 1.2)
            
            # Confirm password field
            confirm_password_element = self._wait_for_element(driver, "id", "reenterPassword")
            if not confirm_password_element:
                print("      ❌ Confirm password field niet gevonden")
                return False
            
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", confirm_password_element)
            random_delay(0.3, 0.6)
            self.human_type(confirm_password_element, password, driver)
            print("      ✓ Password bevestigd")
            random_delay(0.8, 1.2)
            return True
            
        except Exception as e:
            print(f"      ❌ Password form error: {e}")
            return False
    
    def _select_birthdate_from_picker(self, driver, birthdate: str) -> bool:
        """Select birthdate using the datepicker - navigate to year/month then select day"""
        try:
            # Parse birthdate (format: YYYY-MM-DD)
            parts = birthdate.split('-')
            if len(parts) != 3:
                return False
            
            target_year = int(parts[0])
            target_month = int(parts[1])  # 1-12
            target_day = int(parts[2])
            
            # Find and click the birthdate field to open datepicker
            birthdate_element = self._wait_for_element(driver, "id", "extension_Birthdate", timeout=10)
            if not birthdate_element:
                print("      ⚠️ Geboortedatum veld niet gevonden")
                return False
            
            random_delay(0.5, 1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", birthdate_element)
            random_delay(0.3, 0.6)
            
            # Click to open datepicker
            self.human_click(driver, birthdate_element)
            print(f"      📅 Datepicker geopend voor {target_year}-{target_month:02d}-{target_day:02d}")
            random_delay(1.0, 1.5)
            
            # Wait for datepicker to appear
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            try:
                # Find datepicker container
                datepicker = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "ui-datepicker-calendar"))
                )
            except:
                print("      ⚠️ Datepicker niet gevonden")
                return False
            
            # Step 1: Navigate to correct year
            # Find year dropdown or prev/next buttons for year
            current_year_element = None
            year_select = None
            
            # Try to find year select dropdown first
            try:
                year_select = driver.find_element(By.CLASS_NAME, "ui-datepicker-year")
                if year_select:
                    select_year = Select(year_select)
                    select_year.select_by_value(str(target_year))
                    print(f"      ✓ Jaar geselecteerd: {target_year}")
                    random_delay(0.5, 1.0)
            except:
                # No year dropdown, try prev/next navigation
                try:
                    # Find current year display (might be in header)
                    current_year_text = driver.find_element(By.CLASS_NAME, "ui-datepicker-year").text
                    current_year = int(current_year_text)
                    
                    # Calculate how many clicks needed
                    year_diff = target_year - current_year
                    
                    if year_diff != 0:
                        # Find prev/next buttons for year
                        # Usually clicking month prev/next multiple times changes year
                        if year_diff < 0:
                            # Need to go back
                            prev_button = driver.find_element(By.CLASS_NAME, "ui-datepicker-prev")
                            for _ in range(abs(year_diff) * 12):  # Go back by months
                                prev_button.click()
                                random_delay(0.1, 0.2)
                        else:
                            # Need to go forward
                            next_button = driver.find_element(By.CLASS_NAME, "ui-datepicker-next")
                            for _ in range(year_diff * 12):  # Go forward by months
                                next_button.click()
                                random_delay(0.1, 0.2)
                        
                        print(f"      ✓ Genavigeerd naar jaar: {target_year}")
                        random_delay(0.5, 1.0)
                except Exception as e:
                    print(f"      ⚠️ Kon jaar niet navigeren: {e}")
            
            # Step 2: Navigate to correct month
            try:
                month_select = driver.find_element(By.CLASS_NAME, "ui-datepicker-month")
                if month_select:
                    select_month = Select(month_select)
                    # jQuery UI months are 0-indexed (0 = January, 11 = December)
                    select_month.select_by_value(str(target_month - 1))
                    print(f"      ✓ Maand geselecteerd: {target_month}")
                    random_delay(0.5, 1.0)
            except:
                # No month dropdown, use prev/next buttons
                try:
                    # Get current month
                    current_month_text = driver.find_element(By.CLASS_NAME, "ui-datepicker-month").text
                    # Map month names to numbers (jQuery UI uses full names or abbreviations)
                    month_names = ["January", "February", "March", "April", "May", "June",
                                 "July", "August", "September", "October", "November", "December"]
                    month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                    
                    current_month = None
                    for i, name in enumerate(month_names):
                        if name in current_month_text or month_abbr[i] in current_month_text:
                            current_month = i + 1
                            break
                    
                    if current_month:
                        month_diff = target_month - current_month
                        
                        if month_diff < 0:
                            prev_button = driver.find_element(By.CLASS_NAME, "ui-datepicker-prev")
                            for _ in range(abs(month_diff)):
                                prev_button.click()
                                random_delay(0.2, 0.3)
                        elif month_diff > 0:
                            next_button = driver.find_element(By.CLASS_NAME, "ui-datepicker-next")
                            for _ in range(month_diff):
                                next_button.click()
                                random_delay(0.2, 0.3)
                        
                        print(f"      ✓ Genavigeerd naar maand: {target_month}")
                        random_delay(0.5, 1.0)
                except Exception as e:
                    print(f"      ⚠️ Kon maand niet navigeren: {e}")
            
            # Step 3: Select the day
            try:
                # Wait a bit for calendar to update
                random_delay(0.5, 1.0)
                
                # Find all clickable day links in the calendar
                day_links = driver.find_elements(By.XPATH, 
                    f"//td[@data-handler='selectDay' and @data-month='{target_month-1}' and @data-year='{target_year}']//a[text()='{target_day}']")
                
                if not day_links:
                    # Try without data attributes (fallback)
                    day_links = driver.find_elements(By.XPATH,
                        f"//table[@class='ui-datepicker-calendar']//a[text()='{target_day}']")
                
                if day_links:
                    # Filter to only selectable days (not disabled)
                    for link in day_links:
                        parent_td = link.find_element(By.XPATH, "./..")
                        classes = parent_td.get_attribute("class") or ""
                        if "ui-datepicker-unselectable" not in classes and "ui-state-disabled" not in classes:
                            self.human_click(driver, link)
                            print(f"      ✓ Dag geselecteerd: {target_day}")
                            random_delay(0.5, 1.0)
                            return True
                
                print(f"      ⚠️ Dag {target_day} niet gevonden of niet selecteerbaar")
                return False
                
            except Exception as e:
                print(f"      ⚠️ Kon dag niet selecteren: {e}")
                return False
            
            # Click to open datepicker
            self.human_click(driver, birthdate_element)
            print(f"      📅 Datepicker geopend")
            random_delay(1.0, 1.5)
            
            # Wait for datepicker to appear
            datepicker = self._wait_for_element(driver, "css", ".ui-datepicker-calendar", timeout=10)
            if not datepicker:
                print("      ⚠️ Datepicker niet gevonden")
                return False
            
            # Navigate to target year and month
            # Keep clicking prev/next until we're at the right month/year
            max_navigations = 300  # Safety limit (25 years * 12 months)
            navigations = 0
            
            while navigations < max_navigations:
                # Get current displayed month and year from datepicker
                try:
                    current_month_1_based = None
                    current_year = None
                    
                    # Method 1: Try to get from data attributes of any visible day (most reliable)
                    day_cells = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-calendar td[data-month]")
                    if day_cells:
                        # Get from first selectable day with data attributes
                        for day_cell in day_cells:
                            try:
                                month_attr = day_cell.get_attribute('data-month')
                                year_attr = day_cell.get_attribute('data-year')
                                if month_attr is not None and year_attr is not None:
                                    current_month = int(month_attr)  # 0-11
                                    current_year = int(year_attr)
                                    current_month_1_based = current_month + 1  # Convert to 1-12
                                    break
                            except:
                                continue
                    
                    # Method 2: Fallback to month/year selects if available
                    if current_month_1_based is None or current_year is None:
                        month_elements = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-month option[selected]")
                        year_elements = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-year option[selected]")
                        if month_elements and year_elements:
                            try:
                                current_month = int(month_elements[0].get_attribute('value'))  # 0-11
                                current_year = int(year_elements[0].get_attribute('value'))
                                current_month_1_based = current_month + 1  # Convert to 1-12
                            except:
                                pass
                    
                    if current_month_1_based is None or current_year is None:
                        print("      ⚠️ Kon huidige maand/jaar niet bepalen")
                        break
                    
                    # Check if we're at target month and year
                    if current_month_1_based == target_month and current_year == target_year:
                        print(f"      📅 Navigatie naar {target_month}/{target_year} voltooid")
                        break
                    
                    # Navigate: click prev or next button
                    if current_year < target_year or (current_year == target_year and current_month_1_based < target_month):
                        # Need to go forward (future)
                        next_btn = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-next")
                        if next_btn and next_btn[0].is_displayed():
                            self.human_click(driver, next_btn[0])
                            random_delay(0.5, 0.8)
                        else:
                            break
                    else:
                        # Need to go backward (past)
                        prev_btn = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-prev")
                        if prev_btn and prev_btn[0].is_displayed():
                            self.human_click(driver, prev_btn[0])
                            random_delay(0.5, 0.8)
                        else:
                            break
                    
                    navigations += 1
                    random_delay(0.3, 0.5)
                    
                except Exception as e:
                    print(f"      ⚠️ Error navigating datepicker: {e}")
                    break
            
            # Find all selectable days in the calendar
            # Selectable days have: <td> with data-handler="selectDay" and <a> inside (not disabled)
            selectable_days = driver.find_elements(
                By.CSS_SELECTOR, 
                ".ui-datepicker-calendar td[data-handler='selectDay']:not(.ui-datepicker-unselectable):not(.ui-state-disabled) a.ui-state-default"
            )
            
            if not selectable_days:
                print("      ⚠️ Geen selecteerbare dagen gevonden")
                return False
            
            # Filter days to match target day if possible, otherwise pick random
            matching_days = [day for day in selectable_days if int(day.text.strip()) == target_day]
            
            if matching_days:
                # Click the exact target day
                day_to_click = matching_days[0]
            else:
                # Pick a random selectable day (human-like variation)
                day_to_click = random.choice(selectable_days)
            
            # Scroll to the day element
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", day_to_click)
            random_delay(0.3, 0.5)
            
            # Click the day
            self.human_click(driver, day_to_click)
            selected_day = day_to_click.text.strip()
            print(f"      ✓ Geboortedatum geselecteerd: dag {selected_day}")
            random_delay(0.8, 1.2)
            
            return True
            
        except Exception as e:
            print(f"      ⚠️ Datepicker selectie error: {e}")
            return False
    
    def _fill_additional_details(self, driver, task_number: int, email: str) -> tuple:
        """Fill additional details on the follow-up page after account creation
        Returns: (city, address, postal_code, nif, house_number) or (None, None, None, None, None) if failed
        """
        try:
            # Generate Portuguese data (now includes house_number)
            city, address, postal_code, house_number = self.generate_portuguese_city()
            nif = self.generate_nif()
            
            # Save address data immediately (live update)
            self.update_account_status(
                email,
                city=city,
                address=address,
                postal_code=postal_code,
                nif=nif,
                house_number=house_number
            )
            print(f"      💾 Adres gegevens live opgeslagen: city={city}, postal_code={postal_code}, nif={nif}")
            
            # Step 1: Quick check if we're already on the form page
            print(f"      🔍 Controleren of we al op de form pagina zijn...")
            random_delay(1.0, 2.0)
            
            # Quick check for form fields - don't wait long
            form_visible = False
            try:
                # Check for any form field quickly
                city_element_check = driver.find_elements(By.ID, "ember6")
                select2_check = driver.find_elements(By.CSS_SELECTOR, "select.select2-countries")
                parabens_check = driver.find_elements(By.XPATH, "//h2[contains(text(), 'Parabéns!')]")
                
                if city_element_check or select2_check or parabens_check:
                    form_visible = True
                    print("      ✓ Form pagina al zichtbaar, registratie button niet nodig")
            except:
                pass
            
            # If form is not visible, click register button
            if not form_visible:
                # Step 1: Click "Registar" button again (only if form is not visible) - prioritize CSS
                print(f"      📝 Registratie button zoeken op vervolgpagina...")
                register_selectors = [
                    ("id", "IndexFinalCta"),  # Try ID first, then find button child
                    ("css", "#IndexFinalCta button.btn-primary"),  # CSS with ID parent
                    ("css", "button.btn.btn-primary[data-ember-action]"),  # CSS by class and attribute
                    ("css", "button[data-ember-action]"),  # CSS by attribute
                    ("xpath", "//button[contains(., 'Registar')]"),  # XPath fallback
                ]
                
                register_button = None
                for selector_type, selector in register_selectors:
                    # Special handling for ID selector - find button child
                    if selector_type == "id" and selector == "IndexFinalCta":
                        try:
                            parent = self._wait_for_element(driver, "id", "IndexFinalCta", timeout=10)
                            if parent:
                                register_button = parent.find_element(By.CSS_SELECTOR, "button")
                                if register_button:
                                    break
                        except:
                            continue
                    else:
                        register_button = self._wait_for_element(driver, selector_type, selector, timeout=10)
                        if register_button:
                            break
                
                if register_button:
                    random_delay(1.0, 2.0)
                    # Check if element is visible and has size
                    try:
                        is_displayed = register_button.is_displayed()
                        size = register_button.size
                        location = register_button.location
                        
                        if is_displayed and size['width'] > 0 and size['height'] > 0:
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", register_button)
                            random_delay(0.5, 1.0)
                            # Try JavaScript click first (more reliable)
                            try:
                                driver.execute_script("arguments[0].click();", register_button)
                                print("      ✓ Registratie button geklikt (JavaScript)")
                            except:
                                self.human_click(driver, register_button)
                                print("      ✓ Registratie button geklikt")
                            random_delay(2.0, 3.0)
                        else:
                            print("      ⚠️ Registratie button niet interactable, proberen met JavaScript...")
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", register_button)
                            random_delay(0.5, 1.0)
                            driver.execute_script("arguments[0].click();", register_button)
                            print("      ✓ Registratie button geklikt (JavaScript fallback)")
                            random_delay(2.0, 3.0)
                    except Exception as e:
                        print(f"      ⚠️ Fout bij klikken registratie button: {e}, proberen JavaScript click...")
                        try:
                            driver.execute_script("arguments[0].click();", register_button)
                            print("      ✓ Registratie button geklikt (JavaScript error fallback)")
                            random_delay(2.0, 3.0)
                        except Exception as e2:
                            print(f"      ❌ Kon registratie button niet klikken: {e2}")
                            return (None, None, None, None, None)
                else:
                    # If register button not found, check if form is already visible
                    city_element_check2 = self._wait_for_element(driver, "id", "ember6", timeout=5)
                    if not city_element_check2:
                        print("      ❌ Registratie button niet gevonden en form niet zichtbaar")
                        return (None, None, None, None, None)
                    else:
                        print("      ✓ Form pagina al zichtbaar, registratie button niet nodig")
            
            # Step 2: Navigate to register-details page and select Portugal dropdown with CAPTCHA detection
            register_details_url = "https://portugal.fpf.pt/register-details?lang=pt-PT"
            print(f"      🔄 Navigeren naar register-details pagina...")
            driver.get(register_details_url)
            random_delay(2.0, 3.0)
            
            # Wait for page to fully load and check for CAPTCHA/loaders
            # Check for CAPTCHA/Turnstile and refresh if detected
            try:
                page_source = driver.page_source.lower()
                captcha_indicators = [
                    'cf-turnstile', 'turnstile', 'challenges.cloudflare.com',
                    'recaptcha', 'hcaptcha', 'captcha', 'challenge',
                    'cloudflare', 'just a moment', 'checking your browser'
                ]
                has_captcha = False
                
                for indicator in captcha_indicators:
                    if indicator in page_source:
                        has_captcha = True
                        print(f"      🔍 CAPTCHA indicator gevonden: {indicator}")
                        break
                
                # Also check for CAPTCHA iframes
                try:
                    captcha_iframes = driver.find_elements(By.CSS_SELECTOR, 
                        'iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], '
                        'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .cf-turnstile iframe')
                    if captcha_iframes:
                        has_captcha = True
                        print(f"      🔍 CAPTCHA iframe gevonden")
                except:
                    pass
                
                # If CAPTCHA detected, refresh immediately
                if has_captcha:
                    print(f"      ⚠️ CAPTCHA gedetecteerd op register-details, direct refreshen...")
                    try:
                        driver.refresh()
                        random_delay(0.5, 1.0)
                        print(f"      ✅ Pagina gerefreshed na CAPTCHA detectie")
                    except Exception as refresh_error:
                        print(f"      ⚠️ Fout bij refreshen: {refresh_error}")
                        random_delay(0.5, 1.0)
            except Exception as e:
                print(f"      ⚠️ Fout bij checken CAPTCHA: {e}")
                pass
            
            # Wait for any loaders to disappear
            try:
                loader_selectors = [
                    "div[class*='loader']",
                    "div[class*='loading']",
                    "app-game-loader",
                    ".spinner"
                ]
                for loader_selector in loader_selectors:
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.invisibility_of_element_located((By.CSS_SELECTOR, loader_selector))
                        )
                    except:
                        pass
            except:
                pass
            
            random_delay(1.0, 2.0)
            
            # CAPTCHA detectie: Als Portugal dropdown niet zichtbaar is, refresh max 3x
            print(f"      🌍 Portugal selecteren (CAPTCHA detectie)...")
            portugal_selected = False
            max_refresh_attempts = 3
            
            for attempt in range(max_refresh_attempts):
                try:
                    # Wait a bit for page to stabilize
                    random_delay(1.0, 2.0)
                    
                    # EERST CHECKEN OF PORTUGAL AL GESELECTEERD IS
                    all_select2_containers = driver.find_elements(By.CSS_SELECTOR, "span.select2-selection.select2-selection--single")
                    portugal_already_selected = False
                    
                    for container in all_select2_containers:
                        try:
                            rendered = container.find_element(By.CSS_SELECTOR, "span.select2-selection__rendered")
                            title = rendered.get_attribute("title") or ""
                            text = rendered.text or ""
                            
                            # Check if Portugal is already selected
                            if "Portugal" in title or "Portugal" in text or "PT" in title:
                                print(f"      ✓ Portugal is al geselecteerd: '{title or text}'")
                                portugal_already_selected = True
                                portugal_selected = True
                                break
                        except:
                            continue
                    
                    if portugal_already_selected:
                        # Portugal is al geselecteerd, gewoon doorgaan
                        random_delay(0.5, 1.0)
                        break
                    
                    # Zoek naar span met "Selecione uma opção" (Portugal dropdown)
                    portugal_container = None
                    
                    # Try to wait for select2 containers to be present
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "span.select2-selection.select2-selection--single"))
                        )
                    except:
                        pass
                    
                    for container in all_select2_containers:
                        try:
                            rendered = container.find_element(By.CSS_SELECTOR, "span.select2-selection__rendered")
                            title = rendered.get_attribute("title") or ""
                            text = rendered.text or ""
                            if "Selecione uma opção" in title or "Selecione uma opção" in text:
                                portugal_container = rendered
                                break
                        except:
                            continue
                    
                    if portugal_container:
                        # Ensure element is visible and clickable
                        try:
                            WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable(portugal_container)
                            )
                        except:
                            pass
                        
                        # Klik op de span container (use JavaScript click for reliability)
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", portugal_container)
                        random_delay(0.3, 0.6)
                        
                        try:
                        portugal_container.click()
                        except:
                            # Fallback to JavaScript click
                            driver.execute_script("arguments[0].click();", portugal_container)
                        
                        random_delay(0.8, 1.2)  # Wait longer for dropdown to open
                        
                        # Klik op Portugal option (li met id zoals select2-qtvw-result-6k6q-PT)
                        portugal_option = None
                        
                        # Wait for dropdown options to appear
                        try:
                            WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "li.select2-results__option"))
                            )
                        except:
                            pass
                        
                        # Try highlighted option first
                        options = driver.find_elements(By.CSS_SELECTOR, "li.select2-results__option.select2-results__option--highlighted")
                        for option in options:
                            try:
                            option_id = option.get_attribute("id") or ""
                            option_text = option.text or ""
                            if "PT" in option_id and "Portugal" in option_text:
                                portugal_option = option
                                break
                            except:
                                continue
                        
                        if not portugal_option:
                            # Fallback: zoek gewoon naar Portugal in alle options
                            all_options = driver.find_elements(By.CSS_SELECTOR, "li.select2-results__option")
                            for option in all_options:
                                try:
                                option_text = option.text or ""
                                if "Portugal" in option_text:
                                    portugal_option = option
                                    break
                                except:
                                    continue
                        
                        if portugal_option:
                            try:
                                # Try regular click first
                            portugal_option.click()
                            except:
                                # Fallback to JavaScript click
                                driver.execute_script("arguments[0].click();", portugal_option)
                            
                            print("      ✓ Portugal geselecteerd")
                            portugal_selected = True
                            random_delay(0.8, 1.2)
                            break
                    else:
                        # Portugal dropdown niet gevonden = mogelijk CAPTCHA, refresh
                        if attempt < max_refresh_attempts - 1:
                            print(f"      ⚠️ Portugal dropdown niet zichtbaar (mogelijk CAPTCHA), refresh poging {attempt + 1}/{max_refresh_attempts}...")
                            driver.get(register_details_url)
                            random_delay(2.0, 3.0)
                            
                            # Wait for loaders again after refresh
                            try:
                                for loader_selector in loader_selectors:
                                    try:
                                        WebDriverWait(driver, 5).until(
                                            EC.invisibility_of_element_located((By.CSS_SELECTOR, loader_selector))
                                        )
                                    except:
                                        pass
                            except:
                                pass
                            random_delay(1.0, 2.0)
                        else:
                            print(f"      ❌ Portugal dropdown niet gevonden na {max_refresh_attempts} refresh pogingen")
                            
                except Exception as e:
                    if attempt < max_refresh_attempts - 1:
                        print(f"      ⚠️ Fout bij poging {attempt + 1}, refresh opnieuw...")
                        driver.get(register_details_url)
                        random_delay(2.0, 3.0)
                        random_delay(1.0, 2.0)
                    else:
                        print(f"      ❌ Fout bij selecteren Portugal: {e}")
            
            if not portugal_selected:
                print("      ❌ Portugal selectie mislukt na alle pogingen")
                return (None, None, None, None, None)
            
            # Step 3: Fill city (locality)
            print(f"      🏙️ Stad invullen: {city}")
            try:
                city_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "ember6"))
                )
                if city_element:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", city_element)
                    random_delay(0.3, 0.6)
                    self.human_type(city_element, city, driver)
                    print(f"      ✓ Stad ingevuld: {city}")
                    # Live update: save city immediately
                    self.update_account_status(email, city=city)
                    random_delay(0.8, 1.2)
            except:
                try:
                    city_element = driver.find_elements(By.ID, "ember6")
                    if city_element:
                        city_element = city_element[0]
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", city_element)
                        random_delay(0.3, 0.6)
                        self.human_type(city_element, city, driver)
                        print(f"      ✓ Stad ingevuld: {city}")
                        # Live update: save city immediately
                        self.update_account_status(email, city=city)
                        random_delay(0.8, 1.2)
                    else:
                        print("      ⚠️ Stad veld niet gevonden")
                except Exception as e:
                    print(f"      ⚠️ Stad veld niet gevonden: {e}")
            
            # Step 4: Fill address
            print(f"      📍 Adres invullen: {address}")
            try:
                address_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "ember7"))
                )
                if address_element:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", address_element)
                    random_delay(0.3, 0.6)
                    self.human_type(address_element, address, driver)
                    print(f"      ✓ Adres ingevuld: {address}")
                    # Live update: save address and house_number immediately
                    self.update_account_status(email, address=address, house_number=house_number)
                    random_delay(0.8, 1.2)
            except:
                try:
                    address_element = driver.find_elements(By.ID, "ember7")
                    if address_element:
                        address_element = address_element[0]
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", address_element)
                        random_delay(0.3, 0.6)
                        self.human_type(address_element, address, driver)
                        print(f"      ✓ Adres ingevuld: {address}")
                        # Live update: save address and house_number immediately
                        self.update_account_status(email, address=address, house_number=house_number)
                        random_delay(0.8, 1.2)
                    else:
                        print("      ⚠️ Adres veld niet gevonden")
                except Exception as e:
                    print(f"      ⚠️ Adres veld niet gevonden: {e}")
            
            # Step 5: Fill postal code
            print(f"      📮 Postcode invullen: {postal_code}")
            try:
                postal_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "ember8"))
                )
                if postal_element:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", postal_element)
                    random_delay(0.3, 0.6)
                    self.human_type(postal_element, postal_code, driver)
                    print(f"      ✓ Postcode ingevuld: {postal_code}")
                    # Live update: save postal_code immediately
                    self.update_account_status(email, postal_code=postal_code)
                    random_delay(0.8, 1.2)
            except:
                try:
                    postal_element = driver.find_elements(By.ID, "ember8")
                    if postal_element:
                        postal_element = postal_element[0]
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", postal_element)
                        random_delay(0.3, 0.6)
                        self.human_type(postal_element, postal_code, driver)
                        print(f"      ✓ Postcode ingevuld: {postal_code}")
                        # Live update: save postal_code immediately
                        self.update_account_status(email, postal_code=postal_code)
                        random_delay(0.8, 1.2)
                    else:
                        print("      ⚠️ Postcode veld niet gevonden")
                except Exception as e:
                    print(f"      ⚠️ Postcode veld niet gevonden: {e}")
            
            # Step 6: Fill NIF
            print(f"      🆔 NIF invullen: {nif}")
            try:
                nif_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "ember9"))
                )
                if nif_element:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", nif_element)
                    random_delay(0.3, 0.6)
                    self.human_type(nif_element, nif, driver)
                    print(f"      ✓ NIF ingevuld: {nif}")
                    # Live update: save nif immediately
                    self.update_account_status(email, nif=nif)
                    random_delay(0.8, 1.2)
            except:
                try:
                    nif_element = driver.find_elements(By.ID, "ember9")
                    if nif_element:
                        nif_element = nif_element[0]
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", nif_element)
                        random_delay(0.3, 0.6)
                        self.human_type(nif_element, nif, driver)
                        print(f"      ✓ NIF ingevuld: {nif}")
                        # Live update: save nif immediately
                        self.update_account_status(email, nif=nif)
                        random_delay(0.8, 1.2)
                    else:
                        print("      ⚠️ NIF veld niet gevonden")
                except Exception as e:
                    print(f"      ⚠️ NIF veld niet gevonden: {e}")
            
            # Step 7: Select "Futebol" - exact volgens specificatie: klik op input.select2-search__field, dan op li
            print(f"      ⚽ Futebol selecteren...")
            random_delay(1.0, 2.0)
            
            futebol_selected = False
            try:
                # Eerst klik op input.select2-search__field
                search_field = driver.find_element(By.CSS_SELECTOR, "input.select2-search__field[placeholder='Seleciona uma ou mais modalidades']")
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_field)
                random_delay(0.3, 0.6)
                search_field.click()
                random_delay(0.5, 1.0)
                
                # Dan klik op li met "Futebol" en id zoals select2-k3z6-result-kbzh-1
                futebol_option = None
                options = driver.find_elements(By.CSS_SELECTOR, "li.select2-results__option.select2-results__option--highlighted")
                for option in options:
                    option_id = option.get_attribute("id") or ""
                    option_text = option.text or ""
                    if "Futebol" in option_text:
                        futebol_option = option
                        break
                
                if not futebol_option:
                    # Fallback: zoek in alle options
                    all_options = driver.find_elements(By.CSS_SELECTOR, "li.select2-results__option")
                    for option in all_options:
                        if "Futebol" in (option.text or ""):
                            futebol_option = option
                            break
                
                if futebol_option:
                    futebol_option.click()
                    print("      ✓ Futebol geselecteerd")
                    futebol_selected = True
                    random_delay(0.8, 1.2)
                else:
                    print("      ⚠️ Futebol option niet gevonden")
            except Exception as e:
                print(f"      ⚠️ Fout bij selecteren Futebol: {e}")
            
            if not futebol_selected:
                print("      ❌ Kon Futebol niet selecteren")
            
            # Step 8: Select "Sim, jogo/já joguei com amigos" - exact volgens specificatie
            print(f"      ✅ 'Sim, jogo/já joguei com amigos' selecteren...")
            random_delay(1.0, 2.0)
            
            try:
                # Zoek span met id zoals select2-x5x1-container en title "Selecione uma opção"
                experiencia_container = None
                all_spans = driver.find_elements(By.CSS_SELECTOR, "span.select2-selection__rendered")
                for span in all_spans:
                    span_id = span.get_attribute("id") or ""
                    span_title = span.get_attribute("title") or ""
                    if "Selecione uma opção" in span_title and "container" in span_id:
                        experiencia_container = span
                        break
                
                if experiencia_container:
                    # Klik op de span
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", experiencia_container)
                    random_delay(0.3, 0.6)
                    experiencia_container.click()
                    random_delay(0.5, 1.0)
                    
                    # Klik op li met id zoals select2-x5x1-result-hgtl-3 en tekst "Sim, jogo/já joguei com amigos"
                    experiencia_option = None
                    options = driver.find_elements(By.CSS_SELECTOR, "li.select2-results__option")
                    for option in options:
                        option_id = option.get_attribute("id") or ""
                        option_text = option.text or ""
                        if "Sim, jogo" in option_text and "3" in option_id:
                            experiencia_option = option
                            break
                    
                    if not experiencia_option:
                        # Fallback: zoek gewoon naar de tekst
                        for option in options:
                            if "Sim, jogo" in (option.text or ""):
                                experiencia_option = option
                                break
                    
                    if experiencia_option:
                        experiencia_option.click()
                        print("      ✓ 'Sim, jogo/já joguei com amigos' geselecteerd")
                        random_delay(0.8, 1.2)
                    else:
                        print("      ⚠️ 'Sim, jogo/já joguei com amigos' option niet gevonden")
                else:
                    print("      ❌ Tweede dropdown container niet gevonden")
                    
            except Exception as e:
                print(f"      ⚠️ Fout bij selecteren tweede dropdown: {e}")
                import traceback
                traceback.print_exc()
            
            # Step 9: Click Continue button (Continuar) - exact selector: input.btn.btn-green met value="Continuar"
            print(f"      ▶️ Continuar button klikken...")
            continue_button = None
            try:
                # Exact selector: input.btn.btn-green met type="submit" en value="Continuar"
                continue_button = driver.find_element(By.CSS_SELECTOR, "input.btn.btn-green[type='submit'][value='Continuar']")
            except:
                try:
                    # Fallback: zoek gewoon naar input met value="Continuar"
                    continue_button = driver.find_element(By.CSS_SELECTOR, "input[value='Continuar']")
                except:
                    print("      ⚠️ Continuar button niet gevonden met exacte selector")
            
            if continue_button:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", continue_button)
                random_delay(0.5, 1.0)
                continue_button.click()
                print("      ✓ Continuar button geklikt")
                random_delay(3.0, 4.0)
                
                # Update CSV: account created = account=ja, maar signup nog niet (wordt pas later gezet na messenger)
                self.update_account_status(
                    email,
                    account=True,  # Account is aangemaakt
                    signup=False,  # Signup nog niet gedaan
                    city=city,
                    address=address,
                    postal_code=postal_code,
                    nif=nif,
                    house_number=house_number
                )
                
                return (city, address, postal_code, nif, house_number)
            else:
                print("      ❌ Continue button niet gevonden")
                return (None, None, None, None, None)
            
        except Exception as e:
            print(f"      ❌ Additional details error: {e}")
            import traceback
            traceback.print_exc()
            return (None, None, None, None, None)
    
    def _fill_personal_info(self, driver, first_name: str, last_name: str, birthdate: str, phone_number: str) -> bool:
        """Fill personal information form"""
        try:
            # First name
            first_name_element = self._wait_for_element(driver, "id", "givenName")
            if first_name_element:
                random_delay(0.5, 1.0)
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", first_name_element)
                random_delay(0.3, 0.6)
                self.human_type(first_name_element, first_name, driver)
                print(f"      ✓ Voornaam ingevuld: {first_name}")
                random_delay(0.8, 1.2)
            
            # Last name
            last_name_element = self._wait_for_element(driver, "id", "surname")
            if last_name_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", last_name_element)
                random_delay(0.3, 0.6)
                self.human_type(last_name_element, last_name, driver)
                print(f"      ✓ Achternaam ingevuld: {last_name}")
                random_delay(0.8, 1.2)
            
            # Phone prefix - select "Portugal" (PT)
            phone_prefix_element = self._wait_for_element(driver, "id", "extension_PhonePrefix")
            if phone_prefix_element:
                random_delay(0.5, 1.0)
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", phone_prefix_element)
                random_delay(0.3, 0.6)
                
                select = Select(phone_prefix_element)
                try:
                    select.select_by_value("PT")  # Portugal
                    print("      ✓ Telefoon prefix geselecteerd: Portugal")
                    random_delay(0.8, 1.2)
                except:
                    # Try by visible text
                    try:
                        select.select_by_visible_text("Portugal +351")
                        print("      ✓ Telefoon prefix geselecteerd: Portugal")
                        random_delay(0.8, 1.2)
                    except Exception as e:
                        print(f"      ⚠️ Kon telefoon prefix niet selecteren: {e}")
            
            # Phone number field (if exists after prefix)
            print(f"      📱 Zoeken naar telefoonnummer veld...")
            phone_selectors = [
                ("id", "extension_Mobile"),  # Priority 1: Direct ID (fastest and most human-like)
                ("css", "input#extension_Mobile"),  # CSS version of ID
                ("css", "input[type='text'][id*='Mobile']"),  # CSS contains ID
                ("css", "input[type='text'][name*='Mobile']"),  # CSS contains name
                ("css", "input[aria-label*='telemóvel' i]"),  # CSS by aria-label (case-insensitive)
                ("css", "input[placeholder*='telemóvel' i]"),  # CSS by placeholder
                ("css", "input[title*='telemóvel' i]"),  # CSS by title
                ("css", "input[type='tel']"),  # CSS by type
                ("id", "extension_PhoneNumber"),  # Alternative ID
                ("name", "phoneNumber"),  # By name
                ("name", "extension_PhoneNumber"),  # By name
                ("xpath", "//input[contains(@id, 'Mobile')]"),  # XPath fallback
                ("css", "input[id='extension_Mobile']"),
                ("css", "input[type='tel']"),
                ("css", "input[name*='Phone']"),
                ("css", "input[name*='phone']"),
                ("css", "input[id*='Phone']"),
                ("css", "input[id*='phone']"),
                ("css", "input[id*='Mobile']"),
                ("xpath", "//input[@type='tel']"),
                ("xpath", "//input[contains(@name, 'Phone')]"),
                ("xpath", "//input[contains(@id, 'Phone')]"),
                ("xpath", "//input[contains(@id, 'Mobile')]"),
            ]
            phone_element = None
            for selector_type, selector in phone_selectors:
                print(f"      🔍 Proberen selector: {selector_type} = {selector}")
                phone_element = self._wait_for_element(driver, selector_type, selector, timeout=5)
                if phone_element:
                    print(f"      ✓ Telefoonnummer veld gevonden met {selector_type}: {selector}")
                    break
            
            if phone_element:
                random_delay(0.5, 1.0)
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", phone_element)
                random_delay(0.3, 0.6)
                
                # Click on the field first to focus it
                try:
                    phone_element.click()
                    random_delay(0.2, 0.4)
                except:
                    # If click fails, try JavaScript click
                    try:
                        driver.execute_script("arguments[0].click();", phone_element)
                        random_delay(0.2, 0.4)
                    except:
                        pass
                
                # Clear any existing value
                try:
                    phone_element.clear()
                    random_delay(0.2, 0.4)
                except:
                    # If clear fails, try JavaScript clear
                    try:
                        driver.execute_script("arguments[0].value = '';", phone_element)
                        random_delay(0.2, 0.4)
                    except:
                        pass
                
                # Type phone number
                self.human_type(phone_element, phone_number, driver)
                print(f"      ✓ Telefoonnummer ingevuld: {phone_number}")
                random_delay(0.8, 1.2)
                
                # Verify the number was entered
                try:
                    entered_value = phone_element.get_attribute('value')
                    if entered_value != phone_number:
                        print(f"      ⚠️ Waarschuwing: Ingevoerde waarde ({entered_value}) komt niet overeen met verwachte waarde ({phone_number})")
                        # Try typing again
                        phone_element.clear()
                        random_delay(0.2, 0.4)
                        self.human_type(phone_element, phone_number, driver)
                        random_delay(0.5, 1.0)
                except:
                    pass
            else:
                print(f"      ❌ Telefoonnummer veld niet gevonden na alle selectors geprobeerd te hebben")
                # Try to find any input field that might be the phone field by looking at all inputs
                try:
                    all_inputs = driver.find_elements(By.TAG_NAME, "input")
                    print(f"      🔍 {len(all_inputs)} input velden gevonden op de pagina")
                    for i, inp in enumerate(all_inputs):
                        inp_id = inp.get_attribute('id') or ''
                        inp_name = inp.get_attribute('name') or ''
                        inp_type = inp.get_attribute('type') or ''
                        inp_placeholder = inp.get_attribute('placeholder') or ''
                        if any(term in (inp_id + inp_name + inp_placeholder).lower() for term in ['phone', 'tel', 'telefone', 'telemovel']):
                            print(f"      💡 Mogelijk telefoonnummer veld gevonden: id={inp_id}, name={inp_name}, type={inp_type}, placeholder={inp_placeholder}")
                            phone_element = inp
                            # Try to use this field
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", phone_element)
                            random_delay(0.3, 0.6)
                            self.human_type(phone_element, phone_number, driver)
                            print(f"      ✓ Telefoonnummer ingevuld in gevonden veld: {phone_number}")
                            random_delay(0.8, 1.2)
                            break
                    if not phone_element:
                        print(f"      ❌ Kon geen telefoonnummer veld vinden")
                        return False
                except Exception as e:
                    print(f"      ❌ Fout bij zoeken naar telefoonnummer veld: {e}")
                    return False
            
            # Birthdate - use datepicker instead of typing
            if not self._select_birthdate_from_picker(driver, birthdate):
                # Fallback to typing if datepicker fails
                birthdate_element = self._wait_for_element(driver, "id", "extension_Birthdate", timeout=5)
                if birthdate_element:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", birthdate_element)
                    random_delay(0.3, 0.6)
                    self.human_type(birthdate_element, birthdate, driver)
                    print(f"      ✓ Geboortedatum ingevuld (typing fallback): {birthdate}")
                    random_delay(0.8, 1.2)
            
            # Gender - random select
            gender_element = self._wait_for_element(driver, "id", "extension_Gender")
            if gender_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", gender_element)
                random_delay(0.3, 0.6)
                select = Select(gender_element)
                options = [opt.get_attribute('value') for opt in select.options if opt.get_attribute('value')]
                if options:
                    random_gender = random.choice(options)
                    select.select_by_value(random_gender)
                    print(f"      ✓ Geslacht geselecteerd: {random_gender}")
                    random_delay(0.8, 1.2)
            
            # Nationality - select "Portugal"
            nationality_element = self._wait_for_element(driver, "id", "country")
            if nationality_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", nationality_element)
                random_delay(0.3, 0.6)
                select = Select(nationality_element)
                try:
                    select.select_by_value("PT")
                    print("      ✓ Nationaliteit geselecteerd: Portugal")
                    random_delay(0.8, 1.2)
                except:
                    try:
                        select.select_by_visible_text("Portugal")
                        print("      ✓ Nationaliteit geselecteerd: Portugal")
                        random_delay(0.8, 1.2)
                    except Exception as e:
                        print(f"      ⚠️ Kon nationaliteit niet selecteren: {e}")
            
            # Country of residence - select "Portugal"
            residence_element = self._wait_for_element(driver, "id", "extension_CountryResidence")
            if residence_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", residence_element)
                random_delay(0.3, 0.6)
                select = Select(residence_element)
                try:
                    select.select_by_value("PT")
                    print("      ✓ Land van verblijf geselecteerd: Portugal")
                    random_delay(0.8, 1.2)
                except:
                    try:
                        select.select_by_visible_text("Portugal")
                        print("      ✓ Land van verblijf geselecteerd: Portugal")
                        random_delay(0.8, 1.2)
                    except Exception as e:
                        print(f"      ⚠️ Kon land van verblijf niet selecteren: {e}")
            
            # Marketing consent - select "Não" (No)
            marketing_element = self._wait_for_element(driver, "id", "extension_mkt_ok_False")
            if marketing_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", marketing_element)
                random_delay(0.3, 0.6)
                self.human_click(driver, marketing_element)
                print("      ✓ Marketing toestemming: Nee")
                random_delay(0.8, 1.2)
            
            # Terms and conditions checkbox
            tc_element = self._wait_for_element(driver, "id", "extension_tc_accepted_true")
            if tc_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", tc_element)
                random_delay(0.3, 0.6)
                self.human_click(driver, tc_element)
                print("      ✓ Terms and conditions geaccepteerd")
                random_delay(0.8, 1.2)
            
            # Final continue button
            continue_element = self._wait_for_element(driver, "id", "continue")
            if continue_element:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", continue_element)
                random_delay(0.5, 1.0)
                self.human_click(driver, continue_element)
                print("      ✓ Formulier verzonden")
                random_delay(3.0, 4.0)
                return True
            else:
                print("      ⚠️ Continue button niet gevonden")
                return False
                
        except Exception as e:
            print(f"      ❌ Personal info error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _fill_messenger_form(self, driver, task_number: int, first_name: str, email: str, phone_number: str, fan_number: str) -> bool:
        """Fill the messenger.engage-engine.com form after account registration (using iframe like Playwright example)"""
        try:
            print(f"[{task_number}] 📝 Messenger formulier invullen (met iframe)...")
            
            # Wait for page to load (already navigated in _execute_site_automation)
            WebDriverWait(driver, self.timeout_seconds).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            random_delay(2.0, 3.0)
            
            # Step 1: Wait for the iframe (like Playwright: wait_for_selector)
            iframe_selector = '#gameIframe'
            print(f"      ⏳ Wachten op iframe: {iframe_selector}")
            iframe = None
            try:
                iframe = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector))
                )
                print(f"      ✓ Iframe gevonden")
            except Exception as e:
                print(f"      ❌ Kon iframe {iframe_selector} niet vinden: {e}")
                return False
            
            # Step 2: Switch to iframe (Selenium equivalent of frame_locator)
            print(f"      🔄 Overschakelen naar iframe...")
            driver.switch_to.frame(iframe)
            random_delay(1.0, 2.0)
            
            # Step 3: Look for 'Pedir', 'pendir', or 'CONTACTAR' button (retry logic like Playwright)
            print(f"      🔍 Zoeken naar 'PEDIR' button in iframe (retry logic)...")
            pedir_button = None
            max_retries = 10
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    # Try different button selectors (like Playwright example)
                    # 1. Button with text "PEDIR" (case insensitive)
                    all_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
                    for btn in all_buttons:
                        btn_text = (btn.text or "").upper()
                        if "PEDIR" in btn_text or "PENDIR" in btn_text or "CONTACTAR" in btn_text:
                            # Check if visible
                            if btn.is_displayed():
                                pedir_button = btn
                                print(f"      ✓ PEDIR button gevonden (poging {attempt + 1}/{max_retries}): '{btn.text}'")
                                break
                    
                    # 2. Try CSS selector button.startBTN
                    if not pedir_button:
                        try:
                            btn = driver.find_element(By.CSS_SELECTOR, "button.startBTN")
                            if btn.is_displayed():
                                pedir_button = btn
                                print(f"      ✓ PEDIR button gevonden via CSS (poging {attempt + 1}/{max_retries})")
                        except:
                            pass
                    
                    # 3. Try XPath: //*[@id="end-screen-wrapper"]/div/div[2]/div/button
                    if not pedir_button:
                        try:
                            btn = driver.find_element(By.XPATH, "//*[@id='end-screen-wrapper']/div/div[2]/div/button")
                            if btn.is_displayed():
                                pedir_button = btn
                                print(f"      ✓ PEDIR button gevonden via XPath (poging {attempt + 1}/{max_retries})")
                        except:
                            pass
                    
                    if pedir_button:
                        break
                    
                    if attempt < max_retries - 1:
                        print(f"      ⏳ PEDIR button nog niet zichtbaar, wachten {retry_delay}s... (poging {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"      ⚠️ Fout bij zoeken (poging {attempt + 1}): {e}, retry...")
                        time.sleep(retry_delay)
                    else:
                        print(f"      ❌ Fout bij zoeken naar PEDIR button: {e}")
            
            if pedir_button:
                print(f"      🔘 'PEDIR' button gevonden, klikken...")
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", pedir_button)
                random_delay(0.5, 1.0)
                
                # Wait for loader to disappear before clicking
                try:
                    loader_selector = "app-game-loader.loader"
                    WebDriverWait(driver, 10).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, loader_selector))
                    )
                    print(f"      ✓ Loader verdwenen, kan nu klikken")
                except:
                    # Loader might not exist or already gone, continue anyway
                    print(f"      ⚠️ Loader niet gevonden of al weg, doorgaan...")
                    random_delay(0.5, 1.0)
                
                # Try JavaScript click first (more reliable when element might be intercepted)
                try:
                    driver.execute_script("arguments[0].click();", pedir_button)
                    print(f"      ✓ 'PEDIR' button geklikt (via JavaScript)")
                except:
                    # Fallback to regular click
                    try:
                pedir_button.click()
                        print(f"      ✓ 'PEDIR' button geklikt (via Selenium)")
                    except Exception as e:
                        print(f"      ⚠️ Fout bij klikken PEDIR button: {e}")
                        # Last resort: try ActionChains
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            ActionChains(driver).move_to_element(pedir_button).click().perform()
                            print(f"      ✓ 'PEDIR' button geklikt (via ActionChains)")
                        except:
                            print(f"      ❌ Kon PEDIR button niet klikken na alle pogingen")
                
                random_delay(3.0, 5.0)
            else:
                print(f"      ⚠️ PEDIR button niet gevonden na {max_retries} pogingen, misschien al op form pagina")
            
            # Step 4: Wait for form to appear in iframe (like Playwright: wait_for state="visible")
            print(f"      ⏳ Wachten op formulier in iframe...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "text"))
                )
                random_delay(1.0, 2.0)
                print(f"      ✓ Formulier gevonden in iframe")
            except:
                print(f"      ⚠️ Form veld niet gevonden, maar doorgaan...")
            
            # Step 5: Fill name - exact selector: input[placeholder="Escreve o teu nome"][id="text"]
            print(f"      👤 Naam invullen: {first_name}")
            name_input = None
            try:
                # Exact selector: input met placeholder "Escreve o teu nome" en id="text"
                name_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Escreve o teu nome'][id='text']"))
                )
                print(f"      ✓ Naam input gevonden via exacte selector")
            except:
                # Fallback: try by placeholder only
                try:
                    name_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='Escreve o teu nome']")
                    print(f"      ✓ Naam input gevonden via placeholder")
                except:
                    # Last fallback: try by ID
                    try:
                        # Find all input#text and check placeholder
                        all_text_inputs = driver.find_elements(By.CSS_SELECTOR, "input#text")
                        for inp in all_text_inputs:
                            placeholder = inp.get_attribute("placeholder") or ""
                            if "nome" in placeholder.lower():
                                name_input = inp
                                break
                        if not name_input and all_text_inputs:
                            name_input = all_text_inputs[0]  # First input#text
                    except:
                        pass
            
            if name_input:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", name_input)
                random_delay(0.3, 0.6)
                name_input.click()  # Click first (like user said)
                random_delay(0.2, 0.4)
                self.human_type(name_input, first_name, driver)
                print(f"      ✓ Naam ingevuld: {first_name}")
                random_delay(0.8, 1.2)
            else:
                print(f"      ⚠️ Naam input niet gevonden")
            
            # Step 6: Fill email - exact selector: input[type="email"][id="email"][placeholder="exemplo@gmail.com"]
            print(f"      📧 Email invullen: {email}")
            email_input = None
            try:
                # Exact selector: input met type="email", id="email", placeholder="exemplo@gmail.com"
                email_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'][id='email']"))
                )
                print(f"      ✓ Email input gevonden via exacte selector")
            except:
                # Fallback: try by ID only
                try:
                    email_input = driver.find_element(By.ID, "email")
                    print(f"      ✓ Email input gevonden via ID")
                except:
                    pass
            
            if email_input:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", email_input)
                random_delay(0.3, 0.6)
                email_input.click()  # Click first (like user said)
                random_delay(0.2, 0.4)
                self.human_type(email_input, email, driver)
                print(f"      ✓ Email ingevuld: {email}")
                random_delay(0.8, 1.2)
            else:
                print(f"      ⚠️ Email input niet gevonden")
            
            # Step 7: Fill phone number - exact selector: input[type="tel"][class*="text text_12"][placeholder="123-45-67"]
            # Portugal +351 is al automatisch geselecteerd, vul alleen nummer in
            print(f"      📱 Telefoonnummer invullen: {phone_number}")
            phone_input = None
            try:
                # Exact selector: input[type="tel"] met class "text text_12"
                phone_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel'][class*='text text_12']"))
                )
                print(f"      ✓ Telefoonnummer input gevonden via exacte selector")
            except:
                # Fallback: try by type only
                try:
                    phone_input = driver.find_element(By.CSS_SELECTOR, "input[type='tel']")
                    print(f"      ✓ Telefoonnummer input gevonden via type")
                except:
                    pass
            
            if phone_input:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", phone_input)
                random_delay(0.3, 0.6)
                phone_input.click()  # Click first (like user said)
                random_delay(0.2, 0.4)
                self.human_type(phone_input, phone_number, driver)
                print(f"      ✓ Telefoonnummer ingevuld: {phone_number}")
                random_delay(0.8, 1.2)
            else:
                print(f"      ⚠️ Telefoonnummer input niet gevonden")
            
            # Step 8: Fill fan number - exact selector: input[placeholder="Escreve o teu número de fã"][id="text"]
            if fan_number:
                print(f"      🎫 Fan number invullen: {fan_number}")
                fan_input = None
                try:
                    # Exact selector: input met placeholder "Escreve o teu número de fã" en id="text"
                    fan_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Escreve o teu número de fã'][id='text']"))
                    )
                    print(f"      ✓ Fan number input gevonden via exacte selector")
                except:
                    # Fallback: find by placeholder containing "número de fã"
                    try:
                        all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                        for inp in all_inputs:
                            placeholder = inp.get_attribute("placeholder") or ""
                            if "número de fã" in placeholder.lower():
                                fan_input = inp
                                break
                    except:
                        pass
                    
                    # Last fallback: find input#text with fan placeholder
                    if not fan_input:
                        try:
                            all_text_inputs = driver.find_elements(By.CSS_SELECTOR, "input#text")
                            for inp in all_text_inputs:
                                placeholder = inp.get_attribute("placeholder") or ""
                                if "fã" in placeholder.lower():
                                    fan_input = inp
                                    break
                        except:
                            pass
                
                if fan_input:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", fan_input)
                    random_delay(0.3, 0.6)
                    fan_input.click()  # Click first (like user said)
                    random_delay(0.2, 0.4)
                    self.human_type(fan_input, fan_number, driver)
                    print(f"      ✓ Fan number ingevuld: {fan_number}")
                    random_delay(0.8, 1.2)
                else:
                    print(f"      ⚠️ Fan number input niet gevonden")
            else:
                print(f"      ⚠️ Fan number niet beschikbaar, veld wordt overgeslagen")
            
            # Step 9: Select Portugal from country dropdown - exact selector: span.mat-mdc-select-placeholder met tekst
            print(f"      🌍 Portugal selecteren...")
            try:
                # Klik op span met class "mat-mdc-select-placeholder" en tekst "Escolhe o teu país de residência"
                country_span = None
                try:
                    # Try to find span with exact text
                    all_spans = driver.find_elements(By.CSS_SELECTOR, "span.mat-mdc-select-placeholder")
                    for span in all_spans:
                        span_text = span.text or ""
                        if "Escolhe o teu país" in span_text or "país de residência" in span_text:
                            country_span = span
                            break
                except:
                    pass
                
                if not country_span:
                    # Fallback: find any span with class
                    try:
                        country_span = driver.find_element(By.CSS_SELECTOR, "span.mat-mdc-select-placeholder")
                    except:
                        # Last fallback: find mat-select and click it
                        try:
                            country_select = driver.find_element(By.CSS_SELECTOR, "mat-select")
                            if country_select:
                                country_select.click()
                                random_delay(1.0, 1.5)
                        except:
                            pass
                
                if country_span:
                    # Klik op de span om dropdown te openen
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", country_span)
                    random_delay(0.3, 0.6)
                    country_span.click()
                    print(f"      ✓ Country dropdown geopend")
                    random_delay(1.0, 1.5)
                
                # Klik op mat-option met id="mat-option-246" en tekst "🇵🇹 Portugal"
                portugal_option = None
                try:
                    # Try ID first (exact match)
                    portugal_option = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "mat-option-246"))
                    )
                    print(f"      ✓ Portugal option gevonden via ID")
                except:
                    # Fallback: zoek op tekst "🇵🇹 Portugal" of "Portugal"
                    try:
                        all_options = driver.find_elements(By.CSS_SELECTOR, "mat-option")
                        for opt in all_options:
                            opt_text = opt.text or ""
                            if "🇵🇹 Portugal" in opt_text or ("Portugal" in opt_text and "🇵🇹" in opt_text):
                                portugal_option = opt
                                print(f"      ✓ Portugal option gevonden via tekst")
                                break
                    except:
                        pass
                
                if portugal_option:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", portugal_option)
                    random_delay(0.3, 0.6)
                    portugal_option.click()
                    print(f"      ✓ Portugal geselecteerd")
                    random_delay(0.8, 1.2)
                else:
                    print(f"      ⚠️ Portugal optie niet gevonden")
            except Exception as e:
                print(f"      ⚠️ Fout bij selecteren Portugal: {e}")
                import traceback
                traceback.print_exc()
            
            # Step 10: Click SUBMETER button - exact selector: button[id="button"][class*="btn_"]
            print(f"      ▶️ SUBMETER button klikken...")
            submit_button = None
            try:
                # Exact selector: button met id="button" en class "btn_"
                submit_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[id='button'][class*='btn_']"))
                )
                print(f"      ✓ SUBMETER button gevonden via exacte selector")
            except:
                # Fallback: try by ID
                try:
                    submit_button = driver.find_element(By.ID, "button")
                    print(f"      ✓ SUBMETER button gevonden via ID")
                except:
                    # Last fallback: try by class
                    try:
                        submit_button = driver.find_element(By.CSS_SELECTOR, "button.btn_")
                        print(f"      ✓ SUBMETER button gevonden via class")
                    except:
                        pass
            
            if submit_button:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_button)
                random_delay(0.5, 1.0)
                submit_button.click()
                print(f"      ✓ SUBMETER button geklikt")
                random_delay(3.0, 5.0)
                
                # Check for success message - exact tekst: "Após validação dos dados, os fãs que cumpram todos os requisitos receberão um código. O preenchimento do formulário não garante o acesso à compra."
                print(f"      🔍 Controleren op success message...")
                success_found = False
                try:
                    # Zoek naar p element met class "title subtitle" met de specifieke tekst
                    all_p_elements = driver.find_elements(By.CSS_SELECTOR, "p.title.subtitle")
                    for elem in all_p_elements:
                        elem_text = elem.text or ""
                        if "Após validação dos dados" in elem_text or "validação dos dados" in elem_text:
                            success_found = True
                            print(f"      ✅ Success message gevonden! Signup voltooid.")
                            break
                except:
                    pass
                
                if success_found:
                    # Send Discord webhook notification (same webhook as Lysted monitor)
                    try:
                        webhook_url = self.site_config.get('discord', {}).get('finished_webhook', '')
                        if webhook_url:
                            embed = {
                                "title": "✅ Portugal FPF Signup Succesvol",
                                "description": f"**Email:** {email}\n\nSignup succesvol afgerond!",
                                "color": 0x00ff00,  # Green color
                                "timestamp": datetime.utcnow().isoformat(),
                                "footer": {
                                    "text": "ADJEHOUSE Portugal FPF Automation"
                                }
                            }
                            
                            payload = {"embeds": [embed]}
                            response = requests.post(webhook_url, json=payload, timeout=10)
                            response.raise_for_status()
                            print(f"      ✅ Discord webhook verstuurd voor {email}")
                        else:
                            print(f"      ⚠️ Geen Discord webhook URL geconfigureerd")
                    except Exception as webhook_error:
                        print(f"      ⚠️ Fout bij versturen Discord webhook: {webhook_error}")
                else:
                    print(f"      ⚠️ Success message niet gevonden met exacte tekst")
                
                # Switch back to main content before returning
                driver.switch_to.default_content()
                return success_found  # Return True alleen als success message gevonden is
            else:
                print(f"      ❌ SUBMETER button niet gevonden")
                driver.switch_to.default_content()
                return False
                
        except Exception as e:
            print(f"      ❌ Messenger formulier error: {e}")
            import traceback
            traceback.print_exc()
            try:
                driver.switch_to.default_content()
            except:
                pass
            return False
    
    def _execute_site_automation(self, driver, site_config: Dict[str, Any], account_data: Dict[str, str], task_number: int) -> bool:
        """Execute the full Portugal FPF registration flow"""
        # Check stop event at the start (unless ignored for background signups)
        ignore_stop = getattr(self, '_ignore_stop_event', False)
        if not ignore_stop and self.stop_event.is_set():
            print(f"[{task_number}] 🛑 Stop signaal ontvangen - automation wordt overgeslagen")
            return False
        
        # Ensure driver has a page loaded (fix voor lege tab)
        # ALTIJD proberen site URL te laden als browser leeg is of als we niet op de juiste pagina zijn
        try:
            current_url = driver.current_url
            # Check if browser is empty or not on the target site
            is_empty = not current_url or current_url == "data:," or current_url == "about:blank"
            is_not_target = self.site_url and self.site_url not in current_url
            
            if is_empty or is_not_target:
                # Load site URL if browser is empty or not on target site
                if is_empty:
                    print(f"[{task_number}] 🔄 Browser is leeg, laad site URL...")
                else:
                    print(f"[{task_number}] 🔄 Browser niet op target site ({current_url}), laad site URL...")
                
                try:
                    driver.get(self.site_url)
                    random_delay(1.0, 2.0)
                    print(f"[{task_number}] ✅ Site URL succesvol geladen: {driver.current_url}")
                except Exception as nav_error:
                    print(f"[{task_number}] ⚠️ Fout bij laden site URL: {nav_error}")
                    # Retry once
                    try:
                        random_delay(1.0, 2.0)
                        driver.get(self.site_url)
                        random_delay(1.0, 2.0)
                        print(f"[{task_number}] ✅ Site URL succesvol geladen na retry: {driver.current_url}")
                    except Exception as retry_error:
                        print(f"[{task_number}] ❌ Kon site URL niet laden na retry: {retry_error}")
                        # Don't fail here, continue and let the main navigation handle it
        except Exception as e:
            # If we can't check/load URL, try to load site URL anyway
            try:
                print(f"[{task_number}] ⚠️ Fout bij checken URL, probeer site URL te laden: {e}")
                driver.get(self.site_url)
                random_delay(1.0, 2.0)
                print(f"[{task_number}] ✅ Site URL succesvol geladen na exception: {driver.current_url}")
            except Exception as load_error:
                print(f"[{task_number}] ⚠️ Kon site URL niet laden in exception handler: {load_error}")
                # Continue anyway - main navigation will handle it
        
        try:
            email = account_data['email']
            
            # Check if account already exists (account=ja) but signup not done (signup=nee)
            # ALTIJD de nieuwste data uit CSV halen (background scanner kan fan_number hebben toegevoegd)
            account_exists = False
            first_name_retry = ''
            last_name_retry = ''
            phone_number_retry = ''
            password_retry = ''
            fan_number_retry = ''
            profile_id_retry = ''
            
            try:
                if self.accounts_file.exists():
                    with open(self.accounts_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('email') == email:
                                # Check both "entered" (old) and "account" (new) for backward compatibility
                                account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                                signup_done = row.get('signup', '').lower() == 'ja'
                                if account_made and not signup_done:
                                    account_exists = True
                                    # Load existing data (ALTIJD nieuwste data uit CSV)
                                    first_name_retry = row.get('first_name', '')
                                    last_name_retry = row.get('last_name', '')
                                    phone_number_retry = row.get('phone_number', '')
                                    password_retry = row.get('password', '')
                                    fan_number_retry = row.get('fan_number', '').strip()  # Strip whitespace
                                    profile_id_retry = row.get('profile_id', '').strip()  # Strip whitespace
                                    # Add profile_id to account_data for reuse
                                    account_data['profile_id'] = profile_id_retry
                                    print(f"[{task_number}] ℹ️ Account bestaat al (account=ja, signup=nee), direct naar signup pagina...")
                                    print(f"[{task_number}] 📋 CSV data: fan_number={fan_number_retry}, profile_id={profile_id_retry}")
                                    break
            except Exception as e:
                print(f"[{task_number}] ⚠️ Fout bij checken account status: {e}")
            
            if account_exists:
                # Account bestaat al, skip registratie en ga direct naar messenger signup URL
                print(f"[{task_number}] ℹ️ Account bestaat al (account=ja, signup=nee)")
                
                # Use existing data from CSV (ALTIJD nieuwste data - background scanner kan fan_number hebben toegevoegd)
                email = account_data.get('email', '')  # Zeker weten dat email gevuld is!
                first_name = first_name_retry if first_name_retry else account_data.get('first_name', '')
                phone_number = phone_number_retry if phone_number_retry else account_data.get('phone_number', '')
                fan_number = fan_number_retry.strip() if fan_number_retry else account_data.get('fan_number', '').strip()
                
                if not email:
                    print(f"[{task_number}] ❌ Fout: Geen email gevonden voor dit account!")
                    return False
                
                # ALTIJD opnieuw checken in CSV voor fan_number (background scanner kan het net hebben toegevoegd)
                print(f"[{task_number}] 🔍 Opnieuw checken in CSV voor fan_number (background scanner kan het net hebben toegevoegd)...")
                if self.accounts_file.exists():
                    with open(self.accounts_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('email') == email:
                                csv_fan_number = row.get('fan_number', '').strip()
                                if csv_fan_number and csv_fan_number.lower() != 'nee':
                                    if csv_fan_number != fan_number:
                                        print(f"[{task_number}] ✅ Fan number gevonden in CSV (door background scanner): {csv_fan_number} (was: {fan_number})")
                                    fan_number = csv_fan_number
                                    break
                
                # Check if fan_number exists - als niet, skip direct
                if not fan_number or fan_number.strip() == '' or fan_number.lower() == 'nee':
                    print(f"[{task_number}] ⚠️ Geen fan_number in CSV gevonden")
                    print(f"[{task_number}] ⏭️ Account wordt overgeslagen (fan_number wordt later opgehaald door background scanner)")
                    self.update_account_status(email, skip_reason='geen_fan_number')
                    return "SKIP"  # Skip dit account, ga door met volgende
                
                print(f"[{task_number}] ✅ Fan number beschikbaar: {fan_number}")
                
                # Fan number is er, direct naar signup pagina
                messenger_url = "https://messenger.engage-engine.com/?cid=1261051&aid=14026&medium=GAME_ZONE&identifier=1762790719.3316&bid=1762790792140&skip_messenger=true"
                print(f"[{task_number}] 📍 Navigeren naar messenger signup pagina: {messenger_url}")
                try:
                    driver.get(messenger_url)
                    random_delay(3.0, 5.0)
                    
                    # Check if we're on the contacts page (should skip this account)
                    current_url = driver.current_url.lower()
                    if '/contacts' in current_url and 'pico_identifier' in current_url:
                        print(f"[{task_number}] ⚠️ Contacts pagina gedetecteerd na messenger navigatie: {driver.current_url}")
                        print(f"[{task_number}] ⏭️ Account wordt overgeslagen (contacts pagina)")
                        self.update_account_status(email, skip_reason='contacts_pagina')
                        return "SKIP"
                    
                    # Check for landing page after navigation
                    current_url = driver.current_url.lower()
                    if '/landing' in current_url or 'portugal.fpf.pt/landing' in current_url:
                        print(f"[{task_number}] ⚠️ Landing pagina gedetecteerd op messenger pagina: {driver.current_url}")
                        print(f"[{task_number}] 🔄 Nieuw profiel nodig - oude profiel wordt verwijderd en opnieuw geprobeerd")
                        return "LANDING_PAGE_RETRY"  # Signal to retry with new profile
                    
                    # Check for IP ban after navigation
                    if self._check_for_ip_ban(driver):
                        print(f"[{task_number}] ⚠️ IP BAN gedetecteerd op messenger pagina, nieuw profiel met andere proxy nodig")
                        return "IP_BANNED_RETRY"  # Signal to retry with new profile
                except WebDriverException as e:
                    error_msg = str(e).lower()
                    if 'err_tunnel_connection_failed' in error_msg or 'proxy' in error_msg:
                        print(f"      ❌ Proxy verbindingsfout: {e}")
                        print(f"      ⚠️ Sluit browser en probeer opnieuw met andere proxy")
                        return False
                    else:
                        raise
                
                # Fill messenger form directly
                print(f"[{task_number}] 📝 Messenger formulier invullen...")
                messenger_success = self._fill_messenger_form(
                    driver, 
                    task_number, 
                    first_name, 
                    email, 
                    phone_number, 
                    fan_number
                )
                
                if messenger_success:
                    self.update_account_status(email, signup=True)
                    print(f"[{task_number}] ✅ Signup volledig voltooid!")
                else:
                    print(f"[{task_number}] ⚠️ Messenger formulier niet succesvol ingevuld")
                    print(f"[{task_number}] ℹ️ Je kunt later opnieuw proberen - script zal automatisch naar signup pagina gaan")
                
                return messenger_success
            
            # NEW ACCOUNT FLOW - continue with registration
            # Generate Portuguese names if not provided
            first_name = account_data.get('first_name', '')
            if not first_name or first_name.lower() == 'nee':
                first_name = self.generate_portuguese_first_name()
                print(f"[{task_number}] 👤 Portugese voornaam gegenereerd: {first_name}")
            
            last_name = account_data.get('last_name', '')
            if not last_name or last_name.lower() == 'nee':
                last_name = self.generate_portuguese_last_name()
                print(f"[{task_number}] 👤 Portugese achternaam gegenereerd: {last_name}")
            
            # Use default password or provided password
            password = account_data.get('password', '')
            if not password or password.lower() == 'nee':
                password = self.default_password
                print(f"[{task_number}] 🔑 Standaard wachtwoord gebruikt: {password}")
            else:
                print(f"[{task_number}] 🔑 Gebruiker wachtwoord gebruikt: {password}")
            
            # Generate birthdate if not provided (must be >20 years old, minimum 21)
            birthdate = account_data.get('birthdate', '')
            if not birthdate or birthdate.lower() == 'nee':
                birthdate = self.generate_birthdate()
                print(f"[{task_number}] 📅 Geboortedatum gegenereerd: {birthdate}")
            
            # Generate phone number if not provided, and track it
            phone_number = account_data.get('phone_number', '')
            if not phone_number or phone_number.lower() == 'nee':
                phone_number = self.generate_phone_number()
                print(f"[{task_number}] 📱 Nieuw Portugees mobielnummer gegenereerd: {phone_number}")
            else:
                # If phone number exists in CSV, mark it as used
                self.used_phone_numbers.add(phone_number)
                print(f"[{task_number}] 📱 Bestaand telefoonnummer gebruikt: {phone_number}")
            
            # Navigate to site (proxy is configured via Dolphin profile, not Chrome options)
            # ALTIJD navigeren naar site, zelfs als we denken dat we er al zijn
            print(f"[{task_number}] 📍 Navigeren naar {self.site_url}")
            navigation_success = False
            max_nav_retries = 3
            
            # Check current URL first
            try:
                current_url_before = driver.current_url
                print(f"[{task_number}] 🔍 Huidige URL voor navigatie: {current_url_before}")
            except:
                current_url_before = "unknown"
                print(f"[{task_number}] ⚠️ Kon huidige URL niet ophalen")
            
            for nav_attempt in range(1, max_nav_retries + 1):
            try:
                # Apply additional stealth headers before navigation
                self._apply_stealth_headers(driver)
                
                    print(f"[{task_number}] 🔄 Navigatie poging {nav_attempt}/{max_nav_retries} naar {self.site_url}...")
                driver.get(self.site_url)
                
                    # Wait for page to load and verify it's not empty
                random_delay(2.0, 3.0)
                
                    # Verify page loaded successfully
                    try:
                        current_url = driver.current_url
                        print(f"[{task_number}] ✅ Navigatie voltooid, huidige URL: {current_url}")
                        
                        if current_url and current_url != "data:," and current_url != "about:blank":
                            # Check if we're actually on the target site
                            if self.site_url in current_url or "portugal.fpf.pt" in current_url:
                                navigation_success = True
                                print(f"[{task_number}] ✅ Succesvol genavigeerd naar target site")
                                break
                            else:
                                print(f"[{task_number}] ⚠️ Niet op target site (huidige URL: {current_url}), retry...")
                        else:
                            print(f"[{task_number}] ⚠️ Pagina niet correct geladen (leeg/blank), retry...")
                    except Exception as url_check_error:
                        print(f"[{task_number}] ⚠️ Fout bij checken URL na navigatie: {url_check_error}")
                    
                    if nav_attempt < max_nav_retries:
                        print(f"[{task_number}] ⏳ Wachten 2 seconden voor retry...")
                        time.sleep(2.0)
                        continue
                    else:
                        print(f"[{task_number}] ⚠️ Max navigatie retries bereikt, maar doorgaan...")
                        
                except (TimeoutException, WebDriverException) as e:
                error_msg = str(e).lower()
                if 'err_tunnel_connection_failed' in error_msg or 'proxy' in error_msg:
                        print(f"[{task_number}] ❌ Proxy verbindingsfout: {e}")
                        print(f"[{task_number}] ⚠️ Sluit browser en probeer opnieuw met andere proxy")
                    return False
                    elif 'timeout' in error_msg or 'timed out' in error_msg:
                        print(f"[{task_number}] ⚠️ Timeout bij laden site (poging {nav_attempt}/{max_nav_retries}): {e}")
                        if nav_attempt < max_nav_retries:
                            time.sleep(2.0)
                            continue
                else:
                            print(f"[{task_number}] ❌ Kon site URL niet laden na {max_nav_retries} pogingen - browser blijft leeg")
                            return False
                    elif 'no such window' in error_msg or 'invalid session id' in error_msg:
                        print(f"[{task_number}] ⚠️ Browser gesloten tijdens navigatie")
                        return False
                    else:
                        print(f"[{task_number}] ⚠️ Fout bij navigatie (poging {nav_attempt}/{max_nav_retries}): {e}")
                        if nav_attempt < max_nav_retries:
                            time.sleep(2.0)
                            continue
                        else:
                    raise
            
            if not navigation_success:
                print(f"[{task_number}] ❌ Kon site URL niet laden na {max_nav_retries} pogingen - browser blijft leeg")
                return False
            
            # Simulate human scroll behavior before checking for captcha
            try:
                self._simulate_human_scroll(driver)
            except (NoSuchWindowException, InvalidSessionIdException, WebDriverException):
                print(f"[{task_number}] ⚠️ Browser gesloten tijdens scroll simulatie")
                return False
            
            # Check for IP ban and CAPTCHA
            print(f"[{task_number}] 🔍 Controleren op IP ban en CAPTCHA...")
            captcha_result = self._check_and_handle_captcha(driver, task_number)
            if captcha_result == "IP_BANNED" or captcha_result == "IP_BANNED_RETRY":
                print(f"[{task_number}] ⚠️ IP BAN/CAPTCHA gedetecteerd, nieuw profiel met andere proxy nodig")
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            
            # Check if we're on the contacts page (should skip this account)
            current_url = driver.current_url.lower()
            if '/contacts' in current_url and 'pico_identifier' in current_url:
                print(f"[{task_number}] ⚠️ Contacts pagina gedetecteerd: {driver.current_url}")
                print(f"[{task_number}] ⏭️ Account wordt overgeslagen (contacts pagina)")
                self.update_account_status(email, skip_reason='contacts_pagina')
                return "SKIP"
            
            # Check if we're on the landing page (https://portugal.fpf.pt/landing)
            if '/landing' in current_url or 'portugal.fpf.pt/landing' in current_url:
                print(f"[{task_number}] ⚠️ Landing pagina gedetecteerd: {driver.current_url}")
                print(f"[{task_number}] 🔄 Nieuw profiel nodig - oude profiel wordt verwijderd en opnieuw geprobeerd")
                return "LANDING_PAGE_RETRY"  # Signal to retry with new profile
            
            # Track last activity time for inactivity detection
            last_activity_time = time.time()
            inactivity_timeout = 60  # 1 minute
            waiting_for_otp = False  # Flag to disable inactivity check during OTP wait
            
            # Helper function to check for inactivity and IP ban
            def check_inactivity_and_ban():
                nonlocal last_activity_time, waiting_for_otp
                current_time = time.time()
                elapsed_inactive = current_time - last_activity_time
                
                # Check for IP ban (always check, even during OTP wait) - returns IP_BANNED not IP_BANNED_RETRY from helper
                if self._check_for_ip_ban(driver):
                    print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                    return "IP_BANNED_RETRY"  # Signal to retry with new profile
                
                # Skip inactivity check if we're waiting for OTP (can take longer than 1 minute)
                if waiting_for_otp:
                    return None
                
                # Check for inactivity
                if elapsed_inactive > inactivity_timeout:
                    print(f"[{task_number}] ⚠️ {elapsed_inactive:.0f} seconden inactiviteit gedetecteerd, pagina refreshen...")
                    try:
                        driver.refresh()
                        last_activity_time = time.time()
                        random_delay(0.5, 1.0)  # Sneller refreshen
                        print(f"[{task_number}] ✅ Pagina gerefreshed na inactiviteit")
                        
                        # Check for IP ban again after refresh
                        if self._check_for_ip_ban(driver):
                            print(f"[{task_number}] ⚠️ IP BAN nog steeds aanwezig na refresh, nieuw profiel nodig")
                            return "IP_BANNED_RETRY"  # Signal to retry with new profile
                    except Exception as e:
                        print(f"[{task_number}] ⚠️ Fout bij refreshen na inactiviteit: {e}")
                        return "INACTIVITY_ERROR"
                
                return None
            
            # Step 1: Accept cookies
            print(f"[{task_number}] 🍪 Cookie banner accepteren...")
            if not self._click_cookie_accept(driver):
                print("      ⚠️ Cookie accept failed, maar doorgaan...")
            last_activity_time = time.time()
            
            # Check for inactivity and IP ban
            check_result = check_inactivity_and_ban()
            if check_result in ["IP_BANNED", "INACTIVITY_ERROR"]:
                return "SKIP"
            
            # Wait for page to stabilize after cookie accept
            print(f"[{task_number}] ⏳ Wachten op vervolg pagina na cookie accept...")
            random_delay(2.0, 3.0)
            
            # Wait for page to be ready
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except:
                pass
            
            # Check for IP ban before proceeding
            if self._check_for_ip_ban(driver):
                print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            
            # Step 2: Click register button (if not already on form page)
            print(f"[{task_number}] 📝 Registratie button klikken...")
            if not self._click_register_button(driver):
                print("      ⚠️ Register button click failed, misschien al op form pagina")
            last_activity_time = time.time()
            
            # Check for inactivity and IP ban
            check_result = check_inactivity_and_ban()
            if check_result in ["IP_BANNED", "INACTIVITY_ERROR"]:
                return "SKIP"
            
            # Wait for next page to load (email input page)
            print(f"[{task_number}] ⏳ Wachten op vervolg pagina (email invoer)...")
            random_delay(2.0, 3.0)
            
            # Wait for email field to appear (indicates page loaded)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "email"))
                )
                print("      ✓ Vervolg pagina geladen (email veld zichtbaar)")
                last_activity_time = time.time()
            except:
                print("      ⚠️ Email veld nog niet zichtbaar, maar doorgaan...")
            
            # Check for IP ban before proceeding
            if self._check_for_ip_ban(driver):
                print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            
            # Step 3: IMAP login VOORDAT email wordt ingevuld (zo kunnen we vanaf dat moment monitoren)
            print(f"[{task_number}] 🔐 IMAP login VOORDAT email wordt ingevuld...")
            imap_start_time = datetime.now()
            print(f"[{task_number}] 🔐 Monitor start tijd: {imap_start_time}")
            
            # Initialize IMAP connection early (voorbereiden op monitoren)
            print(f"[{task_number}] 🔐 IMAP verbinding voorbereiden...")
            
            # Step 4: Fill email and submit (klikt eerst op email veld, vult dan in, klikt dan op button)
            print(f"[{task_number}] ✉️ Email invullen en versturen...")
            email_submit_result = self._fill_email_and_submit(driver, email)
            last_activity_time = time.time()
            
            # Check for IP ban after email submit
            if self._check_for_ip_ban(driver):
                print(f"[{task_number}] ⚠️ IP BAN gedetecteerd na email submit, nieuw profiel met andere proxy nodig")
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            if email_submit_result == "SKIP_EMAIL_EXISTS":
                # Email already exists - mark as account=ja and go directly to signup page
                print(f"[{task_number}] ⏭️ Email bestaat al, account wordt gemarkeerd en direct naar signup pagina...")
                # Update CSV: account bestaat al (account=ja), signup nog niet (signup=nee)
                self.update_account_status(email, account=True, signup=False)
                print(f"[{task_number}] 💾 CSV bijgewerkt: account=ja, signup=nee")
                
                # Check if fan_number exists in CSV, if not try to get it from welcome email
                fan_number = account_data.get('fan_number', '')
                if not fan_number or fan_number.strip() == '' or fan_number.lower() == 'nee':
                    print(f"[{task_number}] 🔍 Fan number niet in CSV, proberen uit welkomstmail te halen...")
                    # Quick check for fan number in existing emails
                    fan_number = self._check_existing_emails_for_fan_number(email)
                    if fan_number:
                        print(f"[{task_number}] ✅ Fan number gevonden in welkomstmail: {fan_number}")
                        self.update_account_status(email, fan_number=fan_number)
                        print(f"[{task_number}] 💾 Fan number live opgeslagen in CSV: {fan_number}")
                    else:
                        print(f"[{task_number}] ⚠️ Fan number niet gevonden in welkomstmail")
                        # Background scanner zal het later vinden
                
                # Get fan_number from CSV (might have been updated above)
                if self.accounts_file.exists():
                    with open(self.accounts_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('email') == email:
                                fan_number = row.get('fan_number', '')
                                break
                
                # If fan_number exists, go directly to signup page
                if fan_number and fan_number.strip() != '' and fan_number.lower() != 'nee':
                    print(f"[{task_number}] 📍 Direct naar signup pagina met fan_number: {fan_number}")
                    messenger_url = "https://messenger.engage-engine.com/?cid=1261051&aid=14026&medium=GAME_ZONE&identifier=1762790719.3316&bid=1762790792140&skip_messenger=true"
                    try:
                        driver.get(messenger_url)
                        random_delay(3.0, 5.0)
                        
                        # Check for landing page
                        current_url = driver.current_url.lower()
                        if '/landing' in current_url or 'portugal.fpf.pt/landing' in current_url:
                            print(f"[{task_number}] ⚠️ Landing pagina gedetecteerd, nieuw profiel nodig")
                            return "LANDING_PAGE_RETRY"
                        
                        # Fill messenger form
                        first_name = account_data.get('first_name', '')
                        phone_number = account_data.get('phone_number', '')
                        messenger_success = self._fill_messenger_form(
                            driver, 
                            task_number, 
                            first_name, 
                            email, 
                            phone_number, 
                            fan_number
                        )
                        
                        if messenger_success:
                            print(f"[{task_number}] ✅ Signup volledig voltooid!")
                            self.update_account_status(email, signup=True)
                            return True
                        else:
                            print(f"[{task_number}] ⚠️ Messenger formulier niet succesvol, maar account bestaat al")
                            return "SKIP"  # Account bestaat al, maar signup mislukt
                    except Exception as e:
                        print(f"[{task_number}] ❌ Fout bij navigeren naar signup pagina: {e}")
                        return "SKIP"
                else:
                    print(f"[{task_number}] ⚠️ Geen fan_number beschikbaar, account wordt overgeslagen (background scanner zal fan_number later vinden)")
                    return "SKIP"  # Skip for now, background scanner will find fan_number later
            elif not email_submit_result:
                return False
            
            # Step 5: Wait for verification code from email (monitoren vanaf imap_start_time)
            # Check for IP ban while waiting (but skip inactivity check during OTP wait)
            print(f"[{task_number}] 🔐 Verificatie code ophalen (monitoren vanaf {imap_start_time})...")
            
            # Set flag to disable inactivity check during OTP wait
            waiting_for_otp = True
            last_activity_time = time.time()  # Reset timer for after OTP wait
            
            # Poll for verification code with IP ban checks (no inactivity check during OTP wait)
            verification_code = None
            timeout = 600  # 10 minutes max (mails kunnen delayed zijn)
            poll_interval = 5  # Check every 5 seconds (niet te snel, maar ook niet te langzaam)
            elapsed = 0
            
            while elapsed < timeout and not verification_code:
                # Check for IP ban (always check, even during OTP wait)
                if self._check_for_ip_ban(driver):
                    waiting_for_otp = False  # Reset flag
                    print(f"[{task_number}] ⚠️ IP BAN gedetecteerd tijdens wachten op OTP, nieuw profiel met andere proxy nodig")
                    return "IP_BANNED_RETRY"  # Signal to retry with new profile
                
                # Validate email before calling extract_verification_code
                if not email or not email.strip():
                    print(f"[{task_number}] ❌ Email is leeg, kan verificatie code niet ophalen")
                    waiting_for_otp = False
                    return False
                
                # Try to get verification code
                verification_code = self.imap_helper.extract_verification_code(email, imap_start_time)
                
                if verification_code:
                    break
                
                # Wait before next check
                time.sleep(min(poll_interval, timeout - elapsed))
                elapsed += poll_interval
            
            # Reset flag after OTP wait
            waiting_for_otp = False
            last_activity_time = time.time()  # Reset timer for next actions
            
            if not verification_code:
                # Final check for IP ban before giving up
                if self._check_for_ip_ban(driver):
                    print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                    return "IP_BANNED_RETRY"  # Signal to retry with new profile
                print(f"[{task_number}] ❌ Geen verificatie code ontvangen na {timeout} seconden")
                return False
            
            # Wacht 3-5 seconden voordat OTP wordt ingevoerd (variëren)
            wait_time = random.uniform(3.0, 5.0)
            print(f"[{task_number}] ⏳ Wachten {wait_time:.1f} seconden voordat OTP wordt ingevoerd...")
            time.sleep(wait_time)
            print(f"[{task_number}] ✓ {wait_time:.1f} seconden gewacht, OTP wordt nu ingevoerd")
            
            # Step 6: Fill verification code (klikt eerst op OTP veld, vult dan in, klikt dan op Confirmar button)
            print(f"[{task_number}] ✅ Verificatie code invullen en bevestigen...")
            if not self._fill_verification_code(driver, verification_code):
                # Check for IP ban before returning False
                if self._check_for_ip_ban(driver):
                    print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                    return "IP_BANNED_RETRY"  # Signal to retry with new profile
                return False
            last_activity_time = time.time()
            
            # Check for inactivity and IP ban
            check_result = check_inactivity_and_ban()
            if check_result == "IP_BANNED":
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            elif check_result == "INACTIVITY_ERROR":
                return "SKIP"
            
            # Step 7: Fill password
            print(f"[{task_number}] 🔒 Password invullen...")
            if not self._fill_password_form(driver, password):
                # Check for IP ban before returning False
                if self._check_for_ip_ban(driver):
                    print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, nieuw profiel met andere proxy nodig")
                    return "IP_BANNED_RETRY"  # Signal to retry with new profile
                return False
            last_activity_time = time.time()
            
            # Check for inactivity and IP ban
            check_result = check_inactivity_and_ban()
            if check_result == "IP_BANNED":
                return "IP_BANNED_RETRY"  # Signal to retry with new profile
            elif check_result == "INACTIVITY_ERROR":
                return "SKIP"
            
            # Save generated data to CSV immediately after password form
            print(f"[{task_number}] 💾 Gegevens opslaan naar CSV...")
            self.update_account_status(email, account=False, signup=False, password=password, first_name=first_name, 
                                     last_name=last_name, birthdate=birthdate, 
                                     phone_number=phone_number)
            
            # Step 8: Fill personal information
            print(f"[{task_number}] 👤 Persoonlijke gegevens invullen...")
            if not self._fill_personal_info(driver, first_name, last_name, birthdate, phone_number):
                return False
            
            # Wait for next page to load
            random_delay(2.0, 3.0)
            
            # Step 9: Fill additional details on follow-up page
            print(f"[{task_number}] 📋 Extra gegevens invullen op vervolgpagina...")
            city, address, postal_code, nif, house_number = self._fill_additional_details(driver, task_number, email)
            
            if not city:
                print(f"[{task_number}] ⚠️ Extra gegevens invullen gefaald")
                return False
            
            # Step 10: Update account status in CSV - account is aangemaakt (account=ja), signup nog niet (signup=nee)
            # Note: profile_id is already saved when profile was created in _process_single_item
            # Fan number wordt NIET hier opgehaald - background scanner doet dit later
            self.update_account_status(
                email, 
                account=True,  # Account is aangemaakt
                signup=False,  # Signup nog niet gedaan
                phone_number=phone_number,
                city=city,
                address=address,
                postal_code=postal_code,
                nif=nif,
                house_number=house_number,
                fan_number=""  # Wordt later opgehaald door background scanner
            )
            
            # Account creation is voltooid - sluit profiel en ga verder met volgende account
            # Background scanner zal fan_number later vinden en CSV updaten
            # Wanneer fan_number beschikbaar is, wordt account automatisch verwerkt voor signup
            print(f"[{task_number}] ✅ Account aangemaakt voltooid (account=ja, signup=nee)")
            print(f"[{task_number}] 📧 Fan number wordt later opgehaald door background scanner")
            print(f"[{task_number}] 🔄 Profiel wordt gesloten - account wordt later afgemaakt wanneer fan_number beschikbaar is")
            return True  # Return True - account is aangemaakt, profiel kan worden gesloten
            
        except Exception as e:
            error_str = str(e).lower()
            # Check if it's a fatal error that shouldn't be retried
            fatal_errors = ['forbidden', '403', 'unauthorized', '401', 'not found', '404']
            is_fatal = any(fatal_err in error_str for fatal_err in fatal_errors)
            
            if not is_fatal:
                # Non-fatal error - re-raise so retry logic in _process_single_item can handle it
                raise
            
            # Fatal error - update status and return False
            print(f"[{task_number}] ❌ Automatisation error (fatal): {e}")
            import traceback
            traceback.print_exc()
            # Update account status as failed (still save phone number if it was generated)
            phone_number = account_data.get('phone_number', '')
            if not phone_number and hasattr(self, 'used_phone_numbers'):
                # Try to get the last generated number
                if self.used_phone_numbers:
                    phone_number = list(self.used_phone_numbers)[-1]
            self.update_account_status(email, account=False, phone_number=phone_number)
            return False
    
    def get_profile_by_id(self, profile_id: int):
        """Get an existing Dolphin profile by ID"""
        try:
            url = f'{self.remote_api_url}/browser_profiles/{profile_id}'
            headers = {
                'Authorization': f'Bearer {self.dolphin_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            # Dolphin API returns profile data in different structures
            # Normalize to match create_profile return format
            profile_data = result.get('data', result)
            
            # Get profile ID from various possible locations
            actual_profile_id = (
                profile_data.get('browserProfileId') or
                profile_data.get('id') or
                profile_data.get('profileId') or
                profile_id  # Fallback to requested ID
            )
            
            # Get profile name
            profile_name = (
                profile_data.get('name') or
                profile_data.get('profileName') or
                'Unknown'
            )
            
            # Return in same format as create_profile
            return {
                'id': actual_profile_id,
                'name': profile_name
            }
        except Exception as e:
            print(f"      ⚠️ Kon profiel {profile_id} niet ophalen: {e}")
            return None
    
    def update_account_status(self, email: str, account: bool = None, signup: bool = None, password: str = '', 
                             first_name: str = '', last_name: str = '', birthdate: str = '',
                             phone_number: str = '', city: str = '', address: str = '', 
                             postal_code: str = '', nif: str = '', house_number: str = '', fan_number: str = '', profile_id: int = None, skip_reason: str = ''):
        """Update account status in CSV with all provided data (live update) - THREAD-SAFE"""
        accounts_file = self.accounts_file
        
        # Use lock to ensure thread-safe CSV operations (entire function is protected)
        with self.csv_lock:
        # Read all accounts
        accounts = []
        fieldnames = []
        if accounts_file.exists():
            with open(accounts_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                accounts = list(reader)
        
        # "entered" is hernoemd naar "account" voor duidelijkheid
        all_fields = ['email', 'password', 'first_name', 'last_name', 'birthdate', 
                     'phone_number', 'account', 'signup', 'timestamp', 'city', 'address', 
                     'postal_code', 'nif', 'house_number', 'fan_number', 'profile_id', 'skip_reason']
        for field in all_fields:
            if field not in fieldnames:
                fieldnames.append(field)
        
        # Migratie: als "entered" bestaat, rename naar "account"
        if 'entered' in fieldnames and 'account' not in fieldnames:
            fieldnames[fieldnames.index('entered')] = 'account'
            for account in accounts:
                if 'entered' in account and 'account' not in account:
                    account['account'] = account.pop('entered')
        
        # Update account
        updated = False
        for acc in accounts:
            if acc.get('email') == email:
                if account is not None:
                    acc['account'] = 'ja' if account else 'nee'
                if signup is not None:
                    acc['signup'] = 'ja' if signup else 'nee'
                acc['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Update all provided fields
                if password:
                    acc['password'] = password
                if first_name:
                    acc['first_name'] = first_name
                if last_name:
                    acc['last_name'] = last_name
                if birthdate:
                    acc['birthdate'] = birthdate
                if phone_number:
                    acc['phone_number'] = phone_number
                if city:
                    acc['city'] = city
                if address:
                    acc['address'] = address
                if postal_code:
                    acc['postal_code'] = postal_code
                if nif:
                    acc['nif'] = nif
                if house_number:
                    acc['house_number'] = house_number
                if fan_number:
                    acc['fan_number'] = fan_number
                if profile_id is not None:
                    acc['profile_id'] = str(profile_id)
                elif profile_id is None and 'profile_id' in acc:
                    # Clear profile_id if explicitly set to None (profile was deleted)
                    acc['profile_id'] = ''
                if skip_reason:
                    acc['skip_reason'] = skip_reason
                
                updated = True
                break
        
        if not updated:
                # Account niet gevonden - voeg toe als nieuw account (voorkomt verlies van emails)
                print(f"⚠️ Account {email} niet gevonden in CSV - wordt toegevoegd als nieuw account")
                new_account = {'email': email}
                # Initialize all fields
                for field in fieldnames:
                    if field != 'email':
                        new_account[field] = ''
                
                # Set provided fields
                if account is not None:
                    new_account['account'] = 'ja' if account else 'nee'
                if signup is not None:
                    new_account['signup'] = 'ja' if signup else 'nee'
                new_account['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if password:
                    new_account['password'] = password
                if first_name:
                    new_account['first_name'] = first_name
                if last_name:
                    new_account['last_name'] = last_name
                if birthdate:
                    new_account['birthdate'] = birthdate
                if phone_number:
                    new_account['phone_number'] = phone_number
                if city:
                    new_account['city'] = city
                if address:
                    new_account['address'] = address
                if postal_code:
                    new_account['postal_code'] = postal_code
                if nif:
                    new_account['nif'] = nif
                if house_number:
                    new_account['house_number'] = house_number
                if fan_number:
                    new_account['fan_number'] = fan_number
                if profile_id is not None:
                    new_account['profile_id'] = str(profile_id)
                if skip_reason:
                    new_account['skip_reason'] = skip_reason
                
                accounts.append(new_account)
                updated = True
        
            # Write back immediately (live update) with backup and error handling
        if accounts:
            # Ensure all accounts have all fields
            for account in accounts:
                for field in fieldnames:
                    if field not in account:
                        account[field] = ''
            
                # Create backup before writing (prevent data loss)
                backup_file = accounts_file.with_suffix('.csv.backup')
                try:
                    if accounts_file.exists():
                        import shutil
                        shutil.copy2(accounts_file, backup_file)
                except Exception as e:
                    print(f"⚠️ Kon backup niet maken: {e}")
                
                # Write with error handling
                try:
            with open(accounts_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(accounts)
                except Exception as e:
                    print(f"❌ Fout bij schrijven naar CSV: {e}")
                    # Restore from backup if write failed
                    if backup_file.exists():
                        try:
                            import shutil
                            shutil.copy2(backup_file, accounts_file)
                            print(f"✅ CSV hersteld vanuit backup")
                        except Exception as e2:
                            print(f"❌ Kon CSV niet herstellen vanuit backup: {e2}")
                    raise
            
            # Print what was saved
            saved_fields = []
            if password:
                saved_fields.append(f"wachtwoord={password[:4]}***")
            if first_name:
                saved_fields.append(f"voornaam={first_name}")
            if last_name:
                saved_fields.append(f"achternaam={last_name}")
            if birthdate:
                saved_fields.append(f"geboortedatum={birthdate}")
            if phone_number:
                saved_fields.append(f"telefoonnummer={phone_number}")
            if city:
                saved_fields.append(f"stad={city}")
            if address:
                saved_fields.append(f"adres={address}")
            if postal_code:
                saved_fields.append(f"postcode={postal_code}")
            if nif:
                saved_fields.append(f"NIF={nif}")
            if house_number:
                saved_fields.append(f"huisnummer={house_number}")
            if fan_number:
                saved_fields.append(f"fannummer={fan_number}")
            if account is not None:
                saved_fields.append(f"account={'ja' if account else 'nee'}")
            if signup is not None:
                saved_fields.append(f"signup={'ja' if signup else 'nee'}")
            
            if saved_fields:
                print(f"      💾 Gegevens opgeslagen in CSV: {', '.join(saved_fields)}")
    
    def _process_single_item(self, site_config, data_item, task_number):
        """
        Override to use lazy proxy creation - proxies are created on demand
        Also handles profile reuse for retry scenarios (account=ja, signup=nee)
        """
        # Check stop event at the start (unless ignored for background signups)
        ignore_stop = getattr(self, '_ignore_stop_event', False)
        if not ignore_stop and self.stop_event.is_set():
            print(f"[{task_number}] 🛑 Stop signaal ontvangen - taak wordt overgeslagen")
            return False
        
        # ALTIJD de nieuwste data uit CSV halen (niet uit data_item dat mogelijk verouderd is)
        # Dit zorgt ervoor dat fan_numbers die door de background scanner zijn toegevoegd, direct worden opgepikt
        email = data_item.get('email', '')
        if email and self.accounts_file.exists():
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('email', '').strip().lower() == email.strip().lower():
                            # Update data_item met nieuwste data uit CSV
                            data_item = row.copy()
                            print(f"[{task_number}] 📖 Nieuwste CSV data geladen voor {email} (fan_number={row.get('fan_number', 'N/A')}, profile_id={row.get('profile_id', 'N/A')})")
                            break
            except Exception as e:
                print(f"[{task_number}] ⚠️ Fout bij lezen nieuwste CSV data: {e}, gebruik originele data_item")
        
        profile = None
        driver = None
        email = data_item.get('email', '')
        is_retry = False
        
        try:
            # Check if this is a retry (account=ja, signup=nee) - try to reuse existing profile
            existing_profile_id = data_item.get('profile_id', '').strip()
            if existing_profile_id and existing_profile_id.isdigit():
                    profile_id_int = int(existing_profile_id)
                    print(f"[{task_number}] 🔄 Probeer bestaand profiel te hergebruiken (profile_id={profile_id_int})...")
                
                # Retry logic for getting profile (especially for 403 errors which might be temporary)
                max_profile_retries = 3
                profile_retry_count = 0
                profile_found = False
                
                while profile_retry_count < max_profile_retries and not profile_found:
                    try:
                        profile_retry_count += 1
                        if profile_retry_count > 1:
                            print(f"[{task_number}] 🔄 Retry {profile_retry_count}/{max_profile_retries} - Opnieuw proberen profiel op te halen...")
                            random_delay(2.0, 4.0)  # Wacht even tussen retries
                        
                    profile = self.get_profile_by_id(profile_id_int)
                    if profile:
                        print(f"[{task_number}] ✅ Bestaand profiel gevonden, hergebruik: {profile.get('name', 'N/A')}")
                        is_retry = True
                            profile_found = True
                        # Store proxy mapping if we have it
                        # We don't have proxy info from existing profile, so we'll skip proxy cleanup for retries
                    else:
                            print(f"[{task_number}] ⚠️ Profiel niet gevonden (poging {profile_retry_count}/{max_profile_retries})...")
                            if profile_retry_count >= max_profile_retries:
                                print(f"[{task_number}] ⚠️ Bestaand profiel niet gevonden na {max_profile_retries} pogingen (mogelijk verwijderd), maak nieuw profiel aan...")
                        # Clear the invalid profile_id from CSV
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, profile_id=None)
                except Exception as e:
                    error_str = str(e).lower()
                        # 403 errors might be temporary (rate limiting, API issues) - retry
                        if '403' in error_str or 'forbidden' in error_str:
                            if profile_retry_count >= max_profile_retries:
                                print(f"[{task_number}] ⚠️ 403 Forbidden na {max_profile_retries} pogingen (mogelijk profiel verwijderd of permanente toegangsproblemen): {e}")
                        print(f"[{task_number}] ℹ️ Maak nieuw profiel aan...")
                        # Clear the invalid profile_id from CSV
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, profile_id=None)
                    else:
                                print(f"[{task_number}] ⚠️ 403 Forbidden (poging {profile_retry_count}/{max_profile_retries}) - mogelijk tijdelijk, probeer opnieuw...")
                        # 404 errors are permanent - don't retry
                        elif '404' in error_str or 'not found' in error_str:
                            print(f"[{task_number}] ⚠️ Profiel niet gevonden (404 - verwijderd): {e}")
                            print(f"[{task_number}] ℹ️ Maak nieuw profiel aan...")
                            # Clear the invalid profile_id from CSV
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, profile_id=None)
                            break  # Don't retry for 404
                        else:
                            if profile_retry_count >= max_profile_retries:
                                print(f"[{task_number}] ⚠️ Fout bij ophalen bestaand profiel na {max_profile_retries} pogingen: {e}, maak nieuw profiel aan...")
                                # Clear the invalid profile_id from CSV
                                email = data_item.get('email', '')
                                if email:
                                    self.update_account_status(email, profile_id=None)
                            else:
                                print(f"[{task_number}] ⚠️ Fout bij ophalen bestaand profiel (poging {profile_retry_count}/{max_profile_retries}): {e}, probeer opnieuw...")
            
            # Create new profile if we don't have an existing one
            if not profile:
                # Generate profile name with email hash for better identification
                email_hash = hashlib.md5(email.encode()).hexdigest()[:8] if email else uuid.uuid4().hex[:8]
                profile_name = f'PORTUGAL_FPF{task_number}_{email_hash}'
                profile = self.create_profile(proxy_data=None, name_prefix=profile_name)
                if not profile:
                    return False
                
                # Save profile_id to CSV for future reuse
                if email:
                    self.update_account_status(email, profile_id=profile['id'])
            
            # Get proxy info for cleanup (only for new profiles, retries don't have proxy info)
            profile_id = profile['id'] if profile else None
            proxy_data = self.profile_proxy_map.get(profile_id) if profile_id else None
            proxy_string = self.profile_proxy_string_map.get(profile_id) if profile_id else None
            
            # Update profile activity timestamp
            if profile_id:
                self.profile_last_activity[profile_id] = time.time()
            
            # Create driver
            driver = self.create_driver(profile_id)
            if not driver:
                return False
            
            # Load a page immediately to prevent empty tab (fix voor lege tab)
            try:
                # Load about:blank first to ensure browser has content, then automation will navigate to actual URL
                driver.get("about:blank")
                random_delay(0.5, 1.0)
            except Exception as e:
                print(f"[{task_number}] ⚠️ Fout bij laden initial page: {e}")
                # Continue anyway - automation will handle navigation
            
            # Run site-specific automation with retry logic
            max_retries = 3
            max_ip_ban_retries = 3  # Max retries with new profile when IP banned
            max_landing_page_retries = 3  # Max retries with new profile when landing page detected
            retry_count = 0
            ip_ban_retry_count = 0
            landing_page_retry_count = 0
            success = False
            
            while (retry_count < max_retries or ip_ban_retry_count < max_ip_ban_retries or landing_page_retry_count < max_landing_page_retries) and not success:
                try:
                    # Handle IP ban retry - create new profile with different proxy
                    if retry_count == 0 and ip_ban_retry_count > 0:
                        print(f"[{task_number}] 🔄 IP BAN retry {ip_ban_retry_count}/{max_ip_ban_retries} - Nieuw profiel met andere proxy aanmaken...")
                        
                        # Stop and cleanup old profile (with banned IP)
                        try:
                            if driver:
                                driver.quit()
                        except:
                            pass
                        
                        try:
                            if profile and profile.get('id'):
                                self.stop_profile(profile['id'])
                                # Cleanup profile and proxy
                                self._cleanup_profile_and_proxy(profile, proxy_data, success=True, proxy_string=proxy_string)
                                print(f"[{task_number}] ✅ Oud profiel met gebande IP gestopt en verwijderd")
                        except Exception as e:
                            print(f"[{task_number}] ⚠️ Fout bij stoppen oud profiel: {e}")
                        
                        # Clear profile_id from CSV so new profile will be created
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, profile_id=None)
                        
                        # Create new profile with different proxy
                        # Generate profile name with email hash for better identification
                        email_hash = hashlib.md5(email.encode()).hexdigest()[:8] if email else uuid.uuid4().hex[:8]
                        profile_name = f'PORTUGAL_FPF{task_number}_{email_hash}_RETRY{ip_ban_retry_count}'
                        profile = self.create_profile(proxy_data=None, name_prefix=profile_name)
                        if not profile:
                            print(f"[{task_number}] ❌ Kon geen nieuw profiel aanmaken, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='kon_geen_profiel_aanmaken')
                            break
                        
                        # Save new profile_id to CSV
                        if email:
                            self.update_account_status(email, profile_id=profile['id'])
                        
                        # Get new proxy info
                        profile_id = profile['id']
                        proxy_data = self.profile_proxy_map.get(profile_id)
                        proxy_string = self.profile_proxy_string_map.get(profile_id)
                        
                        # Update profile activity timestamp
                        self.profile_last_activity[profile_id] = time.time()
                        
                        # Create new driver with new profile
                        driver = self.create_driver(profile_id)
                        if not driver:
                            print(f"[{task_number}] ❌ Kon geen driver maken voor nieuw profiel, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='kon_geen_driver_maken')
                            break
                        
                        print(f"[{task_number}] ✅ Nieuw profiel {profile_id} gemaakt met andere proxy, probeer opnieuw...")
                        random_delay(2.0, 3.0)
                    
                    # Handle landing page retry - create new profile with different proxy (same as IP ban)
                    elif retry_count == 0 and landing_page_retry_count > 0:
                        print(f"[{task_number}] 🔄 LANDING PAGE retry {landing_page_retry_count}/{max_landing_page_retries} - Nieuw profiel met andere proxy aanmaken...")
                        
                        # Stop and cleanup old profile
                        try:
                            if driver:
                                driver.quit()
                        except:
                            pass
                        
                        try:
                            if profile and profile.get('id'):
                                self.stop_profile(profile['id'])
                                # Cleanup profile and proxy
                                self._cleanup_profile_and_proxy(profile, proxy_data, success=True, proxy_string=proxy_string)
                                print(f"[{task_number}] ✅ Oud profiel (landing page) gestopt en verwijderd")
                        except Exception as e:
                            print(f"[{task_number}] ⚠️ Fout bij stoppen oud profiel: {e}")
                        
                        # Clear profile_id from CSV so new profile will be created
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, profile_id=None)
                        
                        # Create new profile with different proxy
                        # Generate profile name with email hash for better identification
                        email_hash = hashlib.md5(email.encode()).hexdigest()[:8] if email else uuid.uuid4().hex[:8]
                        profile_name = f'PORTUGAL_FPF{task_number}_{email_hash}_LANDING_RETRY{landing_page_retry_count}'
                        profile = self.create_profile(proxy_data=None, name_prefix=profile_name)
                        if not profile:
                            print(f"[{task_number}] ❌ Kon geen nieuw profiel aanmaken, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='kon_geen_profiel_aanmaken')
                            break
                        
                        # Save new profile_id to CSV
                        if email:
                            self.update_account_status(email, profile_id=profile['id'])
                        
                        # Get new proxy info
                        profile_id = profile['id']
                        proxy_data = self.profile_proxy_map.get(profile_id)
                        proxy_string = self.profile_proxy_string_map.get(profile_id)
                        
                        # Update profile activity timestamp
                        self.profile_last_activity[profile_id] = time.time()
                        
                        # Create new driver with new profile
                        driver = self.create_driver(profile_id)
                        if not driver:
                            print(f"[{task_number}] ❌ Kon geen driver maken voor nieuw profiel, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='kon_geen_driver_maken')
                            break
                        
                        print(f"[{task_number}] ✅ Nieuw profiel {profile['id']} gemaakt (landing page retry), probeer opnieuw...")
                        random_delay(2.0, 3.0)
                    
                    elif retry_count > 0:
                        print(f"[{task_number}] 🔄 Retry {retry_count}/{max_retries-1} - Refresh pagina en opnieuw proberen...")
                        try:
                            driver.refresh()
                            random_delay(0.5, 1.0)  # Sneller refreshen
                        except:
                            # If refresh fails, try to navigate again
                            try:
                                current_url = driver.current_url
                                driver.get(current_url)
                                random_delay(0.5, 1.0)  # Sneller refreshen
                            except:
                                pass
                    
                    # Check stop event before running automation (unless ignored for background signups)
                    ignore_stop = getattr(self, '_ignore_stop_event', False)
                    if not ignore_stop and self.stop_event.is_set():
                        print(f"[{task_number}] 🛑 Stop signaal ontvangen - automation wordt overgeslagen")
                        success = False
                        break
                    
                    # Run site-specific automation
                    result = self._execute_site_automation(driver, site_config, data_item, task_number)
                    
                    # Check if account was skipped (special return value)
                    if result == "SKIP":
                        # Account was skipped, don't retry
                        success = False
                        print(f"[{task_number}] ℹ️ Account overgeslagen, ga door naar volgende")
                        break
                    elif result == "IP_BANNED_RETRY":
                        # IP ban detected - need new profile with different proxy
                        ip_ban_retry_count += 1
                        retry_count = 0  # Reset regular retry count for new profile
                        if ip_ban_retry_count >= max_ip_ban_retries:
                            print(f"[{task_number}] ❌ Max IP BAN retries bereikt ({max_ip_ban_retries}), account wordt overgeslagen")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='ip_banned_na_retries')
                            success = False
                            break
                        else:
                            print(f"[{task_number}] ⚠️ IP BAN gedetecteerd, probeer opnieuw met nieuw profiel (poging {ip_ban_retry_count}/{max_ip_ban_retries})...")
                            continue
                    elif result == "LANDING_PAGE_RETRY":
                        # Landing page detected - need new profile with different proxy
                        landing_page_retry_count += 1
                        retry_count = 0  # Reset regular retry count for new profile
                        if landing_page_retry_count >= max_landing_page_retries:
                            print(f"[{task_number}] ❌ Max LANDING PAGE retries bereikt ({max_landing_page_retries}), account wordt overgeslagen")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='landing_page_na_retries')
                            success = False
                            break
                        else:
                            print(f"[{task_number}] ⚠️ LANDING PAGE gedetecteerd, probeer opnieuw met nieuw profiel (poging {landing_page_retry_count}/{max_landing_page_retries})...")
                            continue
                    elif result == True:
                        # Success
                        success = True
                        break
                    else:
                        # Failed but might retry (only regular retries, not IP ban retries)
                        success = False
                        retry_count += 1
                        if retry_count >= max_retries:
                            print(f"[{task_number}] ❌ Max retries bereikt, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='max_retries_bereikt')
                            break
                        else:
                            print(f"[{task_number}] ⚠️ Automation gefaald (poging {retry_count}/{max_retries}), probeer opnieuw...")
                            random_delay(2.0, 3.0)
                            continue
                        
                except WebDriverException as e:
                    error_msg = str(e).lower()
                    # Check if it's a fatal error that we shouldn't retry
                    if 'err_tunnel_connection_failed' in error_msg or 'proxy' in error_msg:
                        print(f"[{task_number}] ❌ Fatal proxy error: {e}")
                        print(f"[{task_number}] ⚠️ Geen retry mogelijk, ga door naar volgende account")
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, skip_reason='fatal_proxy_error')
                        break
                    # Check voor handmatig gesloten browser
                    elif 'disconnected' in error_msg or 'not reachable' in error_msg or 'no such execution context' in error_msg or 'target window already closed' in error_msg:
                        print(f"[{task_number}] ❌ Browser verbinding verbroken (mogelijk handmatig gesloten): {e}")
                        print(f"[{task_number}] ⚠️ Taak wordt afgebroken, thread komt vrij voor volgende account")
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, skip_reason='browser_verbinding_verbroken')
                        break
                    elif 'chromedriver' in error_msg or 'session' in error_msg or 'timeout' in error_msg:
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"[{task_number}] ⚠️ WebDriver error (attempt {retry_count}/{max_retries}): {e}")
                            print(f"[{task_number}] 🔄 Probeer opnieuw na korte wachttijd...")
                            random_delay(2.0, 4.0)
                            continue
                        else:
                            print(f"[{task_number}] ❌ Max retries bereikt, ga door naar volgende account")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='webdriver_max_retries')
                            break
                    else:
                        # Other WebDriver errors - try to retry
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"[{task_number}] ⚠️ Error (attempt {retry_count}/{max_retries}): {e}")
                            print(f"[{task_number}] 🔄 Probeer opnieuw...")
                            random_delay(2.0, 4.0)
                            continue
                        else:
                            print(f"[{task_number}] ❌ Max retries bereikt: {e}")
                            email = data_item.get('email', '')
                            if email:
                                self.update_account_status(email, skip_reason='webdriver_error_max_retries')
                            break
                            
                except TimeoutException as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"[{task_number}] ⚠️ Timeout error (attempt {retry_count}/{max_retries}): {e}")
                        print(f"[{task_number}] 🔄 Probeer opnieuw...")
                        random_delay(2.0, 4.0)
                        continue
                    else:
                        print(f"[{task_number}] ❌ Max retries bereikt (timeout), ga door naar volgende account")
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, skip_reason='timeout_max_retries')
                        break
                        
                except Exception as e:
                    retry_count += 1
                    error_str = str(e).lower()
                    # Check if it's a fatal error
                    if 'forbidden' in error_str or '403' in error_str or 'unauthorized' in error_str:
                        print(f"[{task_number}] ❌ Fatal authorization error: {e}")
                        print(f"[{task_number}] ⚠️ Geen retry mogelijk, ga door naar volgende account")
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, skip_reason='fatal_authorization_error')
                        break
                    elif retry_count < max_retries:
                        print(f"[{task_number}] ⚠️ Error (attempt {retry_count}/{max_retries}): {e}")
                        print(f"[{task_number}] 🔄 Probeer opnieuw...")
                        random_delay(2.0, 4.0)
                        continue
                    else:
                        print(f"[{task_number}] ❌ Max retries bereikt: {e}")
                        print(f"[{task_number}] ⚠️ Ga door naar volgende account")
                        email = data_item.get('email', '')
                        if email:
                            self.update_account_status(email, skip_reason='exception_max_retries')
                        break
            
            # Get proxy info for cleanup
            profile_id = profile['id'] if profile else None
            proxy_data = self.profile_proxy_map.get(profile_id) if profile_id else None
            proxy_string = self.profile_proxy_string_map.get(profile_id) if profile_id else None
            
            # Determine if we should cleanup (delete) the profile
            # Only delete if signup is complete (signup=ja), otherwise just stop it
            should_delete_profile = False
            
                # Check if signup is actually done by checking CSV
                try:
                    if self.accounts_file.exists():
                        with open(self.accounts_file, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('email') == email:
                                account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                                    signup_done = row.get('signup', '').lower() == 'ja'
                                # Only delete if both account and signup are done
                                if account_made and signup_done:
                                    should_delete_profile = True
                                    break
            except Exception as e:
                print(f"[{task_number}] ⚠️ Fout bij checken signup status: {e}")
            
            # Cleanup profile based on signup status
            if profile:
                profile_id = profile['id'] if profile else None
                
                if should_delete_profile:
                    # Signup is complete - delete profile and proxy
                    print(f"[{task_number}] ✅ Signup voltooid - profiel {profile_id} wordt verwijderd")
                self._cleanup_profile_and_proxy(
                    profile=profile,
                    proxy=proxy_data,
                    success=True,  # Always True when we cleanup (signup=ja)
                    proxy_string=proxy_string,
                    proxies_file=str(self.proxies_file) if hasattr(self, 'proxies_file') and self.proxies_file else None
                )
                    # Cleanup activity tracking
                    if profile_id and profile_id in self.profile_last_activity:
                        del self.profile_last_activity[profile_id]
                else:
                    # Signup not complete - just stop profile (don't delete) so it can be reused
                try:
                    if profile_id:
                        # Stop the profile but don't delete it
                        self.stop_profile(profile_id)
                            print(f"[{task_number}] ℹ️ Profiel {profile_id} gestopt (behouden voor later gebruik)")
                except Exception as e:
                    print(f"[{task_number}] ⚠️ Fout bij stoppen profiel: {e}")
            
            # Clean up tracking dictionaries
            if profile_id and profile_id in self.profile_proxy_map:
                del self.profile_proxy_map[profile_id]
            if profile_id and profile_id in self.profile_proxy_string_map:
                del self.profile_proxy_string_map[profile_id]
            
            # Update account status in CSV (will be done in _execute_site_automation)
            
            return success
            
        except Exception as e:
            print(f"❌ Error in automation process: {e}")
            import traceback
            traceback.print_exc()
            
            # Update account status as failed (will be done in _execute_site_automation)
            
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
    
    def cleanup_unused_profiles(self, force_cleanup=False):
        """Cleanup ongebruikte Dolphin profielen die niet meer nodig zijn
        
        Args:
            force_cleanup: Als True, verwijder ook profielen waar signup=ja (afgerond)
        """
        try:
            if force_cleanup:
                print("🧹 Force cleanup: verwijderen van alle afgeronde profielen...")
            else:
                print("🧹 Controleren op ongebruikte profielen...")
            
            # Haal alle profile_ids op uit CSV die nog nodig zijn
            active_profile_ids = set()
            completed_profile_ids = set()  # Profielen waar signup=ja (klaar)
            
            if self.accounts_file.exists():
                with open(self.accounts_file, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profile_id = row.get('profile_id', '').strip()
                        if profile_id and profile_id.isdigit():
                            profile_id_int = int(profile_id)
                            account_made = row.get('account', '').lower() == 'ja'
                            signup_done = row.get('signup', '').lower() == 'ja'
                            
                            # Behoud profiel als account niet gemaakt is, of als account gemaakt is maar signup niet
                            if not account_made or (account_made and not signup_done):
                                active_profile_ids.add(profile_id_int)
                            elif force_cleanup and account_made and signup_done:
                                # Bij force cleanup: verzamel afgeronde profielen
                                completed_profile_ids.add(profile_id_int)
            
            print(f"📋 {len(active_profile_ids)} actieve profile ID(s) gevonden in CSV")
            if force_cleanup:
                print(f"✅ {len(completed_profile_ids)} afgeronde profiel(en) gevonden voor cleanup")
            
            # Haal alle Dolphin profielen op die beginnen met 'PORTUGAL_FPF' (in chunks voor veel profielen)
            all_portugal_profiles = []
            offset = 0
            limit = 100  # Haal in batches van 100
            
            while True:
                try:
                    batch = self.list_all_profiles(limit=limit, offset=offset)
                    if not batch:
                        break
                    
                    for profile in batch:
                        profile_name = profile.get('name', '') or profile.get('profileName', '')
                        if profile_name and profile_name.startswith('PORTUGAL_FPF'):
                            profile_id = (
                                profile.get('browserProfileId') or
                                profile.get('id') or
                                profile.get('profileId')
                            )
                            if profile_id:
                                all_portugal_profiles.append({
                                    'id': profile_id,
                                    'name': profile_name
                                })
                    
                    if len(batch) < limit:
                        break  # Laatste batch
                    
                    offset += limit
                    
                    # Limiteer tot 1000 profielen om niet te lang te duren
                    if len(all_portugal_profiles) >= 1000:
                        print(f"⚠️  Te veel profielen gevonden (>1000), alleen eerste 1000 worden gecontroleerd")
                        break
                        
                except Exception as e:
                    print(f"⚠️  Fout bij ophalen profielen batch (offset {offset}): {e}")
                    break
            
            print(f"🔍 {len(all_portugal_profiles)} Portugal FPF profiel(en) gevonden in Dolphin")
            
            # Vind profielen die niet in actieve lijst staan
            unused_profiles = []
            for profile in all_portugal_profiles:
                profile_id = profile['id']
                if force_cleanup:
                    # Bij force cleanup: verwijder ook afgeronde profielen
                    if profile_id not in active_profile_ids:
                        unused_profiles.append(profile)
                else:
                    # Normale cleanup: alleen verwijder als niet actief
                    if profile_id not in active_profile_ids:
                        unused_profiles.append(profile)
            
            if not unused_profiles:
                print("✅ Geen ongebruikte profielen gevonden")
                return
            
            print(f"🗑️  {len(unused_profiles)} ongebruikte profiel(en) gevonden, verwijderen...")
            
            # Verwijder ongebruikte profielen in chunks (niet allemaal tegelijk om rate limiting te vermijden)
            deleted_count = 0
            chunk_size = 10  # Verwijder in chunks van 10
            
            for i in range(0, len(unused_profiles), chunk_size):
                chunk = unused_profiles[i:i+chunk_size]
                total_chunks = (len(unused_profiles) + chunk_size - 1) // chunk_size
                current_chunk = i // chunk_size + 1
                print(f"   🗑️  Verwijderen chunk {current_chunk}/{total_chunks} ({len(chunk)} profielen)...")
                
                for profile in chunk:
                    try:
                        if self.delete_profile(profile['id']):
                            deleted_count += 1
                            # Clear profile_id from CSV als het verwijderd is
                            if force_cleanup:
                                self._clear_profile_id_from_csv(profile['id'])
                        # Kleine delay om rate limiting te vermijden
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"   ⚠️  Fout bij verwijderen profiel {profile['id']}: {e}")
                
                # Extra delay tussen chunks
                if i + chunk_size < len(unused_profiles):
                    time.sleep(2)
            
            print(f"✅ {deleted_count}/{len(unused_profiles)} ongebruikte profiel(en) verwijderd")
            
        except Exception as e:
            print(f"⚠️  Fout bij cleanup ongebruikte profielen: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_profile_id_from_csv(self, profile_id: int):
        """Clear profile_id from CSV voor een specifiek profiel"""
        try:
            accounts = []
            fieldnames = []
            
            if self.accounts_file.exists():
                with open(self.accounts_file, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    fieldnames = list(reader.fieldnames or [])
                    accounts = list(reader)
                
                # Update accounts met lege profile_id
                for acc in accounts:
                    if acc.get('profile_id', '').strip() == str(profile_id):
                        acc['profile_id'] = ''
                
                # Write back
                with open(self.accounts_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(accounts)
        except Exception as e:
            # Silent fail - niet kritisch
            pass
    
    def _keyboard_listener(self):
        """Listen for keyboard input to stop automation (Windows only)"""
        if not HAS_MSVCRT:
            return
        
        print("\n" + "="*70)
        print("⚠️  STOP MECHANISME ACTIEF")
        print("="*70)
        print("Druk op 'S' of 'Q' om de automation netjes te stoppen")
        print("(Bestaande taken worden afgemaakt, geen nieuwe taken starten)")
        print("="*70 + "\n")
        
        while not self.stop_event.is_set():
            try:
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key in ['s', 'q']:
                        print(f"\n\n{'='*70}")
                        print("🛑 STOP SIGNAL ONTVANGEN!")
                        print(f"{'='*70}")
                        print("⏳ Automation wordt gestopt...")
                        print("   - Nieuwe taken starten niet meer")
                        print("   - Bestaande taken worden afgemaakt")
                        print("   - Profielen worden netjes gesloten")
                        print(f"{'='*70}\n")
                        self.stop_event.set()
                        break
            except:
                pass
            time.sleep(0.1)
    
    def run(self):
        """Main run method with auto-restart support"""
        # Reset stop event
        self.stop_event.clear()
        
        # Start keyboard listener thread (Windows only)
        if HAS_MSVCRT:
            self.stop_keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
            self.stop_keyboard_thread.start()
        
        # Load config for auto-restart and cleanup settings
        automation_config = self.config.get('automation', {})
        auto_restart_runs = automation_config.get('auto_restart_runs', 1)
        cleanup_on_start = automation_config.get('cleanup_on_start', True)
        force_cleanup = automation_config.get('force_cleanup_completed', False)
        
        print(f"🔄 Auto-restart instellingen: {auto_restart_runs} run(s)")
        print(f"🧹 Cleanup bij start: {'Aan' if cleanup_on_start else 'Uit'}")
        
        # Check if continuous monitoring is enabled
        continuous_monitoring = automation_config.get('continuous_monitoring', True)
        
        # Run automation multiple times if configured
        # If continuous monitoring is enabled, run indefinitely until stopped
        run_number = 1
        max_runs = auto_restart_runs if not continuous_monitoring else float('inf')
        
        while run_number <= max_runs and not self.stop_event.is_set():
            # Reset fan_number_found_event at start of each run
            self.fan_number_found_event.clear()
            
            # Check stop event before starting new run
            if self.stop_event.is_set():
                print(f"\n{'='*70}")
                print("🛑 Automation gestopt door gebruiker")
                print(f"{'='*70}\n")
                break
            
            if auto_restart_runs > 1 or continuous_monitoring:
                if continuous_monitoring:
                    print(f"\n{'='*70}")
                    print(f"🚀 RUN {run_number} (continue monitoring)")
                    print(f"{'='*70}\n")
                else:
                print(f"\n{'='*70}")
                print(f"🚀 RUN {run_number}/{auto_restart_runs}")
                print(f"{'='*70}\n")
            
            # Cleanup ongebruikte profielen aan het begin (als enabled)
            if cleanup_on_start:
                self.cleanup_unused_profiles(force_cleanup=force_cleanup)
            
            # Check stop event after cleanup
            if self.stop_event.is_set():
                print(f"\n{'='*70}")
                print("🛑 Automation gestopt door gebruiker")
                print(f"{'='*70}\n")
                break
            
            # Load accounts from CSV - ALTIJD opnieuw lezen om de nieuwste data te krijgen (background scanner kan fan_numbers hebben toegevoegd)
            # Dit zorgt ervoor dat accounts die tijdens de vorige run een fan_number kregen, direct worden opgepikt
            new_accounts = []  # Accounts without account=ja (need account creation)
            signup_accounts = []  # Accounts with account=ja, signup=nee, and fan_number exists (need signup)
            
            if self.accounts_file.exists():
                # ALTIJD de nieuwste CSV lezen (niet uit cache/geheugen)
                print(f"📖 CSV opnieuw lezen voor nieuwste data (run {run_number})...")
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    # Filter accounts that need processing:
                    # - Accounts without account=ja (new accounts) -> new_accounts
                    # - Accounts with account=ja but signup=nee AND fan_number exists (retry accounts) -> signup_accounts
                    # - Skip accounts with skip_reason (already processed/skipped)
                    # - Skip accounts with signup=ja (volledig afgerond, niet opnieuw verwerken)
                    for row in reader:
                        account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                        signup_done = row.get('signup', '').lower() == 'ja'
                        
                        # Skip accounts die volledig afgerond zijn (signup=ja)
                        if account_made and signup_done:
                            continue  # Account is volledig afgerond, niet opnieuw verwerken
                        
                        if not account_made:
                            # Nieuwe account - altijd verwerken (skip_reason wordt genegeerd voor nieuwe accounts)
                            new_accounts.append(row)
                        elif account_made and not signup_done:
                            # Bestaande account zonder signup - alleen verwerken als fan_number bestaat
                            # Skip_reason wordt ALTIJD genegeerd als fan_number bestaat (background scanner heeft fan_number gevonden)
                            # Dit zorgt ervoor dat accounts die tijdens de run een fan_number krijgen, direct worden opgepikt
                            fan_number = row.get('fan_number', '').strip()
                            skip_reason = row.get('skip_reason', '').strip()
                            
                            if fan_number and fan_number.lower() != 'nee':
                                # Fan number bestaat - account kan signup doen (skip_reason wordt genegeerd)
                                # Zelfs als skip_reason bestaat, negeren we het omdat fan_number nu beschikbaar is
                                if skip_reason:
                                    print(f"   🔄 Account {row.get('email', 'N/A')} heeft fan_number ({fan_number}) - skip_reason '{skip_reason}' wordt genegeerd")
                                signup_accounts.append(row)  # Fan number bestaat, kan signup doen
                            # Anders skip (geen fan_number = geen signup mogelijk)
            else:
                print(f"❌ Accounts file niet gevonden: {self.accounts_file}")
                if run_number < auto_restart_runs:
                    continue  # Skip to next run
                else:
                    return
            
            total_accounts = len(new_accounts) + len(signup_accounts)
            if total_accounts == 0:
                print(f"ℹ️ Geen accounts om te verwerken in run {run_number}/{auto_restart_runs} (alle accounts zijn al verwerkt)")
                if run_number < auto_restart_runs:
                    print(f"⏭️  Run {run_number} overgeslagen, doorgaan naar volgende run...")
                    continue  # Skip to next run
                else:
                    return
            
            print(f"📋 {total_accounts} account(s) gevonden om te verwerken (run {run_number}/{auto_restart_runs})")
            print(f"   📝 {len(new_accounts)} nieuwe account(s) voor account-aanmaak")
            print(f"   ✅ {len(signup_accounts)} account(s) met fan_number voor signup")
            
            # Log details about signup accounts for debugging
            if signup_accounts:
                print(f"   🔍 Signup accounts details:")
                accounts_without_profile = 0
                accounts_with_profile = 0
                for idx, acc in enumerate(signup_accounts[:10], 1):  # Show first 10
                    email = acc.get('email', 'N/A')
                    fan_num = acc.get('fan_number', 'N/A')
                    profile_id = acc.get('profile_id', '').strip()
                    skip_reason = acc.get('skip_reason', '')
                    profile_status = "heeft profile_id" if profile_id else "GEEN profile_id (nieuw profiel nodig)"
                    if not profile_id:
                        accounts_without_profile += 1
                    else:
                        accounts_with_profile += 1
                    print(f"      {idx}. {email} - fan_number={fan_num}, {profile_status}" + (f", skip_reason={skip_reason} (wordt genegeerd)" if skip_reason else ""))
                if len(signup_accounts) > 10:
                    print(f"      ... en {len(signup_accounts) - 10} meer")
                print(f"   📊 Signup accounts breakdown: {accounts_with_profile} met profile_id, {accounts_without_profile} zonder profile_id (nieuw profiel nodig)")
            
            if not self.proxy_strings:
                print("❌ Geen proxies gevonden!")
                if run_number < auto_restart_runs:
                    continue  # Skip to next run
                else:
                    return
            
            print(f"🔌 {len(self.proxy_strings)} proxy/proxies beschikbaar")
            
            # Set proxies to empty list to enable lazy loading
            self.proxies = []
            
            # Threading: max 10 threads voor account-aanmaak, rest voor signups
            max_account_creation_threads = min(10, len(new_accounts))
            signup_threads = max(0, self.threads - max_account_creation_threads)
            
            print(f"🧵 Threading configuratie:")
            print(f"   📝 Account-aanmaak: {max_account_creation_threads} thread(s)")
            print(f"   ✅ Signup: {signup_threads} thread(s)")
            print(f"   📊 Totaal: {self.threads} thread(s)")
            
            # Run account creation and signup in parallel using separate thread pools
            def run_account_creation():
                if new_accounts and not self.stop_event.is_set():
            self.run_automation(
                site_config=self.site_config,
                        data_list=new_accounts,
                        threads=max_account_creation_threads
                    )
            
            def run_signups():
                if signup_accounts and not self.stop_event.is_set():
                    self.run_automation(
                        site_config=self.site_config,
                        data_list=signup_accounts,
                        threads=signup_threads
            )
            
            # Run both in parallel, but also monitor for new fan_numbers during execution
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = []
                if new_accounts:
                    futures.append(executor.submit(run_account_creation))
                if signup_accounts:
                    futures.append(executor.submit(run_signups))
                
                # Monitor for new fan_numbers while processing
                # This allows us to immediately start signups when fan_numbers are found
                signup_executor = None
                signup_futures = []
                # Track all emails currently being processed to avoid duplicates
                processing_emails = set()
                for acc in signup_accounts:
                    email = acc.get('email', '')
                    if email:
                        processing_emails.add(email)
                
                while futures:
                    done, not_done = [], []
                    for future in futures:
                        if future.done():
                            done.append(future)
                        else:
                            not_done.append(future)
                    
                    # Process completed futures
                    for future in done:
                        try:
                            future.result()
                        except Exception as e:
                            print(f"❌ Error in parallel execution: {e}")
                    
                    # Check if new fan_number was found during processing
                    if self.fan_number_found_event.is_set():
                        print(f"🚀 Nieuwe fan number gevonden tijdens verwerken! Direct nieuwe signup accounts ophalen en verwerken...")
                        self.fan_number_found_event.clear()
                        
                        # Reload CSV to find new signup accounts
                        new_signup_accounts = []
                        try:
                            if self.accounts_file.exists():
                                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                                    reader = csv.DictReader(f)
                                    for row in reader:
                                        account_made = row.get('account', '').lower() == 'ja' or row.get('entered', '').lower() == 'ja'
                                        signup_done = row.get('signup', '').lower() == 'ja'
                                        if account_made and not signup_done:
                                            fan_number = row.get('fan_number', '').strip()
                                            if fan_number and fan_number.lower() != 'nee':
                                                # Check if this account is not already being processed
                                                email = row.get('email', '')
                                                if email and email not in processing_emails:
                                                    new_signup_accounts.append(row)
                                                    processing_emails.add(email)  # Mark as processing
                        
                        except Exception as e:
                            print(f"⚠️ Fout bij ophalen nieuwe signup accounts: {e}")
                        
                        # Start processing new signup accounts if any found
                        if new_signup_accounts:
                            print(f"✅ {len(new_signup_accounts)} nieuwe signup account(s) gevonden, direct starten...")
                            for acc in new_signup_accounts:
                                email = acc.get('email', 'N/A')
                                fan_num = acc.get('fan_number', 'N/A')
                                print(f"   📝 Start signup voor {email} (fan_number={fan_num})")
                            
                            if signup_executor is None:
                                signup_executor = ThreadPoolExecutor(max_workers=1)
                            
                            def run_new_signups():
                                # Background signups found during main loop - should always run
                                self.run_automation(
                                    site_config=self.site_config,
                                    data_list=new_signup_accounts,
                                    threads=min(signup_threads, len(new_signup_accounts)),
                                    ignore_stop_event=True  # Background signups should always run
                                )
                            
                            signup_futures.append(signup_executor.submit(run_new_signups))
                    
                    # Update futures list
                    futures = not_done
                    
                    # Check signup futures
                    if signup_futures:
                        done_signups = []
                        for sf in signup_futures:
                            if sf.done():
                                try:
                                    sf.result()
                                except Exception as e:
                                    print(f"❌ Error in new signup execution: {e}")
                                done_signups.append(sf)
                        signup_futures = [sf for sf in signup_futures if sf not in done_signups]
                    
                    # Small delay to avoid busy waiting
                    if futures or signup_futures:
                        time.sleep(0.5)
                
                # Wait for any remaining signup futures
                if signup_executor:
                    for sf in signup_futures:
                        try:
                            sf.result()
                        except Exception as e:
                            print(f"❌ Error in remaining signup execution: {e}")
                    signup_executor.shutdown(wait=True)
            
            # Check if fan_number was found during processing - if so, skip wait and go directly to next run
            fan_number_found_during_processing = self.fan_number_found_event.is_set()
            
            # Increment run number for next iteration
            run_number += 1
            
            # Check if we need to wait before next run
            if continuous_monitoring or run_number <= auto_restart_runs:
                # If fan_number was found during processing, skip wait and go directly to next run
                if fan_number_found_during_processing:
                    print(f"🚀 Fan number gevonden tijdens verwerken! Direct doorgaan naar volgende run (geen wachttijd)...")
                    # Reset event for next check
                    self.fan_number_found_event.clear()
                    # Don't wait, go directly to next run
                else:
                    # Wait a bit before next run (or monitoring check)
                    if continuous_monitoring:
                        wait_time = 5  # 5 seconden tussen runs in continuous mode (zeer snel reageren op nieuwe fan_numbers van background scanner)
                        print(f"\n⏳ Wachten maximaal {wait_time} seconden voordat volgende check/run (of direct als fan_number wordt gevonden)...")
                    else:
                        wait_time = 10  # 10 seconden tussen runs in normal mode
                        print(f"\n⏳ Wachten maximaal {wait_time} seconden voordat volgende run start...")
                    
                    # Wait with stop event and fan_number_found_event checking
                    # Use event.wait() to immediately wake up if fan_number is found
                    self.fan_number_found_event.clear()  # Reset event before waiting
                    event_triggered = self.fan_number_found_event.wait(timeout=wait_time)
                    
                    if event_triggered:
                        print(f"🚀 Fan number gevonden! Direct doorgaan naar volgende run (geen wachttijd)...")
                
                # Also check stop event
                if self.stop_event.is_set():
                    break
                
                # Optionele cleanup tussen runs (alleen als we niet direct doorgaan vanwege fan_number)
                if not fan_number_found_during_processing and cleanup_on_start:
                    print("🧹 Cleanup tussen runs...")
                    self.cleanup_unused_profiles(force_cleanup=force_cleanup)
        
        if continuous_monitoring:
            print(f"\n{'='*70}")
            print(f"🛑 Continue monitoring gestopt")
            print(f"{'='*70}\n")
        elif auto_restart_runs > 1:
            print(f"\n{'='*70}")
            print(f"✅ Alle {auto_restart_runs} run(s) voltooid!")
            print(f"{'='*70}\n")
    
    def debug_imap_search(self, target_email: str = None):
        """Debug tool om IMAP search te testen voor een specifiek email adres"""
        print("======================================================================")
        print("🔍 Debug IMAP Search Tool - Portugal FPF")
        print("======================================================================")
        
        # Check for placeholder password
        if "jouw_app_specifiek" in self.imap_config.get('password', '') or not self.imap_config.get('password'):
            print("⚠️  LET OP: Het wachtwoord in de config lijkt nog een placeholder te zijn.")
            # Allow manual input
            pwd = input("    Voer hier het IMAP wachtwoord in (wordt niet opgeslagen): ").strip()
            if pwd:
                self.imap_config['password'] = pwd
                # Update helper
                self.imap_helper.password = pwd
            else:
                print("❌ Geen wachtwoord opgegeven.")
                return
        
        # Ask for email to search if not provided
        if not target_email:
            default_target = "koressatuberman@gmail.com"
            target_email = input(f"📧 Voer het emailadres in waarvoor je de OTP zoekt [Enter voor {default_target}]: ").strip()
            if not target_email:
                target_email = default_target
        
        print(f"\n🔄 Zoeken naar emails voor {target_email}...")
        print("    (We zoeken in de hele inbox, niet alleen vandaag, om 'oude' mails te testen)")
        
        try:
            print(f"🔐 IMAP verbinden met {self.imap_helper.server}...")
            with imaplib.IMAP4_SSL(self.imap_helper.server, self.imap_helper.port) as M:
                M.login(self.imap_helper.email, self.imap_helper.password)
                print(f"✓ Login succesvol als {self.imap_helper.email}")
                M.select(self.imap_helper.folder)
                
                # Search criteria: FROM no-reply@fpf.pt (no date limit for this debug test)
                expected_sender = "no-reply@fpf.pt"
                search_criteria = f'FROM "{expected_sender}"'
                
                print(f"🔍 Searching IMAP met criteria: {search_criteria}")
                status, messages = M.search(None, search_criteria)
                
                if status != 'OK' or not messages[0]:
                    print("❌ Geen emails gevonden van no-reply@fpf.pt")
                    return
                    
                email_ids = messages[0].split()
                print(f"📬 {len(email_ids)} emails gevonden van {expected_sender}. Controleren op recipient {target_email}...")
                
                found_count = 0
                # Check last 100 emails
                check_limit = 100
                print(f"    (Checking laatste {check_limit} emails...)")
                
                for email_id in list(reversed(email_ids))[:check_limit]:
                    try:
                        res, msg_data = M.fetch(email_id, '(RFC822)')
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        to_header = self.imap_helper.decode_str(msg.get('To', ''))
                        subject = self.imap_helper.decode_str(msg.get('Subject', ''))
                        date_str = self.imap_helper.decode_str(msg.get('Date', ''))
                        
                        # Normalize emails
                        target_normalized = target_email.lower().strip()
                        if '@gmail.com' in target_normalized:
                            target_normalized = target_normalized.replace('.', '').split('@')[0]
                        
                        to_normalized = to_header.lower()
                        
                        # Check match
                        is_match = False
                        if target_email.lower() in to_normalized:
                            is_match = True
                        elif '@gmail.com' in target_email.lower():
                            # Try fuzzy match for gmail
                            to_parts = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', to_normalized)
                            for em in to_parts:
                                em_norm = em.replace('.', '').split('@')[0] if '@gmail.com' in em else em
                                if target_normalized == em_norm:
                                    is_match = True
                                    break
                        
                        if is_match:
                            print(f"\n✅ MATCH GEVONDEN! (ID: {email_id.decode()})")
                            print(f"   📅 Datum: {date_str}")
                            print(f"   📧 Subject: {subject}")
                            print(f"   👤 To: {to_header}")
                            
                            # Try to extract code using helper logic
                            # Extract text
                            body = self.imap_helper.get_body_text(msg)
                            html_body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/html":
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            html_body = payload.decode('utf-8', errors='ignore')
                                            break
                            else:
                                if msg.get_content_type() == "text/html":
                                    payload = msg.get_payload(decode=True)
                                    if payload:
                                        html_body = payload.decode('utf-8', errors='ignore')
                            
                            # Search code
                            code = None
                            search_body = html_body if html_body else body
                            
                            code_patterns = [
                                r'código é:\s*(\d+)',
                                r'código:\s*(\d+)',
                                r'verification code:\s*(\d+)',
                                r'code:\s*(\d+)',
                                r'(\d{5,6})'
                            ]
                            
                            for pattern in code_patterns:
                                match = re.search(pattern, search_body, re.IGNORECASE)
                                if match:
                                    code = match.group(1).strip()
                                    if len(code) >= 5:
                                        break
                            
                            if code:
                                print(f"   🔑 OTP CODE: {code}")
                            else:
                                print(f"   ⚠️ Geen OTP code gevonden met regex.")
                                print(f"   Body snippet: {body[:200]}...")
                                
                            found_count += 1
                    except Exception as e:
                        # Silently skip errors
                        pass
                
                if found_count == 0:
                    print(f"\n❌ Geen emails gevonden voor {target_email} in de laatste {check_limit} berichten van {expected_sender}.")
                    print("   Tips:")
                    print("   1. Controleer of het emailadres exact klopt (inclusief punten bij niet-Gmail)")
                    print("   2. Controleer of de email niet ouder is dan de laatste 100 berichten")
                    
        except Exception as e:
            print(f"❌ Error during search: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point"""
    import sys
    
    # Check for debug mode
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    target_email = None
    if debug_mode:
        # Check if email provided as argument
        try:
            debug_idx = sys.argv.index('--debug') if '--debug' in sys.argv else sys.argv.index('-d')
            if len(sys.argv) > debug_idx + 1 and not sys.argv[debug_idx + 1].startswith('-'):
                target_email = sys.argv[debug_idx + 1]
        except (ValueError, IndexError):
            pass
    
    # Determine config file path - handle both EXE and script execution
    if getattr(sys, 'frozen', False):
        # Running as EXE - check bundled files first, then dist/
        exe_dir = Path(sys.executable).parent
        config_file = exe_dir / 'signups' / 'portugal_fpf' / 'portugal_fpf_config.json'
        
        if not config_file.exists():
            # Try dist/ directory
            config_dir = exe_dir / 'signups' / 'portugal_fpf'
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / 'portugal_fpf_config.json'
            
            # Copy default config if it exists in bundled files
            bundled_config = exe_dir / 'signups' / 'portugal_fpf' / 'portugal_fpf_config.json'
            if bundled_config.exists() and not config_file.exists():
                import shutil
                shutil.copy2(bundled_config, config_file)
    else:
        # Running as script - look in signups/portugal_fpf/
        script_dir = Path(__file__).parent
        config_file = script_dir / 'portugal_fpf_config.json'
    
    if not config_file.exists():
        print(f"❌ Config file niet gevonden: {config_file}")
        print("Please create portugal_fpf_config.json with your settings.")
        print(f"   Expected location: {config_file}")
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            print(f"   For EXE, place it at: {exe_dir / 'signups' / 'portugal_fpf' / 'portugal_fpf_config.json'}")
            print(f"   The directory will be created automatically if it doesn't exist.")
        return
    
    try:
        automation = PortugalFPFAutomation(str(config_file))
        
        if debug_mode:
            # Run debug IMAP search
            automation.debug_imap_search(target_email=target_email)
            input("\nDruk op Enter om te sluiten...")
        else:
            # Run normal automation
            automation.run()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

