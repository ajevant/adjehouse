#!/bin/bash

# Seated Automation Launcher
# Dubbelklik dit bestand om te starten

cd "$(dirname "$0")"
python3 seated_automation.py

# Wacht tot gebruiker Enter drukt
echo ""
echo "Druk Enter om te sluiten..."
read
