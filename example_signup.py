#!/usr/bin/env python3
"""
Example Signup Module using Dolphin Base Framework
==================================================

Voorbeeld van hoe je het Dolphin base framework gebruikt voor een specifieke site.
"""

import os
import sys
import json
import time
import random
from pathlib import Path

# Add ADJEHOUSE to path
sys.path.append(str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dolphin_base import DolphinAutomation

class ExampleSignupAutomation(DolphinAutomation):
    """Example signup automation extending the base framework"""
    
    def __init__(self, config):
        super().__init__(config)
        self.site_name = "Example Site"
    
    def _execute_site_signup(self, driver, site_config, email):
        """Override base method with site-specific logic"""
        print(f"🎯 Starting signup for {email} on {self.site_name}")
        
        try:
            # Navigate to signup page
            driver.get(site_config['url'])
            time.sleep(random.uniform(3, 5))
            
            # Human-like behavior
            self.human_like_scroll(driver, scroll_count=2)
            self.random_mouse_movement(driver)
            
            # Wait for page to load
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Fill email field
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, site_config['email_selector']))
            )
            
            # Scroll to email field
            driver.execute_script("arguments[0].scrollIntoView(true);", email_field)
            time.sleep(random.uniform(0.5, 1.5))
            
            # Human-like typing
            self.human_like_type(email_field, email)
            time.sleep(random.uniform(1, 2))
            
            # Fill additional fields if needed
            if 'first_name_selector' in site_config:
                try:
                    first_name_field = driver.find_element(By.CSS_SELECTOR, site_config['first_name_selector'])
                    first_name_field.click()
                    time.sleep(random.uniform(0.3, 0.8))
                    self.human_like_type(first_name_field, self._generate_random_name())
                    time.sleep(random.uniform(0.5, 1.0))
                except:
                    pass
            
            if 'last_name_selector' in site_config:
                try:
                    last_name_field = driver.find_element(By.CSS_SELECTOR, site_config['last_name_selector'])
                    last_name_field.click()
                    time.sleep(random.uniform(0.3, 0.8))
                    self.human_like_type(last_name_field, self._generate_random_name())
                    time.sleep(random.uniform(0.5, 1.0))
                except:
                    pass
            
            # Handle checkboxes/terms
            if 'terms_selector' in site_config:
                try:
                    terms_checkbox = driver.find_element(By.CSS_SELECTOR, site_config['terms_selector'])
                    if not terms_checkbox.is_selected():
                        driver.execute_script("arguments[0].click();", terms_checkbox)
                        time.sleep(random.uniform(0.5, 1.0))
                except:
                    pass
            
            # Random pause before submit
            time.sleep(random.uniform(1, 3))
            
            # Submit form
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, site_config['submit_selector']))
            )
            
            # Scroll to submit button
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Click submit
            submit_button.click()
            
            # Wait for response
            time.sleep(random.uniform(3, 6))
            
            # Check for success indicators
            success = self._check_signup_success(driver, site_config)
            
            if success:
                print(f"✅ Signup successful for {email}")
                self._log_success(email)
            else:
                print(f"❌ Signup failed for {email}")
                self._log_failure(email)
            
            return success
            
        except Exception as e:
            print(f"❌ Error during signup for {email}: {e}")
            self._log_failure(email, str(e))
            return False
    
    def _check_signup_success(self, driver, site_config):
        """Check if signup was successful"""
        try:
            # Look for success indicators
            success_selectors = site_config.get('success_selectors', [])
            
            for selector in success_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        return True
                except:
                    continue
            
            # Check URL for success indicators
            current_url = driver.current_url
            success_urls = site_config.get('success_urls', [])
            
            for success_url in success_urls:
                if success_url in current_url:
                    return True
            
            # Check page source for success text
            page_source = driver.page_source.lower()
            success_texts = site_config.get('success_texts', [])
            
            for success_text in success_texts:
                if success_text.lower() in page_source:
                    return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error checking success: {e}")
            return False
    
    def _generate_random_name(self):
        """Generate random first/last name"""
        first_names = ['John', 'Jane', 'Mike', 'Sarah', 'David', 'Lisa', 'Chris', 'Emma', 'Alex', 'Maria']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        
        return random.choice(first_names) if random.random() < 0.5 else random.choice(last_names)
    
    def _log_success(self, email):
        """Log successful signup"""
        try:
            log_file = os.path.join(os.path.dirname(__file__), f"{self.site_name.lower().replace(' ', '_')}_success.txt")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{email} - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except Exception as e:
            print(f"❌ Error logging success: {e}")
    
    def _log_failure(self, email, error=None):
        """Log failed signup"""
        try:
            log_file = os.path.join(os.path.dirname(__file__), f"{self.site_name.lower().replace(' ', '_')}_failures.txt")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{email} - {time.strftime('%Y-%m-%d %H:%M:%S')} - {error or 'Unknown error'}\n")
        except Exception as e:
            print(f"❌ Error logging failure: {e}")


def main():
    """Main function to run the automation"""
    
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found!")
        print("💡 Create a config.json file with your Dolphin token")
        return
    
    # Site configuration
    site_config = {
        'name': 'Example Site',
        'url': 'https://example.com/signup',
        'email_selector': 'input[type="email"]',
        'first_name_selector': 'input[name="first_name"]',
        'last_name_selector': 'input[name="last_name"]',
        'terms_selector': 'input[type="checkbox"][name="terms"]',
        'submit_selector': 'button[type="submit"]',
        'success_selectors': ['.success-message', '.confirmation'],
        'success_urls': ['/success', '/thank-you', '/confirmation'],
        'success_texts': ['thank you', 'success', 'confirmation', 'welcome']
    }
    
    # Load emails
    emails_path = os.path.join(os.path.dirname(__file__), 'emails.txt')
    try:
        with open(emails_path, 'r') as f:
            emails = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print("❌ emails.txt not found!")
        return
    
    if not emails:
        print("❌ No emails found in emails.txt!")
        return
    
    print(f"📧 Loaded {len(emails)} emails")
    print(f"🎯 Target site: {site_config['name']}")
    
    # Run automation
    automation = ExampleSignupAutomation(config)
    automation.run_signup_automation(site_config, emails, threads=3)


if __name__ == "__main__":
    main()
