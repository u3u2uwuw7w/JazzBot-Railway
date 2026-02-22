import os
import time
import threading
import queue
import logging
import re
import telebot
from playwright.sync_api import sync_playwright

# ==================== TRY IMPORT PYTUBEFIX ====================
try:
    from pytubefix import YouTube
    from pytubefix.cli import on_progress
    PYTUBEFIX_AVAILABLE = True
    # Check if callback exists
    import inspect
    sig = inspect.signature(YouTube.__init__)
    HAS_CALLBACK = 'on_oauth_callback' in sig.parameters
except ImportError:
    PYTUBEFIX_AVAILABLE = False
    HAS_CALLBACK = False

# 🔑 APNA TOKEN AUR CHAT ID YAHI DAALO
TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO)

task_queue = queue.Queue()
is_working = False

login_state = {"waiting_for": None, "number": None, "otp": None, "event": threading.Event()}
youtube_state = {"waiting_for": None, "url": None, "event": threading.Event()}

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 Bot Online! YouTube + Direct Links")

@bot.message_handler(commands=['continue'])
def continue_yt(m):
    if youtube_state["waiting_for"] == "continue":
        youtube_state["waiting_for"] = None
        youtube_state["event"].set()
        bot.reply_to(m, "✅ Continuing...")

@bot.message_handler(commands=['login'])
def login(m):
    login_state["waiting_for"] = "number"
    bot.reply_to(m, "📱 Jazz number do:")

# ==================== JAZZ LOGIN ====================
@bot.message_handler(func=lambda m: login_state["waiting_for"] == "number")
def get_num(m):
    login_state["number"] = m.text
    login_state["waiting_for"] = "otp"
    bot.reply_to(m, "⏳ OTP bheja, ab OTP do:")
    threading.Thread(target=jazz_login).start()

@bot.message_handler(func=lambda m: login_state["waiting_for"] == "otp")
def get_otp(m):
    login_state["otp"] = m.text
    login_state["waiting_for"] = None
    login_state["event"].set()

def jazz_login():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://cloud.jazzdrive.com.pk/")
            page.fill("input[type='text']", login_state["number"])
            page.click("button:has-text('Get OTP')")
            bot.send_message(CHAT_ID, "📩 OTP bheja!")
            login_state["event"].wait(60)
            if login_state["otp"]:
                page.fill("input[type='text']", login_state["otp"])
                page.click("button:has-text('Verify')")
                time.sleep(3)
                browser.contexts[0].storage_state(path="state.json")
                bot.send_message(CHAT_ID, "🎉 Login success!")
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Login error: {e}")

# ==================== LINK HANDLER ====================
def is_youtube(text):
    return re.search(r'(youtube\.com|youtu\.be)', text) is not None

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle(m):
    link = m.text.strip()
    if is_youtube(link) and PYTUBEFIX_AVAILABLE:
        task_queue.put(("youtube", link))
        bot.reply_to(m, f"✅ YouTube added! Position: {task_queue.qsize()}")
    else:
        task_queue.put(("direct", link))
        bot.reply_to(m, f"✅ Direct added! Position: {task_queue.qsize()}")
    
    global is_working
    if not is_working:
        threading.Thread(target=worker).start()

def worker():
    global is_working
    is_working = True
    while not task_queue.empty():
        t, d = task_queue.get()
        try:
            if t == "youtube":
                process_youtube(d)
            else:
                process_direct(d)
        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ Error: {e}")
        time.sleep(2)
    is_working = False

# ==================== YOUTUBE ====================
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, "▶️ Processing YouTube link...")

        if HAS_CALLBACK:
            def auth_cb(code, ver_url):
                bot.send_message(CHAT_ID,
                    f"🔐 **LOGIN CODE**\n\nURL: {ver_url}\nCode: `{code}`\n\nVerify karo, phir /continue")
                youtube_state["waiting_for"] = "continue"
                youtube_state["event"].clear()
            
            yt = YouTube(url, use_oauth=True, allow_oauth_cache=True, on_oauth_callback=auth_cb)
        else:
            # Fallback (should not happen if latest installed)
            bot.send_message(CHAT_ID, "⚠️ Old pytubefix. Send /continue after verifying.")
            yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
            youtube_state["waiting_for"] = "continue"
            youtube_state["event"].clear()

        if youtube_state["waiting_for"] == "continue":
            youtube_state["event"].wait(300)
            if youtube_state["waiting_for"]:
                bot.send_message(CHAT_ID, "❌ Timeout")
                return

        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")

        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video", callback_data=f"v_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio", callback_data=f"a_{url}")
        )
        bot.send_message(CHAT_ID, "Choose:", reply_markup=markup)
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ YouTube error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    if call.data.startswith("v_"):
        threading.Thread(target=dl_youtube, args=(call.data[2:], call.message.chat.id, "video")).start()
    elif call.data.startswith("a_"):
        threading.Thread(target=dl_youtube, args=(call.data[2:], call.message.chat.id, "audio")).start()

def dl_youtube(url, chat_id, mode):
    try:
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
        if mode == "audio":
            f = yt.streams.get_audio_only().download(DOWNLOAD_DIR)
            base, _ = os.path.splitext(f)
            new = base + ".mp3"
            os.rename(f, new)
            filename = new
        else:
            filename = yt.streams.get_highest_resolution().download(DOWNLOAD_DIR)
        
        size = os.path.getsize(filename) / (1024*1024)
        bot.send_message(chat_id, f"✅ Downloaded {size:.1f}MB")
        upload_jazz(filename)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Download error: {e}")

# ==================== DIRECT LINK ====================
def process_direct(link):
    name = f"video_{int(time.time())}.mp4"
    path = os.path.join(DOWNLOAD_DIR, name)
    os.system(f'aria2c -x 16 -d "{DOWNLOAD_DIR}" -o "{name}" "{link}"')
    if os.path.exists(path):
        size = os.path.getsize(path) / (1024*1024)
        bot.send_message(CHAT_ID, f"✅ Downloaded {size:.1f}MB")
        upload_jazz(path)

# ==================== JAZZ UPLOAD ====================
def upload_jazz(path):
    try:
        bot.send_message(CHAT_ID, "⬆️ Uploading to Jazz Drive...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = ctx.new_page()
            page.goto("https://cloud.jazzdrive.com.pk/")
            time.sleep(5)
            if page.locator("text='Sign Up/In'").is_visible():
                bot.send_message(CHAT_ID, "⚠️ Login expired. Use /login")
                return
            with page.expect_file_chooser() as fc:
                page.click("text='Upload files'")
            fc.value.set_files(os.path.abspath(path))
            time.sleep(5)
            try:
                page.click("button:has-text('Yes')", timeout=3000)
            except:
                pass
            bot.send_message(CHAT_ID, f"✅ Uploaded {os.path.basename(path)}")
            os.remove(path)
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Upload error: {e}")

# ==================== START ====================
if __name__ == "__main__":
    try:
        bot.send_message(CHAT_ID, "🟢 **Bot Online!** (Latest pytubefix)")
    except:
        pass
    bot.polling(non_stop=True)
