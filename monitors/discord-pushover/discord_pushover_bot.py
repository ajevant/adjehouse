#!/usr/bin/env python3
"""
Discord Pushover Bot
===================
Monitors Discord messages and sends Pushover notifications
Uses JSON config instead of .env

NOTE: This file is for development/editing purposes only.
The actual bot code is integrated in adjehouse_main.py and bundled in the EXE.
"""

import os
import sys
import json
import time
import logging
from typing import Set
from pathlib import Path

import requests
import discord
from discord import Message

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent.parent

# Config path
CONFIG_FILE = BASE_DIR / 'monitors' / 'discord-pushover' / 'discord_pushover_config.json'

def load_config():
    """Load configuration from JSON file"""
    if not CONFIG_FILE.exists():
        print(f"[ERROR] Config file not found: {CONFIG_FILE}")
        return None
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return None

# Load config
config = load_config()
if not config:
    raise SystemExit("Failed to load configuration")

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
    raise SystemExit(f"Missing required config values: {', '.join(missing)}")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# Cooldown per channel to avoid spam
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
        logging.info("Pushover sent.")
    except Exception as e:
        logging.exception(f"Pushover error: {e}")

@client.event
async def on_ready():
    """Called when bot connects to Discord"""
    logging.info(f"Logged in as {client.user} (id={client.user.id})")
    if ALLOWED_CHANNEL_IDS:
        logging.info(f"Alerts only in channels: {', '.join(map(str, ALLOWED_CHANNEL_IDS))}")
    else:
        logging.info("Alerts in all readable channels.")

def mentioned_target_user(msg: Message) -> bool:
    """True if message mentions you or @everyone/@here."""
    # Check personal mention
    for m in msg.mentions:
        if getattr(m, "id", None) == TARGET_USER_ID:
            return True

    content = msg.content or ""

    # Fallback direct mention
    if f"<@{TARGET_USER_ID}>" in content or f"<@!{TARGET_USER_ID}>" in content:
        return True

    # @everyone or @here
    if msg.mention_everyone:
        return True
    if "@everyone" in content or "@here" in content:
        return True

    return False

@client.event
async def on_message(message: Message):
    """Called when a message is received"""
    if message.author == client.user:
        return

    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    if mentioned_target_user(message):
        now = time.time()
        last = LAST_ALERT_TS.get(message.channel.id, 0)
        if now - last < COOLDOWN_SECONDS:
            logging.info("Cooldown active; skipped alert.")
            return
        LAST_ALERT_TS[message.channel.id] = now

        guild_name = getattr(message.guild, "name", "DM/Unknown")
        channel_name = getattr(message.channel, "name", None) or str(message.channel)
        author = message.author.display_name

        title = f"Discord ping in #{channel_name} ({guild_name})"
        preview = (message.content or "").strip() or "[No text / attachment]"
        body = f"From: {author}\nChannel: #{channel_name}\nServer: {guild_name}\n\n{preview}"

        send_pushover(title, body)

def main():
    """Main entry point"""
    try:
        client.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot error: {e}")
        raise

if __name__ == "__main__":
    main()




