#!/usr/bin/env python3
"""
SeatGeek Email Scraper
Fetches emails from SeatGeek using central config
"""

import imaplib
import email
import re
import csv
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from email.header import decode_header
try:
    import urllib.request
    import urllib.parse
except ImportError:
    urllib = None
import html

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
    IMAP_ACCOUNTS = config['imap_accounts'].get('seatgeek', [])
    SEARCH_DAYS = config['search_settings'].get('default_search_days', 2)
else:
    IMAP_ACCOUNTS = []
    SEARCH_DAYS = 2

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

# Output file - in ADJEHOUSE success directory (next to EXE)
OUTPUT_DIR = BASE_DIR / "success"
OUTPUT_FILE = OUTPUT_DIR / "seatgeek_success.csv"

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

def extract_event_data(msg, imap_account):
    """Extract event data from SeatGeek email"""
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
    
    # Extract order number (e.g., "N4Q-9LZY3QE")
    order_patterns = [
        r'Order\s*number\s*\n?\s*([A-Z0-9\-]+)',
        r'Order\s*#\s*([A-Z0-9\-]+)',
        r'Order\s*ID[:\s]*([A-Z0-9\-]+)',
    ]
    
    for pattern in order_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['order_id'] = match.group(1).strip()
            break
    
    # Extract event name (between "Event" and venue/date)
    event_patterns = [
        r'Event\s*\n\s*([^\n]+?)(?:\s*\n\s*[A-Z][a-z]+\s+Stadium|Arena|Theatre|Theater|Hall|Center|Centre)',
        r'Event\s*\n\s*([^\n]+)',
    ]
    
    for pattern in event_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['event_name'] = match.group(1).strip()
            break
    
    # Extract venue (e.g., "Nissan Stadium, Nashville, TN")
    venue_patterns = [
        r'([A-Z][a-z]+\s+(?:Stadium|Arena|Theatre|Theater|Hall|Center|Centre)[^,]*(?:,\s*[A-Za-z\s]+,\s*[A-Z]{2})?)',
        r'([A-Z][A-Za-z\s]+(?:Stadium|Arena|Theatre|Theater|Hall|Center|Centre))',
    ]
    
    for pattern in venue_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['venue'] = match.group(1).strip()
            break
    
    # Extract event date (e.g., "Sat, Jun 27 at 5:30pm")
    date_patterns = [
        r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+)\s+at\s+(\d+:\d+\s*[ap]m)',
        r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+\s*[ap]m)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Parse and convert to DD-MM-YYYY
            try:
                # Map month abbreviations
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }
                
                # Handle different date formats
                if ',' in date_str and len(date_str.split(',')) > 1:
                    # "Saturday, June 27, 2026" format
                    parts = date_str.replace(',', '').split()
                    day_name = parts[0]
                    month = parts[1]
                    day = parts[2]
                    year = parts[3] if len(parts) > 3 else str(datetime.now().year)
                else:
                    # "Sat, Jun 27" format
                    parts = date_str.replace(',', '').split()
                    day_name = parts[0]
                    month = parts[1]
                    day = parts[2]
                    year = str(datetime.now().year)
                
                month_num = month_map.get(month.lower()[:3], '01')
                order_data['event_date'] = f"{day.zfill(2)}-{month_num}-{year}"
                
                # Set day name
                day_mapping = {
                    'Mon': 'Monday', 'Tue': 'Tuesday', 'Wed': 'Wednesday',
                    'Thu': 'Thursday', 'Fri': 'Friday', 'Sat': 'Saturday', 'Sun': 'Sunday'
                }
                if day_name[:3] in day_mapping:
                    order_data['day_name'] = day_mapping[day_name[:3]]
                else:
                    order_data['day_name'] = day_name
            except:
                pass
            break
    
    # Extract quantity (e.g., "6 tickets")
    quantity_patterns = [
        r'Quantity\s*\n?\s*(\d+)\s*tickets?',
        r'(\d+)\s*tickets?',
        r'Qty[:\s]*(\d+)',
    ]
    
    for pattern in quantity_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['quantity'] = match.group(1).strip()
            break
    
    # Extract section (e.g., "331")
    section_patterns = [
        r'Section\s*\n?\s*([A-Z0-9]+)',
        r'Section[:\s]+([A-Z0-9]+)',
    ]
    
    for pattern in section_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['section'] = match.group(1).strip()
            break
    
    # Extract row (e.g., "M")
    row_patterns = [
        r'Row\s*\n?\s*([A-Z0-9]+)',
        r'Row[:\s]+([A-Z0-9]+)',
    ]
    
    for pattern in row_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_data['row'] = match.group(1).strip()
            break
    
    # Extract seats (e.g., "1,2,3,4,5,6")
    seat_patterns = [
        r'Seats?\s*\n?\s*([0-9,\-\s]+)',
        r'Seats?[:\s]+([0-9,\-\s]+)',
    ]
    
    for pattern in seat_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            seats = match.group(1).strip()
            # Clean up seat formatting
            seats = re.sub(r'\s+', '', seats)  # Remove spaces
            order_data['seat'] = seats
            break
    
    # Extract prices (USD) - prioritize TOTAL over individual ticket price
    # First try to get the total (what you actually paid)
    total_patterns = [
        r'Total\s*(?:US\s*)?\$([0-9,]+\.?\d*)',
        r'Grand\s*Total[:\s]*\$([0-9,]+\.?\d*)',
        r'Total[:\s]*\$([0-9,]+\.?\d*)',
    ]
    
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            total_str = match.group(1).replace(',', '')
            order_data['total_usd'] = total_str
            break
    
    # Then try to get individual ticket price (for reference)
    price_patterns = [
        r'Tickets?\s*\$([0-9,]+\.?\d*)',
        r'\$([0-9,]+\.?\d*)\s*x\s*\d+',
        r'(?:Subtotal|Price)[:\s]*\$([0-9,]+\.?\d*)',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            order_data['price_usd'] = price_str
            break
    
    # If we have total but no individual price, calculate it
    if order_data['total_usd'] and not order_data['price_usd'] and order_data['quantity']:
        try:
            total_amount = float(order_data['total_usd'])
            quantity = int(order_data['quantity'])
            if quantity > 0:
                price_per_ticket = total_amount / quantity
                order_data['price_usd'] = f"{price_per_ticket:.2f}"
        except:
            pass
    
    # Convert USD to EUR using current exchange rate
    usd_to_eur = get_usd_to_eur_rate()
    if order_data['price_usd']:
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
    
    # Format USD prices with comma
    if order_data['price_usd']:
        order_data['price_usd'] = order_data['price_usd'].replace('.', ',')
    if order_data['total_usd']:
        order_data['total_usd'] = order_data['total_usd'].replace('.', ',')
    
    return order_data

def fetch_seatgeek_emails():
    """Fetch SeatGeek emails from IMAP"""
    print(f"\n[1/3] Connecting to {len(IMAP_ACCOUNTS)} IMAP account(s)...")
    all_orders = []
    
    for idx, account in enumerate(IMAP_ACCOUNTS, 1):
        print(f"\n[{idx}/{len(IMAP_ACCOUNTS)}] Processing: {account['email']}")
        
        try:
            with imaplib.IMAP4_SSL(account['server'], account['port']) as M:
                M.login(account['email'], account['password'])
                M.select('INBOX')
                
                # Search for emails from SeatGeek
                since_date = (datetime.now() - timedelta(days=SEARCH_DAYS)).strftime('%d-%b-%Y')
                search_criteria = f'(FROM "transactions@seatgeek.com" SINCE "{since_date}")'
                
                print(f"      Searching since {since_date}...")
                status, messages = M.search(None, search_criteria)
                
                if status != 'OK':
                    print(f"      Search failed")
                    continue
                
                email_ids = messages[0].split()
                print(f"      Found {len(email_ids)} emails")
                
                if not email_ids:
                    print(f"      No emails found, skipping...")
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
                        subject = str(decode_header(msg['Subject'])[0][0])
                        
                        # Only process order confirmation emails
                        confirmation_phrases = [
                            'order confirmation',
                            'your order',
                            'purchase confirmation',
                            'ticket confirmation',
                            'your tickets are available',
                            'tickets are available on seatgeek',
                        ]
                        if not any(phrase in subject.lower() for phrase in confirmation_phrases):
                            print(f"    Skipped (not order confirmation): {subject}")
                            continue
                        
                        # Skip unwanted emails
                        skip_phrases = [
                            'password reset',
                            'account verification',
                            'welcome to seatgeek',
                        ]
                        
                        if any(skip_phrase in subject.lower() for skip_phrase in skip_phrases):
                            print(f"    Skipped: {subject}")
                            continue
                        
                        # Fetch full email
                        status, msg_data = M.fetch(email_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        # Extract order data
                        order_data = extract_event_data(msg, account['email'])
                        
                        # Only add if we have essential data
                        if order_data['event_name'] and order_data['order_id']:
                            all_orders.append(order_data)
                            print(f"      FOUND: {order_data['event_name']} ({order_data['order_id']})")
                        else:
                            print(f"      Skipped (incomplete data)")
                        
                        processed += 1
                        
                    except Exception as e:
                        print(f"   Error processing email {email_id}: {e}")
                        continue
                
                print(f"      Processed {processed} emails")
                
        except Exception as e:
            print(f" Error connecting to {account['email']}: {e}")
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
                order['price_gbp'], order['total_gbp'], 
                order['price_usd'], order['total_usd'],
                order['price_eur'], order['total_eur'], 
                order['quantity'], order['section'],
                order['row'], order['seat'], order['venue'], order['order_id'],
                order['recipient_email'], order['email_date'], order['imap_account']
            ])
    
    print(f"      Saved to: {OUTPUT_FILE}")

def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("SEATGEEK EMAIL SCRAPER")
    print("=" * 70)
    
    if not IMAP_ACCOUNTS:
        print("\nERROR: No IMAP accounts configured!")
        print(f"Add accounts to: {CONFIG_FILE}")
        input("\nPress ENTER to exit...")
        return
    
    # Fetch emails
    orders = fetch_seatgeek_emails()
    
    if not orders:
        print("\nNo orders found in emails.")
        input("\nPress ENTER to exit...")
        return
    
    # Save to CSV
    save_to_csv(orders)
    
    # Summary
    print("\n" + "=" * 70)
    print(f"SUCCESS: Found and saved {len(orders)} orders")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 70)
    # Only wait for input if run directly (not when imported)
    if __name__ == "__main__":
        input("\nPress ENTER to exit...")

if __name__ == "__main__":
    main()

