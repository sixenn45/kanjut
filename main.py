import asyncio
import logging
import sqlite3
import json
import random
import re
import os
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerChannel

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV VARIABLES (set di Railway)
API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH") or ""
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("API_ID, API_HASH, BOT_TOKEN WAJIB di set di Railway Variables!")

# DATABASE SQLITE
DB_FILE = "/data/bot_sessions.db"  # path persistent di Railway (pakai volume)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
                 name TEXT PRIMARY KEY,
                 data TEXT NOT NULL)''')
    conn.commit()
    conn.close()

def save_account(name, data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO accounts (name, data) VALUES (?, ?)", (name, json.dumps(data)))
    conn.commit()
    conn.close()

def load_all_accounts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, data FROM accounts")
    rows = c.fetchall()
    conn.close()
    return {name: json.loads(data) for name, data in rows}

def delete_account(name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE name = ?", (name,))
    conn.commit()
    conn.close()

# INIT DB
init_db()

# LOAD AKUN
akun_data = load_all_accounts()

# CACHE CLIENTS
clients = {}

# BOT CLIENT
bot = TelegramClient('bot', API_ID, API_HASH)

# EMOJI RANDOM
def generate_random_emoji():
    emojis = ['🔥','😈','💀','👹','⚡','🎯','🚀','💥','💰','💸','🤑','💎','⭐','🐍','🦂','🔫','💣']
    return ' '.join(random.sample(emojis, k=random.randint(2, 5)))

def add_emoji(pesan):
    em = generate_random_emoji()
    return f"{em} {pesan} {em}"

# GET CLIENT
async def get_client(name):
    if name not in akun_data:
        return None
    if name not in clients:
        try:
            session_str = akun_data[name]["session"]
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.start()
            clients[name] = client
            logger.info(f"[+] {name} connected")
        except Exception as e:
            logger.error(f"[-] {name} gagal connect: {e}")
            return None
    return clients.get(name)

# SPAM LOOP
async def spam_loop(name):
    client = await get_client(name)
    if not client: return
    data = akun_data[name]
    while data.get('spam_running', False):
        if not data.get('pesan_list', []):
            await asyncio.sleep(10)
            continue
        pesan = random.choice(data['pesan_list'])
        if data.get('auto_emoji', True):
            pesan = add_emoji(pesan)
        for grup in data.get('groups', []):
            try:
                await client.send_message(grup, pesan, silent=True)
                await asyncio.sleep(data.get('delay', 90) + random.uniform(-data.get('jitter', 20), data.get('jitter', 20)))
            except errors.FloodWaitError as e:
                logger.warning(f"Flood wait {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(e)
        await asyncio.sleep(5)

# FORWARD LOOP
async def forward_loop(name):
    client = await get_client(name)
    if not client: return
    data = akun_data[name]
    while data.get('forward_running', False):
        for source in data.get('forward_sources', []):
            try:
                async for msg in client.iter_messages(source, limit=1):
                    for target in data.get('forward_targets', []):
                        await client.forward_messages(target, msg)
                        await asyncio.sleep(data.get('forward_delay', 120) + random.uniform(-data.get('jitter', 20), data.get('jitter', 20)))
            except Exception as e:
                logger.error(e)
        await asyncio.sleep(10)

# START ALL LOOPS
async def start_loops():
    for name in akun_data:
        data = akun_data[name]
        if data.get('spam_running', False):
            asyncio.create_task(spam_loop(name))
        if data.get('forward_running', False):
            asyncio.create_task(forward_loop(name))

# BOT COMMANDS
@bot.on(events.NewMessage(pattern=r'^/addakun (\S+) (.+)'))
async def add_akun(event):
    name, session_str = event.pattern_match.group(1), event.pattern_match.group(2)
    if name in akun_data:
        await event.reply(f"Akun '{name}' sudah ada!")
        return
    data = {
        "session": session_str,
        "groups": [],
        "pesan_list": [],
        "forward_sources": [],
        "forward_targets": [],
        "auto_emoji": True,
        "delay": 90,
        "jitter": 20,
        "forward_delay": 120,
        "spam_running": False,
        "forward_running": False
    }
    save_account(name, data)
    akun_data[name] = data
    await event.reply(f"✅ Akun '{name}' ditambahkan! Coba /cek_akun")
    # Auto connect
    client = await get_client(name)
    if client:
        await event.reply(f"Login berhasil sebagai {name}")

@bot.on(events.NewMessage(pattern=r'^/deleteakun (\S+)'))
async def delete_akun(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply(f"Akun '{name}' tidak ditemukan!")
        return
    delete_account(name)
    del akun_data[name]
    if name in clients:
        del clients[name]
    await event.reply(f"🗑️ Akun '{name}' dihapus!")

@bot.on(events.NewMessage(pattern=r'^/addpesan (\S+) (.+)'))
async def add_pesan(event):
    name, pesan = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['pesan_list'].append(pesan)
    save_account(name, akun_data[name])
    await event.reply(f"✅ Pesan ditambahkan ke {name}")

@bot.on(events.NewMessage(pattern=r'^/deletepesan (\S+)'))
async def delete_pesan(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['pesan_list'] = []
    save_account(name, akun_data[name])
    await event.reply(f"🗑️ Semua pesan di {name} dihapus!")

@bot.on(events.NewMessage(pattern=r'^/addgrup (\S+) (.+)'))
async def add_grup(event):
    name, grup = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['groups'].append(grup)
    save_account(name, akun_data[name])
    await event.reply(f"✅ Grup {grup} ditambahkan ke {name}")

@bot.on(events.NewMessage(pattern=r'^/forward_add (\S+) (.+)'))
async def forward_add(event):
    name, target = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_targets'].append(target)
    save_account(name, akun_data[name])
    await event.reply(f"✅ Forward target {target} ditambahkan ke {name}")

@bot.on(events.NewMessage(pattern=r'^/listgrup (\S+)'))
async def list_grup(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    groups = akun_data[name]['groups']
    await event.reply(f"Grup {name}:\n" + "\n".join(groups) if groups else "Kosong")

@bot.on(events.NewMessage(pattern=r'^/listpesan (\S+)'))
async def list_pesan(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    pesan = akun_data[name]['pesan_list']
    await event.reply(f"Pesan {name}:\n" + "\n".join(pesan) if pesan else "Kosong")

@bot.on(events.NewMessage(pattern=r'^/setdelay (\S+) (\d+)'))
async def set_delay(event):
    name, delay = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['delay'] = delay
    save_account(name, akun_data[name])
    await event.reply(f"Delay {name} diatur ke {delay}s")

@bot.on(events.NewMessage(pattern=r'^/setjitter (\S+) (\d+)'))
async def set_jitter(event):
    name, jitter = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['jitter'] = jitter
    save_account(name, akun_data[name])
    await event.reply(f"Jitter {name} diatur ke ±{jitter}s")

@bot.on(events.NewMessage(pattern=r'^/setdelay_forward (\S+) (\d+)'))
async def set_delay_forward(event):
    name, delay = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_delay'] = delay
    save_account(name, akun_data[name])
    await event.reply(f"Forward delay {name} diatur ke {delay}s")

@bot.on(events.NewMessage(pattern=r'^/spam_on (\S+)'))
async def spam_on(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['spam_running'] = True
    save_account(name, akun_data[name])
    asyncio.create_task(spam_loop(name))
    await event.reply(f"Spam ON untuk {name}")

@bot.on(events.NewMessage(pattern=r'^/spam_off (\S+)'))
async def spam_off(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['spam_running'] = False
    save_account(name, akun_data[name])
    await event.reply(f"Spam OFF untuk {name}")

@bot.on(events.NewMessage(pattern=r'^/forward_on (\S+)'))
async def forward_on(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_running'] = True
    save_account(name, akun_data[name])
    asyncio.create_task(forward_loop(name))
    await event.reply(f"Forward ON untuk {name}")

@bot.on(events.NewMessage(pattern=r'^/forward_off (\S+)'))
async def forward_off(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_running'] = False
    save_account(name, akun_data[name])
    await event.reply(f"Forward OFF untuk {name}")

@bot.on(events.NewMessage(pattern=r'^/cek_akun'))
async def cek_akun(event):
    text = "Daftar akun:\n"
    for name in akun_data:
        status = "Online" if name in clients else "Offline"
        text += f"- {name}: {status} (pesan: {len(akun_data[name]['pesan_list'])}, grup: {len(akun_data[name]['groups'])})\n"
    await event.reply(text or "Belum ada akun!")

# START BOT
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot utama online!")
    await start_loops()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
