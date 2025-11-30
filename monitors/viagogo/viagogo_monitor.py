#!/usr/bin/env python3
"""
Viagogo Sales Monitor
=====================
Monitors IMAP for Viagogo sales notifications and sends Discord webhook alerts
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
from datetime import datetime, timedelta
from pathlib import Path
from email.header import decode_header
from lxml import html, etree

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent.parent

# Config paths
CONFIG_FILE = BASE_DIR / 'monitors' / 'viagogo' / 'viagogo_config.json'

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

def get_html_body(msg):
    """Extract HTML from email body for XPath parsing"""
    html_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_content = payload.decode('utf-8', errors='ignore')
                        if html_content:
                            break
                except:
                    pass
    else:
        if msg.get_content_type() == "text/html":
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    html_content = payload.decode('utf-8', errors='ignore')
            except:
                pass
    return html_content

def extract_sale_data(msg, account_email, subject):
    """Extract sale information from Viagogo email using XPath"""
    html_content = get_html_body(msg)
    
    sale_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'email_date': decode_str(msg.get('Date', '')),
        'subject': subject,
        'sender': decode_str(msg.get('From', '')),
        'recipient': account_email,
        'email_type': '',
        'event_name': '',
        'event_date': '',
        'section': '',
        'row': '',
        'seats': '',
        'quantity': '',
        'order_id': '',
        'payment_total': '',
        'price_per_ticket': '',
        'total_proceeds': '',
        'buyer_name': '',
        'buyer_email': ''
    }
    
    # Determine email type from subject
    subject_lower = subject.lower()
    if 'please transfer the tickets for sale' in subject_lower:
        sale_data['email_type'] = 'transfer_tickets'
    elif 'please upload your e-tickets' in subject_lower:
        sale_data['email_type'] = 'upload_tickets'
    elif 'immediately' in subject_lower and 'please send your tickets' in subject_lower:
        sale_data['email_type'] = 'send_tickets_immediately'
    elif 'please send your tickets' in subject_lower:
        sale_data['email_type'] = 'send_tickets'
    elif 'you sold your ticket for' in subject_lower:
        sale_data['email_type'] = 'sold'
    else:
        sale_data['email_type'] = 'unknown'
    
    if not html_content:
        return sale_data
    
    try:
        tree = html.fromstring(html_content)
        
        # New email types: "Please transfer the tickets for sale" and "Please upload your e-tickets"
        if sale_data['email_type'] in ['transfer_tickets', 'upload_tickets']:
            # Extract Order ID from <td colspan="2"><strong>Order ID:</strong> 630242155</td>
            order_id_tds = tree.xpath('//td[contains(., "Order ID:")]')
            for td in order_id_tds:
                td_text = etree.tostring(td, method='text', encoding='unicode').strip()
                order_match = re.search(r'Order\s+ID:\s*(\d+)', td_text, re.IGNORECASE)
                if order_match:
                    sale_data['order_id'] = order_match.group(1).strip()
                    break
            
            # Extract Section and Row from <td>Section 117, Row 8, (1 Ticket(s))</td>
            # Look for td that contains "Ticket(s):" label, then get the next td with Section/Row
            ticket_label_tds = tree.xpath('//td[contains(., "Ticket(s):")]')
            for label_td in ticket_label_tds:
                # Get the next sibling td (the one with Section/Row info)
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            section_row_td = tds[i + 1]
                            text = etree.tostring(section_row_td, method='text', encoding='unicode').strip()
                            # Parse "Section 117, Row 8, (1 Ticket(s))"
                            section_match = re.search(r'Section\s+(\d+)', text, re.IGNORECASE)
                            if section_match:
                                sale_data['section'] = section_match.group(1).strip()
                            
                            row_match = re.search(r'Row\s+(\d+)', text, re.IGNORECASE)
                            if row_match:
                                sale_data['row'] = row_match.group(1).strip()
                            
                            # Extract quantity from "(1 Ticket(s))"
                            qty_match = re.search(r'\((\d+)\s+Ticket', text, re.IGNORECASE)
                            if qty_match:
                                sale_data['quantity'] = qty_match.group(1).strip()
                            break
            
            # Extract event name from <td>Radiohead</td> - look for td after "Event:" label
            event_label_tds = tree.xpath('//td[contains(., "Event:")]')
            for label_td in event_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            event_td = tds[i + 1]
                            event_text = etree.tostring(event_td, method='text', encoding='unicode').strip()
                            # Clean up event name (remove extra whitespace, newlines)
                            event_text = ' '.join(event_text.split())
                            if event_text and len(event_text) < 200:  # Reasonable event name length
                                sale_data['event_name'] = event_text
                            break
            
            # Extract date/time from <td>Thursday, December 04, 2025 | 19:00  Date & Time to be Confirmed</td>
            # Look for td after "Date:" label (not "Must Ship by Date:")
            date_label_tds = tree.xpath('//td[text()="Date:" or contains(., "Date:")]')
            for label_td in date_label_tds:
                # Skip "Must Ship by Date:"
                label_text = etree.tostring(label_td, method='text', encoding='unicode').strip()
                if 'Must Ship' in label_text:
                    continue
                
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            date_td = tds[i + 1]
                            date_text = etree.tostring(date_td, method='text', encoding='unicode').strip()
                            # Check if it looks like a date (contains day of week and month)
                            if re.search(r'\w+day,\s+\w+\s+\d{1,2},\s+\d{4}', date_text, re.IGNORECASE):
                                # Clean up: remove "Date & Time to be Confirmed" and similar
                                date_text = re.sub(r'\s*Date\s*&\s*Time\s*to\s*be\s*Confirmed.*', '', date_text, flags=re.IGNORECASE).strip()
                                # Keep full date with day of week: "Thursday, December 04, 2025 | 19:00"
                                sale_data['event_date'] = date_text
                            break
            
            # Extract email and full name from <p>Email Address: <a href="mailto:...">...</a><br>Full Name: ...</p>
            email_name_elements = tree.xpath('//p[contains(., "Email Address:") or contains(., "Full Name:")]')
            for elem in email_name_elements:
                text = etree.tostring(elem, method='text', encoding='unicode').strip()
                # Extract email from mailto link first (most reliable)
                mailto_links = elem.xpath('.//a[starts-with(@href, "mailto:")]')
                for link in mailto_links:
                    href = link.get('href', '')
                    if href.startswith('mailto:'):
                        sale_data['buyer_email'] = href.replace('mailto:', '').strip()
                        break
                
                # If no mailto link, try regex
                if not sale_data['buyer_email']:
                    email_match = re.search(r'Email\s+Address:\s*([^\s\n<]+@[^\s\n>]+)', text, re.IGNORECASE)
                    if email_match:
                        sale_data['buyer_email'] = email_match.group(1).strip()
                
                # Extract full name
                name_match = re.search(r'Full\s+Name:\s*([^\n<]+)', text, re.IGNORECASE)
                if name_match:
                    sale_data['buyer_name'] = name_match.group(1).strip()
                break
            
            # Extract quantity from "Number of Tickets:" row -> next td with width="55%"
            if not sale_data['quantity']:
                qty_label_tds = tree.xpath('//td[contains(., "Number of Tickets:")]')
                for label_td in qty_label_tds:
                    parent = label_td.getparent()
                    if parent is not None:
                        tds = parent.xpath('.//td')
                        for i, td in enumerate(tds):
                            if td == label_td and i + 1 < len(tds):
                                qty_td = tds[i + 1]
                                qty_text = etree.tostring(qty_td, method='text', encoding='unicode').strip()
                                if qty_text.isdigit():
                                    sale_data['quantity'] = qty_text
                                break
            
            # Extract price per ticket from "Price per Ticket:" row
            price_label_tds = tree.xpath('//td[contains(., "Price per Ticket:")]')
            for label_td in price_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            price_td = tds[i + 1]
                            price_text = etree.tostring(price_td, method='text', encoding='unicode').strip()
                            price_match = re.search(r'€\s*([\d,]+\.?\d*)', price_text)
                            if price_match:
                                sale_data['price_per_ticket'] = price_match.group(1).replace(',', '').strip()
                            break
            
            # Extract total proceeds from "Total Proceeds:" row
            total_label_tds = tree.xpath('//td[contains(., "Total Proceeds:")]')
            for label_td in total_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            total_td = tds[i + 1]
                            total_text = etree.tostring(total_td, method='text', encoding='unicode').strip()
                            total_match = re.search(r'€\s*([\d,]+\.?\d*)', total_text)
                            if total_match:
                                sale_data['total_proceeds'] = total_match.group(1).replace(',', '').strip()
                            break
        
        elif sale_data['email_type'] == 'send_tickets_immediately':
            # "Please send your tickets" with "immediately"
            # Extract name
            name_elements = tree.xpath('//table[2]//tbody//tr[4]//td//table//tbody//tr[6]//td[3]//strong')
            if name_elements:
                sale_data['buyer_name'] = etree.tostring(name_elements[0], method='text', encoding='unicode').strip()
            
            # Extract email
            email_elements = tree.xpath('//table[2]//tbody//tr[4]//td//table//tbody//tr[7]//td[3]//a')
            if email_elements:
                email_href = email_elements[0].get('href', '')
                if email_href.startswith('mailto:'):
                    sale_data['buyer_email'] = email_href.replace('mailto:', '').strip()
                else:
                    sale_data['buyer_email'] = etree.tostring(email_elements[0], method='text', encoding='unicode').strip()
            
            # Extract event name from span with specific style
            event_elements = tree.xpath('//span[@style="color:#2f343b;text-decoration:none"]')
            if event_elements:
                sale_data['event_name'] = etree.tostring(event_elements[0], method='text', encoding='unicode').strip()
            
            # Extract date
            date_elements = tree.xpath('//table[2]//tbody//tr[16]//td//div//table//tbody//tr//td//table//tbody//tr[3]//td//table//tbody//tr[1]//td//span')
            if date_elements:
                date_text = etree.tostring(date_elements[0], method='text', encoding='unicode').strip()
                # Remove day of week and time if present
                if ',' in date_text:
                    parts = date_text.split(',')
                    if len(parts) >= 2:
                        date_text = ','.join(parts[1:]).strip()
                if '|' in date_text:
                    date_text = date_text.split('|')[0].strip()
                sale_data['event_date'] = date_text
            
            # Extract order ID
            order_elements = tree.xpath('//table[2]//tbody//tr[16]//td//div//table//tbody//tr//td//table//tbody//tr[3]//td//table//tbody//tr[3]//td//span//a//span')
            if order_elements:
                sale_data['order_id'] = etree.tostring(order_elements[0], method='text', encoding='unicode').strip()
            
            # Extract quantity
            qty_elements = tree.xpath('//table[2]//tbody//tr[16]//td//div//table//tbody//tr//td//table//tbody//tr[4]//td//span')
            if qty_elements:
                qty_text = etree.tostring(qty_elements[0], method='text', encoding='unicode').strip()
                qty_match = re.search(r'(\d+)', qty_text)
                if qty_match:
                    sale_data['quantity'] = qty_match.group(1).strip()
            
            # Extract section
            section_elements = tree.xpath('//table[2]//tbody//tr[16]//td//div//table//tbody//tr//td//table//tbody//tr[5]//td//table//tbody//tr[1]//td//span')
            if section_elements:
                section_text = etree.tostring(section_elements[0], method='text', encoding='unicode').strip()
                section_text = re.sub(r'^Section\s*:?\s*', '', section_text, flags=re.IGNORECASE).strip()
                sale_data['section'] = section_text
            
            # Extract row and seats
            row_seat_elements = tree.xpath('//table[2]//tbody//tr[16]//td//div//table//tbody//tr//td//table//tbody//tr[5]//td//table//tbody//tr[2]//td//span')
            if row_seat_elements:
                row_seat_text = etree.tostring(row_seat_elements[0], method='text', encoding='unicode').strip()
                # Parse "Row X, Seat(s) Y" or similar
                row_match = re.search(r'Row\s*:?\s*([A-Z0-9]+)', row_seat_text, re.IGNORECASE)
                if row_match:
                    sale_data['row'] = row_match.group(1).strip()
                seats_match = re.search(r'Seats?[:\s]+([0-9\-\s,]+)', row_seat_text, re.IGNORECASE)
                if seats_match:
                    sale_data['seats'] = seats_match.group(1).strip()
            
            # Extract payment total
            payment_elements = tree.xpath('//table[2]//tbody//tr[18]//td//div//table//tbody//tr//td//table//tbody//tr[3]//td//table//tbody//tr[5]//td[2]//span')
            if payment_elements:
                payment_text = etree.tostring(payment_elements[0], method='text', encoding='unicode').strip()
                payment_text = re.sub(r'[€$,\s]', '', payment_text)
                sale_data['payment_total'] = payment_text
        
        elif sale_data['email_type'] == 'send_tickets':
            # "Please send your tickets" (without "immediately") - same structure as transfer/upload
            # Extract Order ID
            order_id_tds = tree.xpath('//td[contains(., "Order ID:")]')
            for td in order_id_tds:
                td_text = etree.tostring(td, method='text', encoding='unicode').strip()
                order_match = re.search(r'Order\s+ID:\s*(\d+)', td_text, re.IGNORECASE)
                if order_match:
                    sale_data['order_id'] = order_match.group(1).strip()
                    break
            
            # Extract Section and Row from Ticket(s) row
            ticket_label_tds = tree.xpath('//td[contains(., "Ticket(s):")]')
            for label_td in ticket_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            section_row_td = tds[i + 1]
                            text = etree.tostring(section_row_td, method='text', encoding='unicode').strip()
                            # Parse "Section Floor, Row , (1 Ticket(s))" or "Section 117, Row 8, (1 Ticket(s))"
                            section_match = re.search(r'Section\s+([^,]+)', text, re.IGNORECASE)
                            if section_match:
                                section_value = section_match.group(1).strip()
                                # Only set if it's not empty
                                if section_value:
                                    sale_data['section'] = section_value
                            
                            row_match = re.search(r'Row\s+([^,)]+)', text, re.IGNORECASE)
                            if row_match:
                                row_value = row_match.group(1).strip()
                                # Only set if it's not empty
                                if row_value:
                                    sale_data['row'] = row_value
                            
                            qty_match = re.search(r'\((\d+)\s+Ticket', text, re.IGNORECASE)
                            if qty_match:
                                sale_data['quantity'] = qty_match.group(1).strip()
                            break
            
            # Extract event name
            event_label_tds = tree.xpath('//td[contains(., "Event:")]')
            for label_td in event_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            event_td = tds[i + 1]
                            event_text = etree.tostring(event_td, method='text', encoding='unicode').strip()
                            event_text = ' '.join(event_text.split())
                            if event_text and len(event_text) < 200:
                                sale_data['event_name'] = event_text
                            break
            
            # Extract date
            date_label_tds = tree.xpath('//td[text()="Date:" or contains(., "Date:")]')
            for label_td in date_label_tds:
                label_text = etree.tostring(label_td, method='text', encoding='unicode').strip()
                if 'Must Ship' in label_text:
                    continue
                
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            date_td = tds[i + 1]
                            date_text = etree.tostring(date_td, method='text', encoding='unicode').strip()
                            if re.search(r'\w+day,\s+\w+\s+\d{1,2},\s+\d{4}', date_text, re.IGNORECASE):
                                date_text = re.sub(r'\s*Date\s*&\s*Time\s*to\s*be\s*Confirmed.*', '', date_text, flags=re.IGNORECASE).strip()
                                sale_data['event_date'] = date_text
                                break
            
            # Extract buyer info from "Ticket Holder Details" section
            # Look for "Full Name:" and "Email Address:" in table
            # The structure is: <tr><td>Full Name:</td><td width="5"></td><td><strong>Roman Sibilev</strong></td></tr>
            name_label_tds = tree.xpath('//td[contains(., "Full Name:")]')
            for label_td in name_label_tds:
                # Get the parent row
                parent_row = label_td.getparent()
                if parent_row is not None and parent_row.tag == 'tr':
                    # Get all tds in this row
                    tds = parent_row.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td:
                            # Find the next td that's not the spacer (width="5")
                            for j in range(i + 1, len(tds)):
                                next_td = tds[j]
                                # Skip spacer tds
                                if next_td.get('width') == '5':
                                    continue
                                # This should be the name td
                                name_text = etree.tostring(next_td, method='text', encoding='unicode').strip()
                                name_text = ' '.join(name_text.split())
                                # Check if it's wrapped in <strong> tags
                                strong_elements = next_td.xpath('.//strong')
                                if strong_elements:
                                    name_text = etree.tostring(strong_elements[0], method='text', encoding='unicode').strip()
                                    name_text = ' '.join(name_text.split())
                                # Only set if it's a valid name (not empty, not a number, not "Order ID:")
                                if name_text and not name_text.isdigit() and 'Order ID:' not in name_text and len(name_text) > 2:
                                    sale_data['buyer_name'] = name_text
                                break
                            break
            
            # Extract buyer email - multiple strategies
            email_label_tds = tree.xpath('//td[contains(., "Email Address:")]')
            for label_td in email_label_tds:
                # Get the parent row
                parent_row = label_td.getparent()
                if parent_row is not None and parent_row.tag == 'tr':
                    # Strategy 1: Find mailto link anywhere in the parent row
                    mailto_links = parent_row.xpath('.//a[starts-with(@href, "mailto:")]')
                    for link in mailto_links:
                        href = link.get('href', '')
                        if href.startswith('mailto:'):
                            email_value = href.replace('mailto:', '').strip()
                            # Clean up email (remove any query parameters or fragments)
                            if '?' in email_value:
                                email_value = email_value.split('?')[0]
                            if '#' in email_value:
                                email_value = email_value.split('#')[0]
                            if '@' in email_value and len(email_value) > 5:
                                # Skip viagogo/automated emails
                                if 'viagogo' not in email_value.lower() and 'automated' not in email_value.lower():
                                    sale_data['buyer_email'] = email_value
                                    break
                    if sale_data.get('buyer_email'):
                        break
                    
                    # Strategy 2: Find the next td after "Email Address:" label (skip spacers)
                    if not sale_data.get('buyer_email'):
                        tds = parent_row.xpath('.//td')
                        for i, td in enumerate(tds):
                            if td == label_td:
                                # Find the next td that's not the spacer (width="5")
                                for j in range(i + 1, len(tds)):
                                    next_td = tds[j]
                                    # Skip spacer tds
                                    if next_td.get('width') == '5':
                                        continue
                                    # This should be the email td
                                    # First try to get href from mailto link if it exists
                                    link_elements = next_td.xpath('.//a[starts-with(@href, "mailto:")]')
                                    if link_elements:
                                        href = link_elements[0].get('href', '')
                                        if href.startswith('mailto:'):
                                            email_value = href.replace('mailto:', '').strip()
                                            if '?' in email_value:
                                                email_value = email_value.split('?')[0]
                                            if '#' in email_value:
                                                email_value = email_value.split('#')[0]
                                            if '@' in email_value and len(email_value) > 5:
                                                if 'viagogo' not in email_value.lower() and 'automated' not in email_value.lower():
                                                    sale_data['buyer_email'] = email_value
                                                    break
                                    # If no mailto link, try text content
                                    if not sale_data.get('buyer_email'):
                                        email_text = etree.tostring(next_td, method='text', encoding='unicode').strip()
                                        email_text = ' '.join(email_text.split())
                                        if '@' in email_text and len(email_text) > 5:
                                            if 'viagogo' not in email_text.lower() and 'automated' not in email_text.lower():
                                                sale_data['buyer_email'] = email_text
                                    break
                                break
                    if sale_data.get('buyer_email'):
                        break
            
            # Strategy 3: Search for mailto links in "Ticket Holder Details" section
            if not sale_data.get('buyer_email'):
                # Look for table that contains "Ticket Holder Details"
                ticket_holder_sections = tree.xpath('//td[contains(., "Ticket Holder Details")]')
                for section_td in ticket_holder_sections:
                    # Find parent table
                    parent_table = section_td
                    while parent_table is not None and parent_table.tag != 'table':
                        parent_table = parent_table.getparent()
                    
                    if parent_table is not None:
                        # Look for mailto links in this table
                        mailto_links = parent_table.xpath('.//a[starts-with(@href, "mailto:")]')
                        for link in mailto_links:
                            href = link.get('href', '')
                            if href.startswith('mailto:'):
                                email_value = href.replace('mailto:', '').strip()
                                # Skip if it's the sender email or contains common non-buyer patterns
                                if 'viagogo' not in email_value.lower() and 'automated' not in email_value.lower():
                                    # Clean up email
                                    if '?' in email_value:
                                        email_value = email_value.split('?')[0]
                                    if '#' in email_value:
                                        email_value = email_value.split('#')[0]
                                    if '@' in email_value and len(email_value) > 5:
                                        sale_data['buyer_email'] = email_value
                                        break
                        if sale_data.get('buyer_email'):
                            break
            
            # Strategy 4: Search for mailto links in <p> tags containing "Email Address:"
            if not sale_data.get('buyer_email'):
                email_paragraphs = tree.xpath('//p[contains(., "Email Address:")]')
                for p_elem in email_paragraphs:
                    mailto_links = p_elem.xpath('.//a[starts-with(@href, "mailto:")]')
                    for link in mailto_links:
                        href = link.get('href', '')
                        if href.startswith('mailto:'):
                            email_value = href.replace('mailto:', '').strip()
                            if '?' in email_value:
                                email_value = email_value.split('?')[0]
                            if '#' in email_value:
                                email_value = email_value.split('#')[0]
                            if '@' in email_value and len(email_value) > 5:
                                if 'viagogo' not in email_value.lower() and 'automated' not in email_value.lower():
                                    sale_data['buyer_email'] = email_value
                                    break
                    if sale_data.get('buyer_email'):
                        break
            
            # Strategy 5: Final fallback - search for all mailto links in the document
            if not sale_data.get('buyer_email'):
                all_mailto_links = tree.xpath('//a[starts-with(@href, "mailto:")]')
                for link in all_mailto_links:
                    href = link.get('href', '')
                    if href.startswith('mailto:'):
                        email_value = href.replace('mailto:', '').strip()
                        # Skip if it's the sender email or contains common non-buyer patterns
                        if 'viagogo' not in email_value.lower() and 'automated' not in email_value.lower():
                            # Clean up email
                            if '?' in email_value:
                                email_value = email_value.split('?')[0]
                            if '#' in email_value:
                                email_value = email_value.split('#')[0]
                            if '@' in email_value and len(email_value) > 5:
                                sale_data['buyer_email'] = email_value
                                break
            
            # Extract quantity
            if not sale_data.get('quantity'):
                qty_label_tds = tree.xpath('//td[contains(., "Number of Tickets:")]')
                for label_td in qty_label_tds:
                    parent = label_td.getparent()
                    if parent is not None:
                        tds = parent.xpath('.//td')
                        for i, td in enumerate(tds):
                            if td == label_td and i + 1 < len(tds):
                                qty_td = tds[i + 1]
                                qty_text = etree.tostring(qty_td, method='text', encoding='unicode').strip()
                                if qty_text.isdigit():
                                    sale_data['quantity'] = qty_text
                                break
            
            # Extract price per ticket
            price_label_tds = tree.xpath('//td[contains(., "Price per Ticket:")]')
            for label_td in price_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            price_td = tds[i + 1]
                            price_text = etree.tostring(price_td, method='text', encoding='unicode').strip()
                            price_match = re.search(r'€\s*([\d,]+\.?\d*)', price_text)
                            if price_match:
                                sale_data['price_per_ticket'] = price_match.group(1).replace(',', '').strip()
                            break
            
            # Extract total proceeds
            total_label_tds = tree.xpath('//td[contains(., "Total Proceeds:")]')
            for label_td in total_label_tds:
                parent = label_td.getparent()
                if parent is not None:
                    tds = parent.xpath('.//td')
                    for i, td in enumerate(tds):
                        if td == label_td and i + 1 < len(tds):
                            total_td = tds[i + 1]
                            total_text = etree.tostring(total_td, method='text', encoding='unicode').strip()
                            total_match = re.search(r'€\s*([\d,]+\.?\d*)', total_text)
                            if total_match:
                                sale_data['total_proceeds'] = total_match.group(1).replace(',', '').strip()
                                break
        
        elif sale_data['email_type'] == 'sold':
            # "You sold your ticket for"
            # Extract payment total
            payment_elements = tree.xpath('//table[2]//tbody//tr[6]//td//div//table//tbody//tr//td//table//tbody//tr[3]//td//table//tbody//tr[5]//td[2]//span')
            if payment_elements:
                payment_text = etree.tostring(payment_elements[0], method='text', encoding='unicode').strip()
                payment_text = re.sub(r'[€$,\s]', '', payment_text)
                sale_data['payment_total'] = payment_text
            
            # Extract event name
            event_elements = tree.xpath('//table[2]//tbody//tr[10]//td//div//table//tbody//tr//td//table//tbody//tr[2]//td//span')
            if event_elements:
                sale_data['event_name'] = etree.tostring(event_elements[0], method='text', encoding='unicode').strip()
            
            # Extract event date
            date_elements = tree.xpath('//table[2]//tbody//tr[10]//td//div//table//tbody//tr//td//table//tbody//tr[3]//td//table//tbody//tr[1]//td//span')
            if date_elements:
                date_text = etree.tostring(date_elements[0], method='text', encoding='unicode').strip()
                if ',' in date_text:
                    parts = date_text.split(',')
                    if len(parts) >= 2:
                        date_text = ','.join(parts[1:]).strip()
                if '|' in date_text:
                    date_text = date_text.split('|')[0].strip()
                sale_data['event_date'] = date_text
            
            # Extract quantity
            qty_elements = tree.xpath('//table[2]//tbody//tr[10]//td//div//table//tbody//tr//td//table//tbody//tr[4]//td//span')
            if qty_elements:
                qty_text = etree.tostring(qty_elements[0], method='text', encoding='unicode').strip()
                qty_match = re.search(r'(\d+)', qty_text)
                if qty_match:
                    sale_data['quantity'] = qty_match.group(1).strip()
            
            # Extract section
            section_elements = tree.xpath('//table[2]//tbody//tr[10]//td//div//table//tbody//tr//td//table//tbody//tr[5]//td//table//tbody//tr[1]//td//span')
            if section_elements:
                section_text = etree.tostring(section_elements[0], method='text', encoding='unicode').strip()
                section_text = re.sub(r'^Section\s*:?\s*', '', section_text, flags=re.IGNORECASE).strip()
                sale_data['section'] = section_text
            
            # Extract row and seats
            row_seat_elements = tree.xpath('//table[2]//tbody//tr[10]//td//div//table//tbody//tr//td//table//tbody//tr[5]//td//table//tbody//tr[2]//td//span')
            if row_seat_elements:
                row_seat_text = etree.tostring(row_seat_elements[0], method='text', encoding='unicode').strip()
                row_match = re.search(r'Row\s*:?\s*([A-Z0-9]+)', row_seat_text, re.IGNORECASE)
                if row_match:
                    sale_data['row'] = row_match.group(1).strip()
                seats_match = re.search(r'Seats?[:\s]+([0-9\-\s,]+)', row_seat_text, re.IGNORECASE)
                if seats_match:
                    sale_data['seats'] = seats_match.group(1).strip()
        
    except Exception as e:
        log_message(f"[ERROR] Failed to parse HTML: {e}")
    
    return sale_data

def send_discord_webhook(webhook_url, sale_data):
    """Send Discord webhook notification - red for normal sales, dark red for urgent"""
    try:
        # Determine color based on email type
        if sale_data.get('email_type') == 'send_tickets_immediately':
            color = 10038562  # Dark Red for urgent
        elif sale_data.get('email_type') in ['transfer_tickets', 'upload_tickets', 'send_tickets']:
            color = 16761035  # Light Pink for transfer/upload/send requests
        elif sale_data.get('email_type') == 'congratulations_sold':
            color = 3066993  # Green for successful sales
        else:
            color = 15158332  # Bright Red for normal sales
        
        # Build embed based on email type
        if sale_data.get('email_type') in ['transfer_tickets', 'upload_tickets', 'send_tickets', 'congratulations_sold']:
            # New email types: transfer/upload tickets
            event_name = sale_data.get('event_name', 'Unknown Event')
            description_parts = []
            
            if sale_data.get('order_id'):
                description_parts.append(f"**Order ID:** {sale_data['order_id']}")
            
            if sale_data.get('event_date'):
                event_date = sale_data['event_date']
                # Keep full date format: "Thursday, December 04, 2025 | 19:00"
                description_parts.append(f"**Date:** {event_date}")
            
            location_parts = []
            if sale_data.get('section'):
                location_parts.append(f"Section {sale_data['section']}")
            if sale_data.get('row'):
                location_parts.append(f"Row {sale_data['row']}")
            if location_parts:
                description_parts.append(f"**Location:** {' | '.join(location_parts)}")
            
            if sale_data.get('quantity'):
                ticket_info = sale_data['quantity']
                if sale_data.get('price_per_ticket'):
                    ticket_info += f" × €{sale_data['price_per_ticket']}"
                description_parts.append(f"**Tickets:** {ticket_info}")
            
            if sale_data.get('total_proceeds'):
                description_parts.append(f"**Total Payout:** €{sale_data['total_proceeds']}")
            
            if sale_data.get('buyer_name'):
                description_parts.append(f"**Buyer:** {sale_data['buyer_name']}")
            
            if sale_data.get('buyer_email'):
                description_parts.append(f"**Email:** {sale_data['buyer_email']}")
            
            embed = {
                "title": f"Viagogo Sale: {event_name}",
                "description": "\n\n".join(description_parts) if description_parts else f"**Order ID:** {sale_data.get('order_id', 'N/A')}",
                "color": color,
                "timestamp": datetime.now().isoformat(),
            }
        
        elif sale_data.get('email_type') == 'send_tickets_immediately':
            # Urgent: order ID with buyer info
            description_parts = []
            if sale_data.get('order_id'):
                description_parts.append(f"**Order ID:** {sale_data['order_id']}")
            if sale_data.get('buyer_name'):
                description_parts.append(f"**Buyer:** {sale_data['buyer_name']}")
            if sale_data.get('buyer_email'):
                description_parts.append(f"**Email:** {sale_data['buyer_email']}")
            if sale_data.get('event_name'):
                description_parts.append(f"**Event:** {sale_data['event_name']}")
            if sale_data.get('event_date'):
                event_date = sale_data['event_date']
                if ',' in event_date:
                    parts = event_date.split(',')
                    if len(parts) >= 2:
                        event_date = ','.join(parts[1:]).strip()
                if '|' in event_date:
                    event_date = event_date.split('|')[0].strip()
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
                description_parts.append(f"**Quantity:** {sale_data['quantity']}")
            
            if sale_data.get('payment_total'):
                description_parts.append(f"**Payment Total:** €{sale_data['payment_total']}")
            
            embed = {
                "title": "URGENT: Send Tickets Immediately",
                "description": "\n\n".join(description_parts) if description_parts else "**Order ID:** " + sale_data.get('order_id', 'N/A'),
                "color": color,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            # Normal sale or send tickets notification
            event_name = sale_data.get('event_name', 'Unknown Event')
            embed = {
                "title": f"Viagogo Sale: {event_name}",
                "color": color,
                "description": "",
                "timestamp": datetime.now().isoformat(),
                "footer": {
                    "text": f"Order ID: {sale_data.get('order_id', 'N/A')}"
                }
            }
            
            # Build description with clean formatting
            description_parts = []
            
            if sale_data.get('event_date'):
                event_date = sale_data['event_date']
                # Remove day of week and time if present
                if ',' in event_date:
                    parts = event_date.split(',')
                    if len(parts) >= 2:
                        # Skip first part (day of week) if it exists
                        event_date = ','.join(parts[1:]).strip()
                # Remove time if present (format: "November 11, 2025 | 18:30")
                if '|' in event_date:
                    event_date = event_date.split('|')[0].strip()
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
                    ticket_info += f" × €{sale_data['price_per_ticket']}"
                description_parts.append(f"**Tickets:** {ticket_info}")
            
            # Payment info
            if sale_data.get('payment_total'):
                description_parts.append(f"**Payment Total:** €{sale_data['payment_total']}")
            
            if sale_data.get('total_proceeds'):
                description_parts.append(f"**Total Proceeds:** €{sale_data['total_proceeds']}")
            
            if sale_data.get('buyer_name'):
                description_parts.append(f"**Buyer:** {sale_data['buyer_name']}")
            
            if sale_data.get('buyer_email'):
                description_parts.append(f"**Email:** {sale_data['buyer_email']}")
            
            if description_parts:
                embed["description"] = "\n\n".join(description_parts)
        
        payload = {
            "embeds": [embed]
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
        
    except Exception as e:
        log_message(f"[ERROR] Failed to send Discord webhook: {e}")
        return False

def check_for_sales(config):
    """Check IMAP for new Viagogo sales emails"""
    global last_check_time, found_sales
    
    imap_accounts = config.get('imap_accounts', [])
    monitoring = config.get('monitoring', {})
    check_interval = monitoring.get('check_interval_seconds', 120)
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
                
                # IMAP OR queries can be problematic, so we'll search for each subject separately and combine results
                log_message(f"[{account['email']}] Searching for Viagogo sales since {since_date}...")
                
                # Search for each subject type separately and combine results
                all_email_ids = set()
                subjects_to_search = [
                    "Please transfer the tickets for sale",
                    "Please upload your e-tickets",
                    "Please send your tickets",
                    "Congratulations your tickets have sold",
                    "You sold your ticket for"
                ]
                
                for subject in subjects_to_search:
                    try:
                        # Escape quotes in subject if needed
                        subject_escaped = subject.replace('"', '\\"')
                        search_criteria = f'SINCE "{since_date}" FROM "automated@orders.viagogo.com" SUBJECT "{subject_escaped}"'
                        status, messages = M.search(None, search_criteria)
                        if status == 'OK' and messages[0]:
                            email_ids = messages[0].split()
                            for email_id in email_ids:
                                all_email_ids.add(email_id)
                    except Exception as e:
                        log_message(f"[WARNING] Search failed for subject '{subject}': {e}")
                        continue
                
                # Convert set back to list for processing
                email_ids = list(all_email_ids)
                
                if not email_ids:
                    log_message(f"[{account['email']}] No new sales found")
                    last_check_time = datetime.now()
                    continue
                
                log_message(f"[{account['email']}] Found {len(email_ids)} potential sale(s), filtering by date...")
                
                processed_count = 0
                # Store original last_check_time to compare against
                check_start_time = last_check_time
                
                # Process emails
                for email_id in email_ids:
                    try:
                        # Fetch email - use RFC822 (emails will be marked as read, but that's acceptable for monitoring)
                        # Convert email_id to string if it's bytes
                        email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                        status, msg_data = M.fetch(email_id_str, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_str(msg.get('Subject', ''))
                        subject_lower = subject.lower()
                        
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
                        
                        # Filter by subject - new types first
                        if 'please transfer the tickets for sale' in subject_lower:
                            # Extract sale data
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this sale
                            is_duplicate = False
                            for existing in found_sales:
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'transfer_tickets'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[TRANSFER TICKETS] {sale_data.get('event_name', 'Unknown')} - Order #{sale_data.get('order_id', 'N/A')}")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                            continue
                        
                        elif 'please upload your e-tickets' in subject_lower:
                            # Extract sale data
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this sale
                            is_duplicate = False
                            for existing in found_sales:
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'upload_tickets'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[UPLOAD TICKETS] {sale_data.get('event_name', 'Unknown')} - Order #{sale_data.get('order_id', 'N/A')}")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                            continue
                        
                        # Skip if "immediately" is in subject (we'll handle those separately)
                        elif 'immediately' in subject_lower and 'please send your tickets' in subject_lower:
                            # This is an urgent reminder - extract only order ID
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this
                            is_duplicate = False
                            for existing in found_sales:
                                existing_key = f"{existing.get('order_id', '')}_{existing.get('email_type', '')}_{existing.get('email_id', '')}"
                                current_key = f"{sale_data.get('order_id', '')}_{sale_data.get('email_type', '')}_{email_id_str}"
                                if current_key == existing_key:
                                    is_duplicate = True
                                    break
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'send_tickets_immediately'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[URGENT] Order {sale_data.get('order_id', 'N/A')} - Send tickets immediately!")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Urgent webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send urgent webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                            continue
                        
                        # Check for "You sold your ticket for" or "Please send your tickets" (without immediately)
                        if 'you sold your ticket for' in subject_lower:
                            # Extract sale data
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this sale (by order_id or email_id)
                            is_duplicate = False
                            for existing in found_sales:
                                existing_key = f"{existing.get('order_id', '')}_{existing.get('email_type', '')}_{existing.get('email_id', '')}"
                                current_key = f"{sale_data.get('order_id', '')}_{sale_data.get('email_type', '')}_{email_id_str}"
                                if current_key == existing_key:
                                    is_duplicate = True
                                    break
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'sold'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[SALE FOUND] {sale_data.get('event_name', 'Unknown')} - Order #{sale_data.get('order_id', 'N/A')}")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                        
                        elif 'please send your tickets' in subject_lower:
                            # Extract sale data
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this (by order_id or email_id)
                            is_duplicate = False
                            for existing in found_sales:
                                existing_key = f"{existing.get('order_id', '')}_{existing.get('email_type', '')}_{existing.get('email_id', '')}"
                                current_key = f"{sale_data.get('order_id', '')}_{sale_data.get('email_type', '')}_{email_id_str}"
                                if current_key == existing_key:
                                    is_duplicate = True
                                    break
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'send_tickets'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[SEND TICKETS] {sale_data.get('event_name', 'Unknown')} - Order #{sale_data.get('order_id', 'N/A')}")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                            continue
                        
                        elif 'congratulations' in subject_lower and 'sold' in subject_lower:
                            # Extract sale data
                            sale_data = extract_sale_data(msg, account['email'], subject)
                            sale_data['email_id'] = email_id_str
                            
                            # Check if we already found this (by order_id or email_id)
                            is_duplicate = False
                            for existing in found_sales:
                                existing_key = f"{existing.get('order_id', '')}_{existing.get('email_type', '')}_{existing.get('email_id', '')}"
                                current_key = f"{sale_data.get('order_id', '')}_{sale_data.get('email_type', '')}_{email_id_str}"
                                if current_key == existing_key:
                                    is_duplicate = True
                                    break
                                if (sale_data.get('order_id') and 
                                    existing.get('order_id') == sale_data.get('order_id') and
                                    existing.get('email_type') == 'congratulations_sold'):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                found_sales.append(sale_data)
                                log_message(f"[CONGRATULATIONS SOLD] {sale_data.get('event_name', 'Unknown')} - Order #{sale_data.get('order_id', 'N/A')}")
                                
                                # Send Discord webhook
                                if webhook_url and webhook_url != 'YOUR_DISCORD_WEBHOOK_URL_HERE':
                                    if send_discord_webhook(webhook_url, sale_data):
                                        log_message(f"[DISCORD] Webhook sent successfully")
                                    else:
                                        log_message(f"[DISCORD] Failed to send webhook")
                                elif not webhook_url:
                                    log_message(f"[WARNING] Webhook URL not configured")
                                else:
                                    log_message(f"[WARNING] Webhook URL not set (using placeholder)")
                            continue
                        
                    except Exception as e:
                        log_message(f"[ERROR] Failed to process email {email_id}: {e}")
                
                if processed_count > 0:
                    log_message(f"[{account['email']}] Processed {processed_count} new sale(s)")
                
                last_check_time = datetime.now()
                
        except Exception as e:
            log_message(f"[ERROR] Failed to connect to {account['email']}: {e}")

def monitoring_loop(config):
    """Main monitoring loop that runs in background thread"""
    global monitoring_active
    
    log_message("=== Viagogo Monitor Started ===")
    monitoring_active = True
    
    while monitoring_active:
        try:
            check_for_sales(config)
        except Exception as e:
            log_message(f"[ERROR] Monitoring error: {e}")
        
        # Wait for next check interval
        check_interval = config.get('monitoring', {}).get('check_interval_seconds', 120)
        for _ in range(check_interval):
            if not monitoring_active:
                break
            time.sleep(1)
    
    log_message("=== Viagogo Monitor Stopped ===")

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
    
    # Give it a moment to start
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
    # For testing
    config = load_config()
    if config:
        print("Starting Viagogo monitor...")
        start_monitoring()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            stop_monitoring()
