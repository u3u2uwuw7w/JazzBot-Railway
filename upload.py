import os
import time
import threading
import queue
import logging
import re
import telebot
from playwright.sync_api import sync_playwright
import yt_dlp

TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

task_queue = queue.Queue()
is_working = False

login_state = {
    "waiting_for": None, "number": None, "otp": None, "event": threading.Event()
}

youtube_auth_state = {
    "waiting_for": None, "url": None, "cookies_file": "youtube_cookies.txt", "event": threading.Event()
}

# ---------------------------
# COMMANDS
# ---------------------------
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🤖 **JAZZ 24/7 UPLOADER**\n✅ YouTube TV method active\n🔗 Link + Code milega")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"📊 Queue: {task_queue.qsize()} | Working: {is_working}")

@bot.message_handler(commands=['login'])
def login_start(message):
    login_state["waiting_for"] = "number"
    bot.reply_to(message, "📱 Jazz Number bhejo:")

@bot.message_handler(commands=['continue'])
def continue_youtube(message):
    if youtube_auth_state["waiting_for"] == "continue":
        youtube_auth_state["waiting_for"] = None
        youtube_auth_state["event"].set()
        bot.reply_to(message, "✅ Verification done! Continuing...")
    else:
        bot.reply_to(message, "❌ No pending verification")

# ---------------------------
# JAZZ LOGIN
# ---------------------------
@bot.message_handler(func=lambda m: login_state["waiting_for"] == "number")
def get_number(m):
    login_state["number"] = m.text
    login_state["waiting_for"] = "otp"
    bot.reply_to(m, "⏳ OTP bhej raha hoon...")
    threading.Thread(target=do_playwright_login).start()

@bot.message_handler(func=lambda m: login_state["waiting_for"] == "otp")
def get_otp(m):
    login_state["otp"] = m.text
    login_state["waiting_for"] = None
    login_state["event"].set()

def do_playwright_login():
    # Same as before — Jazz Drive login
    pass  # (code same rahega)

# ---------------------------
# LINK HANDLER
# ---------------------------
def is_youtube_link(text):
    return re.match(r'(https?://)?(www\.)?(youtube|youtu)\.(com|be)/.+', text) is not None

@bot.message_handler(func=lambda m: login_state["waiting_for"] is None and m.text and (m.text.startswith("http") or is_youtube_link(m.text)))
def handle_link(m):
    link = m.text.strip()
    task_queue.put(("youtube" if is_youtube_link(link) else "direct", link))
    bot.reply_to(m, f"✅ Added to queue! Position: {task_queue.qsize()}")
    if not is_working:
        threading.Thread(target=worker_loop).start()

def worker_loop():
    global is_working
    is_working = True
    while not task_queue.empty():
        t, d = task_queue.get()
        if t == "youtube":
            process_youtube(d)
        else:
            process_direct(d)
    is_working = False

# ---------------------------
# YOUTUBE PROCESSING (LINK + CODE METHOD)
# ---------------------------
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, "▶️ YouTube link process ho raha hai...")

        # Pehle check cookies
        if os.path.exists(youtube_auth_state["cookies_file"]):
            # Try direct download
            if try_download_with_cookies(url):
                return

        # Cookies nahi hain → TV code method
        bot.send_message(CHAT_ID, "⚠️ TV activation required. Code generate kar raha hoon...")

        # Playwright se code + link do
        code = get_tv_activation_code_from_youtube()

        if code:
            youtube_auth_state["waiting_for"] = "continue"
            youtube_auth_state["url"] = url

            # Wait for /continue
            youtube_auth_state["event"].clear()
            youtube_auth_state["event"].wait(timeout=300)

            if youtube_auth_state["waiting_for"] is None:
                bot.send_message(CHAT_ID, "🔄 Ab download kar raha hoon...")
                try_download_with_cookies(url)
            else:
                bot.send_message(CHAT_ID, "❌ Timeout! Dobara link bhejo.")
        else:
            bot.send_message(CHAT_ID, "❌ Code generate nahi ho saka.")

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:200]}")

def get_tv_activation_code_from_youtube():
    """Bot khud code nikalta hai aur aapko link + code bhejta hai"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.youtube.com/tv/activate")
            time.sleep(8)

            # Code dhundho
            selectors = ["code", ".code", ".activation-code", "span[dir='auto']"]
            code = None
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible():
                        code = el.text_content().strip()
                        break
                except:
                    continue

            # Screenshot le lo
            page.screenshot(path="tv_code.png")

            if code:
                bot.send_photo(
                    CHAT_ID,
                    open("tv_code.png", "rb"),
                    caption=f"🔐 **TV ACTIVATION CODE**\n\n"
                            f"🌐 **Link:** https://www.youtube.com/tv/activate\n"
                            f"🔢 **Code:** `{code}`\n\n"
                            f"👉 Ye code browser mein daalo\n👉 Verify karo\n👉 Phir `/continue` likho"
                )
            else:
                bot.send_photo(
                    CHAT_ID,
                    open("tv_code.png", "rb"),
                    caption=f"🔐 **MANUAL TV ACTIVATION**\n\n"
                            f"🌐 **Link:** https://www.youtube.com/tv/activate\n"
                            f"🔢 Code screen par dikhega, wo yahan bhejo\n\n"
                            f"👉 Code bhejne ke baad `/continue` likhna"
                )
                # Manual code receive karne ke liye
                youtube_auth_state["waiting_for"] = "code"
                youtube_auth_state["event"].clear()
                youtube_auth_state["event"].wait(timeout=120)
                code = youtube_auth_state.get("manual_code")

            browser.close()
            return code
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Code generation error: {e}")
        return None

@bot.message_handler(func=lambda m: youtube_auth_state["waiting_for"] == "code")
def receive_manual_code(m):
    youtube_auth_state["manual_code"] = m.text.strip()
    youtube_auth_state["waiting_for"] = None
    youtube_auth_state["event"].set()
    bot.reply_to(m, "✅ Code mil gaya! Ab verification karo aur /continue likho.")

def try_download_with_cookies(url):
    """Cookies ke saath download try karo"""
    try:
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'cookiefile': youtube_auth_state["cookies_file"],
            'extractor_args': {'youtube': 'player_client=android_tv'},
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Find actual file
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(info['title']):
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            if os.path.exists(filename):
                bot.send_message(CHAT_ID, f"✅ Downloaded: {os.path.basename(filename)}")
                upload_to_jazzdrive(filename)
                return True
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Download failed: {str(e)[:100]}")
        return False

# ---------------------------
# DIRECT LINK + UPLOAD (same as before)
# ---------------------------
def process_direct(link):
    filename = f"video_{int(time.time())}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    os.system(f'aria2c -x 16 -s 16 -d "{DOWNLOAD_DIR}" -o "{filename}" "{link}"')
    if os.path.exists(filepath):
        upload_to_jazzdrive(filepath)

def upload_to_jazzdrive(filepath):
    # Same as before — Jazz Drive upload
    pass

# ---------------------------
# START
# ---------------------------
bot.send_message(CHAT_ID, "🟢 Bot online! College wala TV method enabled ✅")
bot.polling(non_stop=True)
