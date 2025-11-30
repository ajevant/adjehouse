#!/usr/bin/env python3
"""
Capsolver API Helper
====================
Helper class for solving reCAPTCHA using Capsolver API
"""

import time
import requests
from typing import Optional, Dict, Any


class CapsolverHelper:
    """Helper class for Capsolver API integration"""
    
    def __init__(self, api_key: str, api_url: str = "https://api.capsolver.com"):
        """
        Initialize Capsolver helper
        
        Args:
            api_key: Capsolver API key
            api_url: Capsolver API URL (default: https://api.capsolver.com)
        """
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.base_url = f"{self.api_url}"
    
    def get_balance(self) -> Optional[float]:
        """
        Get account balance
        
        Returns:
            Balance in USD or None if error
        """
        try:
            response = requests.post(
                f"{self.base_url}/getBalance",
                json={"clientKey": self.api_key},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("errorId") == 0:
                return data.get("balance", 0) / 1000.0  # Convert from cents to USD
            else:
                print(f"❌ Capsolver balance error: {data.get('errorDescription', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"❌ Error getting Capsolver balance: {e}")
            return None
    
    def solve_recaptcha_v3(
        self,
        website_url: str,
        website_key: str,
        page_action: str = "submit",
        min_score: float = 0.3,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v3
        
        Args:
            website_url: URL where reCAPTCHA is located
            website_key: reCAPTCHA site key
            page_action: Page action (default: "submit")
            min_score: Minimum score required (default: 0.3)
            timeout: Maximum time to wait for solution in seconds (default: 120)
        
        Returns:
            reCAPTCHA token or None if error
        """
        try:
            # Create task
            task_data = {
                "clientKey": self.api_key,
                "task": {
                    "type": "ReCaptchaV3TaskProxyLess",
                    "websiteURL": website_url,
                    "websiteKey": website_key,
                    "pageAction": page_action,
                    "minScore": min_score
                }
            }
            
            print(f"🔐 Creating Capsolver reCAPTCHA v3 task...")
            response = requests.post(
                f"{self.base_url}/createTask",
                json=task_data,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("errorId") != 0:
                error_desc = data.get("errorDescription", "Unknown error")
                print(f"❌ Capsolver createTask error: {error_desc}")
                return None
            
            task_id = data.get("taskId")
            if not task_id:
                print(f"❌ No taskId returned from Capsolver")
                return None
            
            print(f"✅ Task created: {task_id}, waiting for solution...")
            
            # Poll for result
            start_time = time.time()
            poll_interval = 2  # Check every 2 seconds
            max_polls = timeout // poll_interval
            
            for poll_count in range(max_polls):
                if time.time() - start_time > timeout:
                    print(f"❌ Capsolver timeout after {timeout} seconds")
                    return None
                
                time.sleep(poll_interval)
                
                result_data = {
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
                
                response = requests.post(
                    f"{self.base_url}/getTaskResult",
                    json=result_data,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("errorId") != 0:
                    error_desc = result.get("errorDescription", "Unknown error")
                    print(f"❌ Capsolver getTaskResult error: {error_desc}")
                    return None
                
                status = result.get("status", "")
                
                if status == "ready":
                    solution = result.get("solution", {})
                    token = solution.get("gRecaptchaResponse")
                    if token:
                        print(f"✅ reCAPTCHA solved! (took {time.time() - start_time:.1f}s)")
                        return token
                    else:
                        print(f"❌ No token in solution: {result}")
                        return None
                elif status == "processing":
                    if poll_count % 5 == 0:  # Print every 5 polls
                        print(f"⏳ Still processing... ({poll_count * poll_interval}s)")
                    continue
                else:
                    # idle or other status
                    continue
            
            print(f"❌ Capsolver timeout: status was '{status}' after {timeout} seconds")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Capsolver API request error: {e}")
            return None
        except Exception as e:
            print(f"❌ Capsolver error: {e}")
            return None
    
    def solve_recaptcha_v2(
        self,
        website_url: str,
        website_key: str,
        is_invisible: bool = False,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v2
        
        Args:
            website_url: URL where reCAPTCHA is located
            website_key: reCAPTCHA site key
            is_invisible: Whether it's invisible reCAPTCHA (default: False)
            timeout: Maximum time to wait for solution in seconds (default: 120)
        
        Returns:
            reCAPTCHA token or None if error
        """
        try:
            task_type = "ReCaptchaV2TaskProxyLess" if not is_invisible else "ReCaptchaV2EnterpriseTaskProxyLess"
            
            # Create task
            task_data = {
                "clientKey": self.api_key,
                "task": {
                    "type": task_type,
                    "websiteURL": website_url,
                    "websiteKey": website_key
                }
            }
            
            print(f"🔐 Creating Capsolver reCAPTCHA v2 task...")
            response = requests.post(
                f"{self.base_url}/createTask",
                json=task_data,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("errorId") != 0:
                error_desc = data.get("errorDescription", "Unknown error")
                print(f"❌ Capsolver createTask error: {error_desc}")
                return None
            
            task_id = data.get("taskId")
            if not task_id:
                print(f"❌ No taskId returned from Capsolver")
                return None
            
            print(f"✅ Task created: {task_id}, waiting for solution...")
            
            # Poll for result
            start_time = time.time()
            poll_interval = 2
            max_polls = timeout // poll_interval
            
            for poll_count in range(max_polls):
                if time.time() - start_time > timeout:
                    print(f"❌ Capsolver timeout after {timeout} seconds")
                    return None
                
                time.sleep(poll_interval)
                
                result_data = {
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
                
                response = requests.post(
                    f"{self.base_url}/getTaskResult",
                    json=result_data,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("errorId") != 0:
                    error_desc = result.get("errorDescription", "Unknown error")
                    print(f"❌ Capsolver getTaskResult error: {error_desc}")
                    return None
                
                status = result.get("status", "")
                
                if status == "ready":
                    solution = result.get("solution", {})
                    token = solution.get("gRecaptchaResponse")
                    if token:
                        print(f"✅ reCAPTCHA solved! (took {time.time() - start_time:.1f}s)")
                        return token
                    else:
                        print(f"❌ No token in solution: {result}")
                        return None
                elif status == "processing":
                    if poll_count % 5 == 0:
                        print(f"⏳ Still processing... ({poll_count * poll_interval}s)")
                    continue
                else:
                    continue
            
            print(f"❌ Capsolver timeout: status was '{status}' after {timeout} seconds")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Capsolver API request error: {e}")
            return None
        except Exception as e:
            print(f"❌ Capsolver error: {e}")
            return None
    
    def solve_cloudflare_turnstile(
        self,
        website_url: str,
        website_key: str,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve Cloudflare Turnstile captcha
        
        Args:
            website_url: URL where Turnstile is located
            website_key: Turnstile site key
            timeout: Maximum time to wait for solution in seconds (default: 120)
        
        Returns:
            Turnstile token or None if error
        """
        try:
            # Create task
            task_data = {
                "clientKey": self.api_key,
                "task": {
                    "type": "AntiTurnstileTaskProxyLess",
                    "websiteURL": website_url,
                    "websiteKey": website_key
                }
            }
            
            print(f"🔐 Creating Capsolver Cloudflare Turnstile task...")
            response = requests.post(
                f"{self.base_url}/createTask",
                json=task_data,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("errorId") != 0:
                error_desc = data.get("errorDescription", "Unknown error")
                print(f"❌ Capsolver createTask error: {error_desc}")
                return None
            
            task_id = data.get("taskId")
            if not task_id:
                print(f"❌ No taskId returned from Capsolver")
                return None
            
            print(f"✅ Task created: {task_id}, waiting for solution...")
            
            # Poll for result
            start_time = time.time()
            poll_interval = 2
            max_polls = timeout // poll_interval
            
            for poll_count in range(max_polls):
                if time.time() - start_time > timeout:
                    print(f"❌ Capsolver timeout after {timeout} seconds")
                    return None
                
                time.sleep(poll_interval)
                
                result_data = {
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
                
                response = requests.post(
                    f"{self.base_url}/getTaskResult",
                    json=result_data,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("errorId") != 0:
                    error_desc = result.get("errorDescription", "Unknown error")
                    print(f"❌ Capsolver getTaskResult error: {error_desc}")
                    return None
                
                status = result.get("status", "")
                
                if status == "ready":
                    solution = result.get("solution", {})
                    token = solution.get("token")
                    if token:
                        print(f"✅ Cloudflare Turnstile solved! (took {time.time() - start_time:.1f}s)")
                        return token
                    else:
                        print(f"❌ No token in solution: {result}")
                        return None
                elif status == "processing":
                    if poll_count % 5 == 0:
                        print(f"⏳ Still processing... ({poll_count * poll_interval}s)")
                    continue
                else:
                    continue
            
            print(f"❌ Capsolver timeout: status was '{status}' after {timeout} seconds")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Capsolver API request error: {e}")
            return None
        except Exception as e:
            print(f"❌ Capsolver error: {e}")
            return None
