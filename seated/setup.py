#!/usr/bin/env python3
"""
Seated Automation Setup
=======================

Dit script helpt je om de Seated automation in te stellen.
"""

import json
import os

def create_config():
    """Maak config.json bestand"""
    print("🎫 Seated Event Reminder Automation Setup")
    print("=" * 50)
    
    # Vraag om Dolphin Anty token
    print("\n📡 Dolphin Anty Token:")
    print("   1. Ga naar https://anty.dolphin.ru.com/panel/#/api")
    print("   2. Maak een nieuwe API token aan")
    print("   3. Kopieer de token hieronder")
    
    token = input("\n🔑 Voer je Dolphin Anty token in: ").strip()
    
    if not token:
        print("❌ Geen token ingevoerd!")
        return False
    
    # Vraag om Twilio configuratie
    print("\n📱 Twilio SMS Configuratie:")
    print("   1. Ga naar https://console.twilio.com/")
    print("   2. Kopieer je Account SID, Auth Token en Service SID")
    
    twilio_sid = input("\n🔑 Voer je Twilio Account SID in: ").strip()
    twilio_auth = input("🔑 Voer je Twilio Auth Token in: ").strip()
    twilio_service = input("🔑 Voer je Twilio Service SID in: ").strip()
    
    if not all([twilio_sid, twilio_auth, twilio_service]):
        print("❌ Twilio configuratie incomplete!")
        return False
    
    # Vraag om aantal threads
    print("\n🔄 Aantal threads (browsers tegelijk):")
    print("   - 1 = Veilig voor testing")
    print("   - 3-5 = Normaal voor productie")
    print("   - 5+ = Alleen als je veel proxies hebt")
    
    try:
        threads = int(input("Aantal threads (1-10): ") or "5")
        if threads < 1 or threads > 10:
            threads = 5
    except ValueError:
        threads = 5
    
    # Vraag om test mode
    print("\n🧪 Test Mode:")
    print("   - True = Test met 1 random email")
    print("   - False = Gebruik echte emails uit emails.txt")
    
    test_mode = input("Test mode? (y/n): ").lower().strip() in ['y', 'yes', 'ja', 'j']
    
    # Maak config
    config = {
        "dolphin_token": token,
        "twilio_account_sid": twilio_sid,
        "twilio_auth_token": twilio_auth,
        "twilio_service_sid": twilio_service,
        "max_threads": threads,
        "test_mode": test_mode,
        "target_url": "https://link.seated.com/cd6659bf-4e2c-4b71-a106-5e24355a8794",
        "random_delay_min": 1.5,
        "random_delay_max": 4.0,
        "use_mouse_movements": True,
        "use_random_typing_speed": True
    }
    
    # Schrijf config.json
    try:
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\n✅ config.json aangemaakt!")
        print(f"   - Dolphin Token: {token[:20]}...")
        print(f"   - Twilio SID: {twilio_sid[:20]}...")
        print(f"   - Threads: {threads}")
        print(f"   - Test mode: {test_mode}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Fout bij aanmaken config.json: {e}")
        return False

def check_requirements():
    """Check of alle requirements geïnstalleerd zijn"""
    print("\n🔍 Controleren requirements...")
    
    try:
        import requests
        import selenium
        import twilio
        print("✅ Alle Python packages zijn geïnstalleerd")
        return True
    except ImportError as e:
        print(f"❌ Missing package: {e}")
        print("💡 Run: pip3 install -r requirements.txt")
        return False

def main():
    """Main setup function"""
    print("🚀 Seated Automation Setup")
    print("=" * 30)
    
    # Check requirements
    if not check_requirements():
        return
    
    # Check of config al bestaat
    if os.path.exists('config.json'):
        print("\n⚠️  config.json bestaat al!")
        overwrite = input("Overschrijven? (y/n): ").lower().strip()
        if overwrite not in ['y', 'yes', 'ja', 'j']:
            print("🛑 Setup geannuleerd")
            return
    
    # Maak config
    if create_config():
        print("\n🎉 Setup voltooid!")
        print("\n📋 Volgende stappen:")
        print("   1. Start Dolphin Anty applicatie")
        print("   2. Start Local API (Settings → API)")
        print("   3. Voeg proxies toe in Dolphin Anty")
        print("   4. Configureer Twilio met UK telefoonnummers")
        print("   5. Voeg emails toe aan emails.txt")
        print("   6. Run: python3 seated_automation.py")
    else:
        print("\n❌ Setup mislukt!")

if __name__ == "__main__":
    main()
