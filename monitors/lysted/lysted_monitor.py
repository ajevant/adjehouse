#!/usr/bin/env python3
"""
Lysted Sales Monitor
===================
Monitors IMAP for Lysted sales notifications and sends Discord webhook alerts
"""

import os
import sys
import imaplib
import email
import email.utils
import json
import re
import time
import threading
import requests
from datetime import datetime
from pathlib import Path
from email.header import decode_header
from lxml import html, etree

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent.parent

# Config paths
CONFIG_FILE = BASE_DIR / 'monitors' / 'lysted' / 'lysted_config.json'

# Global monitoring state
monitoring_active = False
monitor_thread = None
last_check_time = None
found_sales = []

def load_config():
    """Load configuration from JSON file"""
    if not CONFIG_FILE.exists():
        log_message(f"[ERROR] Config file not found: {CONFIG_FILE}")
        return None
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except json.JSONDecodeError as e:
        log_message(f"[ERROR] Invalid JSON in config file: {e}")
        return None
    except Exception as e:
        log_message(f"[ERROR] Failed to load config: {e}")
        return None

def log_message(msg):
    """Log message to console only (no file logging)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    sys.stdout.flush()

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

def get_body_html(msg):
    """Extract HTML from email body"""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode('utf-8', errors='ignore')
                        if html_body:
                            break
                except:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                html_body = payload.decode('utf-8', errors='ignore')
        except:
            pass
    return html_body

def extract_sale_data(msg, account_email):
    """Extract sale information from Lysted email using XPath"""
    subject = decode_str(msg.get('Subject', ''))
    html_body = get_body_html(msg)
    
    sale_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'email_date': decode_str(msg.get('Date', '')),
        'subject': subject,
        'sender': decode_str(msg.get('From', '')),
        'recipient': account_email,
        'event_name': '',
        'event_date': '',
        'section': '',
        'row': '',
        'seats': '',
        'profit': '',
        'roi': '',
        'order_id': '',
        'order_platform': '',
        'invoice_id': '',
        'quantity': '',
        'price_per_ticket': ''
    }
    
    if not html_body:
        # Fallback: try to extract from subject if HTML not available
        invoice_match = re.search(r'Invoice\s*#\s*(\d+)', subject, re.IGNORECASE)
        if invoice_match:
            sale_data['invoice_id'] = invoice_match.group(1).strip()
        
        event_match = re.search(r'\[lysted\]\s+TICKETS\s+SOLD:\s+([^(]+?)\s*\(', subject, re.IGNORECASE)
        if event_match:
            sale_data['event_name'] = event_match.group(1).strip()
        
        return sale_data
    
    try:
        tree = html.fromstring(html_body)
        
        # Extract Invoice ID
        invoice_elements = tree.xpath('//table[1]//span[contains(text(), "#") or contains(., "#")]')
        if not invoice_elements:
            invoice_elements = tree.xpath('//span[contains(text(), "#")]')
        if invoice_elements:
            invoice_text = etree.tostring(invoice_elements[0], method='text', encoding='unicode').strip()
            invoice_match = re.search(r'#\s*(\d+)', invoice_text)
            if invoice_match:
                sale_data['invoice_id'] = invoice_match.group(1).strip()
        
        # Extract Event Name
        event_elements = tree.xpath('//table[2]//h5')
        if event_elements:
            sale_data['event_name'] = etree.tostring(event_elements[0], method='text', encoding='unicode').strip()
        
        # Extract Event Date
        date_elements = tree.xpath('//table[2]//small')
        if date_elements:
            date_text = etree.tostring(date_elements[0], method='text', encoding='unicode').strip()
            if ',' in date_text:
                date_text = date_text.split(',')[0].strip()
            sale_data['event_date'] = date_text
        
        # Extract Section, Row, and Seats from table[2] -> div/div[2]/table/tbody/tr/td/p
        location_elements = tree.xpath('//table[2]//div[2]//p')
        if location_elements:
            location_text = etree.tostring(location_elements[0], method='text', encoding='unicode').strip()
            # Parse "Section 208\nRow 11\nSeats 15-17" or similar format
            lines = [line.strip() for line in location_text.split('\n') if line.strip()]
            for line in lines:
                if re.match(r'^Section\s+', line, re.IGNORECASE):
                    sale_data['section'] = re.sub(r'^Section\s+', '', line, flags=re.IGNORECASE).strip()
                elif re.match(r'^Row\s+', line, re.IGNORECASE):
                    sale_data['row'] = re.sub(r'^Row\s+', '', line, flags=re.IGNORECASE).strip()
                elif re.match(r'^Seats?\s+', line, re.IGNORECASE):
                    sale_data['seats'] = re.sub(r'^Seats?\s+', '', line, flags=re.IGNORECASE).strip()
        
        # Extract Quantity and Price per Ticket
        ticket_elements = tree.xpath('//table[3]//div[2]//p')
        if ticket_elements:
            ticket_text = etree.tostring(ticket_elements[0], method='text', encoding='unicode').strip()
            ticket_match = re.search(r'(\d+)\s*×\s*\$?\s*([\d,]+\.?\d*)', ticket_text)
            if ticket_match:
                sale_data['quantity'] = ticket_match.group(1).strip()
                sale_data['price_per_ticket'] = f"${ticket_match.group(2).strip()}"
        
        # Extract Profit
        profit_elements = tree.xpath('//table[7]//div[2]//p/strong')
        if profit_elements:
            profit_text = etree.tostring(profit_elements[0], method='text', encoding='unicode').strip()
            profit_text = profit_text.replace('$', '').replace(',', '').strip()
            sale_data['profit'] = profit_text
        
        # Extract ROI
        roi_elements = tree.xpath('//strong[contains(text(), "%")]')
        for roi_elem in roi_elements:
            roi_text = etree.tostring(roi_elem, method='text', encoding='unicode').strip()
            if '%' in roi_text:
                roi_match = re.search(r'([\d,]+\.?\d*)%', roi_text)
                if roi_match:
                    sale_data['roi'] = roi_match.group(1).strip()
                    break
        
        # Extract Order ID and Platform from table[9] -> div/div[1]/table/tbody/tr/td/p
        # This contains the platform name and order ID
        order_elements = tree.xpath('//table[9]//div[1]//p')
        if order_elements:
            order_text = etree.tostring(order_elements[0], method='text', encoding='unicode').strip()
            
            # Parse the text to extract platform and order ID
            # Format can be: "StubHub\nOrder 123456" or "SeatGeek\nOrder 18ws0emv85" or "AXS\nOrder 123456"
            lines = [line.strip() for line in order_text.split('\n') if line.strip()]
            
            # Find the order ID (line containing "Order" followed by alphanumeric)
            order_id = None
            platform = None
            
            for i, line in enumerate(lines):
                order_match = re.search(r'Order\s+([A-Z0-9]{6,})', line, re.IGNORECASE)
                if order_match:
                    order_id = order_match.group(1).strip()
                    # Platform is the line before "Order" or the previous line
                    if i > 0:
                        platform = lines[i-1].strip()
                    elif 'Order' in line:
                        # Platform might be on the same line before "Order"
                        platform = line.split('Order')[0].strip()
                    break
            
            if order_id:
                sale_data['order_id'] = order_id
                if platform:
                    sale_data['order_platform'] = platform
        
    except Exception as e:
        log_message(f"[ERROR] Failed to parse HTML: {e}")
        # Fallback to subject parsing
        invoice_match = re.search(r'Invoice\s*#\s*(\d+)', subject, re.IGNORECASE)
        if invoice_match:
            sale_data['invoice_id'] = invoice_match.group(1).strip()
        
        event_match = re.search(r'\[lysted\]\s+TICKETS\s+SOLD:\s+([^(]+?)\s*\(', subject, re.IGNORECASE)
        if event_match:
            sale_data['event_name'] = event_match.group(1).strip()
    
    return sale_data

def send_discord_webhook(webhook_url, sale_data):
    """Send Discord webhook notification with color based on profit/ROI"""
    try:
        # Parse profit and ROI
        profit_value = 0.0
        roi_value = 0.0
        
        try:
            profit_str = sale_data.get('profit', '').replace(',', '').replace('$', '').strip()
            if profit_str:
                profit_value = float(profit_str)
        except:
            pass
        
        try:
            roi_str = sale_data.get('roi', '').replace('%', '').replace(',', '').strip()
            if roi_str:
                roi_value = float(roi_str)
        except:
            pass
        
        # Determine color based on profit/ROI
        if profit_value < 0:
            color = 15158332  # Red
        elif roi_value < 20:
            color = 16776960  # Orange/Yellow
        else:
            color = 3066993  # Green
        
        # Build embed
        embed = {
            "title": f"Lysted Sale: {sale_data.get('event_name', 'Unknown Event')}",
            "color": color,
            "description": "",
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": f"Invoice #{sale_data.get('invoice_id', 'N/A')}"
            }
        }
        
        # Build description
        description_parts = []
        
        if sale_data.get('event_date'):
            event_date = sale_data['event_date']
            if ',' in event_date:
                event_date = event_date.split(',')[0].strip()
            description_parts.append(f"**Event Date:** {event_date}")
        
        location_parts = []
        if sale_data.get('section'):
            location_parts.append(f"Section {sale_data['section']}")
        if sale_data.get('row'):
            location_parts.append(f"Row {sale_data['row']}")
        if sale_data.get('seats'):
            location_parts.append(f"Seats {sale_data['seats']}")
        
        if location_parts:
            description_parts.append(f"**Location:** {' | '.join(location_parts)}")
        
        if sale_data.get('quantity'):
            ticket_info = sale_data['quantity']
            if sale_data.get('price_per_ticket'):
                ticket_info += f" × {sale_data['price_per_ticket']}"
            description_parts.append(f"**Tickets:** {ticket_info}")
        
        if sale_data.get('profit'):
            description_parts.append(f"**Profit:** ${sale_data['profit']}")
        
        if sale_data.get('roi'):
            description_parts.append(f"**ROI:** {sale_data['roi']}%")
        
        if sale_data.get('order_id'):
            platform = sale_data.get('order_platform', 'Order')
            description_parts.append(f"**{platform}**\nOrder: {sale_data['order_id']}")
        
        if description_parts:
            embed["description"] = "\n\n".join(description_parts)
        
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
        
    except Exception as e:
        log_message(f"[ERROR] Failed to send Discord webhook: {e}")
        return False

def check_for_sales(config):
    """Check IMAP for new Lysted sales emails"""
    global last_check_time, found_sales
    
    imap_accounts = config.get('imap_accounts', [])
    webhook_url = config.get('discord', {}).get('webhook_url', '')
    
    if not imap_accounts:
        log_message("[WARNING] No IMAP accounts configured")
        return
    
    for account in imap_accounts:
        try:
            with imaplib.IMAP4_SSL(account['server'], account['port']) as M:
                M.login(account['email'], account['password'])
                M.select('INBOX')
                
                # If first run (last_check_time is None), set it to now and skip old emails
                if last_check_time is None:
                    last_check_time = datetime.now()
                    log_message(f"[{account['email']}] Monitor started - will check for new sales from now onwards (skipping old emails)")
                    continue
                
                # Search for emails since last check
                since_date = last_check_time.strftime('%d-%b-%Y')
                search_criteria = f'SINCE "{since_date}" FROM "noreply@lysted.com" SUBJECT "[lysted] TICKETS SOLD"'
                
                log_message(f"[{account['email']}] Searching for Lysted sales since {since_date}...")
                status, messages = M.search(None, search_criteria)
                
                if status != 'OK':
                    log_message(f"[ERROR] Search failed for {account['email']}")
                    continue
                
                email_ids = messages[0].split()
                
                if not email_ids:
                    log_message(f"[{account['email']}] No new sales found")
                    last_check_time = datetime.now()
                    continue
                
                log_message(f"[{account['email']}] Found {len(email_ids)} potential sale(s), filtering by date...")
                
                processed_count = 0
                # Store original last_check_time to compare against
                check_start_time = last_check_time
                
                for email_id in email_ids:
                    try:
                        email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                        
                        status, msg_data = M.fetch(email_id_str, '(RFC822)')
                        if status != 'OK':
                            log_message(f"[ERROR] Failed to fetch email {email_id_str}")
                            continue
                        
                        if not msg_data or not msg_data[0] or len(msg_data[0]) < 2:
                            log_message(f"[ERROR] Invalid email data for {email_id_str}")
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_str(msg.get('Subject', ''))
                        
                        # Check email date - only process emails received AFTER monitor start time
                        email_date_str = decode_str(msg.get('Date', ''))
                        if email_date_str:
                            try:
                                email_date = email.utils.parsedate_to_datetime(email_date_str)
                                # Only process emails received after the check start time
                                if email_date < check_start_time:
                                    continue  # Skip old emails
                            except Exception:
                                # If date parsing fails, continue anyway (better safe than sorry)
                                pass
                        
                        # Check subject contains "[lysted] TICKETS SOLD"
                        subject_upper = subject.upper().strip()
                        if '[LYSTED] TICKETS SOLD' not in subject_upper:
                            if '[LYSTED]TICKETS SOLD' not in subject_upper.replace(' ', ''):
                                continue
                        
                        sale_data = extract_sale_data(msg, account['email'])
                        
                        # Check for duplicates
                        is_duplicate = False
                        for existing in found_sales:
                            if (sale_data.get('invoice_id') and 
                                existing.get('invoice_id') == sale_data.get('invoice_id')):
                                is_duplicate = True
                                break
                            if (sale_data.get('order_id') and 
                                len(sale_data.get('order_id', '')) >= 6 and
                                existing.get('order_id') == sale_data.get('order_id')):
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            continue
                        
                        sale_data['email_id'] = email_id_str
                        found_sales.append(sale_data)
                        log_message(f"[SALE FOUND] {sale_data.get('event_name', 'Unknown')} - Invoice #{sale_data.get('invoice_id', 'N/A')}")
                        
                        # Send Discord webhook
                        if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                            if send_discord_webhook(webhook_url, sale_data):
                                log_message(f"[DISCORD] Webhook sent successfully!")
                            else:
                                log_message(f"[DISCORD] Failed to send webhook")
                        elif not webhook_url:
                            log_message(f"[WARNING] Webhook URL not configured")
                        else:
                            log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                        
                        processed_count += 1
                        
                    except Exception as e:
                        email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                        log_message(f"[ERROR] Failed to process email {email_id_str}: {e}")
                
                log_message(f"[{account['email']}] Processed {processed_count} sale(s) from {len(email_ids)} email(s)")
                last_check_time = datetime.now()
                
        except Exception as e:
            log_message(f"[ERROR] Failed to connect to {account['email']}: {e}")

def monitoring_loop(config):
    """Main monitoring loop that runs in background thread"""
    global monitoring_active
    
    log_message("=== Lysted Monitor Started ===")
    monitoring_active = True
    
    while monitoring_active:
        try:
            check_for_sales(config)
        except Exception as e:
            log_message(f"[ERROR] Monitoring error: {e}")
        
        check_interval = config.get('monitoring', {}).get('check_interval_seconds', 120)
        for _ in range(check_interval):
            if not monitoring_active:
                break
            time.sleep(1)
    
    log_message("=== Lysted Monitor Stopped ===")

def start_monitoring():
    """Start the monitoring in background thread"""
    global monitor_thread, monitoring_active, last_check_time, found_sales
    
    if monitoring_active:
        return True
    
    # Reset last_check_time to None so only new emails from now onwards are checked
    last_check_time = None
    # Optionally reset found_sales list (to avoid duplicate detection across restarts)
    found_sales = []
    
    config = load_config()
    if not config:
        return False
    
    monitor_thread = threading.Thread(target=monitoring_loop, args=(config,), daemon=True)
    monitor_thread.start()
    time.sleep(1)
    
    return monitoring_active

def stop_monitoring():
    """Stop the monitoring"""
    global monitoring_active
    monitoring_active = False
    if monitor_thread:
        monitor_thread.join(timeout=5)

def is_monitoring():
    """Check if monitoring is active"""
    global monitoring_active, monitor_thread
    if monitor_thread and monitor_thread.is_alive():
        return monitoring_active
    return False

if __name__ == "__main__":
    config = load_config()
    if config:
        print("Starting Lysted monitor...")
        start_monitoring()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            stop_monitoring()
