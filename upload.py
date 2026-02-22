import os
import time
import threading
import queue
import logging
import re
import subprocess
import telebot
from playwright.sync_api import sync_playwright

# ==================== TRY IMPORT PYTUBEFIX ====================
try:
    from pytubefix import YouTube
    from pytubefix.cli import on_progress
    PYTUBEFIX_AVAILABLE = True
except ImportError:
    PYTUBEFIX_AVAILABLE = False
    print("⚠️ pytubefix not installed. YouTube downloads disabled.")

# ==================== CONFIG ====================
TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO)

task_queue = queue.Queue()
is_working = False

# ==================== STATE MANAGEMENT ====================
login_state = {
    "waiting_for": None, 
    "number": None, 
    "otp": None, 
    "event": threading.Event()
}

youtube_oauth_state = {
    "waiting_for": None,   # "code" ya "continue"
    "url": None,
    "code": None,
    "event": threading.Event()
}

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def welcome(message):
    yt_status = "✅ Active" if PYTUBEFIX_AVAILABLE else "❌ Not Installed"
    bot.reply_to(message, 
        "🤖 **JAZZ UPLOADER BOT**\n\n"
        f"📺 YouTube: {yt_status}\n"
        "🔗 Direct Links: ✅ Active\n"
        "☁️ Jazz Drive: ✅ Active\n\n"
        "📤 **Send any link to start!**\n"
        "🔐 Jazz login: `/login`\n"
        "📊 Status: `/status`")

@bot.message_handler(commands=['status'])
def check_status(message):
    state = "WORKING ⚠️" if is_working else "IDLE ✅"
    pending = task_queue.qsize()
    yt_wait = ""
    if youtube_oauth_state["waiting_for"] == "continue":
        yt_wait = "\n⏳ Waiting for /continue"
    bot.reply_to(message, f"📊 **Status**\nState: {state}{yt_wait}\nQueue: {pending}")

@bot.message_handler(commands=['continue'])
def continue_youtube(message):
    if youtube_oauth_state["waiting_for"] == "continue":
        youtube_oauth_state["waiting_for"] = None
        youtube_oauth_state["event"].set()
        bot.reply_to(message, "✅ Continuing download...")
    else:
        bot.reply_to(message, "❌ No pending verification")

@bot.message_handler(commands=['login'])
def start_login(message):
    login_state["waiting_for"] = "number"
    bot.reply_to(message, "📱 Apna Jazz Number bhejein (03XXXXXXXXX):")

# ==================== JAZZ DRIVE LOGIN ====================
@bot.message_handler(func=lambda m: login_state["waiting_for"] == "number")
def receive_number(message):
    login_state["number"] = message.text.strip()
    login_state["waiting_for"] = "otp"
    bot.reply_to(message, "⏳ OTP bhej raha hoon...")
    threading.Thread(target=do_jazz_login).start()

@bot.message_handler(func=lambda m: login_state["waiting_for"] == "otp")
def receive_otp(message):
    login_state["otp"] = message.text.strip()
    login_state["waiting_for"] = None
    login_state["event"].set()

def do_jazz_login():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://cloud.jazzdrive.com.pk/")
            time.sleep(3)
            page.fill("input[type='text']", login_state["number"])
            page.click("button:has-text('Get OTP')")
            bot.send_message(CHAT_ID, "📩 OTP bhej diya!")
            
            login_state["event"].wait(timeout=60)
            if login_state["otp"]:
                page.fill("input[type='text']", login_state["otp"])
                page.click("button:has-text('Verify')")
                time.sleep(3)
                context.storage_state(path="state.json")
                bot.send_message(CHAT_ID, "🎉 Jazz Login Success!")
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Login error: {str(e)[:100]}")

# ==================== LINK DETECTION ====================
def is_youtube_link(text):
    return re.search(r'(youtube\.com|youtu\.be)', text) is not None

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_link(message):
    link = message.text.strip()
    
    if is_youtube_link(link) and PYTUBEFIX_AVAILABLE:
        task_queue.put(("youtube", link))
        bot.reply_to(message, f"✅ YouTube added! Position: {task_queue.qsize()}")
    elif is_youtube_link(link) and not PYTUBEFIX_AVAILABLE:
        bot.reply_to(message, "❌ YouTube disabled (pytubefix not installed)")
        return
    else:
        task_queue.put(("direct", link))
        bot.reply_to(message, f"✅ Direct link added! Position: {task_queue.qsize()}")
    
    global is_working
    if not is_working:
        threading.Thread(target=worker_loop).start()

def worker_loop():
    global is_working
    is_working = True
    while not task_queue.empty():
        task_type, task_data = task_queue.get()
        try:
            if task_type == "youtube":
                process_youtube(task_data)
            else:
                process_direct_link(task_data)
        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:100]}")
        time.sleep(2)
    is_working = False

# ==================== YOUTUBE DOWNLOAD (DOST WALA METHOD) ====================
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, "▶️ YouTube link process ho raha hai...")

        def on_auth_code(code, verification_url):
            bot.send_message(CHAT_ID,
                f"🔐 **LOGIN REQUIRED**\n\n"
                f"**URL:** {verification_url}\n"
                f"**Code:** `{code}`\n\n"
                f"Ye code browser mein dalke verify karo\n"
                f"Phir `/continue` likho")
            
            youtube_oauth_state["waiting_for"] = "continue"
            youtube_oauth_state["event"].clear()

        yt = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True,
            on_oauth_callback=on_auth_code
        )

        if youtube_oauth_state["waiting_for"] == "continue":
            youtube_oauth_state["url"] = url
            youtube_oauth_state["event"].wait(timeout=300)
            if youtube_oauth_state["waiting_for"] is not None:
                bot.send_message(CHAT_ID, "❌ Timeout!")
                return

        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")

        # Quality options
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video", callback_data=f"video_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio", callback_data=f"audio_{url}")
        )
        bot.send_message(CHAT_ID, "Choose:", reply_markup=markup)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ YouTube error: {str(e)[:200]}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("video_"):
        url = call.data.replace("video_", "")
        threading.Thread(target=download_youtube, args=(url, call.message.chat.id, "video")).start()
    elif call.data.startswith("audio_"):
        url = call.data.replace("audio_", "")
        threading.Thread(target=download_youtube, args=(url, call.message.chat.id, "audio")).start()

def download_youtube(url, chat_id, mode):
    try:
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
        if mode == "audio":
            stream = yt.streams.get_audio_only()
            out_file = stream.download(output_path=DOWNLOAD_DIR)
            base, ext = os.path.splitext(out_file)
            new_file = base + '.mp3'
            os.rename(out_file, new_file)
            filename = new_file
        else:
            stream = yt.streams.get_highest_resolution()
            filename = stream.download(output_path=DOWNLOAD_DIR)
        
        size = os.path.getsize(filename) / (1024*1024)
        bot.send_message(chat_id, f"✅ Downloaded: {yt.title[:30]}... ({size:.1f}MB)")
        upload_to_jazzdrive(filename)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Download error: {str(e)[:100]}")

# ==================== DIRECT LINK DOWNLOAD (AAPKA METHOD) ====================
def process_direct_link(link):
    filename = f"video_{int(time.time())}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    try:
        bot.send_message(CHAT_ID, "🌍 Downloading direct link...")
        os.system(f'aria2c -x 16 -s 16 -d "{DOWNLOAD_DIR}" -o "{filename}" "{link}"')
        
        if os.path.exists(filepath):
            size = os.path.getsize(filepath) / (1024*1024)
            bot.send_message(CHAT_ID, f"✅ Downloaded: {size:.1f}MB")
            upload_to_jazzdrive(filepath)
        else:
            bot.send_message(CHAT_ID, "❌ Download failed")
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:100]}")

# ==================== JAZZ DRIVE UPLOAD (COMMON) ====================
def upload_to_jazzdrive(filepath):
    try:
        bot.send_message(CHAT_ID, "⬆️ Uploading to Jazz Drive...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            page.goto("https://cloud.jazzdrive.com.pk/")
            time.sleep(5)
            
            if page.locator("text='Sign Up/In'").is_visible():
                bot.send_message(CHAT_ID, "⚠️ Login expired! Use /login")
                browser.close()
                return
            
            try:
                with page.expect_file_chooser() as fc_info:
                    page.click("text='Upload files'")
                file_chooser = fc_info.value
                file_chooser.set_files(os.path.abspath(filepath))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filepath))
            
            time.sleep(5)
            try:
                page.click("button:has-text('Yes')", timeout=3000)
            except:
                pass
            
            bot.send_message(CHAT_ID, f"✅ Uploaded: {os.path.basename(filepath)}")
            os.remove(filepath)
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Upload error: {str(e)[:100]}")

# ==================== START BOT ====================
if __name__ == "__main__":
    try:
        bot.send_message(CHAT_ID, "🟢 **Bot Online!**\n✅ YouTube + Direct Links + Jazz Drive")
    except:
        pass
    bot.polling(non_stop=True)
