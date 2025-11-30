#!/usr/bin/env python3
"""
Seated Signup Automation
========================
Automates password signup for Seated events using Dolphin Automation with
Twilio Verify SMS handling and realistic human behaviour.
"""

import os
import sys
import csv
import json
import time
import random
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from twilio.rest import Client  # type: ignore
    TWILIO_AVAILABLE = True
except ImportError as import_error:
    print(f"❌ Twilio import error: {import_error}")
    Client = None  # type: ignore
    TWILIO_AVAILABLE = False

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Ensure dolphin_base can be imported regardless of running mode (script or EXE)
if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent  # type: ignore[attr-defined]
    sys.path.insert(0, str(base_path))
    exe_dir = Path(sys.executable).parent
    sys.path.insert(0, str(exe_dir))
else:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dolphin_base import DolphinAutomation  # noqa: E402


class NoPhoneNumbersAvailable(RuntimeError):
    """Error thrown when no Twilio phone numbers remain for the target link."""
    pass

# ------------------------------------------------------------------------------
# Shared state for Twilio number reuse between threads
# ------------------------------------------------------------------------------

USED_PHONE_NUMBERS: Dict[str, Dict[str, float]] = {}
SUCCESS_PHONES: set[tuple[str, str]] = set()
USED_PHONE_LOCK = threading.Lock()

# ------------------------------------------------------------------------------
# Datasets for Dutch names and postcodes
# ------------------------------------------------------------------------------

DUTCH_FIRST_NAMES: List[str] = [
    "Anna", "Noah", "Emma", "Liam", "Julia", "Milan", "Sophie", "Lucas", "Tess", "Levi",
    "Sara", "Sem", "Eva", "Daan", "Zoë", "Finn", "Lotte", "Thomas", "Isa", "Luuk",
    "Mila", "Bram", "Nina", "Siem", "Fleur", "Jesse", "Lieke", "Gijs", "Olivia", "Mees",
    "Evi", "Dex", "Luna", "Jens", "Liv", "Tijn", "Elin", "Sam", "Fenna", "Teun",
    "Noor", "Guus", "Yara", "Pepijn", "Maud", "Ruben", "Maren", "Kai", "Veerle", "Mick",
    "Lina", "Joep", "Isa", "Nout", "Saar", "Rens", "Roos", "Morris", "Elise", "Tygo",
    "Mare", "Pim", "Floor", "Jurre", "Jade", "Lars", "Lena", "Benjamin", "Bo", "Floris",
    "Merel", "Niek", "Benthe", "Siebe", "Karlijn", "Hugo", "Senna", "Olivier", "Janna", "Rayan",
    "Hannah", "Timo", "Iris", "Sven", "Lois", "Melle", "Kiki", "Thijs", "Lynn", "Quinn",
    "Elisa", "Gerrit", "Bibi", "Rein", "Amelia", "Jort", "Ayla", "Nick", "Madelief", "Adam"
]

DUTCH_LAST_NAMES: List[str] = [
    "van Dijk", "de Jong", "Jansen", "Bakker", "Visser", "Smit", "Meijer", "de Boer", "Mulder", "de Groot",
    "Bos", "Vos", "Peters", "Hendriks", "van Leeuwen", "Dekker", "Brouwer", "van der Meer", "Kok", "Jacobs",
    "van der Linden", "Koster", "van Beek", "Sanders", "van den Berg", "Post", "van Dam", "Kuipers", "Willems", "Vermeulen",
    "Maas", "Klein", "van Veen", "Schouten", "Scholten", "Boer", "Walters", "Prins", "Schipper", "Blom",
    "van Wijk", "Hoekstra", "Peeters", "Verhoeven", "Schaap", "Smits", "Schrijver", "Molenaar", "Brands", "Scholz",
    "Drost", "Hermans", "Peels", "Kruis", "Geerts", "Rutten", "Broekhof", "Wouters", "Ottens", "Rietveld",
    "Vissers", "Engels", "Koning", "Mendes", "Martens", "Kramer", "Roelofs", "Lammers", "Kerkhof", "Veenstra",
    "van Tol", "Roos", "Koning", "Bergsma", "Evers", "Hofman", "Rademaker", "Bol", "Verbeek", "Brandsma",
    "Geurts", "Heijnen", "Schuurman", "Janssens", "Timmermans", "van Gerven", "Beekman", "Reinders", "Heuvel", "Keizer",
    "van Druten", "Ligtenberg", "Koopman", "Heuvelink", "Klooster", "van Schaik", "Koeman", "Mulders", "Verstappen", "Hartman"
]

DUTCH_POSTCODES: List[str] = [
    "1011 AB", "1011 AC", "1011 AD", "1011 AE", "1011 AG", "1011 AH", "1011 AJ", "1011 AK", "1011 AL", "1011 AM",
    "1012 AB", "1012 AC", "1012 AD", "1012 AE", "1012 AG", "1012 AH", "1012 AJ", "1012 AK", "1012 AL", "1012 AN",
    "1013 AA", "1013 AB", "1013 AC", "1013 AD", "1013 AE", "1013 AG", "1013 AH", "1013 AJ", "1013 AK", "1013 AL",
    "1021 AA", "1021 AB", "1021 AC", "1021 AD", "1021 AE", "1021 AG", "1021 AH", "1021 AJ", "1021 AK", "1021 AL",
    "1032 AA", "1032 AB", "1032 AC", "1032 AD", "1032 AE", "1032 AG", "1032 AH", "1032 AJ", "1032 AK", "1032 AL",
    "1051 AB", "1051 AC", "1051 AD", "1051 AE", "1051 AG", "1051 AH", "1051 AJ", "1051 AK", "1051 AL", "1051 AN",
    "1052 AA", "1052 AB", "1052 AC", "1052 AD", "1052 AE", "1052 AG", "1052 AH", "1052 AJ", "1052 AK", "1052 AL",
    "1061 AA", "1061 AB", "1061 AC", "1061 AD", "1061 AE", "1061 AG", "1061 AH", "1061 AJ", "1061 AK", "1061 AL",
    "1071 AA", "1071 AB", "1071 AC", "1071 AD", "1071 AE", "1071 AG", "1071 AH", "1071 AJ", "1071 AK", "1071 AL",
    "1082 AA", "1082 AB", "1082 AC", "1082 AD", "1082 AE", "1082 AG", "1082 AH", "1082 AJ", "1082 AK", "1082 AL",
    "1101 AA", "1101 AB", "1101 AC", "1101 AD", "1101 AE", "1101 AG", "1101 AH", "1101 AJ", "1101 AK", "1101 AL",
    "1111 AA", "1111 AB", "1111 AC", "1111 AD", "1111 AE", "1111 AG", "1111 AH", "1111 AJ", "1111 AK", "1111 AL",
    "1121 AA", "1121 AB", "1121 AC", "1121 AD", "1121 AE", "1121 AG", "1121 AH", "1121 AJ", "1121 AK", "1121 AL",
    "1131 AA", "1131 AB", "1131 AC", "1131 AD", "1131 AE", "1131 AG", "1131 AH", "1131 AJ", "1131 AK", "1131 AL"
]


def generate_random_name() -> Dict[str, str]:
    """Return a randomly generated Dutch first and last name."""
    return {
        "first": random.choice(DUTCH_FIRST_NAMES),
        "last": random.choice(DUTCH_LAST_NAMES),
    }


def generate_dutch_postcode() -> str:
    """Return a valid-looking Dutch postcode."""
    return random.choice(DUTCH_POSTCODES)


def random_delay(min_seconds: float, max_seconds: float) -> None:
    """Sleep for a random duration between the given bounds."""
    time.sleep(random.uniform(min_seconds, max_seconds))


# ------------------------------------------------------------------------------
# Twilio helpers
# ------------------------------------------------------------------------------

class TwilioAPI:
    """Thin wrapper around Twilio Verify for UK phone verification."""

    def __init__(self, account_sid: str, auth_token: str, service_sid: str) -> None:
        if not TWILIO_AVAILABLE or Client is None:
            raise RuntimeError("Twilio Python SDK is not installed. Run: pip install twilio")

        if not account_sid or not auth_token or not service_sid:
            raise ValueError("Twilio configuratie incomplete: account_sid, auth_token en service_sid zijn verplicht")

        if not account_sid.startswith("AC"):
            print(f"⚠️  Twilio Account SID ziet er ongebruikelijk uit: {account_sid}")

        try:
            self.client = Client(account_sid, auth_token)
            self.service_sid = service_sid
        except Exception as exc:
            raise RuntimeError(f"Twilio client initialisatie gefaald: {exc}") from exc

    def get_uk_phone_number(self, target_link: str, cooldown_seconds: int = 3600) -> Optional[str]:
        """Return a UK phone number that is not on cooldown for the given link."""
        try:
            phone_numbers = list(self.client.incoming_phone_numbers.list(limit=100))
        except Exception as exc:
            print(f"❌ Twilio error bij ophalen nummers: {exc}")
            return None

        now = time.time()

        with USED_PHONE_LOCK:
            for record in phone_numbers:
                phone_number = getattr(record, "phone_number", "") or getattr(record, "phoneNumber", "")
                if not phone_number:
                    continue

                if phone_number.startswith("+44"):
                    digits = "".join(ch for ch in phone_number if ch.isdigit())
                    digits = digits[-10:] if len(digits) >= 10 else digits
                    if len(digits) < 9:
                        continue

                    success_key = (digits, target_link)
                    if success_key in SUCCESS_PHONES:
                        continue

                    usage_map = USED_PHONE_NUMBERS.setdefault(digits, {})
                    last_used = usage_map.get(target_link)
                    if last_used and now - last_used < cooldown_seconds:
                        continue

                    usage_map[target_link] = now

                    print(f"📱 UK telefoonnummer geselecteerd: +44{digits}")
                    return digits

        print("⚠️  Geen beschikbaar UK telefoonnummer gevonden (cooldown actief?)")
        return None

    def send_verification_code(self, phone_number: str) -> Optional[str]:
        """Send a verification code to the supplied UK number."""
        try:
            verification = (
                self.client.verify.v2.services(self.service_sid)
                .verifications.create(to=f"+44{phone_number}", channel="sms")
            )
            print(f"✅ Verificatiecode verstuurd naar +44{phone_number}")
            return verification.sid
        except Exception as exc:
            print(f"❌ Fout bij versturen verificatiecode: {exc}")
            return None

    def get_verification_code(self, phone_number: str, timeout: int = 90) -> Optional[str]:
        """Poll Twilio messages for a Seated verification code."""
        verification_sid = self.send_verification_code(phone_number)
        if not verification_sid:
            return None

        deadline = time.time() + timeout
        target = f"+44{phone_number}"

        while time.time() < deadline:
            try:
                messages = self.client.messages.list(limit=20)
            except Exception as exc:
                print(f"⚠️  Fout bij ophalen SMS berichten: {exc}")
                time.sleep(5)
                continue

            for message in messages:
                body = (message.body or "").lower()
                to_number = (message.to or "").strip()
                if not body or not to_number.endswith(target):
                    continue

                if "seated" in body and "verification code" in body:
                    digits = [part for part in message.body.split() if part.isdigit() and len(part) == 4]
                    if digits:
                        code = digits[0]
                        print(f"✅ Seated verificatiecode ontvangen: {code}")
                        return code

            remaining = int(deadline - time.time())
            if remaining > 0:
                print(f"⏳ Wachten op SMS code... ({remaining}s resterend)")
            time.sleep(5)

        print("❌ Geen verificatiecode ontvangen binnen de timeout")
        return None

    def mark_success(self, phone_number: str, target_link: str) -> None:
        """Record that a phone number worked for a specific link."""
        with USED_PHONE_LOCK:
            SUCCESS_PHONES.add((phone_number, target_link))


# ------------------------------------------------------------------------------
# Seated automation
# ------------------------------------------------------------------------------

class SeatedAutomation(DolphinAutomation):
    """Seated-specific automation built on top of DolphinAutomation."""

    def __init__(self, config_file: str) -> None:
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as handle:
            self.site_config = json.load(handle)

        dolphin_config_raw = self.site_config.get("dolphin", {})
        dolphin_config: Dict[str, Any] = {}
        if dolphin_config_raw:
            if "token" in dolphin_config_raw:
                dolphin_config["dolphin_token"] = dolphin_config_raw["token"]
            if "remote_api_url" in dolphin_config_raw:
                dolphin_config["dolphin_remote_api_url"] = dolphin_config_raw["remote_api_url"]
            elif "api_url" in dolphin_config_raw and "localhost" not in dolphin_config_raw["api_url"]:
                dolphin_config["dolphin_remote_api_url"] = dolphin_config_raw["api_url"]
            if "local_api_url" in dolphin_config_raw:
                dolphin_config["dolphin_api_url"] = dolphin_config_raw["local_api_url"]
            elif "api_url" in dolphin_config_raw and (
                "localhost" in dolphin_config_raw["api_url"] or "127.0.0.1" in dolphin_config_raw["api_url"]
            ):
                dolphin_config["dolphin_api_url"] = dolphin_config_raw["api_url"]

        if not dolphin_config.get("dolphin_token"):
            print("⚠️  Dolphin token ontbreekt in configuratie!")

        # Initialise DolphinAutomation base class
        super().__init__(dolphin_config)

        self.target_url = self.site_config.get("target_url") or self.site_config.get("site_url")
        if not self.target_url:
            raise ValueError("Config mist 'target_url' of 'site_url'.")

        automation_config = self.site_config.get("automation", {})
        self.threads = int(automation_config.get("threads", 1))
        self.timeout_seconds = automation_config.get("timeout_seconds", 45)
        self.sms_timeout_seconds = automation_config.get("sms_timeout_seconds", 90)

        # Files live next to the config file (dist/signups/seated/)
        self.base_dir = config_path.parent
        self.base_dir.mkdir(parents=True, exist_ok=True)

        files_config = self.site_config.get("files", {})
        accounts_csv = self.base_dir / files_config.get("accounts", "accounts.csv")
        self.accounts_csv = accounts_csv
        self.accounts = self._load_accounts_from_csv(accounts_csv)

        if not self.accounts:
            print("❌ Geen accounts gevonden in accounts.csv!")

        proxies_file = self.base_dir / files_config.get("proxies", "proxies.txt")
        self.proxies_file = proxies_file
        self.proxy_strings = self._load_from_file(proxies_file, "proxies")
        self.used_proxy_strings: set[str] = set()
        self.profile_proxy_string_map: Dict[str, Optional[str]] = {}
        self.profile_proxy_map: Dict[str, Dict[str, Any]] = {}

        discord_config = self.site_config.get("discord", {})
        self.discord_webhook = discord_config.get("finished_webhook", "")

        self.twilio_settings = self.site_config.get("twilio", {})
        required_twilio_keys = ("account_sid", "auth_token", "service_sid")
        self.has_twilio_config = all(self.twilio_settings.get(key) for key in required_twilio_keys)

        if not TWILIO_AVAILABLE:
            print("⚠️  Twilio library niet geïnstalleerd. Installeer met: pip install twilio")
        elif not self.has_twilio_config:
            print("⚠️  Twilio configuratie onvolledig. Vul account_sid, auth_token en service_sid in config in.")

        # Shared stop flag to abort processing once phone numbers run out
        self.stop_event = threading.Event()

    # ------------------------------------------------------------------ Helpers

    def _load_from_file(self, file_path: Path, file_type: str) -> List[str]:
        items: List[str] = []
        if not file_path.exists():
            print(f"⚠️  {file_type.capitalize()} bestand niet gevonden: {file_path}")
            return items

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        items.append(line)
            print(f"✅ {len(items)} {file_type} geladen vanuit {file_path.name}")
        except Exception as exc:
            print(f"❌ Fout bij laden van {file_type}: {exc}")
        return items

    def _load_accounts_from_csv(self, csv_file: Path) -> List[str]:
        accounts: List[str] = []
        if not csv_file.exists():
            print(f"⚠️  accounts.csv niet gevonden: {csv_file}")
            return accounts

        try:
            with open(csv_file, "r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    email = (row.get("email") or "").strip()
                    entered = (row.get("entered") or "").strip().lower()
                    if email and "@" in email and entered not in {"ja", "yes", "done"}:
                        accounts.append(email)
            print(f"✅ {len(accounts)} accounts beschikbaar voor verwerking")
        except Exception as exc:
            print(f"❌ Fout bij laden van accounts: {exc}")
        return accounts

    def _mark_account_entered(self, email: str) -> None:
        if not self.accounts_csv.exists():
            return

        try:
            rows: List[Dict[str, str]] = []
            with open(self.accounts_csv, "r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames or ["email", "entered", "timestamp"]
                for row in reader:
                    if (row.get("email") or "").strip().lower() == email.lower():
                        row["entered"] = "ja"
                        row["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    rows.append(row)

            with open(self.accounts_csv, "w", encoding="utf-8", newline="") as handle:
                fieldnames = fieldnames or ["email", "entered", "timestamp"]
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as exc:
            print(f"⚠️  Fout bij bijwerken accounts.csv: {exc}")

    def _send_discord_notification(self, email: str, success: bool) -> None:
        if not self.discord_webhook:
            return
        try:
            import requests

            payload = {
                "content": (
                    f"{'✅' if success else '❌'} **Seated Signup {'Gelukt' if success else 'Mislukt'}**\n"
                    f"📧 Email: `{email}`\n"
                    f"🕐 Tijd: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                "username": "Seated Automation",
            }
            response = requests.post(self.discord_webhook, json=payload, timeout=10)
            if response.status_code not in {200, 204}:
                print(f"⚠️  Discord webhook gaf status {response.status_code}")
        except Exception as exc:
            print(f"⚠️  Fout bij verzenden Discord melding: {exc}")

    def _get_or_create_proxy(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        unused_proxy = self.get_random_unused_proxy()
        if unused_proxy:
            return unused_proxy, None

        if not self.proxy_strings:
            raise RuntimeError("Geen proxies beschikbaar (proxies.txt leeg?)")

        available = [p for p in self.proxy_strings if p not in self.used_proxy_strings]
        if not available:
            available = list(self.proxy_strings)

        proxy_string = random.choice(available)
        self.used_proxy_strings.add(proxy_string)

        host, port, username, password = proxy_string.strip().split(":")
        proxy_data = {
            "type": "http",
            "host": host,
            "port": int(port),
            "login": username,
            "password": password,
            "name": f"Proxy-{host}-{port}",
        }

        created_proxy = self.create_proxy(proxy_data)
        return created_proxy, proxy_string

    def create_profile(self, proxy_data: Optional[Dict[str, Any]] = None, name_prefix: str = "SEATED") -> Optional[Dict[str, Any]]:
        if not proxy_data:
            proxy_data, proxy_string = self._get_or_create_proxy()
            if proxy_data:
                self.profile_proxy_string_map[proxy_data.get("id")] = proxy_string

        profile = super().create_profile(proxy_data=proxy_data, name_prefix=name_prefix)
        if profile and proxy_data:
            profile_id = profile["id"]
            self.profile_proxy_map[profile_id] = proxy_data
            source_key = proxy_data.get("id")
            if source_key and source_key in self.profile_proxy_string_map:
                self.profile_proxy_string_map[profile_id] = self.profile_proxy_string_map.pop(source_key)
        return profile

    def _process_single_item(self, site_config: Dict[str, Any], data_item: str, task_number: int) -> bool:
        profile = None
        driver = None
        success = False

        try:
            if self.stop_event.is_set():
                print(f"⏹️  Stop aangevraagd – overslaan van {data_item}")
                return False

            profile = self.create_profile(name_prefix=f"SEATED{task_number}")
            if not profile:
                return False

            driver = self.create_driver(profile["id"])
            if not driver:
                return False

            try:
                success = self._execute_site_automation(driver, site_config, data_item, task_number)
            except NoPhoneNumbersAvailable as exc:
                print(f"⛔ {exc}")
                self.stop_event.set()
                raise

            return success
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            proxy_data = None
            proxy_string = None
            if profile:
                profile_id = profile.get("id")
                proxy_data = self.profile_proxy_map.pop(profile_id, None)
                proxy_string = self.profile_proxy_string_map.pop(profile_id, None)
            try:
                self._cleanup_profile_and_proxy(
                    profile=profile,
                    proxy=proxy_data,
                    success=success,
                    proxy_string=proxy_string,
                    proxies_file=str(self.proxies_file) if self.proxies_file else None,
                )
            except Exception as exc:
                print(f"⚠️  Fout bij cleanup: {exc}")

    # ----------------------------------------------------------------- Automation

    def _find_clickable(self, driver, selectors: List[tuple[str, str]], timeout: int = 12):
        for selector_type, value in selectors:
            try:
                if selector_type == "css":
                    element = WebDriverWait(driver, timeout).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, value))
                    )
                else:
                    element = WebDriverWait(driver, timeout).until(
                        EC.element_to_be_clickable((By.XPATH, value))
                    )
                if element and element.is_displayed():
                    return element
            except TimeoutException:
                continue
        return None

    def _find_present(self, driver, selectors: List[tuple[str, str]], timeout: int = 10):
        for selector_type, value in selectors:
            try:
                if selector_type == "css":
                    element = WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, value))
                    )
                else:
                    element = WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, value))
                    )
                if element:
                    return element
            except TimeoutException:
                continue
        return None

    def _wait_for_presence(self, driver, selectors: List[tuple[str, str]], timeout: int = 6) -> bool:
        return self._find_present(driver, selectors, timeout=timeout) is not None

    def _click_with_retries(
        self,
        driver,
        element,
        description: str = "element",
        verify_selectors: Optional[List[tuple[str, str]]] = None,
        max_attempts: int = 3,
    ) -> bool:
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                self.human_click(driver, element)
            except Exception as exc:
                last_error = exc

            if not verify_selectors:
                return True

            if self._wait_for_presence(driver, verify_selectors, timeout=5):
                return True

            random_delay(0.4, 0.9)

            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                    element,
                )
            except Exception as exc:
                last_error = exc

            random_delay(0.2, 0.5)

            try:
                driver.execute_script("arguments[0].click();", element)
            except Exception as exc:
                last_error = exc

            if self._wait_for_presence(driver, verify_selectors, timeout=4):
                return True

            random_delay(0.6, 1.0)

        if last_error:
            print(f"❌ Kon {description} niet activeren na {max_attempts} pogingen: {last_error}")
        else:
            print(f"❌ Kon {description} niet activeren na {max_attempts} pogingen.")
        return False

    def _execute_site_automation(self, driver, site_config: Dict[str, Any], email: str, task_number: int) -> bool:
        print(f"\n🎯 [TASK-{task_number}] Start Seated signup voor {email}")

        try:
            driver.get(self.target_url)
        except Exception as exc:
            print(f"❌ [TASK-{task_number}] Kon pagina niet openen: {exc}")
            return False

        random_delay(2.5, 4.5)
        self.simulate_akamai_behavior(driver, duration=random.uniform(2, 4))
        self.random_mouse_movement(driver)
        self.human_scroll(driver, scroll_count=random.randint(2, 4))

        # Zoek Sign Up button
        sign_up_selectors = [
            ("css", "a[data-test-on-sale-date-link]"),
            ("xpath", "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign up')]"),
            ("xpath", "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'get password')]"),
            ("xpath", "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign up')]"),
        ]

        if self.stop_event.is_set():
            raise NoPhoneNumbersAvailable("Stop aangevraagd nadat telefoonnummers op zijn")

        sign_up_button = self._find_clickable(driver, sign_up_selectors, timeout=15)
        if not sign_up_button:
            sign_up_button = self._find_present(driver, sign_up_selectors, timeout=12)
        if not sign_up_button:
            print(f"❌ [TASK-{task_number}] Sign Up knop niet gevonden")
            return False

        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", sign_up_button)
            random_delay(0.6, 1.2)
        except Exception:
            pass

        first_step_fields = [
            ("css", "input[data-test-first-name]"),
            ("css", "input[name='firstName']"),
            ("css", "input[data-first-name]"),
        ]

        if not self._click_with_retries(
            driver,
            sign_up_button,
            description="Sign Up knop",
            verify_selectors=first_step_fields,
        ):
            return False

        random_delay(1.5, 2.5)

        # Vul formulier pagina 1
        name_data = generate_random_name()

        first_name_field = self._find_clickable(driver, first_step_fields)
        if not first_name_field:
            print(f"❌ [TASK-{task_number}] First name veld niet gevonden")
            return False
        self.human_click(driver, first_name_field)
        self.human_type(first_name_field, name_data["first"])

        last_name_field = self._find_clickable(driver, [
            ("css", "input[data-test-last-name]"),
            ("css", "input[name='lastName']"),
            ("css", "input[data-last-name]"),
        ])
        if not last_name_field:
            print(f"❌ [TASK-{task_number}] Last name veld niet gevonden")
            return False
        self.human_click(driver, last_name_field)
        self.human_type(last_name_field, name_data["last"])

        email_field = self._find_clickable(driver, [
            ("css", "input[data-test-email]"),
            ("css", "input[type='email']"),
        ])
        if not email_field:
            print(f"❌ [TASK-{task_number}] Email veld niet gevonden")
            return False
        self.human_click(driver, email_field)
        self.human_type(email_field, email)

        # Selecteer Nederland als landcode
        try:
            dropdown = self._find_clickable(driver, [
                ("css", "svg[viewBox='0 0 11 8']"),
                ("css", "button[data-test-country-dropdown]"),
            ])
            if dropdown:
                dropdown.click()
                random_delay(0.5, 1.0)
        except Exception:
            pass

        country_option = self._find_clickable(driver, [
            ("css", "div[data-test-calling-code='NL']"),
            ("xpath", "//div[contains(text(),'Netherlands')]"),
        ])
        if country_option:
            country_option.click()
            random_delay(0.8, 1.2)

        postcode_field = self._find_clickable(driver, [
            ("css", "input[data-test-postal-code]"),
            ("css", "input[name='postalCode']"),
        ])
        if postcode_field:
            self.human_click(driver, postcode_field)
            self.human_type(postcode_field, generate_dutch_postcode())

        age_checkbox = self._find_clickable(driver, [
            ("xpath", "//div[contains(text(),'13 years of age')]"),
            ("css", "div[data-test-age-confirmation]"),
            ("css", "div.w-5.h-5.rounded-full"),
        ])
        if age_checkbox:
            try:
                age_checkbox.click()
                random_delay(0.5, 1.0)
            except Exception:
                pass

        next_button = self._find_clickable(driver, [
            ("css", "button[data-test-next]"),
            ("xpath", "//button[contains(text(),'Next')]"),
            ("xpath", "//button[contains(text(),'Continue')]"),
        ])
        if not next_button:
            print(f"❌ [TASK-{task_number}] Next knop niet gevonden")
            return False

        self.human_click(driver, next_button)
        random_delay(2, 3)

        # Pagina 2: kies UK code voor telefoon
        uk_dropdown = self._find_clickable(driver, [
            ("css", "svg[viewBox='0 0 11 8']"),
            ("css", ".fill-current.w-3.h-3.pt-1"),
        ])
        if uk_dropdown:
            uk_dropdown.click()
            random_delay(0.5, 1.0)

        uk_option = self._find_clickable(driver, [
            ("css", "div[data-test-calling-code='GB']"),
            ("xpath", "//div[contains(text(),'United Kingdom')]"),
        ])
        if uk_option:
            uk_option.click()
            random_delay(0.6, 1.2)
        else:
            print(f"❌ [TASK-{task_number}] UK landcode niet gevonden")
            return False

        # Twilio telefoonnummer ophalen
        if not TWILIO_AVAILABLE or not self.has_twilio_config:
            print(f"❌ [TASK-{task_number}] Twilio niet beschikbaar of configuratie ontbreekt")
            return False

        twilio_api = TwilioAPI(
            self.twilio_settings["account_sid"],
            self.twilio_settings["auth_token"],
            self.twilio_settings["service_sid"],
        )

        phone_number = twilio_api.get_uk_phone_number(self.target_url)
        if not phone_number:
            self.stop_event.set()
            raise NoPhoneNumbersAvailable("Geen UK telefoonnummers meer beschikbaar voor deze Seated link – script wordt gestopt.")

        phone_field = self._find_clickable(driver, [
            ("css", "input[data-test-phone]"),
            ("css", "input[type='tel']"),
            ("css", "input[name='phone']"),
        ])
        if not phone_field:
            print(f"❌ [TASK-{task_number}] Telefoonveld niet gevonden")
            return False

        phone_field.clear()
        random_delay(0.2, 0.4)
        phone_field.click()
        for digit in phone_number:
            phone_field.send_keys(digit)
            random_delay(0.07, 0.18)

        verify_button = self._find_clickable(driver, [
            ("css", "button[data-test-next]"),
            ("xpath", "//button[contains(text(),'Verify')]"),
            ("xpath", "//button[contains(text(),'Continue')]"),
        ])
        if verify_button:
            self.human_click(driver, verify_button)
            random_delay(2, 3)

        verification_code = twilio_api.get_verification_code(phone_number, timeout=self.sms_timeout_seconds)
        if not verification_code:
            print(f"❌ [TASK-{task_number}] Geen verificatiecode ontvangen")
            return False

        # Vul verificatiecode in (4 digits)
        for index, digit in enumerate(verification_code[:4], start=1):
            digit_field = self._find_clickable(driver, [
                ("css", f"input[data-test-code-digit{index}]"),
                ("css", f"input[data-code-digit{index}]"),
            ], timeout=6)
            if not digit_field:
                tel_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='tel']")
                if len(tel_inputs) >= index:
                    digit_field = tel_inputs[index - 1]
            if digit_field:
                digit_field.clear()
                digit_field.send_keys(digit)
                random_delay(0.3, 0.6)

        # Wacht op bevestiging
        try:
            confirmation = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test-confirmation]"))
            )
        except TimeoutException:
            print(f"❌ [TASK-{task_number}] Geen bevestiging gevonden na code invoer")
            return False

        if confirmation and "signed up" in confirmation.text.lower():
            print(f"🎉 [TASK-{task_number}] Signup succesvol voor {email}")
            self._mark_account_entered(email)
            twilio_api.mark_success(phone_number, self.target_url)
            self._send_discord_notification(email, True)
            return True

        print(f"⚠️  [TASK-{task_number}] Onverwachte bevestigingspagina, controleer handmatig")
        self._mark_account_entered(email)
        self._send_discord_notification(email, True)
        return True

    # ----------------------------------------------------------------- Public API

    def run(self) -> None:
        print("\n🚀 Seated Signup Automation")
        print(f"📧 Accounts: {len(self.accounts)}")
        print(f"🧵 Threads: {self.threads}")
        print(f"🌐 URL: {self.target_url}\n")

        if not self.accounts:
            print("❌ Geen accounts om te verwerken.")
            return

        site_config = {"name": "Seated", "url": self.target_url}

        # Lazy proxy loading (handled per profile)
        self.proxies = []

        self.run_automation(site_config, self.accounts, threads=self.threads)


def main() -> None:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        config_dir = exe_dir / "signups" / "seated"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "seated_config.json"
        if not config_file.exists() and hasattr(sys, "_MEIPASS"):
            bundled = Path(sys._MEIPASS) / "signups" / "seated" / "seated_config.json"  # type: ignore[attr-defined]
            if bundled.exists():
                import shutil

                shutil.copy2(bundled, config_file)
    else:
        project_root = Path(__file__).parent.parent.parent
        config_dir = project_root / "dist" / "signups" / "seated"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "seated_config.json"

    if not config_file.exists():
        print(f"❌ Config file niet gevonden: {config_file}")
        return

    automation = SeatedAutomation(str(config_file))
    automation.run()


if __name__ == "__main__":
    main()


