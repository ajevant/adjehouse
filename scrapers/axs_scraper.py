#!/usr/bin/env python3
"""
AXS Email Scraper
=================
Scrapes AXS confirmation emails from IMAP using XPath parsing
"""

import os
import sys
import imaplib
import email
import csv
import datetime
import re
import json
import requests
from pathlib import Path
from email.header import decode_header, make_header
from lxml import html, etree

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
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
    IMAP_ACCOUNTS = config['imap_accounts'].get('axs', [])
    DEFAULT_SEARCH_DAYS = config['search_settings'].get('default_search_days', 1)
else:
    IMAP_ACCOUNTS = []
    DEFAULT_SEARCH_DAYS = 1

# Configuration
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
OUTPUT_DIR = BASE_DIR / "success"
OUTPUT_FILE = OUTPUT_DIR / "axs_success.csv"

def decode_str(s):
    """Decode email header strings"""
    if s is None:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s

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

def get_bunq_exchange_rate(from_currency, to_currency):
    """Get exchange rate from Bunq API"""
    try:
        # Bunq API endpoint for exchange rates
        url = f"https://api.bunq.com/v1/currency-exchange-rate"
        # Note: Bunq API requires authentication, so we'll use a fallback
        # For now, use exchangerate-api.com as fallback
        fallback_url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        response = requests.get(fallback_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            rate = data.get('rates', {}).get(to_currency)
            if rate:
                return float(rate)
    except Exception:
        pass
    
    # Fallback rates
    if from_currency == 'USD' and to_currency == 'EUR':
        return 0.92
    elif from_currency == 'GBP' and to_currency == 'EUR':
        return 1.14
    return 1.0

def extract_us_order_data(msg, subject):
    """Extract data from US order email using text/regex parsing"""
    html_content = get_html_body(msg)
    if not html_content:
        return None
    
    # Get plain text from HTML
    tree = html.fromstring(html_content)
    text = etree.tostring(tree, method='text', encoding='unicode')
    
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
        # Event name from subject (title)
        # Subject format: "Thank you for your order for [Event Name]"
        if subject.lower().startswith('thank you for your order for'):
            event_name = subject.replace('Thank you for your order for', '').strip()
            order_data['event_name'] = event_name
        
        # Order ID: "Your confirmation number is 28190034"
        order_match = re.search(r'Your confirmation number is\s+(\d+)', text, re.IGNORECASE)
        if order_match:
            order_data['order_id'] = order_match.group(1).strip()
        
        # Event date: "scheduled on 7/15/2026 8:00 PM"
        date_match = re.search(r'scheduled on\s+(\d{1,2}/\d{1,2}/\d{4})', text, re.IGNORECASE)
        if date_match:
            date_str = date_match.group(1)
            try:
                # Parse MM/DD/YYYY
                parsed_date = datetime.datetime.strptime(date_str, "%m/%d/%Y")
                order_data['event_date'] = parsed_date.strftime("%d-%m-%Y")
                order_data['day_name'] = parsed_date.strftime("%A")
            except:
                order_data['event_date'] = date_str
        
        # Venue: "at Crypto.com Arena scheduled"
        venue_match = re.search(r'at\s+([^scheduled]+?)\s+scheduled', text, re.IGNORECASE)
        if venue_match:
            order_data['venue'] = venue_match.group(1).strip()
        
        # Quantity, Section, Row, Seats, Price from table row
        # Pattern: "4 Presale 333 9 8-11 $60.50 $242.00" or "4 Presale FLOOR4 17 9-12 $130.50 $522.00"
        # Or from HTML: <td>4</td><td>Presale</td><td></td><td>333</td><td>9</td><td>8-11</td><td>$60.50</td><td>$242.00</td>
        # Or: <td>4</td><td>Presale</td><td></td><td>FLOOR4</td><td>17</td><td>9-12</td><td>$130.50</td><td>$522.00</td>
        table_row_match = re.search(r'<td[^>]*>(\d+)</td>\s*<td[^>]*>Presale</td>\s*<td[^>]*></td>\s*<td[^>]*>([A-Z0-9]+)</td>\s*<td[^>]*>(\d+)</td>\s*<td[^>]*>([0-9\-]+)</td>\s*<td[^>]*>\$?([\d.]+)</td>', html_content, re.IGNORECASE)
        if table_row_match:
            order_data['quantity'] = table_row_match.group(1).strip()
            order_data['section'] = table_row_match.group(2).strip()
            order_data['row'] = table_row_match.group(3).strip()
            order_data['seat'] = table_row_match.group(4).strip()
            order_data['price_usd'] = table_row_match.group(5).strip()
        
        # Total price: "Amount Charged To Your Credit Card: $320.60"
        total_match = re.search(r'Amount Charged To Your Credit Card[:\s]+\$?([\d.]+)', text, re.IGNORECASE)
        if total_match:
            order_data['total_usd'] = total_match.group(1).strip()
        else:
            # Fallback: "Grand Total: $320.60"
            total_match = re.search(r'Grand Total[:\s]+\$?([\d.]+)', text, re.IGNORECASE)
            if total_match:
                order_data['total_usd'] = total_match.group(1).strip()
        
        # Convert USD to EUR
        usd_to_eur = get_bunq_exchange_rate('USD', 'EUR')
        if order_data['price_usd']:
            try:
                price_eur_val = float(order_data['price_usd']) * usd_to_eur
                order_data['price_eur'] = str(round(price_eur_val, 2)).replace('.', ',')
            except:
                pass
        if order_data['total_usd']:
            try:
                total_eur_val = float(order_data['total_usd']) * usd_to_eur
                order_data['total_eur'] = str(round(total_eur_val, 2)).replace('.', ',')
            except:
                pass
        
        # Format USD prices
        if order_data['price_usd']:
            try:
                order_data['price_usd'] = str(float(order_data['price_usd'])).replace('.', ',')
            except:
                pass
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

def extract_uk_order_data(msg, subject):
    """Extract data from UK order email using XPath"""
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
        tree = html.fromstring(html_content)
        
        # Event name: "Andrea Bocelli - O2 Priority Presale"
        # Look for td with font-size:18px or try finding text after "Ticket Details"
        event_elements = tree.xpath('//td[@style and contains(@style, "font-size:18px")]')
        if not event_elements:
            # Try finding text in table after "Ticket Details" section
            event_elements = tree.xpath('//td[contains(text(), "Priority") or contains(text(), "Presale")]')
        if event_elements:
            event_text = etree.tostring(event_elements[0], method='text', encoding='unicode').strip()
            # Extract event name (remove " - O2 Priority Presale" if present)
            event_name = event_text.split(' - ')[0].strip()
            order_data['event_name'] = event_name
        
        # Order ID: "1015588616" - look for "confirmation number is" followed by strong tag
        order_elements = tree.xpath('//p[contains(text(), "confirmation number is")]//strong')
        if not order_elements:
            # Try finding in "Order Number" section
            order_elements = tree.xpath('//td[contains(text(), "Order Number")]/following-sibling::td//strong')
        if order_elements:
            order_text = etree.tostring(order_elements[0], method='text', encoding='unicode').strip()
            order_data['order_id'] = order_text
        
        # Date: "02 May 2025 - 18:30"
        # Look for td with date format after calendar icon
        date_elements = tree.xpath('//td[contains(text(), "2025") or contains(text(), "2024") or contains(text(), "2026")]')
        if date_elements:
            for date_elem in date_elements:
                date_text = etree.tostring(date_elem, method='text', encoding='unicode').strip()
                # Check if it matches the format "DD Month YYYY - HH:MM"
                date_match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})', date_text)
                if date_match:
                    day, month, year, hour, minute = date_match.groups()
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
                        
                        # Get day name
                        try:
                            dt = datetime.datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
                            order_data['day_name'] = dt.strftime("%A")
                        except:
                            pass
                        break
                    except:
                        continue
        
        # Venue: "The O2 arena"
        # Look for venue after location icon (img with alt="venue")
        venue_elements = tree.xpath('//img[@alt="venue"]/following-sibling::td')
        if not venue_elements:
            # Try finding td with "arena" text
            venue_elements = tree.xpath('//td[contains(text(), "arena") or contains(text(), "Arena")]')
        if venue_elements:
            venue_text = etree.tostring(venue_elements[0], method='text', encoding='unicode').strip()
            # Extract venue name (before " - " or "&nbsp;" or comma)
            venue_match = re.search(r'^([^—\-&,]+?)(?:\s*[-–—]\s*|&nbsp;|,|$)', venue_text)
            if venue_match:
                order_data['venue'] = venue_match.group(1).strip()
        
        # Section, Row, Seat: "B2|D|25-26" (pipes are in spans, so text will be "B2 D 25-26")
        # Look for Location column in table row after "Item" header
        location_elements = tree.xpath('//tr[td[contains(text(), "Item")]]/following-sibling::tr[1]/td[2]')
        if location_elements:
            location_text = etree.tostring(location_elements[0], method='text', encoding='unicode').strip()
            # Parse "B2 D 25-26" format (pipes are in spans, so they appear as spaces in text)
            # Try regex to find pattern like "B2 D 25-26"
            location_match = re.search(r'([A-Z0-9]+)\s+([A-Z0-9]+)\s+([0-9\-]+)', location_text)
            if location_match:
                order_data['section'] = location_match.group(1).strip()
                order_data['row'] = location_match.group(2).strip()
                order_data['seat'] = location_match.group(3).strip()
        
        # Quantity: "2" - in same row, column 3
        qty_elements = tree.xpath('//tr[td[contains(text(), "Item")]]/following-sibling::tr[1]/td[3]')
        if qty_elements:
            qty_text = etree.tostring(qty_elements[0], method='text', encoding='unicode').strip()
            order_data['quantity'] = qty_text
        
        # Price per ticket: "£170.00" - in same row, column 4
        price_elements = tree.xpath('//tr[td[contains(text(), "Item")]]/following-sibling::tr[1]/td[4]')
        if price_elements:
            price_text = etree.tostring(price_elements[0], method='text', encoding='unicode').strip()
            price_text = re.sub(r'[£,]', '', price_text)
            order_data['price_gbp'] = price_text
        
        # Total: "£390.70"
        # Look for "Total:" in Order Details section
        total_elements = tree.xpath('//td[contains(text(), "Total:")]/following-sibling::td//strong')
        if not total_elements:
            # Try finding strong tag in same row as "Total:"
            total_elements = tree.xpath('//tr[td[contains(text(), "Total:")]]//strong')
        if not total_elements:
            # Try finding any strong tag with £ that's in a row with "Total:"
            total_elements = tree.xpath('//strong[contains(text(), "£") and ancestor::tr[td[contains(text(), "Total:")]]]')
        if total_elements:
            total_text = etree.tostring(total_elements[0], method='text', encoding='unicode').strip()
            total_text = re.sub(r'[£,]', '', total_text)
            order_data['total_gbp'] = total_text
        
        # Convert GBP to EUR
        gbp_to_eur = get_bunq_exchange_rate('GBP', 'EUR')
        if order_data['price_gbp']:
            try:
                price_eur_val = float(order_data['price_gbp']) * gbp_to_eur
                order_data['price_eur'] = str(round(price_eur_val, 2)).replace('.', ',')
            except:
                pass
        if order_data['total_gbp']:
            try:
                total_eur_val = float(order_data['total_gbp']) * gbp_to_eur
                order_data['total_eur'] = str(round(total_eur_val, 2)).replace('.', ',')
            except:
                pass
        
        # Format GBP prices
        if order_data['price_gbp']:
            try:
                order_data['price_gbp'] = str(float(order_data['price_gbp'])).replace('.', ',')
            except:
                pass
        if order_data['total_gbp']:
            try:
                order_data['total_gbp'] = str(float(order_data['total_gbp'])).replace('.', ',')
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
        print(f"[ERROR] Failed to parse UK order: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    return order_data

def extract_event_data(msg, subject):
    """Extract event data based on email type"""
    subject_lower = subject.lower()
    
    if subject_lower.startswith('thank you for your order for'):
        return extract_us_order_data(msg, subject)
    elif subject_lower.startswith('thank you for purchasing tickets for'):
        return extract_uk_order_data(msg, subject)
    
    return None

def fetch_axs_emails():
    """Fetch all AXS emails from multiple accounts"""
    print("\n[1/3] Connecting to email accounts...")
    print(f"      Found {len(IMAP_ACCOUNTS)} IMAP account(s)")
    
    orders = []
    
    for idx, account in enumerate(IMAP_ACCOUNTS, 1):
        print(f"\n[{idx}/{len(IMAP_ACCOUNTS)}] Processing: {account['email']}")
        
        try:
            with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as M:
                M.login(account['email'], account['password'])
                M.select('INBOX')
                
                search_days = (datetime.datetime.now() - datetime.timedelta(days=DEFAULT_SEARCH_DAYS)).strftime('%d-%b-%Y')
                print(f"      Searching since: {search_days} (last {DEFAULT_SEARCH_DAYS} days)")
                print(f"      Looking for subjects: 'Thank you for purchasing tickets for' (UK) or 'Thank you for your order for' (US)")
                
                # Search for emails with subject starting with either pattern
                all_ids = set()
                
                # UK pattern
                search_criteria_uk = f'SUBJECT "Thank you for purchasing tickets for" SINCE {search_days}'
                typ, data = M.search(None, search_criteria_uk)
                if typ == 'OK' and data[0]:
                    uk_ids = data[0].split()
                    all_ids.update(uk_ids)
                    if uk_ids:
                        print(f"        Found {len(uk_ids)} emails with UK pattern")
                
                # US pattern
                search_criteria_us = f'SUBJECT "Thank you for your order for" SINCE {search_days}'
                typ, data = M.search(None, search_criteria_us)
                    if typ == 'OK' and data[0]:
                    us_ids = data[0].split()
                    all_ids.update(us_ids)
                    if us_ids:
                        print(f"        Found {len(us_ids)} emails with US pattern")
                
                ids = list(all_ids)
                print(f"      Total: {len(ids)} unique emails matching search criteria")
                
                if not ids:
                    print("      No emails found, skipping...")
                    continue
                
                ids = ids[::-1]
                
                for i, num in enumerate(ids):
                    if len(ids) > 10 and i % 10 == 0:
                        print(f"      Processing {i+1}/{len(ids)}...")
                    
                    typ, msg_data = M.fetch(num, '(RFC822)')
                    if typ != 'OK' or not msg_data or not msg_data[0]:
                        continue
                    
                    try:
                        msg = email.message_from_bytes(msg_data[0][1])
                    except Exception:
                        continue
                    
                    subject = decode_str(msg.get('Subject', ''))
                    print(f"        Processing email with subject: {subject[:80]}...")
                    order_data = extract_event_data(msg, subject)
                    
                    if not order_data:
                        print(f"        SKIPPED: Could not extract order data")
                        continue
                    
                    order_data['imap_account'] = account['email']
                    
                    # Check if order data is valid
                    if not order_data.get('order_id') and not order_data.get('event_name'):
                        continue
                    
                    orders.append(order_data)
                    # Save to CSV immediately during scraping
                    append_order_to_csv(order_data)
                    print(f"      ✓ FOUND: {order_data['event_name']} ({order_data['event_date']}) - Order ID: {order_data['order_id']}")
        
        except Exception as e:
            print(f"Error with account {account['email']}: {e}")
            continue
    
    return orders

def save_to_csv(orders):
    """Save orders to CSV file"""
    print(f"\n[3/3] Saving results...")
    print(f"      Writing {len(orders)} orders to CSV...")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if file exists to determine if we need to write header
    file_exists = OUTPUT_FILE.exists()
    
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header only if file is new
        if not file_exists:
        writer.writerow([
            'Event Date', 'Day Name', 'Event Name', 'Price GBP', 'Total GBP',
            'Price USD', 'Total USD', 'Price EUR', 'Total EUR', 'Quantity', 
            'Section', 'Row', 'Seat', 'Venue', 'Order ID', 'Recipient Email', 
            'Email Date', 'IMAP Account'
        ])
        
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

def append_order_to_csv(order):
    """Append a single order to CSV file during scraping"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_FILE.exists()
    
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header only if file is new
        if not file_exists:
            writer.writerow([
                'Event Date', 'Day Name', 'Event Name', 'Price GBP', 'Total GBP',
                'Price USD', 'Total USD', 'Price EUR', 'Total EUR', 'Quantity', 
                'Section', 'Row', 'Seat', 'Venue', 'Order ID', 'Recipient Email', 
                'Email Date', 'IMAP Account'
            ])
        
        writer.writerow([
            order['event_date'], order['day_name'], order['event_name'],
            order['price_gbp'], order['total_gbp'], 
            order['price_usd'], order['total_usd'],
            order['price_eur'], order['total_eur'], 
            order['quantity'], order['section'],
            order['row'], order['seat'], order['venue'], order['order_id'],
            order['recipient_email'], order['email_date'], order['imap_account']
        ])

def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("AXS EMAIL SCRAPER")
    print("=" * 70)
    
    if not IMAP_ACCOUNTS:
        print("\nERROR: No IMAP accounts configured!")
        print(f"Add accounts to: {CONFIG_FILE}")
        input("\nPress ENTER to exit...")
        return
    
    # Fetch emails (orders are saved to CSV during scraping)
    orders = fetch_axs_emails()
    
    if not orders:
        print("\nNo orders found in emails.")
        input("\nPress ENTER to exit...")
        return
    
    # Summary
    print("\n" + "=" * 70)
    print(f"SUCCESS: Found and saved {len(orders)} orders")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 70)
    if __name__ == "__main__":
        input("\nPress ENTER to exit...")

if __name__ == "__main__":
    main()
