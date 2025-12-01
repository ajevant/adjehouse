#!/usr/bin/env python3
"""
Dolphin Browser Automation Base Framework
=========================================

Basis framework voor Dolphin Anty browser automation met:
- Fingerprint validation en generation via Dolphin API
- Browser profile management (start/stop via WebSocket)
- Proxy management (create, assign, delete)
- Human-like behavior (ghost-cursor style movements, typing delays)
- Natural events (mouse tremors, micro-corrections)
- Automatic cleanup (profiles + proxies)
- Multi-threading support met rate limiting

Gebaseerd op fifa-entry-mailserver-imap structuur.
"""

import os
import sys
import time
import json
import requests
import random
import threading
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, SessionNotCreatedException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Import natural events helper if available
try:
    from natural_events_helper import NaturalEventsHelper
    HAS_NATURAL_EVENTS = True
except ImportError:
    HAS_NATURAL_EVENTS = False
    NaturalEventsHelper = None


class RateLimitHandler:
    """Global rate limit handler voor Dolphin API 429 errors"""
    _lock = threading.Lock()
    _is_paused = False
    _pause_end_time = None
    
    @classmethod
    def handle_429_error(cls):
        """Pause alle threads voor 3 minuten bij rate limit"""
        with cls._lock:
            if cls._is_paused:
                # Wacht tot pause voorbij is
                while cls._is_paused:
                    if cls._pause_end_time and time.time() < cls._pause_end_time:
                        time.sleep(1)
                    else:
                        cls._is_paused = False
                return
            
            cls._is_paused = True
            cls._pause_end_time = time.time() + 180  # 3 minuten
            print(f"\n🚨 Dolphin API rate limit (429) detected - pausing all threads for 3 minutes...")
            
            # Wacht in aparte thread om niet te blokkeren
            def wait_and_resume():
                time.sleep(180)
                with cls._lock:
                    cls._is_paused = False
                    cls._pause_end_time = None
                    print(f"✅ Rate limit pause complete - resuming all threads")
            
            threading.Thread(target=wait_and_resume, daemon=True).start()
    
    @classmethod
    def check_and_wait(cls):
        """Check of er een rate limit pause actief is en wacht indien nodig"""
        with cls._lock:
            if cls._is_paused and cls._pause_end_time:
                while time.time() < cls._pause_end_time:
                    time.sleep(1)


class DolphinAutomation:
    """Base class voor Dolphin browser automation met fingerprint validation"""
    
    def __init__(self, config):
        self.config = config
        self.dolphin_token = config.get('dolphin_token')
        # Dolphin Anty uses TWO APIs:
        # - REMOTE API (https://dolphin-anty-api.com) for creating profiles/proxies, getting fingerprints
        # - LOCAL API (http://localhost:3001/v1.0) for starting/stopping profiles
        self.remote_api_url = config.get('dolphin_remote_api_url', 'https://dolphin-anty-api.com')
        self.local_api_url = config.get('dolphin_api_url', 'http://localhost:3001/v1.0')
        # base_url is used for backward compatibility, defaults to remote
        self.base_url = config.get('dolphin_api_url', self.remote_api_url)
        self.profiles = []
        self.proxies = []
        self.active_profiles = {}  # {profile_id: {'start_time': timestamp, 'proxy_id': proxy_id}}
        self.proxy_lock = threading.Lock()
        self.profile_lock = threading.Lock()
        self.browser_semaphore = None  # Will be set in run_automation
        self.profile_timeout_seconds = 600  # 10 minuten timeout
        self.cleanup_thread_running = False
        self.cleanup_thread = None
        
        # Start background cleanup thread voor timeout
        self._start_profile_timeout_cleanup()
        
        # Default profile config (zoals in config.ts)
        # Detect OS and use appropriate platform
        import platform as platform_module
        detected_platform = platform_module.system().lower()
        if detected_platform == 'windows':
            platform = 'windows'
        elif detected_platform == 'darwin':
            platform = 'macos'
        elif detected_platform == 'linux':
            platform = 'linux'
        else:
            platform = 'windows'  # Default to windows
        
        print(f"🖥️  Detected OS: {detected_platform} -> Using platform: {platform}")
        
        # Variëer browser versies voor meer uniekheid (Cloudflare detecteert identieke versies)
        # Gebruik recente Chrome versies: 138, 139, 140, 141, 142, 143
        browser_versions = ['138', '139', '140', '141', '142', '143']
        selected_browser_version = random.choice(browser_versions)
        
        self.default_config = {
            'platform': platform,
            'browser_type': 'anty',
            'browser_version': selected_browser_version,  # Variëer browser versie
            'fonts_mode': 'manual',
            'audio_mode': 'real',
            'webrtc_mode': 'altered',  # 'altered' is beter dan 'real' voor anti-detectie
            'canvas_mode': 'real',
            'webgl_mode': 'real',
            'webgpu_mode': 'real',  # Gebruik 'real' voor WebGPU (beter dan 'manual')
            'client_rect_mode': 'auto',  # 'auto' is beter dan 'real' voor variatie
            'timezone_mode': 'auto',
            'locale_mode': 'auto',
            'geolocation_mode': 'auto',
            'cpu_mode': 'manual',
            'memory_mode': 'manual',
            'media_devices_mode': 'real',
            'ports_mode': 'protect',
            'ports_blacklist': '3389,5900,5800,7070,6568,5938,63333,5901,5902,5903,5950,5931,5939,6039,5944,6040,5279,2112'
        }
        
        print(f"🎯 Browser versie: {selected_browser_version} (variatie voor unieke fingerprints)")
        
        if not self.dolphin_token:
            raise ValueError("Dolphin token is required in config")
    
    def _get_headers(self, use_local_api=False):
        """Get request headers met auth token"""
        # Local API (localhost) doesn't require auth headers
        # Remote API requires Bearer token
        if use_local_api:
            return {
                'Content-Type': 'application/json'
            }
        else:
            # Always use Bearer token for remote API calls
            return {
                'Authorization': f'Bearer {self.dolphin_token}',
                'Content-Type': 'application/json'
            }
    
    def _handle_api_response(self, response, operation_name):
        """Handle API responses met rate limit detection"""
        if response.status_code == 429:
            RateLimitHandler.handle_429_error()
            RateLimitHandler.check_and_wait()
            raise Exception(f"Dolphin API rate limit (429) - {operation_name}")
        
        if not response.ok:
            error_text = response.text
            # For debugging - print full response details for 404 errors
            if response.status_code == 404:
                try:
                    error_json = response.json()
                    print(f"⚠️  404 Error details for {operation_name}: {json.dumps(error_json, indent=2)}")
                except:
                    print(f"⚠️  404 Error - response text: {error_text}")
            raise Exception(f"HTTP error! status: {response.status_code}, message: {error_text}")
        
        return response.json()
    
    def get_fingerprint(self, platform='macos', browser_type='anty', browser_version='141', max_retries=20):
        """
        Get complete fingerprint data from Dolphin API met validation
        Gebruikt de correcte API endpoint volgens OpenAPI: /fingerprint (niet /fingerprints/fingerprint)
        Retries tot een geldige, consistente fingerprint is ontvangen
        """
        attempts = 0
        
        # Variëer screen resolutie voor meer uniekheid
        screen_resolutions = ['1920x1080', '1366x768', '1536x864', '1440x900', '1600x900', '1280x720']
        selected_screen = random.choice(screen_resolutions)
        
        while attempts < max_retries:
            attempts += 1
            
            try:
                # Probeer beide endpoint varianten (sommige API versies gebruiken /fingerprints/fingerprint)
                endpoints_to_try = [
                    f"{self.remote_api_url}/fingerprints/fingerprint",  # Oude variant (met 's')
                    f"{self.remote_api_url}/fingerprint"  # Nieuwe variant (volgens OpenAPI)
                ]
                
                data = None
                last_error = None
                
                for url in endpoints_to_try:
                    try:
                        params = {
                            'platform': platform,
                            'browser_type': browser_type,
                            'browser_version': browser_version,
                            'screen': selected_screen  # Variëer screen resolutie
                        }
                        
                        response = requests.get(url, headers=self._get_headers(use_local_api=False), params=params, timeout=30)
                        
                        if response.status_code == 200:
                            data = self._handle_api_response(response, 'get_fingerprint')
                            break  # Success, exit loop
                        else:
                            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                            continue  # Try next endpoint
                    except Exception as e:
                        last_error = str(e)
                        continue  # Try next endpoint
                
                if data is None:
                    raise Exception(f"All fingerprint endpoints failed. Last error: {last_error}")
                
                # Response is now in data variable
                
                # Validate fingerprint consistency
                if self._validate_fingerprint(data):
                    print(f"✅ Valid fingerprint obtained (attempt {attempts}/{max_retries}, screen: {selected_screen})")
                    return data
                else:
                    print(f"⚠️  Invalid fingerprint (attempt {attempts}/{max_retries}), retrying...")
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"❌ Error fetching fingerprint (attempt {attempts}/{max_retries}): {e}")
                
                if attempts >= max_retries:
                    raise Exception(f"Failed to get valid fingerprint after {max_retries} attempts")
                
                time.sleep(0.1)
        
        raise Exception(f"Failed to get valid fingerprint after {max_retries} attempts")
    
    def _validate_fingerprint(self, fingerprint):
        """Validate fingerprint consistency (zoals vriend's implementatie)
        Valideert dat CPU architecture matcht met WebGL vendor en andere consistentie checks
        """
        try:
            # Check 1: Hardware concurrency moet redelijk zijn
            hw_concurrency = fingerprint.get('hardwareConcurrency', 0)
            if hw_concurrency < 2 or hw_concurrency > 128:
                return False
            
            # Check 2: Platform version moet bestaan en redelijk zijn
            platform_version = fingerprint.get('platformVersion', '')
            if not platform_version or len(platform_version) < 5:
                return False
            
            # Check 3: Basis velden moeten bestaan
            if not fingerprint.get('userAgent'):
                return False
            
            # Check 4: CPU Architecture moet matchen met WebGL vendor (zoals vriend's validatie)
            platform = self.default_config.get('platform', 'windows')
            cpu_arch = fingerprint.get('cpu', {}).get('architecture', '').lower()
            webgl_vendor = fingerprint.get('webgl', {}).get('unmaskedVendor', '').lower()
            webgl_renderer = fingerprint.get('webgl', {}).get('unmaskedRenderer', '').lower()
            
            if cpu_arch == 'arm':
                # ARM Macs moeten Apple graphics hebben
                if not webgl_vendor or ('apple' not in webgl_vendor):
                    return False
            elif cpu_arch == 'x86':
                # x86 Macs moeten Intel graphics hebben
                if platform == 'macos' and webgl_vendor and 'intel' not in webgl_vendor:
                    return False
            
            # Check 5: WebGPU architecture moet matchen met CPU (als beschikbaar)
            try:
                webgpu = fingerprint.get('webgpu', '')
                if webgpu:
                    # WebGPU kan een JSON string zijn (double-escaped)
                    if isinstance(webgpu, str):
                        try:
                            webgpu_data = json.loads(webgpu)
                            if isinstance(webgpu_data, str):
                                webgpu_data = json.loads(webgpu_data)
                            
                            webgpu_vendor = webgpu_data.get('info', {}).get('vendor', '').lower() if isinstance(webgpu_data, dict) else ''
                            webgpu_arch = webgpu_data.get('info', {}).get('architecture', '').lower() if isinstance(webgpu_data, dict) else ''
                            
                            if cpu_arch == 'arm':
                                # ARM moet Apple vendor hebben met common architecture
                                if webgpu_vendor and webgpu_vendor != 'apple':
                                    return False
                                if webgpu_arch and 'common' not in webgpu_arch:
                                    return False
                            elif cpu_arch == 'x86':
                                # x86 moet Intel vendor hebben met gen architecture
                                if platform == 'macos' and webgpu_vendor and webgpu_vendor != 'intel':
                                    return False
                                if webgpu_arch and 'gen' not in webgpu_arch:
                                    return False
                        except:
                            pass  # WebGPU parsing failed, skip this check
            except:
                pass  # WebGPU check failed, continue
            
            # Als we hier komen, is de fingerprint acceptabel
            return True
            
        except Exception:
            # Bij twijfel, accepteer de fingerprint (soepelere validatie)
            return True
    
    def get_font_list(self, platform='macos', browser_type='anty', browser_version='141'):
        """Get font list from Dolphin API (via REMOTE API)
        Probeert beide endpoint varianten
        """
        try:
            # Probeer beide endpoint varianten
            endpoints_to_try = [
                f"{self.remote_api_url}/fingerprints/font-list",  # Oude variant
                f"{self.remote_api_url}/font-list"  # Nieuwe variant
            ]
            
            for url in endpoints_to_try:
                try:
                    params = {
                        'platform': platform
                    }
                    
                    response = requests.get(url, headers=self._get_headers(use_local_api=False), params=params, timeout=30)
                    
                    if response.status_code == 200:
                        data = self._handle_api_response(response, 'get_font_list')
                        return data
                except Exception:
                    continue  # Try next endpoint
            
            raise Exception("All font-list endpoints failed")
            
        except Exception as e:
            print(f"❌ Error fetching font list: {e}")
            raise
    
    def get_useragent(self, platform='macos', browser_version='141'):
        """Get random user-agent string from Dolphin API
        Probeert beide endpoint varianten
        """
        try:
            # Probeer beide endpoint varianten
            endpoints_to_try = [
                f"{self.remote_api_url}/fingerprints/useragent",  # Oude variant
                f"{self.remote_api_url}/useragent"  # Nieuwe variant
            ]
            
            for url in endpoints_to_try:
                try:
                    params = {
                        'platform': platform,
                        'browser_version': browser_version
                    }
                    
                    response = requests.get(url, headers=self._get_headers(use_local_api=False), params=params, timeout=30)
                    
                    if response.status_code == 200:
                        data = self._handle_api_response(response, 'get_useragent')
                        # API returns {'data': 'user-agent string'}
                        return data.get('data', '') if isinstance(data, dict) else data
                except Exception:
                    continue  # Try next endpoint
            
            raise Exception("All useragent endpoints failed")
            
        except Exception as e:
            print(f"❌ Error fetching useragent: {e}")
            raise
    
    def get_webgl_list(self, platform='macos', browser_version='141', with_maximum=True):
        """Get WebGL vendor/renderer combinations from Dolphin API
        Probeert beide endpoint varianten
        Returns dict: {vendor: [renderers]} of {vendor: {renderer: {webgl2Maximum: ...}}}
        """
        try:
            # Probeer beide endpoint varianten
            endpoints_to_try = [
                f"{self.remote_api_url}/fingerprints/webgl-list",  # Oude variant
                f"{self.remote_api_url}/webgl-list"  # Nieuwe variant
            ]
            
            # Probeer verschillende parameter namen (API kan verschillen)
            param_variants = [
                {'platform': platform, 'withMaximum': with_maximum, 'browser_version': browser_version},
                {'platform': platform, 'with_maximum': with_maximum, 'browser_version': browser_version},
                {'platform': platform, 'withMaximum': str(with_maximum).lower(), 'browser_version': browser_version},
                {'platform': platform, 'browser_version': browser_version},  # Zonder withMaximum parameter
            ]
            
            for url in endpoints_to_try:
                for params in param_variants:
                    try:
                        response = requests.get(url, headers=self._get_headers(use_local_api=False), params=params, timeout=30)
                        
                        if response.status_code == 200:
                            data = self._handle_api_response(response, 'get_webgl_list')
                            return data
                    except Exception:
                        continue  # Try next parameter variant
            
            # Als alle endpoints falen, return None (niet raise) zodat we kunnen doorgaan met fingerprint default
            print(f"⚠️  Alle webgl-list endpoints gefaald - gebruik fingerprint default")
            return None
            
        except Exception as e:
            print(f"❌ Error fetching webgl list: {e}")
            return None  # Return None instead of raising - we can use fingerprint default
    
    def create_profile(self, proxy_data=None, name_prefix='ADJEHOUSE'):
        """
        Maak een nieuw Dolphin profile met unieke, menselijke fingerprint
        Volgt OpenAPI best practices voor anti-bot detectie:
        - Elke fingerprint is volledig uniek
        - WebGL vendor/renderer wordt random geselecteerd uit realistische combinaties
        - User-Agent wordt random geselecteerd (consistent met fingerprint)
        - Fonts worden random geselecteerd uit platform-specifieke fonts
        - Screen resolutie wordt gevarieerd
        - Browser versie wordt gevarieerd
        """
        try:
            # Variëer browser versie per profile voor meer uniekheid
            browser_versions = ['138', '139', '140', '141', '142', '143']
            selected_browser_version = random.choice(browser_versions)
            self.default_config['browser_version'] = selected_browser_version
            
            # Get complete fingerprint from API (volgens OpenAPI workflow)
            fingerprint = self.get_fingerprint(
                platform=self.default_config['platform'],
                browser_type=self.default_config['browser_type'],
                browser_version=selected_browser_version
            )
            
            # Gebruik WebGL vendor/renderer direct uit fingerprint (zoals vriend's implementatie)
            # Dit zorgt voor consistentie tussen alle fingerprint velden
            selected_vendor = fingerprint.get('webgl', {}).get('unmaskedVendor', '')
            selected_renderer = fingerprint.get('webgl', {}).get('unmaskedRenderer', '')
            webgl2_maximum = fingerprint.get('webgl2Maximum', {})
            
            # Get random user-agent (consistent met fingerprint maar variatie)
            try:
                user_agent = self.get_useragent(
                    platform=self.default_config['platform'],
                    browser_version=selected_browser_version
                )
                if not user_agent:
                    user_agent = fingerprint.get('userAgent', '')
            except Exception as e:
                print(f"⚠️  Error getting useragent, using fingerprint default: {e}")
                user_agent = fingerprint.get('userAgent', '')
            
            # Get font list (platform-specifieke fonts voor realisme)
            font_list = self.get_font_list(
                platform=self.default_config['platform'],
                browser_type=self.default_config['browser_type'],
                browser_version=selected_browser_version
            )
            
            # Gebruik fonts uit fingerprint (zoals vriend's implementatie)
            # fingerprint.fonts is een JSON string zoals: "[\"Adobe Devanagari\", \"Agency FB\"]"
            selected_font_ids = []
            try:
                fingerprint_fonts = json.loads(fingerprint.get('fonts', '[]'))
                if isinstance(font_list, list) and len(font_list) > 0:
                    # Map fingerprint font names naar font IDs uit font_list
                    font_name_to_id = {f.get('font', ''): f.get('id') for f in font_list if isinstance(f, dict) and 'id' in f and 'font' in f}
                    for font_name in fingerprint_fonts:
                        if font_name in font_name_to_id:
                            selected_font_ids.append(font_name_to_id[font_name])
                else:
                    # Fallback: gebruik alle fonts als we geen font_list hebben
                    if isinstance(fingerprint_fonts, list):
                        selected_font_ids = fingerprint_fonts
            except Exception as e:
                print(f"⚠️  Error parsing fingerprint fonts: {e}")
                selected_font_ids = []
            
            # Get proxy
            if not proxy_data:
                proxy_data = self.get_random_unused_proxy()
                if not proxy_data:
                    raise Exception('No unused proxies available')
            
            # Generate random MAC address
            mac_address = self._generate_random_mac_address()
            
            # Generate device name
            device_name = self._generate_random_device_name()
            
            # Build profile data (volledige structuur zoals in profileCreator.ts)
            # If name_prefix already contains a hash/identifier, use it as-is, otherwise add UUID
            if '_' in name_prefix and len(name_prefix.split('_')[-1]) == 8:
                # Name already has identifier (e.g., PORTUGAL_FPF4_e355d0a8)
                profile_name = name_prefix
            else:
                # Add UUID identifier
                profile_name = f'{name_prefix}_{uuid.uuid4().hex[:8]}'
            
            profile_data = {
                'name': profile_name,
                'tags': ['automation', f'batch-{int(time.time())}'],
                'platform': self.default_config['platform'],
                # Platform version - gebruik platformVersion uit fingerprint (zoals vriend's implementatie)
                'platformVersion': fingerprint.get('platformVersion', '10.0' if self.default_config['platform'] == 'windows' else '15.6.1'),
                'browserType': self.default_config['browser_type'],
                'proxy': {
                    'id': proxy_data['id'],
                    'teamId': proxy_data.get('teamId'),
                    'userId': proxy_data.get('userId'),
                    'name': proxy_data.get('name', f"Proxy-{proxy_data['host']}-{proxy_data['port']}"),
                    'type': proxy_data.get('type', 'http'),
                    'host': proxy_data['host'],
                    'port': int(proxy_data['port']),
                    'login': proxy_data.get('login', ''),
                    'password': proxy_data.get('password', ''),
                    'changeIpUrl': proxy_data.get('changeIpUrl', ''),
                    'provider': proxy_data.get('provider', ''),
                    'ip': proxy_data.get('ip', ''),
                    'savedByUser': True,
                    'browser_profiles_count': proxy_data.get('browser_profiles_count', 0),
                    'lastCheck': proxy_data.get('lastCheck', {}),
                    'createdAt': proxy_data.get('createdAt', ''),
                    'updatedAt': proxy_data.get('updatedAt', '')
                },
                'args': [],
                'notes': [],
                'login': None,
                'password': None,
                # KRITIEK: TypeScript code gebruikt leeg object {} voor fingerprint field
                # Dit is waarschijnlijk omdat Dolphin de fingerprint data uit andere velden haalt
                'fingerprint': {},  # Leeg object (zoals TypeScript code)
                'uaFullVersion': fingerprint.get('uaFullVersion', ''),  # Gebruik fingerprint UA versie
                'folderId': None,
                'homepages': [],
                'newHomepages': [],
                'fontsMode': self.default_config['fonts_mode'],
                'fonts': selected_font_ids,
                'macAddress': {
                    'mode': 'off',
                    'value': None
                },
                'deviceName': {
                    'mode': 'off',
                    'value': None,
                    'valueNew': None
                },
                # doNotTrack moet True zijn (zoals vriend's implementatie)
                'doNotTrack': True,
                'statusId': 0,
                'isHiddenProfileName': True,
                'disableLoadWebCameraAndCookies': None,
                'enableArgIsChromeIcon': None,
                # User-agent - gebruik fingerprint userAgent (consistent met volledige fingerprint)
                'useragent': {
                    'mode': 'manual',
                    'value': fingerprint.get('userAgent', user_agent)  # Gebruik fingerprint userAgent (consistent)
                },
                # WebRTC - gebruik 'altered' mode (beter voor anti-detectie volgens voorbeeld)
                'webrtc': {
                    'mode': 'altered',  # Gebruik 'altered' zoals in het voorbeeld
                    'ipAddress': None
                },
            'canvas': {
                    'mode': 'real'  # Gebruik 'real' mode (zoals vriend's implementatie - beter voor anti-detectie)
            },
            'webgl': {
                    'mode': 'real'  # Gebruik 'real' mode (zoals vriend's implementatie - beter voor anti-detectie)
            },
                # WebGL info - gebruik fingerprint waarden direct (zoals vriend's implementatie)
                'webglInfo': {
                    'mode': 'manual',
                    'vendor': selected_vendor,
                    'renderer': selected_renderer,
                    'webgl2Maximum': webgl2_maximum
                },
                'webgpu': {
                    'mode': 'manual',  # Gebruik 'manual' mode met fingerprint waarde (zoals TypeScript code)
                    'value': fingerprint.get('webgpu', '')  # Gebruik WebGPU waarde uit fingerprint
                },
                'clientRect': {
                    'mode': self.default_config['client_rect_mode']
                },
                'timezone': {
                    'mode': self.default_config['timezone_mode'],
                    'value': None
                },
                'locale': {
                    'mode': self.default_config['locale_mode'],
                    'value': None
                },
                'geolocation': {
                    'mode': self.default_config['geolocation_mode'],
                    'latitude': None,
                    'longitude': None,
                    'accuracy': None
                },
                'cpu': {
                    'mode': self.default_config['cpu_mode'],
                    'value': fingerprint.get('hardwareConcurrency', 8)
                },
                'memory': {
                    'mode': self.default_config['memory_mode'],
                    'value': fingerprint.get('deviceMemory', 16)
                },
                # Connection metrics (variëer voor realisme)
                'connectionDownlink': fingerprint.get('connection', {}).get('downlink', random.uniform(8.0, 12.0)),
                'connectionEffectiveType': fingerprint.get('connection', {}).get('effectiveType', '4g'),
                'connectionRtt': fingerprint.get('connection', {}).get('rtt', random.randint(40, 80)),
                'connectionSaveData': 1 if fingerprint.get('connection', {}).get('saveData', False) else 0,  # 0 of 1 (niet boolean)
                # Screen resolutie (variëer voor uniekheid - consistent met fingerprint)
                # Screen resolutie - gebruik fingerprint waarden (zoals vriend's implementatie)
                # Vriend heeft screen mode uitgecommentarieerd, dus we laten het weg (Dolphin gebruikt dan default)
                'screenWidth': fingerprint.get('screen', {}).get('width', 1920),
                'screenHeight': fingerprint.get('screen', {}).get('height', 1080),
                # Alle fingerprint-afgeleide velden (consistent met volledige fingerprint)
                'platformName': fingerprint.get('platform', 'Win32' if self.default_config['platform'] == 'windows' else 'MacIntel'),
                'cpuArchitecture': fingerprint.get('cpu', {}).get('architecture', 'x64' if self.default_config['platform'] == 'windows' else 'arm'),
                'osVersion': fingerprint.get('os', {}).get('version', '10.0' if self.default_config['platform'] == 'windows' else '15.6.1'),
                'vendorSub': fingerprint.get('vendorSub', ''),
                'productSub': fingerprint.get('productSub', ''),
                'vendor': fingerprint.get('vendor', 'Google Inc.' if self.default_config['platform'] == 'windows' else 'Apple Computer, Inc.'),
                'product': fingerprint.get('product', 'Gecko'),
                'appCodeName': fingerprint.get('appCodeName', 'Mozilla'),
                'mediaDevices': {
                    'mode': self.default_config['media_devices_mode'],
                    'audioInputs': None,
                    'videoInputs': None,
                    'audioOutputs': None
                },
                'userFields': [],
                'ports': {
                    'mode': self.default_config['ports_mode'],
                    'blacklist': self.default_config['ports_blacklist']  # FIFA uses string, not array
                }
            }
            
            # Create profile via REMOTE API with retry for deadlock errors
            max_retries = 3
            retry_delay = 2  # Start with 2 seconds
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        f'{self.remote_api_url}/browser_profiles',
                        json=profile_data,
                        headers=self._get_headers(use_local_api=False),
                        timeout=60
                    )
                    
                    result = self._handle_api_response(response, 'create_profile')
                    
                    # If successful, break out of retry loop
                    break
                    
                except Exception as e:
                    error_str = str(e)
                    # Check if it's a deadlock error (500 with E_DB_TRANSACTION_FAILED)
                    if '500' in error_str and ('E_DB_TRANSACTION_FAILED' in error_str or 'Deadlock' in error_str or 'deadlock' in error_str):
                        if attempt < max_retries - 1:
                            # Exponential backoff: wait 2s, 4s, 8s
                            wait_time = retry_delay * (2 ** attempt)
                            print(f"⚠️ Database deadlock detected, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                            continue
                        else:
                            # Last attempt failed, raise the exception
                            raise
                    else:
                        # Not a deadlock error, raise immediately
                        raise
            
            # Dolphin API returns profile data directly in result['data'] or result itself
            profile_data_response = result.get('data', result)
            
            # Get profile ID from various possible locations
            profile_id = (
                profile_data_response.get('browserProfileId') or
                profile_data_response.get('id') or
                profile_data_response.get('profileId') or
                result.get('browserProfileId') or
                result.get('id')
            )
            
            if not profile_id:
                raise Exception(f"Profile creation succeeded but no ID returned: {json.dumps(result)}")
            
            print(f"✅ Profile created: {profile_data['name']} (ID: {profile_id})")
            
            # FIFA doesn't wait after creation - it just returns immediately
            # The sync check happens when trying to start
            
            return {
                'id': profile_id,
                'name': profile_data['name'],
                'proxy_id': proxy_data['id']
            }
                
        except Exception as e:
            print(f"❌ Error creating profile: {e}")
            raise
    
    def _generate_random_mac_address(self):
        """Generate random MAC address"""
        bytes_list = [random.randint(0, 255) for _ in range(6)]
        # Set locally administered (bit 1) and unicast (bit 0 cleared)
        bytes_list[0] = (bytes_list[0] | 0x02) & 0xFE
        return ':'.join(f'{b:02X}' for b in bytes_list)
    
    def _generate_random_device_name(self):
        """Generate realistic device name (platform-aware)"""
        platform = self.default_config.get('platform', 'windows')
        
        if platform == 'macos':
            prefixes = ['MacBook Pro', 'MacBook Air', 'iMac', 'Mac mini', 'Mac Pro']
            names = ['van Luke', 'van Emma', 'van Alex', 'van Sophie', 'van Max']
            prefix = random.choice(prefixes)
            name = random.choice(names)
            if random.random() < 0.5:
                return f"{prefix} — {name}"
            else:
                return f"{name} {prefix}"
        elif platform == 'windows':
            # Windows device names are usually computer names
            prefixes = ['DESKTOP-', 'LAPTOP-', 'PC-']
            suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=7))
            return random.choice(prefixes) + suffix
        else:
            # Linux
            prefixes = ['linux-', 'ubuntu-']
            suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
            return random.choice(prefixes) + suffix
    
    def get_all_proxies(self):
        """Haal alle proxies op (via REMOTE API)"""
        try:
            response = requests.get(
                f'{self.remote_api_url}/proxy',
                headers=self._get_headers(use_local_api=False),
                timeout=30
            )
            data = self._handle_api_response(response, 'get_all_proxies')
            return data.get('data', [])
        except Exception as e:
            print(f"❌ Error getting proxies: {e}")
            return []
    
    def get_unused_proxy(self):
        """Haal een ongebruikte proxy op"""
        proxies = self.get_all_proxies()
        unused = [p for p in proxies if p.get('browser_profiles_count', 0) == 0]
        return unused[0] if unused else None
    
    def get_random_unused_proxy(self):
        """Haal een random ongebruikte proxy op"""
        proxies = self.get_all_proxies()
        unused = [p for p in proxies if p.get('browser_profiles_count', 0) == 0]
        return random.choice(unused) if unused else None
    
    def create_proxy(self, proxy_data):
        """
        Create proxy in Dolphin
        Format: {'host': '...', 'port': ..., 'login': '...', 'password': '...', 'type': 'http'}
        """
        try:
            payload = {
                'type': proxy_data.get('type', 'http'),
                'host': proxy_data['host'],
                'port': proxy_data['port'],
                'login': proxy_data.get('login', ''),
                'password': proxy_data.get('password', ''),
                'name': proxy_data.get('name', f"Proxy-{proxy_data['host']}-{proxy_data['port']}"),
                'changeIpUrl': proxy_data.get('changeIpUrl', ''),
                'provider': proxy_data.get('provider', '')
            }
            
            response = requests.post(
                f'{self.remote_api_url}/proxy',
                json=payload,
                headers=self._get_headers(use_local_api=False),
                timeout=30
            )
            
            result = self._handle_api_response(response, 'create_proxy')
            
            if result.get('data', {}).get('id'):
                return result['data']
            else:
                raise Exception(f"Proxy creation failed: {json.dumps(result)}")
                
        except Exception as e:
            print(f"❌ Error creating proxy: {e}")
            raise
    
    def create_proxies_from_strings(self, proxy_strings):
        """Create proxies from strings in format 'ip:port:username:password'"""
        created_proxies = []
        
        for proxy_string in proxy_strings:
            try:
                parts = proxy_string.strip().split(':')
                if len(parts) != 4:
                    print(f"❌ Invalid proxy format: {proxy_string}")
                    continue
                
                proxy_data = {
                    'type': 'http',
                    'host': parts[0],
                    'port': int(parts[1]),
                    'login': parts[2],
                    'password': parts[3],
                    'name': f"Proxy-{parts[0]}-{parts[1]}"
                }
                
                created_proxy = self.create_proxy(proxy_data)
                created_proxies.append(created_proxy)
                
            except Exception as e:
                print(f"❌ Failed to create proxy from string {proxy_string}: {e}")
        
        return created_proxies
    
    def delete_proxy(self, proxy_id):
        """Verwijder een proxy"""
        try:
            response = requests.delete(
                f'{self.remote_api_url}/proxy/{proxy_id}',
                headers=self._get_headers(use_local_api=False),
                timeout=30
            )
            result = self._handle_api_response(response, 'delete_proxy')
            
            if result.get('success'):
                print(f"✅ Proxy {proxy_id} deleted")
                return True
            else:
                raise Exception(f"Proxy deletion failed: {json.dumps(result)}")
                
        except Exception as e:
            print(f"❌ Error deleting proxy {proxy_id}: {e}")
            return False
    
    def delete_profile(self, profile_id, password=None, force_delete=True):
        """Verwijder een profile"""
        try:
            delete_password = password or self.config.get('profile_delete_password', 'myStrongPassword')
            
            payload = {
                'password': delete_password,
                'forceDelete': force_delete
            }
            
            response = requests.delete(
                f'{self.remote_api_url}/browser_profiles/{profile_id}',
                json=payload,
                headers=self._get_headers(use_local_api=False),
                timeout=30
            )
            
            # Handle 404 gracefully - profile doesn't exist, which is fine
            if response.status_code == 404:
                try:
                    error_json = response.json()
                    error_text = error_json.get('error', {}).get('text', '')
                    if 'not found' in error_text.lower() or 'E_BROWSER_PROFILE_NOT_FOUND' in str(error_json):
                        print(f"ℹ️  Profile {profile_id} niet gevonden (waarschijnlijk al verwijderd) - OK")
                        return True
                except:
                    pass
                print(f"ℹ️  Profile {profile_id} niet gevonden (404) - OK")
                return True
            
            result = self._handle_api_response(response, 'delete_profile')
            
            if result.get('success'):
                print(f"✅ Profile {profile_id} deleted")
                return True
            else:
                raise Exception(f"Profile deletion failed: {json.dumps(result)}")
                
        except Exception as e:
            error_msg = str(e).lower()
            # If it's a 404 error in the exception message, treat as success
            if '404' in error_msg or 'not found' in error_msg:
                print(f"ℹ️  Profile {profile_id} niet gevonden (waarschijnlijk al verwijderd) - OK")
                return True
            print(f"❌ Error deleting profile {profile_id}: {e}")
            return False
    
    def get_profile(self, profile_id):
        """Get profile details by ID (via REMOTE API)"""
        try:
            response = requests.get(
                f'{self.remote_api_url}/browser_profiles/{profile_id}',
                headers=self._get_headers(use_local_api=False),
                timeout=30
            )
            result = self._handle_api_response(response, 'get_profile')
            profile_data = result.get('data', result)
            if profile_data:
                print(f"🔍 Profile {profile_id} exists: {profile_data.get('name', 'Unknown')}")
            return profile_data
        except Exception as e:
            print(f"⚠️  Error getting profile {profile_id}: {e}")
            return None
    
    def list_all_profiles(self, limit=1000, offset=0):
        """Haal alle browser profielen op via API met paginatie"""
        try:
            response = requests.get(
                f'{self.remote_api_url}/browser_profiles',
                headers=self._get_headers(use_local_api=False),
                params={
                    'limit': limit,
                    'offset': offset
                },
                timeout=30
            )
            result = self._handle_api_response(response, 'list_profiles')
            
            # Dolphin API returns profiles in result['data'] or result itself
            profiles_data = result.get('data', result)
            
            # If it's a list, return it directly
            if isinstance(profiles_data, list):
                return profiles_data
            
            # If it has a 'list' key, return that
            if isinstance(profiles_data, dict) and 'list' in profiles_data:
                return profiles_data['list']
            
            # If it has a 'data' key with a list, return that
            if isinstance(profiles_data, dict) and 'data' in profiles_data:
                if isinstance(profiles_data['data'], list):
                    return profiles_data['data']
            
            # Fallback: return empty list if structure is unexpected
            print(f"⚠️  Unexpected profile list structure: {type(profiles_data)}")
            return []
            
        except Exception as e:
            print(f"⚠️  Error listing profiles: {e}")
            return []
    
    def start_profile(self, profile_id):
        """
        Start een browser profile en krijg WebSocket URL
        Returns WebSocket URL voor Selenium connectie
        """
        # Retry logic: sometimes the local API needs time to sync with remote API after profile creation
        max_retries = 5
        retry_delay = 3.0  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                # First verify profile exists (via remote API)
                profile = self.get_profile(profile_id)
                if not profile:
                    raise Exception(f"Profile {profile_id} does not exist or cannot be accessed")
                
                # Dolphin LOCAL API uses /browser_profiles/{id}/start with GET (NO HEADERS AT ALL!)
                # Based on fifa-entry-mailserver-imap implementation
                url = f'{self.local_api_url}/browser_profiles/{profile_id}/start?automation=1'
                print(f"🔍 Starting profile via local API (attempt {attempt}/{max_retries}): {url}")
                # FIFA sends NO headers at all for local API - not even Content-Type!
                response = requests.get(url, timeout=30)
                
                print(f"🔍 Response status: {response.status_code}")
                
                # Try to parse response even on 500 errors to see what the actual error is
                try:
                    result = response.json()
                    if not response.ok:
                        print(f"⚠️  Response JSON: {json.dumps(result)[:300]}")
                except:
                    pass
                
                # CRITICAL: Handle 402 error - "On free plan you can't use automation"
                if response.status_code == 402:
                    error_json = None
                    try:
                        error_json = response.json()
                    except:
                        pass
                    
                    error_msg = "Unknown error"
                    if error_json:
                        error_msg = error_json.get('error', 'Unknown error')
                    
                    # Check if it's the free plan error
                    if 'free plan' in str(error_msg).lower() or 'automation' in str(error_msg).lower():
                        raise Exception(
                            f"❌ DOLPHIN FREE PLAN LIMITATIE: Automation is niet beschikbaar op het free plan.\n"
                            f"   Error: {error_msg}\n"
                            f"   Oplossing: Upgrade naar een betaald Dolphin Anty plan om automation te gebruiken.\n"
                            f"   Zonder automation kunnen we geen Selenium driver maken voor profile {profile_id}."
                        )
                    else:
                        raise Exception(f"Payment required (402): {error_msg}")
                
                if response.status_code == 500:
                    # 500 error often means profile not yet synced to local API or internal error
                    # OR "Profile ID already running" - in which case we should stop it first
                    error_text = response.text
                    error_json = None
                    try:
                        error_json = response.json()
                    except:
                        pass
                    
                    # Check if it's the "already running" error
                    is_already_running = False
                    if error_json:
                        error_msg = str(error_json.get('error', {}).get('text', '')).lower()
                        if 'already running' in error_msg or 'already running' in error_text.lower():
                            is_already_running = True
                    elif 'already running' in error_text.lower():
                        is_already_running = True
                    
                    if is_already_running and attempt < max_retries:
                        print(f"⚠️  Profile {profile_id} appears to be already running. Attempting to stop it first...")
                        try:
                            self.stop_profile(profile_id)
                            time.sleep(2.0)  # Wait for profile to fully stop
                        except Exception as stop_error:
                            print(f"⚠️  Could not stop profile {profile_id}: {stop_error}")
                        
                        # Retry starting after stopping
                        print(f"🔄 Retrying to start profile {profile_id} after stop (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(retry_delay)
                        retry_delay += 1.0
                        continue
                    elif attempt < max_retries:
                        print(f"⚠️  Profile start returned 500 (likely sync delay or internal error), retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay += 1.0  # Increase delay each time
                        continue
                    else:
                        raise Exception(f"Failed to start profile after {max_retries} attempts. Status: 500, Error: {error_text[:300]}")
                
                if response.status_code not in [200, 201]:
                    error_text = response.text
                    error_json = None
                    try:
                        error_json = response.json()
                        if error_json:
                            error_msg = error_json.get('error', error_text[:300])
                            raise Exception(f"Failed to start profile. Status: {response.status_code}, Error: {error_msg}")
                    except:
                        pass
                    raise Exception(f"Failed to start profile. Status: {response.status_code}, Error: {error_text[:300]}")
                
                # Check response structure - FIFA checks: result.success && result.automation
                result = response.json()
                
                # FIFA's exact check: if (result.success && result.automation)
                if not result.get('success'):
                    error_msg = result.get('error', 'Unknown error')
                    raise Exception(f"Profile start failed: success=false, error={error_msg}")
                
                # FIFA gets ws_url from result.automation directly
                ws_url = result.get('automation')
                
                if not ws_url:
                    raise Exception(f"No 'automation' field in response. Full response: {json.dumps(result)[:500]}")
                
                # If automation is a dict, it contains port and wsEndpoint
                # Format: {'port': 35394, 'wsEndpoint': '/devtools/browser/...'}
                if isinstance(ws_url, dict):
                    port = ws_url.get('port')
                    if port:
                        # Return dict with port - we'll construct debugger address in create_driver
                        print(f"✅ Profile {profile_id} started successfully (Port: {port}, wsEndpoint: {ws_url.get('wsEndpoint', 'N/A')[:30]}...)")
                        # Track profile start time
                        with self.profile_lock:
                            self.active_profiles[profile_id] = {
                                'start_time': time.time(),
                                'proxy_id': None  # Will be set when driver is created
                            }
                        return ws_url
                    else:
                        raise Exception(f"Automation dict missing 'port' field. Got: {ws_url}")
                
                # If it's a string (old format), return as-is
                if isinstance(ws_url, str):
                    print(f"✅ Profile {profile_id} started successfully (WebSocket URL: {ws_url[:50]}...)")
                    # Track profile start time
                    with self.profile_lock:
                        self.active_profiles[profile_id] = {
                            'start_time': time.time(),
                            'proxy_id': None  # Will be set when driver is created
                        }
                    return ws_url
                
                # Unknown format
                raise Exception(f"WebSocket URL has unknown format. Got: {type(ws_url)}, value: {ws_url}")
                
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠️  Error starting profile (attempt {attempt}/{max_retries}): {e}")
                    print(f"   Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay += 1.0
                    continue
                else:
                    print(f"❌ Error starting profile {profile_id} after {max_retries} attempts: {e}")
                    raise
        
        # Should never reach here, but just in case
        raise Exception(f"Failed to start profile {profile_id} after {max_retries} attempts")
    
    def _start_profile_timeout_cleanup(self):
        """Start background thread voor profile timeout cleanup (10 minuten)"""
        if self.cleanup_thread_running:
            return
        
        self.cleanup_thread_running = True
        self.cleanup_thread = threading.Thread(
            target=self._profile_timeout_cleanup_loop,
            daemon=True,
            name="ProfileTimeoutCleanup"
        )
        self.cleanup_thread.start()
        print(f"🔄 Profile timeout cleanup gestart (verwijdert profielen na {self.profile_timeout_seconds}s)")
    
    def _stop_profile_timeout_cleanup(self):
        """Stop background cleanup thread"""
        if self.cleanup_thread_running:
            self.cleanup_thread_running = False
            if self.cleanup_thread:
                self.cleanup_thread.join(timeout=5)
            print("🛑 Profile timeout cleanup gestopt")
    
    def _profile_timeout_cleanup_loop(self):
        """Background loop die oude profielen verwijdert"""
        while self.cleanup_thread_running:
            try:
                current_time = time.time()
                profiles_to_cleanup = []
                
                # Check alle actieve profielen
                with self.profile_lock:
                    for profile_id, profile_info in list(self.active_profiles.items()):
                        start_time = profile_info.get('start_time', 0)
                        age_seconds = current_time - start_time
                        
                        if age_seconds >= self.profile_timeout_seconds:
                            profiles_to_cleanup.append((profile_id, profile_info))
                
                # Cleanup oude profielen
                for profile_id, profile_info in profiles_to_cleanup:
                    try:
                        start_time = profile_info.get('start_time', 0)
                        age_seconds = current_time - start_time
                        print(f"⏰ Profile {profile_id} is {int(age_seconds)}s oud (> {self.profile_timeout_seconds}s) - automatisch verwijderen...")
                        
                        # Stop profile
                        try:
                            self.stop_profile(profile_id)
                        except:
                            pass
                        
                        # Delete profile
                        try:
                            self.delete_profile(profile_id)
                            print(f"✅ Profile {profile_id} automatisch verwijderd (timeout)")
                        except:
                            pass
                        
                        # Delete proxy if exists
                        proxy_id = profile_info.get('proxy_id')
                        if proxy_id:
                            try:
                                self.delete_proxy(proxy_id)
                                print(f"✅ Proxy {proxy_id} automatisch verwijderd (timeout)")
                            except:
                                pass
                        
                        # Remove from tracking
                        with self.profile_lock:
                            if profile_id in self.active_profiles:
                                del self.active_profiles[profile_id]
                                
                    except Exception as e:
                        print(f"⚠️ Error tijdens timeout cleanup van profile {profile_id}: {e}")
                
            except Exception as e:
                # Silent fail in background thread
                pass
            
            # Check elke minuut
            time.sleep(60)
    
    def stop_profile(self, profile_id):
        """Stop een browser profile (via LOCAL API) - uses GET method with NO headers"""
        try:
            # FIFA sends NO headers at all for local API
            response = requests.get(
                f'{self.local_api_url}/browser_profiles/{profile_id}/stop',
                timeout=30
            )
            
            self._handle_api_response(response, 'stop_profile')
            print(f"✅ Profile {profile_id} stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping profile {profile_id}: {e}")
            return False
    
    def _wait_for_chrome_ready(self, debugger_address, max_wait=10):
        """
        Wacht tot Chrome klaar is om verbindingen te accepteren op de debugger poort
        Controleert of de poort bereikbaar is voordat we proberen te verbinden
        """
        import socket
        host, port = debugger_address.split(':')
        port = int(port)
        
        for attempt in range(max_wait):
            try:
                # Probeer een socket verbinding te maken naar de poort
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    # Poort is open en bereikbaar
                    return True
            except Exception:
                pass
            
            # Wacht een seconde en probeer opnieuw
            time.sleep(1)
        
        return False
    
    def _check_local_api_available(self):
        """Controleer of Dolphin Anty local API bereikbaar is"""
        try:
            response = requests.get(f'{self.local_api_url}/browser_profiles', timeout=5)
            return response.status_code in [200, 401, 403]  # 401/403 betekent API is bereikbaar maar auth nodig
        except:
            return False
    
    def create_driver(self, profile_id):
        """
        Maak Selenium driver voor profile
        Gebaseerd op browserHelper.ts - gebruikt WebSocket connectie
        """
        try:
            # Controleer eerst of local API bereikbaar is
            if not self._check_local_api_available():
                raise Exception(
                    f"Dolphin Anty local API is niet bereikbaar op {self.local_api_url}.\n"
                    f"Zorg ervoor dat:\n"
                    f"1. Dolphin Anty applicatie is gestart\n"
                    f"2. Local API is ingeschakeld in Dolphin Anty instellingen\n"
                    f"3. Firewall/antivirus blokkeert localhost verbindingen niet"
                )
            
            # Start profile en krijg automation info
            automation_info = self.start_profile(profile_id)
            
            # Handle different response formats
            if isinstance(automation_info, dict):
                # New format: {'port': 35394, 'wsEndpoint': '/devtools/browser/...'}
                port = automation_info.get('port')
                if port:
                    debugger_address = f"127.0.0.1:{port}"
                else:
                    raise Exception(f"Automation dict missing 'port': {automation_info}")
            elif isinstance(automation_info, str):
                # Old format: ws://127.0.0.1:port/puppeteer -> 127.0.0.1:port
                debugger_address = automation_info.replace('ws://', '').replace('/puppeteer', '')
            else:
                raise Exception(f"Unknown automation format: {type(automation_info)}, value: {automation_info}")
            
            # Wacht tot Chrome klaar is om verbindingen te accepteren
            print(f"⏳ Wachten tot Chrome klaar is op {debugger_address}...")
            if not self._wait_for_chrome_ready(debugger_address, max_wait=10):
                raise Exception(
                    f"Chrome is niet bereikbaar op {debugger_address} na 10 seconden.\n"
                    f"Mogelijke oorzaken:\n"
                    f"1. Firewall/antivirus blokkeert localhost verbindingen\n"
                    f"2. Chrome is nog niet volledig gestart\n"
                    f"3. Poort {port} wordt geblokkeerd door Windows Firewall\n"
                    f"Oplossing: Controleer Windows Firewall instellingen en voeg localhost toe aan uitzonderingen"
                )
            
            print(f"✅ Chrome is klaar op {debugger_address}")
            
            # Configure Chrome options - MAXIMUM stealth voor Cloudflare bypass
            options = Options()
            options.add_experimental_option("debuggerAddress", debugger_address)
            
            # Critical: Remove automation indicators
            # NOTE: excludeSwitches werkt NIET met debuggerAddress - Chrome is al gestart door Dolphin
            # We gebruiken alleen argumenten die werken met een bestaande Chrome instance
            options.add_argument("--disable-blink-features=AutomationControlled")
            # excludeSwitches verwijderd - werkt niet met debuggerAddress
            # useAutomationExtension ook verwijderd - niet nodig met debuggerAddress
            
            # Additional stealth options (alleen die werken met debuggerAddress)
            options.add_argument("--disable-dev-shm-usage")
            # --no-sandbox en --disable-setuid-sandbox verwijderd - Chrome is al gestart
            # --disable-web-security verwijderd - kan conflicteren
            # --disable-features verwijderd - kan conflicteren
            
            # Realistic browser behavior
            options.add_argument("--lang=pt-PT")
            options.add_argument("--accept-lang=pt-PT,pt,en-US,en")
            
            # Since we're using debuggerAddress, ChromeDriver mainly needs to communicate via CDP
            # When using debuggerAddress, ChromeDriver doesn't need to match Chrome version exactly
            # Selenium Manager should automatically download to the correct user folder
            # But in PyInstaller EXE, we need to ensure USERPROFILE is correctly set
            import os
            # Ensure USERPROFILE is set correctly (important for PyInstaller EXE)
            if 'USERPROFILE' not in os.environ or not os.environ.get('USERPROFILE'):
                # Fallback: try to detect user profile from common locations
                username = os.environ.get('USERNAME', os.environ.get('USER', 'Administrator'))
                if sys.platform == 'win32':
                    potential_profile = f"C:\\Users\\{username}"
                    if os.path.exists(potential_profile):
                        os.environ['USERPROFILE'] = potential_profile
            
            driver = None
            max_connection_retries = 3
            retry_delay = 2.0
            
            for connection_attempt in range(1, max_connection_retries + 1):
                try:
                    # Method 1: Let Selenium Manager automatically download/manage ChromeDriver
                    # Selenium 4.6+ has built-in Selenium Manager that handles driver downloads
                    # It will automatically download to the correct user's cache folder
                    driver = webdriver.Chrome(options=options)
                    break  # Success, exit retry loop
                except Exception as e:
                    error_str = str(e).lower()
                    error_msg = str(e)
                    
                    # Check if it's a connection issue (cannot connect to chrome)
                    is_connection_error = (
                        "cannot connect to chrome" in error_str or
                        "connection refused" in error_str or
                        "connection reset" in error_str or
                        "session not created" in error_str
                    )
                    
                    if is_connection_error and connection_attempt < max_connection_retries:
                        print(f"⚠️  Verbindingsfout met Chrome op {debugger_address} (poging {connection_attempt}/{max_connection_retries})...")
                        print(f"    Wachten {retry_delay}s en opnieuw proberen...")
                        time.sleep(retry_delay)
                        retry_delay += 1.0
                        continue
                    
                    # Check if it's a driver path/version issue
                    if "driver" in error_str or "chromedriver" in error_str or "path" in error_str or "version" in error_str:
                        print(f"⚠️  ChromeDriver issue detected: {error_msg[:100]}...")
                        print(f"    Attempting with additional options (debuggerAddress should bypass version check)...")
                        # Method 2: Try with additional options to bypass version check
                        try:
                            options.add_argument("--disable-dev-shm-usage")
                            options.add_argument("--no-sandbox")
                            options.add_argument("--disable-gpu")
                            # Note: excludeSwitches removed - not supported by all Chrome versions
                            # When using debuggerAddress, we can use any ChromeDriver version
                            # Selenium Manager should handle this automatically
                            driver = webdriver.Chrome(options=options)
                            break  # Success
                        except Exception as e2:
                            # Method 3: Try with Service() - let Selenium Manager auto-detect
                            try:
                                # Selenium Manager (built into Selenium 4.6+) will auto-download
                                # Don't specify executable_path - let Selenium find/download it automatically
                                service = Service()
                                driver = webdriver.Chrome(service=service, options=options)
                                break  # Success
                            except Exception as e3:
                                # Method 4: Try using ChromeDriverManager if available (fallback)
                                # Note: webdriver-manager is an optional dependency
                                try:
                                    from selenium.webdriver.chrome.service import Service as ChromeService
                                    from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
                                    service = ChromeService(ChromeDriverManager().install())
                                    driver = webdriver.Chrome(service=service, options=options)
                                    break  # Success
                                except ImportError:
                                    # webdriver-manager not installed, skip this method
                                    pass
                                except Exception as e4:
                                    # Final attempt failed
                                    if connection_attempt >= max_connection_retries:
                                        # Provide detailed troubleshooting info
                                        troubleshooting = (
                                            f"\n❌ Kan niet verbinden met Chrome op {debugger_address}\n"
                                            f"Error: {error_msg[:300]}\n\n"
                                            f"🔧 Troubleshooting stappen:\n"
                                            f"1. Controleer of Dolphin Anty applicatie is gestart\n"
                                            f"2. Controleer Windows Firewall instellingen:\n"
                                            f"   - Open Windows Defender Firewall\n"
                                            f"   - Ga naar 'Geavanceerde instellingen'\n"
                                            f"   - Controleer of 'Inkomende regels' localhost (127.0.0.1) toestaan\n"
                                            f"3. Controleer antivirus software:\n"
                                            f"   - Voeg Dolphin Anty toe aan uitzonderingen\n"
                                            f"   - Voeg localhost/127.0.0.1 toe aan uitzonderingen\n"
                                            f"4. Herstart Dolphin Anty applicatie\n"
                                            f"5. Controleer of poort {port} niet wordt gebruikt door andere applicaties\n"
                                        )
                                        raise Exception(troubleshooting)
                                    continue
                    else:
                        # Not a driver-related error, re-raise if last attempt
                        if connection_attempt >= max_connection_retries:
                            raise Exception(
                                f"Failed to create Chrome driver after {max_connection_retries} attempts.\n"
                                f"Error: {error_msg[:300]}\n"
                                f"Debugger address: {debugger_address}"
                            )
                        continue
            
            if not driver:
                raise Exception(
                    f"Failed to create Chrome driver after {max_connection_retries} attempts.\n"
                    f"Debugger address: {debugger_address}\n"
                    f"Zorg ervoor dat Dolphin Anty is gestart en localhost verbindingen zijn toegestaan."
                )
            
            driver.implicitly_wait(10)
            
            # Set browser window size to full screen (fix voor pagina in hoekje)
            try:
                driver.set_window_size(1920, 1080)
                driver.maximize_window()  # Maximize window voor volledig scherm
            except:
                pass  # Als dit faalt, doorgaan zonder error
            
            # Apply stealth features to bypass Cloudflare bot detection
            self._apply_stealth_features(driver)
            
            return driver
            
        except Exception as e:
            print(f"❌ Error creating driver: {e}")
            # Stop profile als driver creation faalt om lege browsers te voorkomen
            try:
                print(f"🧹 Stoppen van profile {profile_id} omdat driver creation faalde...")
                self.stop_profile(profile_id)
            except Exception as stop_error:
                print(f"⚠️  Kon profile niet stoppen: {stop_error}")
            raise
    
    def _apply_stealth_features(self, driver):
        """
        Apply MAXIMUM stealth features to bypass Cloudflare bot detection
        Volgens artikel: https://www.zenrows.com/blog/cloudflare-bypass
        
        Implements:
        - Complete webdriver removal (navigator.webdriver = false)
        - All automation detection properties removed
        - Canvas fingerprinting (consistent met Dolphin fingerprint)
        - WebGL fingerprinting (consistent met Dolphin fingerprint)
        - Timestamp tracking (realistic navigationStart)
        - Event tracking simulation
        - Browser-specific API spoofing
        - Sandboxing detection bypass
        """
        try:
            # COMPLETE stealth JavaScript - alle Cloudflare detecties
            stealth_script = """
            (function() {
                'use strict';
                
                // ===== 1. REMOVE ALL WEBDRIVER TRACES =====
            Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
            });
            
                // Remove Selenium/PhantomJS indicators
                delete window.__selenium_unwrapped;
                delete window.__webdriver_evaluate;
                delete window.__driver_evaluate;
                delete window.__selenium_evaluate;
                delete window.__fxdriver_evaluate;
                delete window.__driver_unwrapped;
                delete window.__webdriver_unwrapped;
                delete window.callPhantom;
                delete window._phantom;
                delete window.__nightmare;
                delete window.domAutomation;
                delete window.domAutomationController;
            
                // Remove Chrome DevTools Protocol indicators
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Object;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Proxy;
                
                // ===== 2. SPOOF CHROME RUNTIME =====
                if (!window.chrome) {
                    window.chrome = {};
                }
                if (!window.chrome.runtime) {
                    window.chrome.runtime = {};
                }
                
                // ===== 3. PERMISSIONS API SPOOFING =====
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
                // ===== 4. PLUGINS SPOOFING =====
            Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [];
                        for (let i = 0; i < 5; i++) {
                            plugins.push({
                                0: { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                                description: 'Portable Document Format',
                                filename: 'internal-pdf-viewer',
                                length: 1,
                                name: 'Chrome PDF Plugin'
                            });
                        }
                        return plugins;
                    },
                    configurable: true
            });
            
                // ===== 5. LANGUAGES SPOOFING =====
            Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-PT', 'pt', 'en-US', 'en'],
                    configurable: true
            });
            
                // ===== 6. CANVAS FINGERPRINTING (consistent met Dolphin) =====
                // Canvas moet consistent zijn met Dolphin fingerprint, niet random
                // Dolphin gebruikt 'real' mode, dus we laten canvas normaal werken
                // Maar we voegen minimale noise toe om uniekheid te behouden
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
                
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                    const context = this.getContext('2d');
                    if (context && (type === 'image/png' || !type)) {
                        try {
                            const imageData = context.getImageData(0, 0, Math.min(this.width, 100), Math.min(this.height, 100));
                            // Add minimal consistent noise (based on canvas size for consistency)
                            const noiseSeed = this.width * 1000 + this.height;
                        for (let i = 0; i < imageData.data.length; i += 4) {
                                const noise = (noiseSeed + i) % 3;
                                imageData.data[i] = Math.min(255, imageData.data[i] + noise);
                        }
                        context.putImageData(imageData, 0, 0);
                        } catch(e) {
                            // Canvas may be tainted, continue normally
                    }
                }
                return originalToDataURL.apply(this, arguments);
            };
            
                // ===== 7. WEBGL FINGERPRINTING (consistent met Dolphin fingerprint) =====
                // WebGL moet consistent zijn met Dolphin fingerprint
                // Dolphin gebruikt 'real' mode, dus we laten WebGL normaal werken
                // Maar we kunnen vendor/renderer overschrijven als nodig
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // UNMASKED_VENDOR_WEBGL = 37445
                    // UNMASKED_RENDERER_WEBGL = 37446
                    // Laat Dolphin fingerprint bepalen wat deze waarden zijn
                    // We overschrijven alleen als er een conflict is
                return getParameter.apply(this, arguments);
            };
            
                // ===== 8. CONNECTION API SPOOFING =====
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                        saveData: false,
                        onchange: null,
                        addEventListener: function() {},
                        removeEventListener: function() {},
                        dispatchEvent: function() { return true; }
                    }),
                    configurable: true
            });
            
                // ===== 9. TIMESTAMP TRACKING (realistic navigationStart) =====
                // Cloudflare checkt window.performance.timing.navigationStart
                // Zorg dat dit realistisch is (niet te snel, niet te langzaam)
                if (window.performance && window.performance.timing) {
                    const navStart = window.performance.timing.navigationStart;
                    if (!navStart || navStart === 0) {
                        // Set realistic navigationStart (current time minus page load time)
                        Object.defineProperty(window.performance.timing, 'navigationStart', {
                            get: () => Date.now() - 1000, // 1 second ago
                            configurable: true
                        });
                    }
                }
                
                // ===== 10. SANDBOXING DETECTION BYPASS =====
                // Cloudflare checkt op Node.js process object
                // Zorg dat dit undefined is
                if (typeof globalThis !== 'undefined') {
                    Object.defineProperty(globalThis, 'process', {
                        get: () => undefined,
                        configurable: true
                    });
                }
                
                // ===== 11. FUNCTION PROTOTYPE TOSTRING CHECK =====
                // Cloudflare checkt of native functions zijn aangepast
                // Zorg dat toString() nog steeds "[native code]" retourneert
                const originalToString = Function.prototype.toString;
                Function.prototype.toString = function() {
                    if (this === navigator.webdriver || 
                        this === window.chrome ||
                        this === navigator.plugins) {
                        return originalToString.apply(this, arguments);
                    }
                    return originalToString.apply(this, arguments);
                };
                
                // ===== 12. EVENT TRACKING SIMULATION =====
                // Cloudflare trackt mouse movements, clicks, etc.
                // Simuleer minimale events om niet verdacht te zijn
                let eventCount = 0;
                const simulateEvent = () => {
                    if (eventCount < 3) {
                        // Simuleer minimale mouse movement
                        const event = new MouseEvent('mousemove', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            clientX: Math.random() * 100,
                            clientY: Math.random() * 100
                        });
                        document.dispatchEvent(event);
                        eventCount++;
                    }
                };
                
                // Simuleer events na page load
                if (document.readyState === 'complete') {
                    setTimeout(simulateEvent, 100);
                } else {
                    window.addEventListener('load', () => {
                        setTimeout(simulateEvent, 100);
                    });
                }
            
            return true;
            })();
            """
            
            # Inject complete stealth script
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_script
            })
            
            # ===== 13. CDP EMULATION (consistent met Dolphin fingerprint) =====
            # Get fingerprint from profile (if available) for consistent emulation
            # For now, use realistic defaults
            
            # Set realistic viewport (consistent met screen resolution uit fingerprint)
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
                'width': 1920,
                'height': 1080,
                'deviceScaleFactor': 1,
                'mobile': False
            })
            
            # Set realistic timezone (Portugal timezone)
            driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {
                'timezoneId': 'Europe/Lisbon'
            })
            
            # Set realistic locale
            driver.execute_cdp_cmd('Emulation.setLocaleOverride', {
                'locale': 'pt-PT'
            })
            
            # ===== 14. ADDITIONAL CDP COMMANDS =====
            # Override navigator.webdriver via CDP (extra layer)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                '''
            })
            
            # ===== 15. HEADERS (via CDP Network domain) =====
            # Set realistic headers (Dolphin doet dit al, maar we zorgen voor consistentie)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': driver.execute_script('return navigator.userAgent;')
            })
            
            # Enable Network domain for header manipulation
            driver.execute_cdp_cmd('Network.enable', {})
            
            # ===== 15. INITIALIZE NATURAL EVENTS HELPER =====
            # Store helper instance in driver for later use
            if HAS_NATURAL_EVENTS and NaturalEventsHelper:
                try:
                    driver._natural_events = NaturalEventsHelper(driver)
                except Exception as helper_error:
                    print(f"      ⚠️ Kon NaturalEventsHelper niet initialiseren: {helper_error}")
            
            print("      ✅ MAXIMUM stealth features toegepast (alle Cloudflare detecties gebypassed)")
            
        except Exception as e:
            print(f"      ⚠️ Fout bij toepassen stealth features: {e}")
            # Continue anyway - stealth is nice to have but not critical

    
    # Human-like behavior methods (gebaseerd op humanInteractions.ts)
    
    def human_mouse_move(self, driver, from_pos, to_pos):
        """
        Human-like mouse movement met Bezier curves
        Gebaseerd op ghost-cursor algoritme uit humanInteractions.ts
        """
        try:
            actions = ActionChains(driver)
            
            # Generate Bezier curve control points
            steps = random.randint(20, 40)
            
            # Control points voor natuurlijke beweging
            cp1_x = from_pos[0] + (to_pos[0] - from_pos[0]) * 0.3 + random.uniform(-50, 50)
            cp1_y = from_pos[1] + (to_pos[1] - from_pos[1]) * 0.3 + random.uniform(-50, 50)
            cp2_x = from_pos[0] + (to_pos[0] - from_pos[0]) * 0.7 + random.uniform(-50, 50)
            cp2_y = from_pos[1] + (to_pos[1] - from_pos[1]) * 0.7 + random.uniform(-50, 50)
            
            # Bezier curve path
            for i in range(steps + 1):
                t = i / steps
                
                # Cubic Bezier formula
                x = ((1-t)**3 * from_pos[0] + 
                     3 * (1-t)**2 * t * cp1_x + 
                     3 * (1-t) * t**2 * cp2_x + 
                     t**3 * to_pos[0])
                y = ((1-t)**3 * from_pos[1] + 
                     3 * (1-t)**2 * t * cp1_y + 
                     3 * (1-t) * t**2 * cp2_y + 
                     t**3 * to_pos[1])
                
                # Variable speed - slower at start and end
                speed = int(30 * abs(0.5 - t) + 10)  # Faster in middle
                
                actions.move_by_offset(
                    int(x - from_pos[0]) if i == 0 else int(x - prev_x),
                    int(y - from_pos[1]) if i == 0 else int(y - prev_y)
                )
                actions.pause(speed / 1000.0)
                
                prev_x, prev_y = x, y
            
            actions.perform()
            
        except Exception as e:
            # Fallback naar simpele beweging
            try:
                actions = ActionChains(driver)
                actions.move_by_offset(to_pos[0] - from_pos[0], to_pos[1] - from_pos[1])
                actions.perform()
            except:
                pass
    
    def human_click(self, driver, element):
        """
        Human-like click met realistic mouse movement en delays
        Gebaseerd op humanInteractions.ts humanClick functie
        Met viewport bounds checking om "move target out of bounds" errors te voorkomen
        Nu met NaturalEventsHelper integratie voor Cloudflare/Akamai bypass
        """
        try:
            # Get NaturalEventsHelper if available
            natural_events = None
            if hasattr(driver, '_natural_events'):
                natural_events = driver._natural_events
            
            # Scroll element into view
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", element)
            time.sleep(random.uniform(0.2, 0.5))
            
            # Get viewport size to check bounds
            try:
                viewport_width = driver.execute_script("return window.innerWidth") or 1920
                viewport_height = driver.execute_script("return window.innerHeight") or 1080
            except:
                viewport_width = 1920
                viewport_height = 1080
            
            # Get element position
            location = element.location
            size = element.size
            
            # Calculate click position (niet exact center, maar inner random band)
            click_x = location['x'] + size['width'] * (0.25 + random.random() * 0.5)
            click_y = location['y'] + size['height'] * (0.25 + random.random() * 0.5)
            
            # Ensure click coordinates are within viewport bounds
            click_x = max(10, min(click_x, viewport_width - 10))
            click_y = max(10, min(click_y, viewport_height - 10))
            
            # CRITICAL: Inject pointer events (10% chance) - Akamai tracks this
            if natural_events and random.random() < 0.1:
                natural_events.inject_pointer_events(int(click_x), int(click_y), 'move')
            
            # Get current mouse position (of start from reasonable position within viewport)
            current_pos = [
                max(10, min(100 + random.randint(-50, 50), viewport_width - 10)),
                max(10, min(100 + random.randint(-50, 50), viewport_height - 10))
            ]
            
            # Ensure target position is also within bounds
            target_pos = [
                max(10, min(click_x, viewport_width - 10)),
                max(10, min(click_y, viewport_height - 10))
            ]
            
            # Try to move mouse realistically to element (only if coordinates are reasonable)
            try:
                if abs(target_pos[0] - current_pos[0]) < viewport_width and abs(target_pos[1] - current_pos[1]) < viewport_height:
                    self.human_mouse_move(driver, current_pos, target_pos)
                else:
                    # Coordinates too far apart, use simpler approach
                    actions = ActionChains(driver)
                    actions.move_to_element(element)
                    actions.perform()
            except Exception as e:
                # If mouse movement fails, just move to element directly
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element(element)
                    actions.perform()
                except:
                    pass
            
            # Hover for a moment
            hover_delay = random.uniform(0.12, 0.42)
            # Use smart delay if NaturalEventsHelper available
            if natural_events:
                hover_delay = natural_events.get_smart_delay(300, 'hover') / 1000.0
            time.sleep(hover_delay)
            
            # CRITICAL: Inject pointer events before click (10% chance)
            if natural_events and random.random() < 0.1:
                natural_events.inject_pointer_events(int(click_x), int(click_y), 'down')
            
            # Try to click using ActionChains (move_to_element is safer than move_by_offset)
            try:
                actions = ActionChains(driver)
                actions.move_to_element(element)
                actions.pause(random.uniform(0.05, 0.15))
                actions.click()
                actions.perform()
            except Exception as e:
                # If ActionChains fails, try JavaScript click
                try:
                    driver.execute_script("arguments[0].click();", element)
                except:
                    # Last resort: simple click
                    element.click()
            
            # CRITICAL: Inject pointer events after click (10% chance)
            if natural_events and random.random() < 0.1:
                natural_events.inject_pointer_events(int(click_x), int(click_y), 'up')
            
            # Wait after click - use smart delay if available
            click_delay = random.uniform(0.3, 0.8)
            if natural_events:
                click_delay = natural_events.get_smart_delay(500, 'click') / 1000.0
            time.sleep(click_delay)
            
        except Exception as e:
            print(f"⚠️ Error in human click: {e}")
            # Fallback to JavaScript click (most reliable)
            try:
                driver.execute_script("arguments[0].click();", element)
            except:
                # Last fallback: simple click
                try:
                    element.click()
                except:
                    pass
    
    def human_type(self, element, text, driver=None):
        """
        Human-like typing met realistic delays en burst typing
        Gebaseerd op humanInteractions.ts robustFill functie
        Nu met NaturalEventsHelper integratie voor Cloudflare/Akamai bypass
        """
        try:
            # Get NaturalEventsHelper if available
            natural_events = None
            if driver and hasattr(driver, '_natural_events'):
                natural_events = driver._natural_events
            
            # CRITICAL: Inject focus events BEFORE typing (Akamai tracks this)
            if natural_events:
                natural_events.inject_focus_events(element)
                time.sleep(random.uniform(0.05, 0.1))
            
            element.clear()
            
            # Click field eerst
            time.sleep(random.uniform(0.14, 0.28))
            
            # Select all en delete
            element.send_keys('\b' * 50)  # Backspace spam
            time.sleep(random.uniform(0.12, 0.26))
            
            # Type character by character
            is_word_boundary = lambda c: c in ' -_/.,'
            is_special = lambda c: c in '!@#$%^&*()+={}[]|\\;:\'",<>?'
            
            burst_counter = 0
            for i, char in enumerate(text):
                prev_char = text[i-1] if i > 0 else ''
                next_char = text[i+1] if i < len(text) - 1 else ''
                
                # CRITICAL: Inject beforeinput event BEFORE typing (Cloudflare detects input without beforeinput)
                if natural_events:
                    natural_events.inject_before_input_event(element, char)
                
                # Base delay
                min_delay = 45
                max_delay = 120
                
                if char.isupper():
                    min_delay, max_delay = 110, 260
                elif char.isdigit():
                    min_delay, max_delay = 90, 220
                elif is_special(char):
                    min_delay, max_delay = 140, 320
                
                if is_word_boundary(prev_char) or is_word_boundary(char):
                    min_delay += 40
                    max_delay += 80
                
                # Burst typing in middle of words
                if not is_word_boundary(char) and not is_word_boundary(prev_char) and random.random() < 0.15 and burst_counter < 6:
                    min_delay, max_delay = 25, 65
                    burst_counter += 1
                elif is_word_boundary(char):
                    burst_counter = 0
                
                # Occasional hesitation before special chars
                if (is_special(char) or is_word_boundary(char)) and random.random() < 0.25:
                    time.sleep(random.uniform(0.12, 0.24))
                
                # Type character
                element.send_keys(char)
                
                # CRITICAL: Inject input event AFTER typing
                if natural_events:
                    natural_events.inject_input_event(element)
                
                time.sleep(random.uniform(min_delay / 1000.0, max_delay / 1000.0))
                
                # Occasional micro-pause mid-word
                if not is_word_boundary(char) and random.random() < 0.08:
                    time.sleep(random.uniform(0.08, 0.18))
                
                # Typo correction (rare)
                if (is_special(char) or (not is_word_boundary(char) and not is_word_boundary(prev_char) and not is_word_boundary(next_char))) and random.random() < 0.035 and i > 2:
                    element.send_keys('\b')
                    time.sleep(random.uniform(0.06, 0.12))
                    element.send_keys(char)
                    if natural_events:
                        natural_events.inject_input_event(element)
                    time.sleep(random.uniform(min_delay / 1000.0, max_delay / 1000.0))
            
            # CRITICAL: Dispatch realistic field events (randomizes event sequence)
            if natural_events:
                natural_events.dispatch_field_events_realistically(element)
            else:
                # Fallback: Trigger events manually
                element.send_keys('\t')  # Tab to trigger blur
                time.sleep(random.uniform(0.2, 0.42))
            
        except Exception as e:
            print(f"⚠️ Error in human type: {e}")
            # Fallback
            try:
                element.clear()
                element.send_keys(text)
            except:
                pass
    
    def human_scroll(self, driver, scroll_count=3):
        """Human-like scrolling behavior"""
        for _ in range(scroll_count):
            scroll_amount = random.randint(200, 800)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 2.0))
            
            # Sometimes scroll back up
            if random.random() < 0.3:
                back_scroll = random.randint(50, 200)
                driver.execute_script(f"window.scrollBy(0, -{back_scroll});")
                time.sleep(random.uniform(0.3, 1.0))
    
    def random_mouse_movement(self, driver):
        """Random mouse movements to simulate human behavior"""
        try:
            actions = ActionChains(driver)
            
            for _ in range(random.randint(2, 5)):
                x_offset = random.randint(-100, 100)
                y_offset = random.randint(-100, 100)
                actions.move_by_offset(x_offset, y_offset)
                actions.pause(random.uniform(0.1, 0.5))
            
            actions.perform()
        except:
            pass
    
    def simulate_akamai_behavior(self, driver, duration=5):
        """
        Simulate Akamai-friendly human behavior on page load
        Gebaseerd op humanInteractions.ts simulateAkamaiHumanBehavior
        """
        try:
            start_time = time.time()
            max_duration = min(duration, 8)  # Max 8 seconds
            
            # Get viewport size
            viewport_width = driver.execute_script("return window.innerWidth") or 1920
            viewport_height = driver.execute_script("return window.innerHeight") or 1080
            
            # Set initial cursor position
            start_x = random.uniform(viewport_width * 0.2, viewport_width * 0.8)
            start_y = random.uniform(viewport_height * 0.2, viewport_height * 0.8)
            
            actions = ActionChains(driver)
            actions.move_by_offset(int(start_x - viewport_width/2), int(start_y - viewport_height/2))
            actions.perform()
            
            time.sleep(random.uniform(0.3, 0.5))
            
            # Perform random actions
            for _ in range(5):
                if time.time() - start_time > max_duration:
                    break
                
                time.sleep(random.uniform(0.4, 0.3))
                
                action_type = random.random()
                
                if action_type < 0.5:
                    # Mouse movement
                    target_x = random.uniform(viewport_width * 0.05, viewport_width * 0.95)
                    target_y = random.uniform(viewport_height * 0.05, viewport_height * 0.95)
                    
                    # Simple move (Bezier zou beter zijn maar complexer)
                    actions = ActionChains(driver)
                    actions.move_by_offset(int(target_x - start_x), int(target_y - start_y))
                    actions.perform()
                    
                    # Jitter
                    jitter_x = target_x + random.uniform(-10, 10)
                    jitter_y = target_y + random.uniform(-10, 10)
                    actions = ActionChains(driver)
                    actions.move_by_offset(int(jitter_x - target_x), int(jitter_y - target_y))
                    actions.perform()
                    
                    start_x, start_y = jitter_x, jitter_y
                    
                elif action_type < 0.70:
                    # Safe click (away from center)
                    center_x = viewport_width / 2
                    click_x = random.choice([
                        random.uniform(50, max(50, center_x - 400)),
                        random.uniform(center_x + 400, max(center_x + 450, viewport_width - 50))
                    ])
                    click_y = random.uniform(150, max(200, viewport_height - 450))
                    
                    actions = ActionChains(driver)
                    actions.move_by_offset(int(click_x - start_x), int(click_y - start_y))
                    actions.pause(random.uniform(0.08, 0.15))
                    actions.click()
                    actions.perform()
                    
                elif action_type < 0.85:
                    # Small scroll
                    scroll_amount = random.randint(-100, 100)
                    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                    time.sleep(random.uniform(0.15, 0.2))
                    
                else:
                    # Jitter movements
                    for _ in range(random.randint(2, 5)):
                        if time.time() - start_time > max_duration:
                            break
                        jitter_x = start_x + random.uniform(-15, 15)
                        jitter_y = start_y + random.uniform(-15, 15)
                        actions = ActionChains(driver)
                        actions.move_by_offset(int(jitter_x - start_x), int(jitter_y - start_y))
                        actions.perform()
                        time.sleep(random.uniform(0.06, 0.1))
                        start_x, start_y = jitter_x, jitter_y
            
        except Exception as e:
            # Silent fail
            pass
    
    # Main automation methods
    
    def run_automation(self, site_config, data_list, threads=5, ignore_stop_event=False):
        """
        Run automation met multiple threads
        data_list: list van data items (bijv. emails, accounts, etc.)
        ignore_stop_event: If True, ignore stop_event (for background signups)
        """
        # Store ignore_stop_event flag so _process_single_item can access it
        self._ignore_stop_event = ignore_stop_event
        
        # Safety: limit threads to max 20 to prevent too many browsers
        threads = max(1, min(int(threads), 20))
        print(f"🚀 Starting automation for {len(data_list)} items with {threads} threads (limited to max 20)")
        
        # Create semaphore to strictly limit concurrent browsers
        self.browser_semaphore = threading.Semaphore(threads)
        
        # Load proxies (skip if already set to empty list for lazy loading)
        # Laylo automation uses lazy loading, so proxies might be []
        if not hasattr(self, 'proxies') or self.proxies is None:
            self.proxies = self.get_all_proxies()
            if not self.proxies:
                print("⚠️  No proxies from API (using lazy loading or proxies from file)")
                # Don't return - allow lazy loading to work
            else:
                print(f"📡 Loaded {len(self.proxies)} proxies from API")
        elif isinstance(self.proxies, list) and len(self.proxies) == 0:
            print("📡 Using lazy proxy loading (proxies will be created on demand)")
        else:
            print(f"📡 Using {len(self.proxies)} pre-loaded proxies")
        
        # Process in batches
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            
            for i, data_item in enumerate(data_list):
                # Check stop event before submitting new tasks (unless ignored for background signups)
                if not ignore_stop_event and hasattr(self, 'stop_event') and self.stop_event.is_set():
                    print(f"🛑 Stop signaal ontvangen - geen nieuwe taken meer starten")
                    break
                
                # Add 1 second delay between starting browsers (behalve eerste)
                if i > 0:
                    time.sleep(1.0)
                
                future = executor.submit(self._process_single_item, site_config, data_item, i + 1)
                futures.append(future)
            
            # Wait for completion
            completed = 0
            for future in as_completed(futures):
                # Check stop event (unless ignored for background signups)
                if not ignore_stop_event and hasattr(self, 'stop_event') and self.stop_event.is_set():
                    print(f"🛑 Stop signaal ontvangen - wachten tot bestaande taken klaar zijn...")
                
                try:
                    result = future.result()
                    completed += 1
                    print(f"✅ Completed {completed}/{len(data_list)} items")
                except Exception as e:
                    print(f"❌ Item failed: {e}")
                    completed += 1
                
                # If stop event is set, cancel remaining futures (unless ignored)
                if not ignore_stop_event and hasattr(self, 'stop_event') and self.stop_event.is_set():
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break
    
    def _process_single_item(self, site_config, data_item, task_number):
        """
        Process single data item
        Deze methode moet worden overridden door site-specific implementaties
        """
        profile = None
        proxy = None
        driver = None
        semaphore_acquired = False
        
        try:
            # Acquire semaphore to limit concurrent browsers
            if self.browser_semaphore:
                self.browser_semaphore.acquire()
                semaphore_acquired = True
            
            # Get proxy (only if we have pre-loaded proxies, otherwise skip for lazy loading)
            if hasattr(self, 'proxies') and isinstance(self.proxies, list) and len(self.proxies) > 0:
                with self.proxy_lock:
                    proxy = self.proxies.pop(0) if self.proxies else None
                
                if not proxy:
                    print("❌ No unused proxies available!")
                    return False
            # If proxies list is empty, assume lazy loading (handled by overridden methods)
            
            # Create profile with proxy
            profile = self.create_profile(proxy_data=proxy, name_prefix=f'TASK{task_number}')
            if not profile:
                return False
            
            profile_id = profile['id']
            proxy_id = proxy.get('id') if proxy else None
            
            # Update profile tracking with proxy_id
            with self.profile_lock:
                if profile_id in self.active_profiles:
                    self.active_profiles[profile_id]['proxy_id'] = proxy_id
            
            # Create driver
            driver = self.create_driver(profile_id)
            if not driver:
                return False
            
            # Run site-specific automation
            success = self._execute_site_automation(driver, site_config, data_item, task_number)
            
            return success
            
        except Exception as e:
            print(f"❌ Error in automation process: {e}")
            return False
            
        finally:
            # Cleanup - always stop driver
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            # Cleanup profile and proxy based on success status
            if profile:
                self._cleanup_profile_and_proxy(profile, proxy, success)
            
            # Release semaphore to allow next browser
            if semaphore_acquired and self.browser_semaphore:
                self.browser_semaphore.release()
    
    def _cleanup_profile_and_proxy(self, profile, proxy=None, success=True, proxy_string=None, proxies_file=None):
        """
        Cleanup profile and proxy after automation
        Can be overridden by subclasses for custom cleanup logic
        
        Args:
            profile: Profile dict with 'id' key
            proxy: Proxy dict with 'id' key (optional)
            success: Whether automation was successful (default: True)
            proxy_string: Proxy string to remove from file (optional, for file-based proxies)
            proxies_file: Path to proxies file to remove proxy string from (optional)
        """
        profile_id = profile.get('id') if profile else None
        
        if not profile_id:
            return
        
        # Remove from active profiles tracking
        with self.profile_lock:
            if profile_id in self.active_profiles:
                del self.active_profiles[profile_id]
        
        # Stop profile first
        try:
            self.stop_profile(profile_id)
        except Exception as e:
            print(f"⚠️  Error stopping profile {profile_id}: {e}")
        
        # Only delete on success
        if success:
            # Delete profile from Dolphin
            try:
                print(f"🗑️  Deleting profile {profile_id} from Dolphin...")
                self.delete_profile(profile_id)
                print(f"✅ Profile {profile_id} deleted from Dolphin")
            except Exception as e:
                print(f"⚠️  Error deleting profile {profile_id} from Dolphin: {e}")
            
            # Delete proxy from Dolphin if provided
            if proxy and proxy.get('id'):
                proxy_id = proxy.get('id')
                try:
                    print(f"🗑️  Deleting proxy {proxy_id} from Dolphin...")
                    result = self.delete_proxy(proxy_id)
                    if result:
                        print(f"✅ Proxy {proxy_id} deleted from Dolphin")
                    else:
                        print(f"⚠️  Proxy {proxy_id} deletion returned False")
                except Exception as e:
                    print(f"⚠️  Error deleting proxy {proxy_id} from Dolphin: {e}")
            
            # Remove proxy string from file if provided
            if proxy_string and proxies_file:
                self._remove_proxy_string_from_file(proxy_string, proxies_file)
        else:
            # On failure, just stop but don't delete (allow retry)
            print(f"⚠️  Profile {profile_id} stopped but not deleted (failure - will retry later)")
    
    def _remove_proxy_string_from_file(self, proxy_string, proxies_file):
        """
        Remove a used proxy string from the proxies.txt file
        Can be overridden by subclasses for custom file handling
        
        Args:
            proxy_string: The proxy string to remove (format: ip:port:username:password)
            proxies_file: Path to the proxies file
        """
        if not proxies_file or not Path(proxies_file).exists():
            return
        
        try:
            proxy_string_stripped = proxy_string.strip()
            remaining_lines = []
            removed = False
            
            # Read all lines
            with open(proxies_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Filter out the used proxy string
            for line in lines:
                line_stripped = line.strip()
                # Skip empty lines and comments
                if not line_stripped or line_stripped.startswith('#'):
                    remaining_lines.append(line)
                    continue
                
                # Compare stripped proxy strings (case-insensitive)
                if line_stripped.lower() == proxy_string_stripped.lower():
                    removed = True
                    print(f"🗑️  Removed used proxy from file: {proxy_string_stripped[:30]}...")
                    continue  # Skip this line
                
                remaining_lines.append(line)
            
            # Write back to file if we removed something
            if removed:
                with open(proxies_file, 'w', encoding='utf-8') as f:
                    f.writelines(remaining_lines)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                print(f"✅ Updated proxies file (removed 1 used proxy)")
            
        except Exception as e:
            print(f"⚠️  Error removing proxy string from file: {e}")
    
    def _execute_site_automation(self, driver, site_config, data_item, task_number):
        """
        Execute site-specific automation logic
        Deze methode moet worden overridden door site-specific implementaties
        """
        print(f"📝 Executing automation for task {task_number} on {site_config.get('name', 'Unknown Site')}")
        
        try:
            # Navigate to site
            driver.get(site_config.get('url', ''))
            time.sleep(random.uniform(2, 4))
            
            # Human-like behavior
            self.human_scroll(driver)
            self.random_mouse_movement(driver)
            self.simulate_akamai_behavior(driver, duration=3)
            
            print(f"✅ Automation completed for task {task_number}")
            return True
            
        except Exception as e:
            print(f"❌ Automation failed for task {task_number}: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Example config
    config = {
        'dolphin_token': 'your_dolphin_token_here',
        'dolphin_api_url': 'https://dolphin-anty-api.com',
        'profile_delete_password': 'myStrongPassword'
    }
    
    # Example site config
    site_config = {
        'name': 'Example Site',
        'url': 'https://example.com'
    }
    
    # Example data list
    data_list = ['item1', 'item2', 'item3']
    
    # Run automation
    automation = DolphinAutomation(config)
    automation.run_automation(site_config, data_list, threads=3)




