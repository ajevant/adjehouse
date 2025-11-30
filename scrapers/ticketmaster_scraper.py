#!/usr/bin/env python3
"""
Ticketmaster Email Scraper
Fetches emails from Ticketmaster using central config
"""

import imaplib
import email
import re
import csv
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from email.header import decode_header, make_header
import html
try:
    from lxml import html as lxml_html
    from lxml import etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
try:
    import urllib.request
    import urllib.parse
except ImportError:
    urllib = None

# Determine base directory (same logic for config and output)
if getattr(sys, 'frozen', False):
    # Running as EXE - use EXE directory
    BASE_DIR = Path(sys.executable).parent
else:
    # Running as script - use script directory (ADJEHOUSE root)
    BASE_DIR = Path(__file__).parent.parent

# Load central config
CONFIG_DIR = BASE_DIR / 'settings_for_scraper'
CONFIG_FILE = CONFIG_DIR / 'config.json'

def load_config():
    """Load configuration from central settings"""
    if not CONFIG_FILE.exists():
        print(f"[ERROR] Config file not found: {CONFIG_FILE}")
        return None
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in config file: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return None

# Load config
config = load_config()
if config:
    IMAP_ACCOUNTS = config['imap_accounts'].get('ticketmaster', [])
    SEARCH_DAYS = config['search_settings'].get('default_search_days', 2)
else:
    IMAP_ACCOUNTS = []
    SEARCH_DAYS = 2

# Output file - in ADJEHOUSE success directory (next to EXE)
OUTPUT_DIR = BASE_DIR / "success"
OUTPUT_FILE = OUTPUT_DIR / "ticketmaster_success.csv"

def get_body_text(msg):
    """Extract text content from email message"""
    text = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    text += body
                except:
                    pass
            elif content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    # Remove HTML tags and decode entities
                    clean_text = re.sub(r'<[^>]+>', ' ', html_body)
                    clean_text = html.unescape(clean_text)
                    text += clean_text
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            if msg.get_content_type() == "text/html":
                clean_text = re.sub(r'<[^>]+>', ' ', body)
                clean_text = html.unescape(clean_text)
                text = clean_text
            else:
                text = body
        except:
            pass
    
    return text

def get_usd_to_eur_rate():
    """Get current USD to EUR exchange rate"""
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        if urllib:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                rate = data.get('rates', {}).get('EUR', 0.92)
                return float(rate)
    except Exception:
        pass
    return 0.92  # Fallback

def get_gbp_to_eur_rate():
    """Get current GBP to EUR exchange rate"""
    try:
        url = "https://api.exchangerate-api.com/v4/latest/GBP"
        if urllib:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                rate = data.get('rates', {}).get('EUR', 1.18)
                return float(rate)
    except Exception:
        pass
    return 1.18  # Fallback

def get_dkk_to_eur_rate():
    """Get current DKK to EUR exchange rate"""
    try:
        url = "https://api.exchangerate-api.com/v4/latest/DKK"
        if urllib:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                rate = data.get('rates', {}).get('EUR', 0.134)
                return float(rate)
    except Exception:
        pass
    return 0.134  # Fallback (approximately 1 DKK = 0.134 EUR)

def decode_str(s):
    """Decode email header strings properly"""
    if s is None:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        # Fallback if make_header fails
        try:
            decoded = decode_header(s)[0]
            if isinstance(decoded[0], bytes):
                return decoded[0].decode('utf-8', errors='ignore')
            else:
                return str(decoded[0])
        except Exception:
            return str(s) if s else ""

def get_html_body(msg):
    """Extract HTML content from email message"""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    return html_body
                except:
                    pass
    else:
        try:
            if msg.get_content_type() == "text/html":
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                return body
        except:
            pass
    return None

def extract_us_order_data(msg, subject):
    """Extract data from US Ticketmaster 'You Got Tickets To' email"""
    if not LXML_AVAILABLE:
        return None
    
    html_content = get_html_body(msg)
    if not html_content:
        return None
    
    order_data = {
        'event_name': '',
        'event_date': '',
        'day_name': '',
        'venue': '',
        'section': '',
        'row': '',
        'seat': '',
        'quantity': '',
        'price_usd': '',
        'total_usd': '',
        'price_eur': '',
        'total_eur': '',
        'price_gbp': '',
        'total_gbp': '',
        'order_id': '',
        'recipient_email': '',
        'email_date': decode_str(msg.get('Date', '')),
        'imap_account': ''
    }
    
    try:
        tree = lxml_html.fromstring(html_content)
        
        # Event name from subject (title)
        # Subject format: "You Got Tickets To [Event Name]"
        if subject.lower().startswith('you got tickets to'):
            event_name = subject.replace('You Got Tickets To', '').strip()
            order_data['event_name'] = event_name
        
        # Order ID: "Order # 37-55107/NY7"
        order_elements = tree.xpath('//td[contains(text(), "Order #")]')
        if order_elements:
            order_text = etree.tostring(order_elements[0], method='text', encoding='unicode').strip()
            order_match = re.search(r'Order\s*#\s*([A-Z0-9\-/]+)', order_text, re.IGNORECASE)
            if order_match:
                order_data['order_id'] = order_match.group(1).strip()
        
        # Date: "Mon · Aug 17, 2026 · 8:00 PM"
        # Try multiple XPath patterns to find the date
        date_elements = tree.xpath('//td[contains(text(), "·") and (contains(text(), "PM") or contains(text(), "AM"))]')
        if not date_elements:
            # Try finding td elements with day names
            date_elements = tree.xpath('//td[contains(text(), "Mon") or contains(text(), "Tue") or contains(text(), "Wed") or contains(text(), "Thu") or contains(text(), "Fri") or contains(text(), "Sat") or contains(text(), "Sun")]')
        if date_elements:
            for date_elem in date_elements:
                date_text = etree.tostring(date_elem, method='text', encoding='unicode').strip()
                # Parse "Mon · Aug 17, 2026 · 8:00 PM" format
                date_match = re.search(r'(\w+)\s*·\s*(\w+)\s+(\d+),\s+(\d+)\s*·\s*(\d+):(\d+)\s*(PM|AM)', date_text, re.IGNORECASE)
                if date_match:
                    day_name, month, day, year, hour, minute, am_pm = date_match.groups()
                    try:
                        month_map = {
                            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
                            'january': '01', 'february': '02', 'march': '03', 'april': '04',
                            'may': '05', 'june': '06', 'july': '07', 'august': '08',
                            'september': '09', 'october': '10', 'november': '11', 'december': '12'
                        }
                        month_num = month_map.get(month.lower()[:3], '01')
                        order_data['event_date'] = f"{day.zfill(2)}-{month_num}-{year}"
                        
                        # Convert short day names to full names
                        day_mapping = {
                            'Mon': 'Monday', 'Tue': 'Tuesday', 'Wed': 'Wednesday',
                            'Thu': 'Thursday', 'Fri': 'Friday', 'Sat': 'Saturday', 'Sun': 'Sunday'
                        }
                        order_data['day_name'] = day_mapping.get(day_name, day_name)
                        break
                    except:
                        continue
        
        # Venue: "Madison Square Garden — New York, New York"
        venue_elements = tree.xpath('//td[contains(text(), "—")]')
        if venue_elements:
            venue_text = etree.tostring(venue_elements[0], method='text', encoding='unicode').strip()
            # Extract venue name before "—"
            venue_match = re.search(r'^([^—]+)', venue_text)
            if venue_match:
                order_data['venue'] = venue_match.group(1).strip()
        
        # Section, Row, Seat: "Sec 223, Row B25, Seat 5 - 6"
        seat_elements = tree.xpath('//td[contains(text(), "Sec") and contains(text(), "Row") and contains(text(), "Seat")]')
        if seat_elements:
            seat_text = etree.tostring(seat_elements[0], method='text', encoding='unicode').strip()
            # Parse "Sec 223, Row B25, Seat 5 - 6"
            section_match = re.search(r'Sec\s*([A-Z0-9]+)', seat_text, re.IGNORECASE)
            if section_match:
                order_data['section'] = section_match.group(1).strip()
            
            row_match = re.search(r'Row\s*([A-Z0-9]+)', seat_text, re.IGNORECASE)
            if row_match:
                order_data['row'] = row_match.group(1).strip()
            
            seat_match = re.search(r'Seat\s*([0-9\s\-]+)', seat_text, re.IGNORECASE)
            if seat_match:
                order_data['seat'] = seat_match.group(1).strip()
                # Extract quantity from seat range (e.g., "5 - 6" = 2 tickets)
                if ' - ' in order_data['seat']:
                    try:
                        seat_parts = order_data['seat'].split(' - ')
                        if len(seat_parts) == 2:
                            start_seat = int(seat_parts[0].strip())
                            end_seat = int(seat_parts[1].strip())
                            quantity = end_seat - start_seat + 1
                            order_data['quantity'] = str(quantity)
                    except:
                        pass
        
        # Total price: "Total: $218.30"
        total_elements = tree.xpath('//td[contains(text(), "Total:")]')
        if total_elements:
            total_text = etree.tostring(total_elements[0], method='text', encoding='unicode').strip()
            total_match = re.search(r'Total[:\s]*\$?([\d.]+)', total_text, re.IGNORECASE)
            if total_match:
                order_data['total_usd'] = total_match.group(1).strip()
        
        # Convert USD to EUR
        usd_to_eur = get_usd_to_eur_rate()
        if order_data['total_usd']:
            try:
                total_eur_val = float(order_data['total_usd']) * usd_to_eur
                order_data['total_eur'] = str(round(total_eur_val, 2)).replace('.', ',')
            except:
                pass
        
        # Format USD prices
        if order_data['total_usd']:
            try:
                order_data['total_usd'] = str(float(order_data['total_usd'])).replace('.', ',')
            except:
                pass
        
        # Recipient email
        to_header = decode_str(msg.get('To', ''))
        if to_header:
            email_match = re.search(r'<([^>]+)>', to_header)
            if email_match:
                order_data['recipient_email'] = email_match.group(1)
            else:
                order_data['recipient_email'] = to_header
        
    except Exception as e:
        print(f"[ERROR] Failed to parse US order: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    return order_data

def extract_event_data(msg, imap_account):
    """Extract event data from Ticketmaster email"""
    text = get_body_text(msg)
    
    # Initialize data
    order_data = {
        'event_name': '',
        'event_date': '',
        'day_name': '',
        'venue': '',
        'section': '',
        'row': '',
        'seat': '',
        'quantity': '',
        'price_gbp': '',
        'total_gbp': '',
        'price_usd': '',
        'total_usd': '',
        'price_eur': '',
        'total_eur': '',
        'order_id': '',
        'recipient_email': '',
        'email_date': '',
        'imap_account': imap_account
    }
    
    # Extract recipient email
    to_header = msg.get('To', '')
    if to_header:
        decoded = decode_header(to_header)[0]
        if isinstance(decoded[0], bytes):
            email_text = decoded[0].decode('utf-8', errors='ignore')
        else:
            email_text = str(decoded[0])
        
        # Extract just the email address from "Hide My Email <mondo-arbiter2v@icloud.com>"
        email_match = re.search(r'<([^>]+)>', email_text)
        if email_match:
            order_data['recipient_email'] = email_match.group(1)
        else:
            order_data['recipient_email'] = email_text
    
    # Extract email date
    date_header = msg.get('Date', '')
    if date_header:
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_header)
            order_data['email_date'] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except:
            order_data['email_date'] = date_header
    
    # Get subject line for event name extraction
    subject_line = msg.get('Subject', '')
    subject_text = ''
    if subject_line:
        decoded = decode_header(subject_line)[0]
        if isinstance(decoded[0], bytes):
            subject_text = decoded[0].decode('utf-8', errors='ignore')
        else:
            subject_text = str(decoded[0])
    
    # Event name patterns for Ticketmaster - prioritize subject line patterns
    # First try subject line only, then body if needed
    event_name_patterns_subject = [
        # Subject line patterns - extract event name between "Your"/"You're in! Your" and "ticket confirmation"
        # Use positive lookahead to ensure we stop before "ticket confirmation"
        r"You're in!\s+Your\s+([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)(?=\s+ticket\s+confirmation)",  # You're in! Your CITY POP WAVES: MASAYOSHI TAKANAKA SUPER TAKANAKA WORLD LIVE 2026 ticket confirmation
        r"Your\s+([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)(?=\s+ticket\s+confirmation)",  # Your FRED AGAIN.. ticket confirmation
        # Danish format: "Ordrebekræftelse. Ordrenummer: RE18925289 (Radiohead Europe 2025 - 4. december 2025 18.00)"
        r'Ordrebekræftelse[^\(]*\(([A-Z][A-Za-z\s\-:&\.]+(?:\s+\d{4})?)\s*-',  # DK: Extract from parentheses in subject, year optional
        r'\(([A-Z][A-Za-z\s\-:&\.]+(?:\s+\d{4})?)\s*-',  # Generic: Extract event name from parentheses before date, year optional
        # German format: "Deine Bestellbestätigung RE18790116 - Lady Gaga: The MAYHEM Ball"
        r'Deine Bestellbestätigung\s+\w+\s*-\s*([A-Z][A-Za-z\s\-:&\.]+[A-Za-z])',  # DE: Subject line
        r'Your Order Confirmation\s+([A-Z][A-Za-z\s\-:&\.]+[A-Za-z])',  # DE: English part of subject
        # Belgian format: "Lady Gaga: The MAYHEM Ball 11.11.2025 18:30 | Jouw bestelling..."
        r'([A-Z][A-Za-z\s\-:&\.]+[A-Za-z])\s+\d+\.\d+\.\d+\s+\d+:\d+\s*\|',  # Belgian subject: Event name | date | bestelling
    ]
    
    # Try subject line first (most reliable)
    for pattern in event_name_patterns_subject:
        match = re.search(pattern, subject_text, re.MULTILINE | re.IGNORECASE)
        if match:
            event_name = match.group(1).strip()
            
            # Clean up event name - remove leading "Your" and trailing "ticket confirmation" if present
            event_name = re.sub(r'^Your\s+', '', event_name, flags=re.IGNORECASE)
            event_name = re.sub(r'\s+ticket\s+confirmation$', '', event_name, flags=re.IGNORECASE)
            event_name = re.sub(r'\s+ticket\s*$', '', event_name, flags=re.IGNORECASE)
            event_name = re.sub(r'\s+confirmation\s*$', '', event_name, flags=re.IGNORECASE)
            event_name = event_name.strip()
            
            # Skip generic words that aren't event names
            if event_name.lower() not in ['your', 'ticket', 'confirmation', 'you', 'got', 'tickets', 'event', 'reminder', 'last', 'chance', 'book', 'miss', 'moment', 'important', 'instructions', 'upcoming', 'jouw', 'bestelling', 'votre', 'commande', 'order']:
                # Additional check: make sure it's a reasonable event name
                if len(event_name) > 2 and (len(event_name.split()) > 1 or event_name.isupper() or ':' in event_name or '..' in event_name):
                    order_data['event_name'] = event_name
                    break
    
    # If no match in subject, try body patterns (more restrictive to avoid false matches)
    if not order_data['event_name']:
        # Body patterns - more restrictive to avoid matching insurance text, etc.
        event_name_patterns_body = [
            # UK format: Event names before dates (in body, often on own line or before date)
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Tue\s+\d+\s+\w+\s+\d+',  # Tuesday - non-greedy to stop before date
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Wed\s+\d+\s+\w+\s+\d+',  # Wednesday
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Thu\s+\d+\s+\w+\s+\d+',  # Thursday
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Fri\s+\d+\s+\w+\s+\d+',  # Friday
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Sat\s+\d+\s+\w+\s+\d+',  # Saturday
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Sun\s+\d+\s+\w+\s+\d+',  # Sunday
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*Mon\s+\d+\s+\w+\s+\d+',  # Monday
            # US Ticketmaster format: "Demi Lovato - One Night Only at the Palladium" on its own line
            r'([A-Z][A-Za-z0-9\s\-:&\.]+?(?:at the|at|@)\s+[A-Za-z\s]+?)(?=\s*(?:Sat|Sun|Mon|Tue|Wed|Thu|Fri)\s*·)',  # US: Event name before date - non-greedy with lookahead
            # Event name on its own line (common in email body)
            r'^([A-Z][A-Za-z0-9\s\-:&\.]+?(?:\s+\d{4})?)\s*$',  # Standalone event name on its own line
        ]
        
        for pattern in event_name_patterns_body:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                event_name = match.group(1).strip()
                
                # Clean up event name
                event_name = re.sub(r'^Your\s+', '', event_name, flags=re.IGNORECASE)
                event_name = re.sub(r'\s+ticket\s+confirmation$', '', event_name, flags=re.IGNORECASE)
                event_name = re.sub(r'\s+ticket\s*$', '', event_name, flags=re.IGNORECASE)
                event_name = re.sub(r'\s+confirmation\s*$', '', event_name, flags=re.IGNORECASE)
                event_name = event_name.strip()
                
                # Skip generic words and check for common false positives (like "including COVID")
                skip_words = ['your', 'ticket', 'confirmation', 'you', 'got', 'tickets', 'event', 'reminder', 'last', 
                             'chance', 'book', 'miss', 'moment', 'important', 'instructions', 'upcoming', 'jouw', 
                             'bestelling', 'votre', 'commande', 'order', 'including', 'covid', 'insurance', 'serious', 
                             'illness', 'weather', 'traffic', 'transport', 'delay', 'mechanical', 'breakdown', 'theft', 
                             'jury', 'service', 'job', 'loss']
                
                # Check if event name contains any skip words
                event_lower = event_name.lower()
                if event_lower not in skip_words and not any(skip in event_lower for skip in skip_words):
                    # Additional check: make sure it's a reasonable event name
                    if len(event_name) > 2 and (len(event_name.split()) > 1 or event_name.isupper() or ':' in event_name or '..' in event_name):
                        order_data['event_name'] = event_name
                        break
    
    # Event date patterns
    date_patterns = [
        # Danish format: Torsdag 4. december 2025 18.00
        r'(Mandag|Tirsdag|Onsdag|Torsdag|Fredag|Lørdag|Søndag)\s+(\d+)\.\s+(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s+(\d+)\s+(\d+)[\.:](\d+)',
        # German format: Mittwoch, 05. November 2025, 20:00 Uhr
        r'(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+(\d+)\.\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d+),\s+(\d+):(\d+)\s+Uhr',
        # US format: Sat · Oct 25, 2025 · 7:00 PM
        r'(Sat|Sun|Mon|Tue|Wed|Thu|Fri)\s*·\s*(\w+)\s+(\d+),\s+(\d+)\s*·\s*(\d+):(\d+)\s*PM',
        r'(Sat|Sun|Mon|Tue|Wed|Thu|Fri)\s*·\s*(\w+)\s+(\d+),\s+(\d+)\s*·\s*(\d+):(\d+)\s*AM',
        r'(Saturday|Sunday|Monday|Tuesday|Wednesday|Thursday|Friday)\s*·\s*(\w+)\s+(\d+),\s+(\d+)\s*·\s*(\d+):(\d+)\s*PM',
        r'(Saturday|Sunday|Monday|Tuesday|Wednesday|Thursday|Friday)\s*·\s*(\w+)\s+(\d+),\s+(\d+)\s*·\s*(\d+):(\d+)\s*AM',
        # UK format: Fri 03 Oct 2025 • 7:00 pm
        r'(\w+)\s+(\d+)\s+(\w+)\s+(\d+)\s*•\s*(\d+):(\d+)\s*pm',  # Fri 03 Oct 2025 • 7:00 pm
        r'(\w+)\s+(\d+)\s+(\w+)\s+(\d+)\s*•\s*(\d+):(\d+)\s*am',  # AM times
        r'(\d+)\s+(\w+)\s+(\d+)\s*•\s*(\d+):(\d+)\s*pm',
        r'(\d+)\s+(\w+)\s+(\d+)\s*•\s*(\d+):(\d+)\s*am',
        # Belgian format: 11.11.2025 - 18:30
        r'(\d+)\.(\d+)\.(\d+)\s*-\s*(\d+):(\d+)',  # 11.11.2025 - 18:30
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                groups = match.groups()
                
                # Danish format: (day_name, day, month, year, hour, minute) - "Torsdag 4. december 2025 18.00"
                if len(groups) == 6 and any(dk_day in groups[0] for dk_day in ['Mandag', 'Tirsdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lørdag', 'Søndag']):
                    # Danish format: day_name, day, month, year, hour, minute
                    day_name_dk, day, month_dk, year, hour, minute = groups
                    # Map Danish day names to English
                    dk_day_map = {
                        'Mandag': 'Monday', 'Tirsdag': 'Tuesday', 'Onsdag': 'Wednesday',
                        'Torsdag': 'Thursday', 'Fredag': 'Friday', 'Lørdag': 'Saturday', 'Søndag': 'Sunday'
                    }
                    order_data['day_name'] = dk_day_map.get(day_name_dk, '')
                    # Map Danish month names
                    dk_month_map = {
                        'januar': '01', 'februar': '02', 'marts': '03', 'april': '04',
                        'maj': '05', 'juni': '06', 'juli': '07', 'august': '08',
                        'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
                    }
                    month_num = dk_month_map.get(month_dk.lower(), '01')
                    event_date = f"{day.zfill(2)}-{month_num}-{year}"
                    order_data['event_date'] = event_date
                    break
                # German format: (day_name, day, month, year, hour, minute) - "Mittwoch, 05. November 2025, 20:00 Uhr"
                elif len(groups) == 6 and any(de_day in groups[0] for de_day in ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']):
                    # German format: day_name, day, month, year, hour, minute
                    day_name_de, day, month_de, year, hour, minute = groups
                    # Map German day names to English
                    de_day_map = {
                        'Montag': 'Monday', 'Dienstag': 'Tuesday', 'Mittwoch': 'Wednesday',
                        'Donnerstag': 'Thursday', 'Freitag': 'Friday', 'Samstag': 'Saturday', 'Sonntag': 'Sunday'
                    }
                    order_data['day_name'] = de_day_map.get(day_name_de, '')
                    # Map German month names
                    de_month_map = {
                        'januar': '01', 'februar': '02', 'märz': '03', 'april': '04',
                        'mai': '05', 'juni': '06', 'juli': '07', 'august': '08',
                        'september': '09', 'oktober': '10', 'november': '11', 'dezember': '12'
                    }
                    month_num = de_month_map.get(month_de.lower(), '01')
                    event_date = f"{day.zfill(2)}-{month_num}-{year}"
                    order_data['event_date'] = event_date
                    break
                # Belgian format: (day, month, year, hour, minute) - DD.MM.YYYY
                elif len(groups) == 5 and '.' in match.group(0) and groups[1].isdigit():
                    # Belgian format: 11.11.2025 - 18:30 (month is numeric)
                    day, month, year, hour, minute = groups
                    # Get day name from the date
                    try:
                        dt = datetime(int(year), int(month), int(day))
                        order_data['day_name'] = dt.strftime('%A')
                    except:
                        order_data['day_name'] = ''
                elif len(groups) == 6:  # Day name included
                    # Check if second element is a digit (UK) or word (US)
                    if groups[1].isdigit():
                        # UK format: day_name, day, month, year, hour, minute
                        day_name, day, month, year, hour, minute = groups
                    else:
                        # US format: day_name, month, day, year, hour, minute
                        day_name, month, day, year, hour, minute = groups
                    
                    order_data['day_name'] = day_name
                else:  # No day name (5 groups)
                    if groups[0].isdigit():
                        # UK format: day, month, year, hour, minute
                        day, month, year, hour, minute = groups
                    else:
                        # US format: month, day, year, hour, minute
                        month, day, year, hour, minute = groups
                    order_data['day_name'] = ''
                
                # Convert to datetime
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
                    'january': '01', 'february': '02', 'march': '03', 'april': '04',
                    'may': '05', 'june': '06', 'july': '07', 'august': '08',
                    'september': '09', 'october': '10', 'november': '11', 'december': '12'
                }
                
                month_num = month_map.get(month.lower()[:3], '01')
                event_date = f"{day.zfill(2)}-{month_num}-{year}"
                order_data['event_date'] = event_date
                
                # Get day name if not already extracted
                if not order_data['day_name']:
                    try:
                        dt = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
                        order_data['day_name'] = dt.strftime('%A')
                    except:
                        pass
                
                # Convert short day names to full names
                day_mapping = {
                    'Mon': 'Monday',
                    'Tue': 'Tuesday', 
                    'Wed': 'Wednesday',
                    'Thu': 'Thursday',
                    'Fri': 'Friday',
                    'Sat': 'Saturday',
                    'Sun': 'Sunday'
                }
                if order_data['day_name'] in day_mapping:
                    order_data['day_name'] = day_mapping[order_data['day_name']]
                break
            except:
                continue
    
    # Venue patterns
    venue_patterns = [
        # German format: "Uber Arena" (standalone, before date)
        r'([A-Z][A-Za-z\s]+(?:Arena|Theatre|Theater|Hall|Stadium|Center|Centre|Garden|Forum|Pavilion|Amphitheatre|Amphitheater|Palladium|Opera House|Dome))\s*(?:Mittwoch|Montag|Dienstag|Donnerstag|Freitag|Samstag|Sonntag)',
        r'([A-Z][A-Za-z\s]+Arena)\s*$',  # German: "Uber Arena" on its own line
        # Belgian format: "AFAS Dome" on its own line
        r'([A-Z][A-Za-z\s]+(?:Dome|Arena|Theatre|Theater|Hall|Stadium|Center|Centre|Garden|Forum|Pavilion|Amphitheatre|Amphitheater|Palladium|Opera House))\s*\n\s*\d+\.\d+\.\d+',
        # US format: "Hollywood Palladium — Hollywood, California"
        r'([A-Z][A-Za-z\s]+(?:Palladium|Arena|Theatre|Theater|Hall|Stadium|Center|Centre|Garden|Forum|Pavilion|Amphitheatre|Amphitheater))\s*—\s*[A-Za-z\s,]+',
        # UK format
        r'([A-Z][A-Za-z\s,]+(?:Centre|Arena|Theatre|Hall|Stadium|O2|Apollo|Academy|Palladium|Coliseum|Opera House|Royal Albert Hall|Wembley|Twickenham|Stadium|Ground|Park|Garden|Place|Square|Centre|Center|Arena|Theatre|Theater|Hall|Stadium|O2|Apollo|Academy|Palladium|Coliseum|Opera House|Royal Albert Hall|Wembley|Twickenham|Stadium|Ground|Park|Garden|Place|Square))',
        r'Venue:\s*([^\n]+)',
        r'Location:\s*([^\n]+)',
    ]
    
    for pattern in venue_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            venue = match.group(1).strip()
            # Clean up venue name - remove "pm" and extra spaces
            venue = re.sub(r'\s+pm\s*$', '', venue, flags=re.IGNORECASE)
            venue = re.sub(r'^pm\s+', '', venue, flags=re.IGNORECASE)
            venue = re.sub(r'\s+', ' ', venue)
            order_data['venue'] = venue
            break
    
    # Section/Row/Seat patterns for Ticketmaster
    section_patterns = [
        r'SEKTION\s*/\s*SECTION[:\s]*([A-Z0-9\-]+)',  # Danish: "SEKTION/SECTION: 1-117"
        r'BLOCK/SECTION\s+([A-Z0-9\-]+)',  # German: "BLOCK/SECTION O-420"
        r'BLOCK\s*/\s*SECTION\s*([A-Z0-9\-]+)',  # German alternative
        r'ZONE\s*-\s*BLOCK\s*([A-Z0-9\-]+)',  # Belgian: "ZONE - BLOCK TR-138"
        r'TR\-(\d+)',  # Belgian: "TR-138"
        r'(Unreserved Standing)',
        r'(General Admission)',
        r'(Standing)',
        r'(Floor)',
        r'Section\s*([A-Z0-9]+)',
        r'([A-Z0-9]+)\s*Section',
    ]
    
    for pattern in section_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            section = match.group(1).strip()
            # Add TR- prefix if it's just a number from Belgian format
            if section.isdigit():
                order_data['section'] = f'TR-{section}'
            else:
                order_data['section'] = section
            break
    
    # Row patterns
    row_patterns = [
        r'RÆKKE\s*/\s*ROW[:\s]*(\d+)',  # Danish: "RÆKKE/ROW: 8"
        r'RIJ\s*-\s*RANGÉE\s*-\s*ROW\s*(\d+)',  # Belgian: "RIJ - RANGÉE - ROW 32"
        r'REIHE\s*/\s*ROW[:\s]*(\d+)',  # German: "REIHE/ROW 8"
        r'Row[:\s]*(\d+)',
        r'Rangée[:\s]*(\d+)',
    ]
    
    for pattern in row_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['row'] = match.group(1).strip()
            break
    
    # Seat patterns
    seat_patterns = [
        r'PLADS\s*/\s*SEAT[:\s]*(\d+)',  # Danish: "PLADS/SEAT: 341"
        r'STOEL\s*-\s*SIÈGE\s*-\s*SEAT\s*(\d+)',  # Belgian: "STOEL - SIÈGE - SEAT 4"
        r'PLATZ\s*/\s*SEAT[:\s]*(\d+-\d+)',  # German: "PLATZ/SEAT 15-16"
        r'PLATZ\s*/\s*SEAT[:\s]*(\d+)',  # German: "PLATZ/SEAT 15"
        r'Seat[:\s]*(\d+-\d+)',  # Generic: "Seat 15-16" (multiple seats)
        r'Seat[:\s]*(\d+)',  # Generic: "Seat 15"
        r'Siège[:\s]*(\d+)',
        r'Seat[:\s]*([A-Z]\d+)',  # Letter+number like A1
    ]
    
    for pattern in seat_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['seat'] = match.group(1).strip()
            break
    
    # Quantity patterns
    quantity_patterns = [
        r'Antal\s+billetter[:\s]*(\d+)',  # Danish: "Antal billetter: 1"
        r'Ticketanzahl\s*/\s*Quantity[:\s]*(\d+)',  # German: "Ticketanzahl/Quantity:2"
        r'Ticket\s+quantity[:\s]*(\d+)',  # Belgian: "Ticket quantity: 1"
        r'Aantal\s+tickets[:\s]*(\d+)',  # Belgian Dutch
        r'Nombre\s+de\s+tickets[:\s]*(\d+)',  # Belgian French
        r'(\d+)\s+x\s+tickets',  # "1 x tickets" format
        r'(\d+)x\s+Mobile\s+Ticket',
        r'(\d+)x\s+Full\s+Price\s+Ticket',
        r'(\d+)\s+x\s+',
        r'Qty[:\s]*(\d+)',
        r'Quantity[:\s]*(\d+)',
    ]
    
    for pattern in quantity_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['quantity'] = match.group(1).strip()
            break
    
    # Price patterns - look for per-ticket prices (GBP, EUR, and DKK)
    price_patterns = [
        # Danish DKK format: Billet(ter)/Ticket(s): 1 x 1.073,00 DKK (i alt/total: 1.073,00 DKK)
        r'Billet\(ter\)[:\s]*(\d+)\s*x\s*(\d+[,\.]?\d*)\s*DKK',  # "Billet(ter)/Ticket(s): 1 x 1.073,00 DKK"
        r'(\d+)\s*x\s*(\d+[,\.]?\d*)\s*DKK',  # "1 x 1.073,00 DKK"
        # German EUR format: Ticket(s): €118,25 x 2: €236,50
        r'Ticket\(s\)[:\s]*€(\d+[,\.]?\d*)\s*x\s*(\d+)',
        r'€(\d+[,\.]?\d*)\s*x\s*(\d+)',  # Generic EUR: €118,25 x 2
        r'(\d+)\s*x\s*[^\d]*€(\d+[,\.]?\d*)',  # 2 x ... €118,25
        # GBP patterns
        r'£(\d+\.?\d*)\s*x\s*(\d+)',  # £61.25 x4
        r'(\d+)\s*x\s*Full\s+Price\s+Ticket\s*£(\d+\.?\d*)',  # 4 x Full Price Ticket £245.00
        r'(\d+)\s*x\s*[^£]*£(\d+\.?\d*)',  # 4 x Mobile Ticket £245.00
        r'£(\d+\.?\d*)\s*per\s*ticket',  # £61.25 per ticket
        r'£(\d+\.?\d*)\s*each',  # £61.25 each
        r'£(\d+\.?\d*)\s*per\s*item',  # £61.25 per item
        # Look for prices in payment summary section
        r'(\d+)\s*x\s*Full\s+Price\s+Ticket\s*£(\d+\.?\d*)',  # 4 x Full Price Ticket £245.00
        r'(\d+)\s*x\s*[^£]*£(\d+\.?\d*)',  # 4 x Mobile Ticket £245.00
        # Look for specific price patterns in the email
        r'£(\d+\.?\d*)\s*x\s*(\d+)',  # £61.25 x4
        r'(\d+)\s*x\s*[^£]*£(\d+\.?\d*)',  # 4 x Mobile Ticket £245.00
        # Look for prices in the email body more broadly
        r'£(\d+\.?\d*)\s*x\s*(\d+)',  # £61.25 x4
        r'(\d+)\s*x\s*[^£]*£(\d+\.?\d*)',  # 4 x Mobile Ticket £245.00
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) == 2:
                # Check if this is DKK, EUR, or GBP to handle group order correctly
                is_dkk = 'DKK' in pattern
                is_eur = '€' in pattern
                
                # For DKK patterns: "1 x 1.073,00 DKK" - groups are (qty, price)
                # For EUR patterns: "€118,25 x 2" - groups are (price, qty)
                # For GBP patterns: "£61.25 x4" - groups are (price, qty)
                if is_dkk:
                    qty, price_per_ticket_str = match.groups()
                else:
                    price_per_ticket_str, qty = match.groups()
                
                if not order_data['quantity']:
                    order_data['quantity'] = qty.strip()
                
                try:
                    # Handle DKK format (1.073,00 DKK) - dot is thousands separator, comma is decimal
                    if is_dkk:
                        price_per_ticket_val = float(price_per_ticket_str.replace('.', '').replace(',', '.'))
                        # Convert DKK to EUR
                        dkk_to_eur = get_dkk_to_eur_rate()
                        eur_value = price_per_ticket_val * dkk_to_eur
                        order_data['price_eur'] = f"{eur_value:.2f}".replace('.', ',')
                    # Handle EUR comma format (€118,25)
                    elif is_eur:
                        price_per_ticket_val = float(price_per_ticket_str.replace(',', '.'))
                        # Save directly to price_eur (no conversion needed)
                        order_data['price_eur'] = f"{price_per_ticket_val:.2f}".replace('.', ',')
                    else:
                        qty_num = float(qty.strip())
                        total_num = float(price_per_ticket_str.strip())
                        if qty_num > 0 and total_num > 0:
                            price_per_ticket = total_num / qty_num
                            if 10 <= price_per_ticket <= 1000:
                                order_data['price_gbp'] = f"{price_per_ticket:.2f}"
                                break
                except:
                    pass
            elif len(match.groups()) == 1:
                price = match.group(1)
                try:
                    price_num = float(price.strip().replace(',', '.'))
                    if 10 <= price_num <= 1000:
                        if '€' in pattern:
                            order_data['price_eur'] = f"{price_num:.2f}".replace('.', ',')
                        else:
                            order_data['price_gbp'] = price.strip()
                        break
                except:
                    pass
    
    # Total price patterns (GBP, EUR, and DKK)
    total_patterns = [
        # Danish DKK format: Samlet pris/Total: 1.201,76 DKK
        r'Samlet\s+pris\s*/\s*Total[:\s]*(\d+[,\.]?\d*)\s*DKK',
        # German EUR format: Gesamtpreis/Total: €271,98
        r'Gesamtpreis\s*/\s*Total[:\s]*€(\d+[,\.]?\d*)',
        # Order Total format: "Order Total: 589,40 EUR"
        r'Order\s+Total[:\s]*(\d+[,\.]?\d*)\s*EUR',
        r'Order\s+Total[:\s]*€(\d+[,\.]?\d*)',
        r'Total[:\s]*€(\d+[,\.]?\d*)',  # Generic EUR total
        r'Total\s*\(incl\.\s*fee\)\s*£(\d+\.?\d*)',
        r'Total[:\s]*£(\d+\.?\d*)',
        r'Grand\s+Total[:\s]*£(\d+\.?\d*)',
        # Belgian EUR format: Totaal - Total: €155,86
        r'Totaal\s*-\s*Total[:\s]*€(\d+[,\.]?\d*)',
    ]
    
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Check if this is DKK, EUR, or GBP based on the pattern
            if 'DKK' in pattern or 'Samlet' in pattern:
                # DKK format - handle dot as thousands separator and comma as decimal (1.201,76 DKK)
                try:
                    # Remove thousands separator (dot), replace comma with dot for conversion
                    dkk_value = float(value.replace('.', '').replace(',', '.'))
                    # Convert DKK to EUR
                    dkk_to_eur = get_dkk_to_eur_rate()
                    eur_value = dkk_value * dkk_to_eur
                    order_data['total_eur'] = f"{eur_value:.2f}".replace('.', ',')
                    # Store DKK value with comma as decimal separator
                    order_data['total_dkk'] = value.replace('.', '')
                except:
                    order_data['total_dkk'] = value.replace('.', '')
            elif '€' in pattern or 'Totaal' in pattern or 'Gesamtpreis' in pattern or 'EUR' in pattern or 'Order Total' in pattern:
                # EUR format - handle comma as decimal separator (German/Belgian: €271,98)
                try:
                    # Replace comma with dot for conversion, then format back with comma
                    eur_value = float(value.replace(',', '.'))
                    order_data['total_eur'] = f"{eur_value:.2f}".replace('.', ',')
                except:
                    order_data['total_eur'] = value.replace('.', ',')
            else:
                # GBP format
                order_data['total_gbp'] = value
            break
    
    # USD Price patterns (for US Ticketmaster)
    usd_price_patterns = [
        r'\$(\d+\.?\d*)\s*x\s*(\d+)',  # $61.25 x4
        r'(\d+)\s*x\s*Full\s+Price\s+Ticket\s*\$(\d+\.?\d*)',
        r'(\d+)\s*x\s*[^\$]*\$(\d+\.?\d*)',
        r'\$(\d+\.?\d*)\s*per\s*ticket',
        r'\$(\d+\.?\d*)\s*each',
        r'\$(\d+\.?\d*)\s*per\s*item',
    ]
    
    for pattern in usd_price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) == 2:
                qty, total_price = match.groups()
                if not order_data['quantity']:
                    order_data['quantity'] = qty.strip()
                try:
                    qty_num = float(qty.strip())
                    total_num = float(total_price.strip())
                    if qty_num > 0 and total_num > 0:
                        price_per_ticket = total_num / qty_num
                        if 10 <= price_per_ticket <= 1000:
                            order_data['price_usd'] = f"{price_per_ticket:.2f}"
                            break
                except:
                    pass
            elif len(match.groups()) == 1:
                price = match.group(1)
                try:
                    price_num = float(price.strip())
                    if 10 <= price_num <= 1000:
                        order_data['price_usd'] = price.strip()
                        break
                except:
                    pass
    
    # USD Total price patterns
    usd_total_patterns = [
        r'Total\s*\(incl\.\s*fee\)\s*\$(\d+\.?\d*)',
        r'Total[:\s]*\$(\d+\.?\d*)',
        r'Grand\s+Total[:\s]*\$(\d+\.?\d*)',
    ]
    
    for pattern in usd_total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['total_usd'] = match.group(1).strip()
            break
    
    # Order ID patterns
    order_id_patterns = [
        r'ORDER\s*#\s*([A-Z0-9\-/]+)',  # UK: "ORDER # 14-50156/UK7" - prioritize this format
        r'Ordrenummer[:\s]+([A-Z0-9\-]+)',  # Danish: "Ordrenummer: RE18925289" (in subject or body)
        r'Ordrenummer\s*/\s*Order\s+number[:\s]*([A-Z0-9\-]+)',  # Danish: "Ordrenummer/Order number: RE18925289"
        r'Auftragsnummer\s*/\s*Order[:\s]*([A-Z0-9\-]+)',  # German: "Auftragsnummer/Order: RE18790116"
        r'\bRE(\d+)\b',  # German/Danish order format: RE18790116 (standalone, word boundary)
        r'ORDER\s*NUMBER[:\s]*([A-Z0-9\-/]+)',  # "ORDER NUMBER: 31881862"
        r'Order\s*Number[:\s]*([A-Z0-9\-/]+)',
        r'Order\s*ID[:\s]*([A-Z0-9\-/]+)',
        r'Reference[:\s]*([A-Z0-9\-/]+)',
    ]
    
    for pattern in order_id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_id = match.group(1).strip()
            # If pattern matched just the number (RE\d+), add RE prefix back
            if pattern == r'\bRE(\d+)\b':
                order_data['order_id'] = f'RE{order_id}'
            else:
                order_data['order_id'] = order_id
            break
    
    # Convert prices to EUR using current exchange rates
    # Convert DKK to EUR using current exchange rate
    dkk_to_eur = get_dkk_to_eur_rate()
    if order_data.get('total_dkk') and not order_data.get('total_eur'):
        try:
            # DKK format: dot is thousands separator, comma is decimal (1.201,76)
            dkk_value = float(order_data['total_dkk'].replace(',', '.'))
            total_eur = round(dkk_value * dkk_to_eur, 2)
            order_data['total_eur'] = str(total_eur).replace('.', ',')
        except:
            pass
    
    # Convert GBP to EUR using current exchange rate
    gbp_to_eur = get_gbp_to_eur_rate()
    if order_data['price_gbp'] and not order_data.get('price_eur'):
        try:
            price_eur = round(float(order_data['price_gbp'].replace(',', '')) * gbp_to_eur, 2)
            order_data['price_eur'] = str(price_eur).replace('.', ',')
        except:
            pass
    
    if order_data['total_gbp'] and not order_data.get('total_eur'):
        try:
            total_eur = round(float(order_data['total_gbp'].replace(',', '')) * gbp_to_eur, 2)
            order_data['total_eur'] = str(total_eur).replace('.', ',')
        except:
            pass
    
    # Convert USD to EUR using current exchange rate
    usd_to_eur = get_usd_to_eur_rate()
    if order_data['price_usd'] and not order_data.get('price_eur'):
        try:
            price_eur = round(float(order_data['price_usd'].replace(',', '')) * usd_to_eur, 2)
            order_data['price_eur'] = str(price_eur).replace('.', ',')
        except:
            pass
    
    if order_data['total_usd']:
        try:
            total_eur = round(float(order_data['total_usd'].replace(',', '')) * usd_to_eur, 2)
            order_data['total_eur'] = str(total_eur).replace('.', ',')
        except:
            pass
    
    # Format GBP prices with comma
    if order_data['price_gbp']:
        order_data['price_gbp'] = order_data['price_gbp'].replace('.', ',')
    if order_data['total_gbp']:
        order_data['total_gbp'] = order_data['total_gbp'].replace('.', ',')
    
    # Format USD prices with comma
    if order_data['price_usd']:
        order_data['price_usd'] = order_data['price_usd'].replace('.', ',')
    if order_data['total_usd']:
        order_data['total_usd'] = order_data['total_usd'].replace('.', ',')
    
    return order_data

def fetch_ticketmaster_emails():
    """Fetch Ticketmaster emails from IMAP"""
    log_message(f"\nConnecting to {len(IMAP_ACCOUNTS)} IMAP account(s)...")
    all_orders = []
    
    for idx, account in enumerate(IMAP_ACCOUNTS, 1):
        log_message(f"\n[{idx}/{len(IMAP_ACCOUNTS)}] Connecting to {account['email']}...")
        
        try:
            with imaplib.IMAP4_SSL(account['server'], account['port']) as M:
                M.login(account['email'], account['password'])
                M.select('INBOX')
                
                # Search for emails from last 7 days containing 'ticketmaster' (including .be, .com, .co.uk, .no, .de)
                since_date = (datetime.now() - timedelta(days=SEARCH_DAYS)).strftime('%d-%b-%Y')
                # List of Ticketmaster senders to search for
                target_senders = [
                    'no-reply@ticketmaster.de',
                    'no-reply@ticketmaster.no',
                    'no-reply@ticketmaster.be',
                    'no-reply@ticketmaster.dk',
                    'noreply@ticketmaster.com',
                    'noreply@ticketmaster.co.uk',
                    'customer_support@email.ticketmaster.com',
                ]
                
                log_message(f"Searching for emails from ticketmaster (BE/COM/CO.UK/NO/DE/DK) since {since_date}...")
                
                # Search for each sender separately and combine results (more reliable than OR query)
                all_ids = set()
                for sender in target_senders:
                    search_criteria = f'FROM "{sender}" SINCE "{since_date}"'
                    status, messages = M.search(None, search_criteria)
                    if status == 'OK' and messages[0]:
                        sender_ids = messages[0].split()
                        all_ids.update(sender_ids)
                        if sender_ids:
                            log_message(f"  Found {len(sender_ids)} emails from {sender}")
                
                # Also search for emails with ticketmaster keywords in subject (catches forwarded emails, iCloud sends, etc.)
                # This helps catch UK Ticketmaster emails that might come from different senders
                # Also search for US "You Got Tickets To" emails regardless of sender
                # IMAP search: search for each keyword separately and combine (more reliable than complex OR queries)
                subject_before_count = len(all_ids)
                subject_keywords = ['ticketmaster', 'ticket confirmation', 'order confirmation', 'confirmation', 'you got tickets to']
                for keyword in subject_keywords:
                    try:
                        subject_search = f'SUBJECT "{keyword}" SINCE "{since_date}"'
                        status, messages = M.search(None, subject_search)
                        if status == 'OK' and messages[0]:
                            keyword_ids = messages[0].split()
                            all_ids.update(keyword_ids)
                    except Exception as e:
                        # Skip if search fails (e.g., special characters)
                        pass
                
                subject_after_count = len(all_ids)
                additional_found = subject_after_count - subject_before_count
                if additional_found > 0:
                    log_message(f"  Found {additional_found} additional emails via subject keyword search")
                
                email_ids = list(all_ids)
                log_message(f"Found {len(email_ids)} total emails matching ticketmaster criteria")
                
                if not email_ids:
                    log_message(f"No new emails found for {account['email']}")
                    continue
                
                # Process emails (newest first)
                email_ids = email_ids[::-1]
                processed = 0
                
                for email_id in email_ids:
                    try:
                        # Fetch email headers first
                        status, msg_data = M.fetch(email_id, '(RFC822.HEADER)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_str(msg.get('Subject', ''))
                        
                        # Only process ticket confirmation emails (UK, US, and international)
                        confirmation_phrases = [
                            # English
                            'ticket confirmation',
                            'you\'re in!',
                            'you got tickets',  # US Ticketmaster
                            'you got the tickets',  # US Ticketmaster variant
                            'your order',
                            'order confirmation',
                            'confirmation',
                            # Dutch/Belgian
                            'jouw bestelling',  # BE/NL
                            'bestelbevestiging',  # NL
                            # French/Belgian
                            'votre commande',
                            'confirmation de commande',
                            # German
                            'deine bestellbestätigung',  # DE
                            'bestellbestätigung',
                            # Spanish
                            'confirmación de pedido',  # ES
                            # Italian
                            'conferma dell\'ordine',
                            # Polish
                            'potwierdzenie zamówienia',  # PL
                            # Danish
                            'ordrebekræftelse',  # DK
                            'ordrenummer',  # DK - order number in subject
                            # Norwegian
                            'bekreftelse'  # NO
                        ]
                        
                        # Check both subject and body for confirmation phrases
                        # First, get a preview of the body to check
                        status, msg_preview = M.fetch(email_id, '(BODY.PEEK[TEXT])')
                        body_preview = ""
                        if status == 'OK' and msg_preview[0]:
                            try:
                                preview_msg = email.message_from_bytes(msg_preview[0][1])
                                body_preview = get_body_text(preview_msg).lower()
                            except:
                                pass
                        
                        # Debug: print subject for inspection when it contains order confirmation phrases
                        subject_lower = subject.lower()
                        contains_confirmation = any(phrase in subject_lower for phrase in confirmation_phrases)
                        
                        # Also check body for "YOU GOT THE TICKETS!" which might not be in subject
                        if not contains_confirmation and body_preview:
                            contains_confirmation = any(phrase in body_preview for phrase in confirmation_phrases)
                        
                        if not contains_confirmation:
                            print(f"    Skipped (not ticket confirmation): {subject}")
                            continue
                        
                        # If it contains confirmation phrases but wasn't caught before, log for debugging
                        if contains_confirmation:
                            print(f"    Processing: {subject}")
                        
                        # Skip unwanted emails
                        skip_phrases = [
                            'successfully listed for sale',
                            'listed for sale',
                            'tickets listed',
                            'no longer for sale',
                            'ticket(s) have been successfully listed',
                            'tickets are no longer',
                            'your tickets are here',
                            'tickets are here',
                            'notification-ticket transfer complete',
                            'ticket transfer complete',
                            'refund',
                            'cancelled',
                            'postponed',
                            'password reset',
                            'password has been updated',
                            'check out our upcoming events',
                            'get info about your mobile tickets',
                            'important ticket instructions'
                        ]
                        
                        if any(skip_phrase in subject.lower() for skip_phrase in skip_phrases):
                            print(f"    Skipped: {subject}")
                            continue
                        
                        # Fetch full email
                        status, msg_data = M.fetch(email_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        # Check if this is a US "You Got Tickets To" email
                        subject_lower = subject.lower()
                        is_us_email = subject_lower.startswith('you got tickets to')
                        
                        # Extract order data
                        if is_us_email:
                            order_data = extract_us_order_data(msg, subject)
                            if not order_data:
                                # Fallback to regular extraction if US extraction fails
                                order_data = extract_event_data(msg, account['email'])
                        else:
                            order_data = extract_event_data(msg, account['email'])
                        
                        # Set imap_account if not set
                        if not order_data.get('imap_account'):
                            order_data['imap_account'] = account['email']
                        
                        # Only add if we have essential data
                        if order_data['event_name'] and order_data['order_id']:
                            all_orders.append(order_data)
                            log_message(f"FOUND: {order_data['event_name']} - {order_data['order_id']}")
                        else:
                            log_message(f"Skipped (incomplete data): {subject}")
                        
                        processed += 1
                        
                    except Exception as e:
                        print(f"Error processing email {email_id}: {e}")
                        continue
                
                log_message(f"Processed {processed} emails from {account['email']}")
                
        except Exception as e:
            log_message(f"ERROR connecting to {account['email']}: {e}")
            continue
    
    return all_orders

def save_to_csv(orders):
    """Save orders to CSV file"""
    print(f"\n[3/3] Saving results...")
    print(f"      Writing {len(orders)} orders to CSV...")
    
    # Ensure directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not orders:
        print("      Creating empty CSV with headers")
        # Create empty CSV with headers
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'Event Date', 'Day Name', 'Event Name', 'Price GBP', 'Total GBP',
                'Price USD', 'Total USD', 'Price EUR', 'Total EUR', 'Quantity', 
                'Section', 'Row', 'Seat', 'Venue', 'Order ID', 'Recipient Email', 
                'Email Date', 'IMAP Account'
            ])
        return
    
    # Create CSV with specified column order
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow([
            'Event Date', 'Day Name', 'Event Name', 'Price GBP', 'Total GBP',
            'Price USD', 'Total USD', 'Price EUR', 'Total EUR', 'Quantity', 
            'Section', 'Row', 'Seat', 'Venue', 'Order ID', 'Recipient Email', 
            'Email Date', 'IMAP Account'
        ])
        
        # Write data
        for order in orders:
            writer.writerow([
                order['event_date'], order['day_name'], order['event_name'],
                order['price_gbp'], order['total_gbp'], order['price_usd'],
                order['total_usd'], order['price_eur'], order['total_eur'], 
                order['quantity'], order['section'], order['row'], order['seat'], 
                order['venue'], order['order_id'], order['recipient_email'],
                order['email_date'], order['imap_account']
            ])
    
    print(f"      Saved to: {OUTPUT_FILE}")

def log_message(msg):
    """Log a message both to console and file"""
    print(msg)
    sys.stdout.flush()
    
    # Also write to log file
    try:
        log_file = Path(__file__).parent.parent / "tm_scraper.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {msg}\n")
    except:
        pass

def main():
    """Main function"""
    log_message("\n" + "=" * 70)
    log_message("TICKETMASTER EMAIL SCRAPER")
    log_message("=" * 70)
    log_message("\nStarting scraper...")
    log_message("Loading config...")
    
    if not IMAP_ACCOUNTS:
        log_message("\nERROR: No IMAP accounts configured!")
        log_message(f"Add accounts to: {CONFIG_FILE}")
        input("\nPress ENTER to exit...")
        return
    
    log_message(f"\nConfigured with {len(IMAP_ACCOUNTS)} IMAP accounts")
    
    # Fetch emails
    orders = fetch_ticketmaster_emails()
    
    if not orders:
        log_message("\nNo orders found in emails.")
        input("\nPress ENTER to exit...")
        return
    
    # Save to CSV
    save_to_csv(orders)
    
    # Summary
    log_message("\n" + "=" * 70)
    log_message(f"SUCCESS: Found and saved {len(orders)} orders")
    log_message(f"Output: {OUTPUT_FILE}")
    log_message("=" * 70)
    # Only wait for input if run directly (not when imported)
    if __name__ == "__main__":
        input("\nPress ENTER to exit...")

if __name__ == "__main__":
    main()
