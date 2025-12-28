import asyncio
import logging
import sqlite3
import json
import random
import os
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from telethon.tl.custom import Button

# Logging (ubah ke WARNING kalau log terlalu banyak)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ENV VARIABLES (set di Railway)
API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH") or ""
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("API_ID, API_HASH, BOT_TOKEN WAJIB di set di Railway Variables!")

# DATABASE SQLITE (persistent di /data)
DB_FILE = "/data/bot_sessions.db"

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

# SPAM LOOP (serentak ke semua grup)
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
        
        # Kirim serentak ke semua grup
        for grup in data.get('groups', []):
            try:
                await client.send_message(grup, pesan, silent=True)
            except errors.FloodWaitError as e:
                logger.warning(f"Flood wait {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(e)
        
        # Tunggu delay + jitter setelah kirim ke semua
        await asyncio.sleep(data.get('delay', 90) + random.uniform(-data.get('jitter', 20), data.get('jitter', 20)))

# FORWARD LOOP (serentak ke semua grup)
async def forward_loop(name):
    client = await get_client(name)
    if not client: return
    data = akun_data[name]
    sources = data.get('forward_sources', [])
    if not sources:
        logger.info(f"{name}: forward aktif tapi gak ada source → skip")
        return
    while data.get('forward_running', False):
        for source in sources:
            try:
                async for msg in client.iter_messages(source, limit=1):
                    if msg:
                        # Forward serentak ke semua grup
                        for target in data.get('groups', []):
                            await client.forward_messages(target, msg)
                        await asyncio.sleep(data.get('forward_delay', 120) + random.uniform(-data.get('jitter', 20), data.get('jitter', 20)))
            except Exception as e:
                logger.error(f"Error forward {name} dari {source}: {e}")
        await asyncio.sleep(10)

# START ALL LOOPS
async def start_loops():
    for name in akun_data:
        data = akun_data[name]
        if data.get('spam_running', False):
            asyncio.create_task(spam_loop(name))
        if data.get('forward_running', False):
            asyncio.create_task(forward_loop(name))

# SET COMMAND RESMI
async def set_bot_commands():
    commands = [
        BotCommand('menu', 'Lihat semua command'),
        BotCommand('addakun', 'Tambah akun'),
        BotCommand('deleteakun', 'Hapus akun'),
        BotCommand('addpesan', 'Tambah pesan spam'),
        BotCommand('deletepesan', 'Hapus semua pesan'),
        BotCommand('addgrup', 'Tambah grup (spam + forward target)'),
        BotCommand('forward_source', 'Tambah channel sumber forward'),
        BotCommand('listgrup', 'Lihat grup'),
        BotCommand('listpesan', 'Lihat pesan'),
        BotCommand('setdelay', 'Atur delay spam'),
        BotCommand('setjitter', 'Atur jitter'),
        BotCommand('setdelay_forward', 'Atur delay forward'),
        BotCommand('spam_on', 'Nyalain spam'),
        BotCommand('spam_off', 'Matikan spam'),
        BotCommand('forward_on', 'Nyalain forward'),
        BotCommand('forward_off', 'Matikan forward'),
        BotCommand('cek_akun', 'Cek akun')
    ]
    try:
        await bot.set_bot_commands(commands, BotCommandScopeDefault(), 'id')
        logger.info("Commands berhasil diset!")
    except Exception as e:
        logger.error(f"Gagal set commands: {e}")

# COMMAND /MENU
@bot.on(events.NewMessage(pattern=r'^/menu$'))
async def menu(event):
    menu_text = """
🔥 **JINX SPAM BOT MENU** 🔥

/addakun nama session_string → Tambah akun baru
/deleteakun nama → Hapus akun
/addpesan nama pesan → Tambah pesan spam
/deletepesan nama → Hapus semua pesan
/addgrup nama @grup → Tambah grup (spam + target forward)
/forward_source nama @channel → Tambah channel sumber forward
/listgrup nama → Lihat daftar grup
/listpesan nama → Lihat daftar pesan
/setdelay nama 90 → Atur delay spam
/setjitter nama 20 → Atur jitter
/setdelay_forward nama 120 → Atur delay forward
/spam_on nama → Nyalain spam
/spam_off nama → Matikan spam
/forward_on nama → Nyalain forward
/forward_off nama → Matikan forward
/cek_akun → Cek semua akun & status

Gunakan di chat privat dengan bot!
    """
    buttons = [
        [Button.inline("🔄 Refresh Menu", b'refresh_menu')],
        [Button.url("📢 Join Channel Jinx", "https://t.me/jinxchannel")]
    ]
    await event.reply(menu_text, buttons=buttons, parse_mode='md')

@bot.on(events.CallbackQuery(data=b'refresh_menu'))
async def refresh_menu(event):
    await event.answer("Menu di-refresh! 🔥")
    await menu(event)

# COMMAND ADD AKUN
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
        "auto_emoji": True,
        "delay": 90,
        "jitter": 20,
        "forward_delay": 120,
        "spam_running": False,
        "forward_running": False
    }
    save_account(name, data)
    akun_data[name] = data
    await event.reply(f"✅ Akun '{name}' ditambahkan!")
    client = await get_client(name)
    if client:
        await event.reply(f"Login berhasil sebagai {name}")

# COMMAND DELETE AKUN
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

# COMMAND ADD PESAN
@bot.on(events.NewMessage(pattern=r'^/addpesan (\S+) (.+)'))
async def add_pesan(event):
    name, pesan = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['pesan_list'].append(pesan)
    save_account(name, akun_data[name])
    await event.reply(f"✅ Pesan ditambahkan ke {name}")

# COMMAND DELETE PESAN
@bot.on(events.NewMessage(pattern=r'^/deletepesan (\S+)'))
async def delete_pesan(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['pesan_list'] = []
    save_account(name, akun_data[name])
    await event.reply(f"🗑️ Semua pesan di {name} dihapus!")

# COMMAND ADD GRUP (spam + forward target)
@bot.on(events.NewMessage(pattern=r'^/addgrup (\S+) (.+)'))
async def add_grup(event):
    name, grup = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    if grup not in akun_data[name]['groups']:
        akun_data[name]['groups'].append(grup)
        save_account(name, akun_data[name])
        await event.reply(f"✅ Grup {grup} ditambahkan ke {name} (spam + target forward)")
    else:
        await event.reply(f"Grup {grup} sudah ada di {name}")

# COMMAND ADD SOURCE FORWARD
@bot.on(events.NewMessage(pattern=r'^/forward_source (\S+) (.+)'))
async def forward_source(event):
    name, source = event.pattern_match.group(1), event.pattern_match.group(2)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    if source not in akun_data[name]['forward_sources']:
        akun_data[name]['forward_sources'].append(source)
        save_account(name, akun_data[name])
        await event.reply(f"✅ Channel sumber {source} ditambahkan ke {name}")
    else:
        await event.reply(f"Channel {source} sudah ada di {name}")

# COMMAND LIST GRUP
@bot.on(events.NewMessage(pattern=r'^/listgrup (\S+)'))
async def list_grup(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    groups = akun_data[name]['groups']
    await event.reply(f"Grup {name}:\n" + "\n".join(groups) if groups else "Kosong")

# COMMAND LIST PESAN
@bot.on(events.NewMessage(pattern=r'^/listpesan (\S+)'))
async def list_pesan(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    pesan = akun_data[name]['pesan_list']
    await event.reply(f"Pesan {name}:\n" + "\n".join(pesan) if pesan else "Kosong")

# COMMAND SET DELAY
@bot.on(events.NewMessage(pattern=r'^/setdelay (\S+) (\d+)'))
async def set_delay(event):
    name, delay = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['delay'] = delay
    save_account(name, akun_data[name])
    await event.reply(f"Delay {name} diatur ke {delay}s")

# COMMAND SET JITTER
@bot.on(events.NewMessage(pattern=r'^/setjitter (\S+) (\d+)'))
async def set_jitter(event):
    name, jitter = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['jitter'] = jitter
    save_account(name, akun_data[name])
    await event.reply(f"Jitter {name} diatur ke ±{jitter}s")

# COMMAND SET DELAY FORWARD
@bot.on(events.NewMessage(pattern=r'^/setdelay_forward (\S+) (\d+)'))
async def set_delay_forward(event):
    name, delay = event.pattern_match.group(1), int(event.pattern_match.group(2))
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_delay'] = delay
    save_account(name, akun_data[name])
    await event.reply(f"Forward delay {name} diatur ke {delay}s")

# COMMAND SPAM ON
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

# COMMAND SPAM OFF
@bot.on(events.NewMessage(pattern=r'^/spam_off (\S+)'))
async def spam_off(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['spam_running'] = False
    save_account(name, akun_data[name])
    await event.reply(f"Spam OFF untuk {name}")

# COMMAND FORWARD ON
@bot.on(events.NewMessage(pattern=r'^/forward_on (\S+)'))
async def forward_on(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    if not akun_data[name].get('forward_sources'):
        await event.reply("Tambahin source channel dulu pake /forward_source!")
        return
    akun_data[name]['forward_running'] = True
    save_account(name, akun_data[name])
    asyncio.create_task(forward_loop(name))
    await event.reply(f"Forward ON untuk {name}")

# COMMAND FORWARD OFF
@bot.on(events.NewMessage(pattern=r'^/forward_off (\S+)'))
async def forward_off(event):
    name = event.pattern_match.group(1)
    if name not in akun_data:
        await event.reply("Akun tidak ditemukan!")
        return
    akun_data[name]['forward_running'] = False
    save_account(name, akun_data[name])
    await event.reply(f"Forward OFF untuk {name}")

# COMMAND CEK AKUN
@bot.on(events.NewMessage(pattern=r'^/cek_akun$'))
async def cek_akun(event):
    text = "Daftar akun:\n"
    for name in akun_data:
        status = "Online" if name in clients else "Offline"
        text += f"- {name}: {status} (pesan: {len(akun_data[name]['pesan_list'])}, grup: {len(akun_data[name]['groups'])}, source: {len(akun_data[name]['forward_sources'])})\n"
    await event.reply(text or "Belum ada akun!")

# MAIN
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    await set_bot_commands()
    logger.info("Bot utama online!")
    await start_loops()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
