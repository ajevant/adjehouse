#!/usr/bin/env python3
"""
ADJEHOUSE - Main Console Application
====================================
Menu-based application for running various automation scripts
"""

import os
import sys
import subprocess
import platform
import json
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Set

# Discord bot imports (only if discord is available)
try:
    import requests
    import discord
    from discord import Message
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# Version info - extract from executable name only (version.txt is no longer used)
VERSION = "BUILD-200"  # Default fallback
try:
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - extract version from filename
        exe_name = Path(sys.executable).name
        import re
        match = re.search(r'v(\d+)', exe_name, re.IGNORECASE)
        if match:
            VERSION = f"BUILD-{match.group(1)}"
    else:
        # Running as script - find latest executable in dist directory
        base_path = Path(__file__).parent
        dist_dir = base_path / "dist"
        if dist_dir.exists():
            exe_files = list(dist_dir.glob("ADJEHOUSE_v*.exe"))
            if exe_files:
                import re
                versions = []
                for exe_file in exe_files:
                    match = re.search(r'v(\d+)', exe_file.name, re.IGNORECASE)
                    if match:
                        versions.append(int(match.group(1)))
                if versions:
                    VERSION = f"BUILD-{max(versions)}"
except Exception:
    pass  # Use default if extraction fails

BUILD_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Auto-update system
try:
    from update_checker import check_for_updates, cleanup_old_versions
    UPDATE_AVAILABLE = True
except ImportError:
    UPDATE_AVAILABLE = False
    print("[WARNING] Update checker module not available")

# ASCII Art Logo (Felroze - pink)
LOGO = r"""
     _    ____      _ _____ _   _  ___  _   _ ____  _____ 
    / \  |  _ \    | | ____| | | |/ _ \| | | / ___|| ____|
   / _ \ | | | |_  | |  _| | |_| | | | | | | \___ \|  _|  
  / ___ \| |_| | |_| | |___|  _  | |_| | |_| |___) | |___ 
 /_/   \_\____/ \___/|_____|_| |_|\___/ \___/|____/|_____|
"""

def clear_screen():
    """Clear the console screen"""
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')

def print_logo():
    """Print the ADJEHOUSE logo in baby blue (cyan)"""
    if platform.system() == "Windows":
        import ctypes
        # Get console handle
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        
        # Print logo with color codes
        for line in LOGO.strip().split('\n'):
            # Set text color to cyan (11) for baby blue
            kernel32.SetConsoleTextAttribute(h, 11)  # Bright cyan
            print(line)
            # Reset to white (7)
            kernel32.SetConsoleTextAttribute(h, 7)
    else:
        # For Unix/Mac, use ANSI codes for baby blue
        print('\033[96m' + LOGO + '\033[0m')  # Bright cyan (baby blue)

def print_welcome():
    """Print welcome message"""
    print_logo()
    print(f"Welcome, {os.getenv('USERNAME', 'User')}! Version: {VERSION}")
    print(f"Build Date: {BUILD_DATE}\n")

def print_separator():
    """Print separator line"""
    print("-" * 70)

def print_green(text):
    """Print text in green color"""
    if platform.system() == "Windows":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        kernel32.SetConsoleTextAttribute(h, 10)  # Green
        print(text)
        kernel32.SetConsoleTextAttribute(h, 7)  # Reset to white
    else:
        print('\033[92m' + text + '\033[0m')  # Green ANSI code

def is_discord_bot_running():
    """Check if Discord bot is still running"""
    global discord_bot_active, discord_bot_thread
    return discord_bot_active and discord_bot_thread and discord_bot_thread.is_alive()

def start_lysted_monitor():
    """Start Lysted sales monitor"""
    global lysted_monitor_module
    
    if lysted_monitor_module:
        # Check if already running
        if hasattr(lysted_monitor_module, 'is_monitoring'):
            if lysted_monitor_module.is_monitoring():
                return True
    
    try:
        import importlib.util
        monitor_path = Path(__file__).parent / 'monitors' / 'lysted' / 'lysted_monitor.py'
        
        if not monitor_path.exists():
            print(f"\n[ERROR] Lysted monitor file not found: {monitor_path}")
            return False
        
        spec = importlib.util.spec_from_file_location("lysted_monitor", monitor_path)
        lysted_monitor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lysted_monitor_module)
        
        if hasattr(lysted_monitor_module, 'start_monitoring'):
            return lysted_monitor_module.start_monitoring()
        else:
            print("\n[ERROR] Lysted monitor module missing start_monitoring() function")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Failed to start Lysted monitor: {e}")
        import traceback
        traceback.print_exc()
        return False

def is_lysted_monitoring():
    """Check if Lysted monitor is running"""
    global lysted_monitor_module
    if lysted_monitor_module and hasattr(lysted_monitor_module, 'is_monitoring'):
        return lysted_monitor_module.is_monitoring()
    return False

def start_viagogo_monitor():
    """Start Viagogo sales monitor"""
    global viagogo_monitor_module
    
    if viagogo_monitor_module:
        # Check if already running
        if hasattr(viagogo_monitor_module, 'is_monitoring'):
            if viagogo_monitor_module.is_monitoring():
                return True
    
    try:
        import importlib.util
        monitor_path = Path(__file__).parent / 'monitors' / 'viagogo' / 'viagogo_monitor.py'
        
        if not monitor_path.exists():
            print(f"\n[ERROR] Viagogo monitor file not found: {monitor_path}")
            return False
        
        spec = importlib.util.spec_from_file_location("viagogo_monitor", monitor_path)
        viagogo_monitor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(viagogo_monitor_module)
        
        if hasattr(viagogo_monitor_module, 'start_monitoring'):
            return viagogo_monitor_module.start_monitoring()
        else:
            print("\n[ERROR] Viagogo monitor module missing start_monitoring() function")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Failed to start Viagogo monitor: {e}")
        import traceback
        traceback.print_exc()
        return False

def is_viagogo_monitoring():
    """Check if Viagogo monitor is running"""
    global viagogo_monitor_module
    if viagogo_monitor_module and hasattr(viagogo_monitor_module, 'is_monitoring'):
        return viagogo_monitor_module.is_monitoring()
    return False

def load_discord_config():
    """Load Discord Pushover config from JSON"""
    if getattr(sys, 'frozen', False):
        BASE_DIR = Path(sys.executable).parent
    else:
        BASE_DIR = Path(__file__).parent
    
    config_file = BASE_DIR / 'monitors' / 'discord-pushover' / 'discord_pushover_config.json'
    
    if not config_file.exists():
        print(f"[ERROR] Discord config file not found: {config_file}")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in Discord config file: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to load Discord config: {e}")
        return None

def discord_bot_loop():
    """Discord bot main loop (runs in thread)"""
    global discord_bot_active, discord_bot_client
    
    if not DISCORD_AVAILABLE:
        print("\n[ERROR] discord.py library not installed!")
        return
    
    config = load_discord_config()
    if not config:
        print("\n[ERROR] Failed to load Discord config!")
        return
    
    discord_config = config.get('discord', {})
    pushover_config = config.get('pushover', {})
    settings = config.get('settings', {})
    
    DISCORD_TOKEN = discord_config.get('bot_token', '')
    PUSHOVER_USER_KEY = pushover_config.get('user_key', '')
    PUSHOVER_API_TOKEN = pushover_config.get('api_token', '')
    TARGET_USER_ID = int(discord_config.get('target_user_id', 0))
    ALLOWED_CHANNEL_IDS: Set[int] = set(discord_config.get('allowed_channel_ids', []))
    COOLDOWN_SECONDS = settings.get('cooldown_seconds', 5)
    
    # Check required variables
    missing = []
    if not DISCORD_TOKEN:
        missing.append("discord.bot_token")
    if not PUSHOVER_USER_KEY:
        missing.append("pushover.user_key")
    if not PUSHOVER_API_TOKEN:
        missing.append("pushover.api_token")
    if not TARGET_USER_ID:
        missing.append("discord.target_user_id")
    
    if missing:
        print(f"\n[ERROR] Missing required config values: {', '.join(missing)}")
        return
    
    # Cooldown per channel
    LAST_ALERT_TS = {}
    
    def send_pushover(title: str, message: str):
        """Send push via Pushover."""
        try:
            r = requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": PUSHOVER_API_TOKEN,
                    "user": PUSHOVER_USER_KEY,
                    "title": title[:100],
                    "message": message[:1024],
                    "priority": 1,  # high priority (sound)
                },
                timeout=10,
            )
            r.raise_for_status()
        except Exception:
            pass  # Silent fail
    
    def mentioned_target_user(msg: Message) -> bool:
        """True if message mentions you or @everyone/@here."""
        for m in msg.mentions:
            if getattr(m, "id", None) == TARGET_USER_ID:
                return True
        content = msg.content or ""
        if f"<@{TARGET_USER_ID}>" in content or f"<@!{TARGET_USER_ID}>" in content:
            return True
        if msg.mention_everyone:
            return True
        if "@everyone" in content or "@here" in content:
            return True
        return False
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True
    
    client = discord.Client(intents=intents)
    discord_bot_client = client
    
    @client.event
    async def on_ready():
        pass  # Silent
    
    @client.event
    async def on_message(message: Message):
        if message.author == client.user:
            return
        if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
            return
        if mentioned_target_user(message):
            now = time.time()
            last = LAST_ALERT_TS.get(message.channel.id, 0)
            if now - last < COOLDOWN_SECONDS:
                return
            LAST_ALERT_TS[message.channel.id] = now
            guild_name = getattr(message.guild, "name", "DM/Unknown")
            channel_name = getattr(message.channel, "name", None) or str(message.channel)
            author = message.author.display_name
            title = f"Discord ping in #{channel_name} ({guild_name})"
            preview = (message.content or "").strip() or "[No text / attachment]"
            body = f"From: {author}\nChannel: #{channel_name}\nServer: {guild_name}\n\n{preview}"
            send_pushover(title, body)
    
    discord_bot_active = True
    try:
        client.run(DISCORD_TOKEN)
    except Exception:
        pass
    finally:
        discord_bot_active = False

def start_discord_bot():
    """Start Discord Pushover bot in background thread"""
    global discord_bot_thread, discord_bot_active
    
    if is_discord_bot_running():
        print_green("\n[INFO] Discord Pushover bot is already running!")
        return True
    
    if not DISCORD_AVAILABLE:
        print("\n[ERROR] discord.py library not installed!")
        print("Install with: pip install discord.py requests")
        return False
    
    discord_bot_thread = threading.Thread(target=discord_bot_loop, daemon=True)
    discord_bot_thread.start()
    
    # Give it a moment to start
    time.sleep(2)
    
    if is_discord_bot_running():
        print_green("\n[SUCCESS] Discord Pushover bot started successfully!")
        return True
    else:
        print("\n[ERROR] Discord bot failed to start")
        return False

# Scraper modules configuration
# Paths are relative to parent directory (one level up)
SCRAPER_MODULES = {
    "1": {"name": "AXS", "path": "scrapers/axs_scraper.py"},
    "2": {"name": "Ticketmaster", "path": "scrapers/ticketmaster_scraper.py"},
    "3": {"name": "SeatGeek", "path": "scrapers/seatgeek_scraper.py"},
}

# Sign-up modules configuration
SIGNUP_MODULES = {
    "1": {"name": "Laylo RSVP", "path": "signups/laylo/laylo_automation.py"},
    "2": {"name": "Seated Signup", "path": "signups/seated/seated_automation.py"},
    "3": {"name": "Portugal FPF Registration", "path": "signups/portugal_fpf/portugal_fpf_automation.py"},
    "4": {"name": "Example (Dolphin Base)", "path": "example_signup.py"},
}

# Discord Pushover bot tracking
discord_bot_thread = None
discord_bot_client = None
discord_bot_active = False

# Monitor modules tracking
lysted_monitor_module = None
viagogo_monitor_module = None

def run_module(module_path, module_name):
    """Run a Python module by importing and executing it directly"""
    print(f"\n{'='*70}")
    print(f"Starting: {module_name}")
    print(f"{'='*70}\n")
    
    # Check if file exists
    if module_path.startswith('../'):
        full_path = Path(__file__).parent.parent / module_path.replace('../', '')
    else:
        full_path = Path(__file__).parent / module_path
    
    if not full_path.exists():
        print(f"[ERROR] Module file not found: {module_path}")
        input("\nPress ENTER to continue...")
        return
    
    try:
        # Save current directory
        original_dir = os.getcwd()
        
        # Import and run the module's main function directly
        import importlib.util
        
        # Load the module
        spec = importlib.util.spec_from_file_location("scraper_module", full_path)
        module = importlib.util.module_from_spec(spec)
        
        # Temporarily change to the module's directory for imports to work
        os.chdir(full_path.parent)
        try:
            spec.loader.exec_module(module)
        finally:
            # Always restore original directory
            os.chdir(original_dir)
        
        # Check if module has a main function and run it
        if hasattr(module, 'main'):
            module.main()
        else:
            print("[ERROR] Module does not have a main() function")
            
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\nError running module: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n{'='*70}")
        print(f"Module finished: {module_name}")
        print(f"{'='*70}")
        input("\nPress ENTER to return to main menu...")

def scraper_menu():
    """Display and handle scraper submenu"""
    while True:
        clear_screen()
        print_logo()
        print_separator()
        print("\n[START SCRAPER]\n")
        
        for key, module in SCRAPER_MODULES.items():
            # Check if file exists
            if module['path'].startswith('../'):
                full_path = Path(__file__).parent.parent / module['path'].replace('../', '')
            else:
                full_path = Path(__file__).parent / module['path']
            status = "✓" if full_path.exists() else "✗"
            print(f"{status} {key}. {module['name']} Scraper")
        
        print(f"\n{'-'*70}")
        print("\n0. Back to Main Menu")
        
        choice = input("\nSelect a scraper: ").strip()
        
        if choice == "0":
            return
        elif choice in SCRAPER_MODULES:
            module = SCRAPER_MODULES[choice]
            module_path = module['path']
            module_name = f"{module['name']} Scraper"
            
            if module_path.startswith('../'):
                full_path = Path(__file__).parent.parent / module_path.replace('../', '')
            else:
                full_path = Path(__file__).parent / module_path
            
            if not full_path.exists():
                print(f"\n[ERROR] Scraper file not found: {module_path}")
                input("\nPress ENTER to continue...")
                continue
            
            clear_screen()
            run_module(module_path, module_name)
        else:
            print("\n[ERROR] Invalid option. Please try again.")
            input("\nPress ENTER to continue...")

def signup_menu():
    """Display and handle sign-up submenu"""
    while True:
        clear_screen()
        print_logo()
        print_separator()
        print("\n[START SIGN-UPS]\n")
        
        if not SIGNUP_MODULES:
            print("** No sign-up modules available yet.")
            print("   Coming soon...")
        else:
            for key, module in SIGNUP_MODULES.items():
                # Check if path is relative to current directory
                if module['path'].startswith('../'):
                    full_path = Path(__file__).parent.parent / module['path'].replace('../', '')
                else:
                    full_path = Path(__file__).parent / module['path']
                status = "✓" if full_path.exists() else "✗"
                print(f"{status} {key}. {module['name']}")
        
        print(f"\n{'-'*70}")
        print("\n0. Back to Main Menu")
        
        choice = input("\nSelect an option: ").strip()
        
        if choice == "0":
            return
        elif choice in SIGNUP_MODULES:
            module = SIGNUP_MODULES[choice]
            module_path = module['path']
            module_name = module['name']
            
            # Check if path is relative to current directory
            if module_path.startswith('../'):
                full_path = Path(__file__).parent.parent / module_path.replace('../', '')
            else:
                full_path = Path(__file__).parent / module_path
            
            if not full_path.exists():
                print(f"\n[ERROR] Module file not found: {module_path}")
                input("\nPress ENTER to continue...")
                continue
            
            clear_screen()
            run_module(module_path, module_name)
        else:
            print("\n[ERROR] Invalid option. Please try again.")
            input("\nPress ENTER to continue...")

def main_menu():
    """Display and handle main menu"""
    while True:
        clear_screen()
        print_welcome()
        print_separator()
        print("\nSelect an option:\n")
        print("1. Start Scraper")
        print("2. Start Sign-ups")
        
        # Show Discord Pushover status
        if is_discord_bot_running():
            print_green("3. Discord Pushover [RUNNING]")
        else:
            print("3. Discord Pushover")
        
        # Show Lysted Monitor status
        if is_lysted_monitoring():
            print_green("4. Lysted Monitor [RUNNING]")
        else:
            print("4. Lysted Monitor")
        
        # Show Viagogo Monitor status
        if is_viagogo_monitoring():
            print_green("5. Viagogo Monitor [RUNNING]")
        else:
            print("5. Viagogo Monitor")
        
        print("\n0. Exit ADJEHOUSE")
        
        choice = input("\nSelect an option: ").strip()
        
        if choice == "0":
            print("\nGoodbye!")
            sys.exit(0)
        elif choice == "1":
            scraper_menu()
        elif choice == "2":
            signup_menu()
        elif choice == "3":
            # Start Discord Pushover bot
            clear_screen()
            print_logo()
            print_separator()
            print("\n[DISCORD PUSHOVER]\n")
            
            if is_discord_bot_running():
                print_green("Discord Pushover bot is already running!")
                print("\nThe bot is active and monitoring Discord messages.")
            else:
                print("Starting Discord Pushover bot...")
                if start_discord_bot():
                    print_green("\n✓ Discord Pushover bot is now running in the background!")
                    print("\nThe bot will continue running even when you return to the main menu.")
                else:
                    print("\n[ERROR] Failed to start Discord Pushover bot.")
            
            input("\nPress ENTER to return to main menu...")
        elif choice == "4":
            # Start Lysted Monitor
            clear_screen()
            print_logo()
            print_separator()
            print("\n[LYSTED MONITOR]\n")
            
            if is_lysted_monitoring():
                print_green("Lysted Monitor is already running!")
                print("\nThe monitor is active and checking for sales.")
            else:
                print("Starting Lysted sales monitor...")
                if start_lysted_monitor():
                    print_green("\n✓ Lysted Monitor is now running in the background!")
                    print("\nThe monitor will check for sales every 2 minutes.")
                else:
                    print("\n[ERROR] Failed to start Lysted Monitor.")
                    print("Check the config file: monitors/lysted/lysted_config.json")
            
            input("\nPress ENTER to return to main menu...")
        elif choice == "5":
            # Start Viagogo Monitor
            clear_screen()
            print_logo()
            print_separator()
            print("\n[VIAGOGO MONITOR]\n")
            
            if is_viagogo_monitoring():
                print_green("Viagogo Monitor is already running!")
                print("\nThe monitor is active and checking for sales.")
            else:
                print("Starting Viagogo sales monitor...")
                if start_viagogo_monitor():
                    print_green("\n✓ Viagogo Monitor is now running in the background!")
                    print("\nThe monitor will check for sales every 2 minutes.")
                else:
                    print("\n[ERROR] Failed to start Viagogo Monitor.")
                    print("Check the config file: monitors/viagogo/viagogo_config.json")
            
            input("\nPress ENTER to return to main menu...")
        else:
            print("\n[ERROR] Invalid option. Please try again.")
            input("\nPress ENTER to continue...")

def ensure_settings_exist():
    """Create all necessary directories and default config files if they don't exist"""
    # Determine base directory (where EXE is located or script directory)
    if getattr(sys, 'frozen', False):
        # Running as EXE - use EXE directory
        BASE_DIR = Path(sys.executable).parent
    else:
        # Running as script - use script directory
        BASE_DIR = Path(__file__).parent
    
    # Create all directories in one location
    SETTINGS_DIR = BASE_DIR / 'settings_for_scraper'
    SUCCESS_DIR = BASE_DIR / 'success'
    SIGNUPS_DIR = BASE_DIR / 'signups'
    LAYLO_DIR = SIGNUPS_DIR / 'laylo'
    SEATED_DIR = SIGNUPS_DIR / 'seated'
    PORTUGAL_FPF_DIR = SIGNUPS_DIR / 'portugal_fpf'
    MONITORS_DIR = BASE_DIR / 'monitors'
    LYSTED_DIR = MONITORS_DIR / 'lysted'
    VIAGOGO_DIR = MONITORS_DIR / 'viagogo'
    DISCORD_PUSHOVER_DIR = MONITORS_DIR / 'discord-pushover'
    
    # Create directories
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SUCCESS_DIR.mkdir(parents=True, exist_ok=True)
    SIGNUPS_DIR.mkdir(parents=True, exist_ok=True)
    LAYLO_DIR.mkdir(parents=True, exist_ok=True)
    SEATED_DIR.mkdir(parents=True, exist_ok=True)
    PORTUGAL_FPF_DIR.mkdir(parents=True, exist_ok=True)
    MONITORS_DIR.mkdir(parents=True, exist_ok=True)
    LYSTED_DIR.mkdir(parents=True, exist_ok=True)
    VIAGOGO_DIR.mkdir(parents=True, exist_ok=True)
    DISCORD_PUSHOVER_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create default scraper config.json with example IMAP account
    CONFIG_FILE = SETTINGS_DIR / 'config.json'
    if not CONFIG_FILE.exists():
        default_config = {
            "imap_accounts": {
                "axs": [
                    {
                        "email": "jouw.email@gmail.com",
                        "password": "jouw_app_specifiek_wachtwoord"
                    }
                ],
                "ticketmaster": [
                    {
                        "email": "jouw.email@gmail.com",
                        "password": "jouw_app_specifiek_wachtwoord"
                    }
                ],
                "seatgeek": [
                    {
                        "email": "jouw.email@gmail.com",
                        "password": "jouw_app_specifiek_wachtwoord"
                    }
                ]
            },
            "search_settings": {
                "default_search_days": 1
            }
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            # Silently fail if we can't create config
            pass
    
    # Create default Laylo config.json if it doesn't exist
    LAYLO_CONFIG_FILE = LAYLO_DIR / 'laylo_config.json'
    if not LAYLO_CONFIG_FILE.exists():
        default_laylo_config = {
            "site_name": "Laylo",
            "site_url": "https://laylo.com/sonxchun/skrillex-fourtet-sf-dec30",
            
            "dolphin": {
                "token": "YOUR_DOLPHIN_TOKEN_HERE",
                "remote_api_url": "https://dolphin-anty-api.com",
                "api_url": "http://localhost:3001/v1.0"
            },
            
            "files": {
                "emails": "emails.csv",
                "proxies": "proxies.txt"
            },
            
            "automation": {
                "threads": 5,
                "max_retries": 3,
                "timeout_seconds": 60
            },
            
            "discord": {
                "finished_webhook": ""
            },
            
            "_notes": {
                "profile_delete_password": "Dit is het wachtwoord dat je instelt in Dolphin Anty voor het verwijderen van profiles. Zet dit in de Dolphin Anty app zelf, niet hier.",
                "emails.csv": "Eén email adres per regel met kolommen: email,entered,timestamp",
                "proxies.txt": "Eén proxy per regel in formaat: ip:port:username:password"
            }
        }
        try:
            with open(LAYLO_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_laylo_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass

    # Create default Seated config.json if it doesn't exist
    SEATED_CONFIG_FILE = SEATED_DIR / 'seated_config.json'
    if not SEATED_CONFIG_FILE.exists():
        default_seated_config = {
            "site_name": "Seated",
            "target_url": "https://go.seated.com/tour-events/9eb887de-b4d6-4544-96e7-21fa006e5cf3",
            "dolphin": {
                "token": "YOUR_DOLPHIN_TOKEN_HERE",
                "remote_api_url": "https://dolphin-anty-api.com",
                "api_url": "http://localhost:3001/v1.0"
            },
            "twilio": {
                "account_sid": "AC55c05dd8d99b317927f1bed97c77d41e",
                "auth_token": "176b89c7d73c50b93046ac6fd03a1693",
                "service_sid": "VAcc553657dccd1bb87ba69c3acf6f3682"
            },
            "files": {
                "accounts": "accounts.csv",
                "proxies": "proxies.txt"
            },
            "automation": {
                "threads": 3,
                "timeout_seconds": 45,
                "sms_timeout_seconds": 90
            },
            "discord": {
                "finished_webhook": ""
            },
            "_notes": {
                "accounts.csv": "Kolommen: email,entered,timestamp. Gebruik 'nee' voor nieuwe accounts.",
                "proxies.txt": "Formaat: ip:port:username:password",
                "twilio": "Vul Twilio Verify gegevens in met UK nummers."
            }
        }
        try:
            with open(SEATED_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_seated_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass

    # Create default emails.csv if it doesn't exist
    EMAILS_CSV = LAYLO_DIR / 'emails.csv'
    if not EMAILS_CSV.exists():
        try:
            with open(EMAILS_CSV, 'w', encoding='utf-8', newline='') as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(['email', 'entered', 'timestamp'])
                writer.writerow(['voorbeeld@email.com', 'nee', ''])
        except Exception as e:
            pass
    
    # Create default proxies.txt if it doesn't exist
    PROXIES_TXT = LAYLO_DIR / 'proxies.txt'
    if not PROXIES_TXT.exists():
        try:
            with open(PROXIES_TXT, 'w', encoding='utf-8') as f:
                f.write("# Proxy format: ip:port:username:password\n")
                f.write("# Example:\n")
                f.write("# 127.0.0.1:8080:user:pass\n")
        except Exception as e:
            pass

    # Create default Seated accounts.csv if it doesn't exist
    SEATED_ACCOUNTS = SEATED_DIR / 'accounts.csv'
    if not SEATED_ACCOUNTS.exists():
        try:
            import csv
            with open(SEATED_ACCOUNTS, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['email', 'entered', 'timestamp'])
                writer.writerow(['voorbeeld@domein.nl', 'nee', ''])
        except Exception as e:
            pass

    # Create default Seated proxies.txt if it doesn't exist
    SEATED_PROXIES = SEATED_DIR / 'proxies.txt'
    if not SEATED_PROXIES.exists():
        try:
            with open(SEATED_PROXIES, 'w', encoding='utf-8') as f:
                f.write("# Proxy format: ip:port:username:password\n")
                f.write("# Example:\n")
                f.write("# 127.0.0.1:8080:user:pass\n")
        except Exception as e:
            pass
    
    # Create default Portugal FPF config.json if it doesn't exist
    PORTUGAL_FPF_CONFIG_FILE = PORTUGAL_FPF_DIR / 'portugal_fpf_config.json'
    if not PORTUGAL_FPF_CONFIG_FILE.exists():
        default_portugal_fpf_config = {
            "site_name": "Portugal FPF",
            "site_url": "https://portugal.fpf.pt/",
            "dolphin": {
                "token": "YOUR_DOLPHIN_TOKEN_HERE",
                "remote_api_url": "https://dolphin-anty-api.com",
                "api_url": "http://localhost:3001/v1.0"
            },
            "imap": {
                "email": "your_imap_email@gmail.com",
                "password": "your_app_password",
                "server": "imap.gmail.com",
                "port": 993,
                "folder": "INBOX",
                "sender": "",
                "subject_phrase": "Código de verificação",
                "code_timeout_seconds": 120,
                "code_poll_interval": 3
            },
            "files": {
                "accounts": "accounts.csv",
                "proxies": "proxies.txt"
            },
            "automation": {
                "threads": 1,
                "timeout_seconds": 45,
                "password_length": 12,
                "auto_restart_runs": 1,
                "cleanup_on_start": True,
                "force_cleanup_completed": False
            },
            "discord": {
                "finished_webhook": ""
            },
            "_notes": {
                "accounts.csv": "Kolommen: email,password,first_name,last_name,birthdate,phone_number,entered,timestamp. Gebruik 'nee' voor nog te verwerken accounts.",
                "proxies.txt": "Formaat: ip:port:username:password",
                "imap": "Gebruik een app-wachtwoord voor Gmail. De verificatie code wordt automatisch uit de email gehaald.",
                "birthdate": "Formaat: YYYY-MM-DD (bijv. 2003-03-14). Gebruiker moet ouder zijn dan 20.",
                "phone_number": "9 cijfers die beginnen met 6 (bijv. 612345678). Nederlands telefoonnummer (+31)."
            }
        }
        try:
            with open(PORTUGAL_FPF_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_portugal_fpf_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass
    
    # Create default Portugal FPF accounts.csv if it doesn't exist
    PORTUGAL_FPF_ACCOUNTS = PORTUGAL_FPF_DIR / 'accounts.csv'
    if not PORTUGAL_FPF_ACCOUNTS.exists():
        try:
            import csv
            with open(PORTUGAL_FPF_ACCOUNTS, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['email', 'password', 'first_name', 'last_name', 'birthdate', 'phone_number', 'entered', 'timestamp'])
                writer.writerow(['voorbeeld@email.com', '', '', '', '', '', 'nee', ''])
        except Exception as e:
            pass
    
    # Create default Portugal FPF proxies.txt if it doesn't exist
    PORTUGAL_FPF_PROXIES = PORTUGAL_FPF_DIR / 'proxies.txt'
    if not PORTUGAL_FPF_PROXIES.exists():
        try:
            with open(PORTUGAL_FPF_PROXIES, 'w', encoding='utf-8') as f:
                f.write("# Proxy format: ip:port:username:password\n")
                f.write("# Example:\n")
                f.write("# 127.0.0.1:8080:user:pass\n")
        except Exception as e:
            pass
    
    # Create default Lysted config.json if it doesn't exist
    LYSTED_CONFIG_FILE = LYSTED_DIR / 'lysted_config.json'
    if not LYSTED_CONFIG_FILE.exists():
        default_lysted_config = {
            "monitor_name": "Lysted Sales Monitor",
            "imap_accounts": [
                {
                    "email": "adjehouse@gmail.com",
                    "password": "jouw_app_specifiek_wachtwoord",
                    "server": "imap.gmail.com",
                    "port": 993
                }
            ],
            "monitoring": {
                "check_interval_seconds": 120
            },
            "discord": {
                "webhook_url": "YOUR_DISCORD_WEBHOOK_URL_HERE"
            },
            "_notes": {
                "check_interval_seconds": "Hoe vaak te checken (120 = elke 2 minuten, 300 = elke 5 minuten)",
                "webhook_url": "Discord webhook URL voor notificaties bij nieuwe sales",
                "filter": "Monitor filtert automatisch op emails met subject '[lysted] TICKETS SOLD' van noreply@lysted.com"
            }
        }
        try:
            with open(LYSTED_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_lysted_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass
    
    # Create default Viagogo config.json if it doesn't exist
    VIAGOGO_CONFIG_FILE = VIAGOGO_DIR / 'viagogo_config.json'
    if not VIAGOGO_CONFIG_FILE.exists():
        default_viagogo_config = {
            "monitor_name": "Viagogo Sales Monitor",
            "imap_accounts": [
                {
                    "email": "ajevan04@gmail.com",
                    "password": "jouw_app_specifiek_wachtwoord",
                    "server": "imap.gmail.com",
                    "port": 993
                }
            ],
            "monitoring": {
                "check_interval_seconds": 120
            },
            "discord": {
                "webhook_url": "YOUR_DISCORD_WEBHOOK_URL_HERE"
            },
            "_notes": {
                "check_interval_seconds": "Hoe vaak te checken (120 = elke 2 minuten, 300 = elke 5 minuten)",
                "webhook_url": "Discord webhook URL voor notificaties bij nieuwe sales (gebruik zelfde als Lysted)",
                "filter": "Monitor filtert automatisch op emails van automated@orders.viagogo.com met subjects: 'You sold your ticket for' of 'Please send your tickets'"
            }
        }
        try:
            with open(VIAGOGO_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_viagogo_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass
    
    # Create default Discord Pushover config.json if it doesn't exist
    DISCORD_PUSHOVER_CONFIG_FILE = DISCORD_PUSHOVER_DIR / 'discord_pushover_config.json'
    if not DISCORD_PUSHOVER_CONFIG_FILE.exists():
        default_discord_config = {
            "monitor_name": "Discord Pushover Bot",
            "discord": {
                "bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
                "target_user_id": 0,
                "allowed_channel_ids": []
            },
            "pushover": {
                "user_key": "YOUR_PUSHOVER_USER_KEY_HERE",
                "api_token": "YOUR_PUSHOVER_API_TOKEN_HERE"
            },
            "settings": {
                "cooldown_seconds": 5
            },
            "_notes": {
                "bot_token": "Discord bot token van https://discord.com/developers/applications",
                "target_user_id": "Discord user ID om te monitoren (getal)",
                "allowed_channel_ids": "Array van channel ID's om te monitoren (bijv. [123456789, 987654321])",
                "user_key": "Pushover user key van https://pushover.net/",
                "api_token": "Pushover API token van https://pushover.net/apps",
                "cooldown_seconds": "Hoeveel seconden tussen pushover notificaties per channel"
            }
        }
        try:
            with open(DISCORD_PUSHOVER_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_discord_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass


def main():
    """Main entry point"""
    try:
        # Check for updates before starting
        if UPDATE_AVAILABLE:
            try:
                # Cleanup old versions first (happens automatically in check_for_updates, but we can also do it here)
                if getattr(sys, 'frozen', False):
                    cleanup_old_versions()
                
                # Check for updates - pass current VERSION to ensure correct comparison
                update_available = check_for_updates(skip_prompt=False, current_version=VERSION)
                if update_available:
                    # Update will be installed automatically, just exit immediately
                    os._exit(0)  # Force immediate exit without cleanup
            except Exception as e:
                # Silently continue with normal startup if update check fails
                pass
        
        # Ensure settings directory and config exist before starting
        ensure_settings_exist()
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print_welcome()
        main_menu()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()

