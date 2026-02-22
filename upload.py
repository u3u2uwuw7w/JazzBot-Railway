import os
import time
import threading
import queue
import logging
import re
import telebot
from pytubefix import YouTube                     # ✅ Sahi import
from pytubefix.cli import on_progress              # ✅ Sahi import
from playwright.sync_api import sync_playwright
import subprocess

# 🔑 APNI DETAILS YAHAN DALO
TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

task_queue = queue.Queue()
is_working = False

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

# ---------------------------
# COMMANDS
# ---------------------------
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, 
        "🤖 **JAZZ 24/7 UPLOADER**\n"
        "✅ **pytubefix OAuth Method**\n"
        "• YouTube link bhejo – agar login manga to code milega\n"
        "• Code browser mein dalke verify karo\n"
        "• Phir `/continue` likho\n"
        "• Download + Jazz Drive upload\n"
        "• Direct links bhi kaam karein\n"
        "🔐 Jazz Drive login: `/login`")

@bot.message_handler(commands=['status'])
def check_status(message):
    state = "WORKING ⚠️" if is_working else "IDLE ✅"
    pending = task_queue.qsize()
    wait_text = ""
    if youtube_oauth_state["waiting_for"] == "continue":
        wait_text = "\n⏳ Waiting for /continue after verification"
    bot.reply_to(message, f"📊 **System Status**\nState: {state}{wait_text}\nPending: {pending}")

@bot.message_handler(commands=['continue'])
def continue_youtube(message):
    if youtube_oauth_state["waiting_for"] == "continue":
        youtube_oauth_state["waiting_for"] = None
        youtube_oauth_state["event"].set()
        bot.reply_to(message, "✅ Verification done! Continuing download...")
    else:
        bot.reply_to(message, "❌ No pending YouTube verification.")

@bot.message_handler(commands=['login'])
def start_login(message):
    login_state["waiting_for"] = "number"
    bot.reply_to(message, "📱 Apna Jazz Number bhejein (Jaise: 03001234567):")

# ---------------------------
# JAZZ DRIVE LOGIN (PLAYWRIGHT)
# ---------------------------
@bot.message_handler(func=lambda m: login_state["waiting_for"] == "number")
def receive_number(message):
    login_state["number"] = message.text.strip()
    login_state["waiting_for"] = "otp"
    bot.reply_to(message, f"⏳ Number `{login_state['number']}` Jazz Drive par daal raha hoon. OTP ka wait karein...")
    threading.Thread(target=do_playwright_login).start()

@bot.message_handler(func=lambda m: login_state["waiting_for"] == "otp")
def receive_otp(message):
    login_state["otp"] = message.text.strip()
    login_state["waiting_for"] = None
    login_state["event"].set()

def do_playwright_login():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            
            bot.send_message(CHAT_ID, "🌐 Website khol raha hoon...")
            page.goto("https://cloud.jazzdrive.com.pk/", timeout=60000)
            time.sleep(3)
            
            page.fill("input[type='text'], input[placeholder*='03']", login_state["number"])
            page.click("button:has-text('Subscribe'), button:has-text('Login'), button:has-text('Get OTP')")
            
            bot.send_message(CHAT_ID, "📩 OTP bhej diya gaya hai! Jaldi se yahan OTP likh kar reply karein:")
            
            login_state["event"].clear()
            login_state["event"].wait(timeout=60) 
            
            if login_state["otp"]:
                bot.send_message(CHAT_ID, "🔑 OTP website par daal raha hoon...")
                page.locator("input").nth(0).click() 
                page.keyboard.type(login_state["otp"])
                time.sleep(3)
                
                try:
                    page.click("button:has-text('Verify'), button:has-text('Submit')", timeout=3000)
                except:
                    pass 
                
                time.sleep(5)
                context.storage_state(path="state.json")
                bot.send_message(CHAT_ID, "🎉 **LOGIN SUCCESSFUL!** 🎉")
            else:
                bot.send_message(CHAT_ID, "❌ Timeout! Dobara `/login` likhein.")
                login_state["waiting_for"] = None
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Login Error: {str(e)[:150]}")
        login_state["waiting_for"] = None

# ---------------------------
# LINK DETECTION
# ---------------------------
def is_youtube_link(text):
    return re.search(r'(youtube\.com|youtu\.be)', text) is not None

@bot.message_handler(func=lambda m: m.text and (m.text.startswith("http") or is_youtube_link(m.text)))
def handle_link(message):
    link = message.text.strip()
    if is_youtube_link(link):
        task_queue.put(("youtube", link))
    else:
        task_queue.put(("direct", link))
    bot.reply_to(message, f"✅ Added to Queue! Position: {task_queue.qsize()}")
    global is_working
    if not is_working:
        threading.Thread(target=worker_loop).start()

def worker_loop():
    global is_working
    is_working = True
    while not task_queue.empty():
        task_type, task_data = task_queue.get()
        if task_type == "youtube":
            process_youtube(task_data)
        else:
            process_direct_link(task_data)
        time.sleep(2)
    is_working = False

# ---------------------------
# YOUTUBE DOWNLOAD (PYTUBEFIX OAUTH)
# ---------------------------
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, "▶️ YouTube link process kar raha hoon...")

        # OAuth callback function
        def on_auth_code(code, verification_url):
            bot.send_message(CHAT_ID,
                f"🔐 **LOGIN REQUIRED**\n\n"
                f"**URL:** {verification_url}\n"
                f"**Code:** `{code}`\n\n"
                f"Ye code browser mein dalke verify karo\n"
                f"Phir `/continue` likho")
            
            youtube_oauth_state["waiting_for"] = "continue"
            youtube_oauth_state["event"].clear()

        # Create YouTube object with OAuth
        yt = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True,
            on_oauth_callback=on_auth_code
        )

        # Agar OAuth manga to wait karo
        if youtube_oauth_state["waiting_for"] == "continue":
            youtube_oauth_state["url"] = url
            youtube_oauth_state["event"].wait(timeout=300)  # 5 min
            if youtube_oauth_state["waiting_for"] is not None:
                bot.send_message(CHAT_ID, "❌ Timeout! Dobara link bhejo.")
                return

        # Video info mil gayi
        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")

        # Quality options
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video (720p)", callback_data=f"video_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio MP3", callback_data=f"audio_{url}")
        )
        bot.send_message(CHAT_ID, "Choose quality:", reply_markup=markup)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ YouTube error: {str(e)[:200]}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("video_"):
        url = call.data.replace("video_", "")
        threading.Thread(target=download_youtube_video, args=(url, call.message.chat.id, "video")).start()
        bot.answer_callback_query(call.id, "Downloading video...")
    elif call.data.startswith("audio_"):
        url = call.data.replace("audio_", "")
        threading.Thread(target=download_youtube_video, args=(url, call.message.chat.id, "audio")).start()
        bot.answer_callback_query(call.id, "Downloading audio...")

def download_youtube_video(url, chat_id, mode="video"):
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

# ---------------------------
# DIRECT LINK DOWNLOAD (ARIA2)
# ---------------------------
def process_direct_link(link):
    filename = f"video_{int(time.time())}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    try:
        bot.send_message(CHAT_ID, "🌍 Direct link download ho raha hai...")
        os.system(f'aria2c -x 16 -s 16 -d "{DOWNLOAD_DIR}" -o "{filename}" "{link}"')
        
        if os.path.exists(filepath):
            size = os.path.getsize(filepath) / (1024*1024)
            bot.send_message(CHAT_ID, f"✅ Download complete: {size:.1f}MB")
            upload_to_jazzdrive(filepath)
        else:
            bot.send_message(CHAT_ID, "❌ Download Failed!")
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Download error: {str(e)[:100]}")
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

# ---------------------------
# JAZZ DRIVE UPLOAD (PLAYWRIGHT)
# ---------------------------
def upload_to_jazzdrive(filepath):
    try:
        bot.send_message(CHAT_ID, "⬆️ Jazz Drive par upload ho raha hai...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            
            page.goto("https://cloud.jazzdrive.com.pk/", timeout=60000)
            time.sleep(5)

            if page.locator("text='Sign Up/In'").is_visible():
                bot.send_message(CHAT_ID, "⚠️ Jazz Drive login expired! Use /login")
                browser.close()
                return

            # Upload file
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    page.click("text='Upload files'")
                file_chooser = fc_info.value
                file_chooser.set_files(os.path.abspath(filepath))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filepath), timeout=15000)
            
            time.sleep(5)
            
            # Large file warning
            try:
                page.click("button:has-text('Yes')", timeout=3000)
                time.sleep(1)
            except:
                pass
            
            bot.send_message(CHAT_ID, f"✅ Upload successful: {os.path.basename(filepath)}")
            
            # Delete local file
            os.remove(filepath)
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Upload error: {str(e)[:100]}")

# ---------------------------
# START BOT
# ---------------------------
try:
    bot.send_message(CHAT_ID, "🟢 **Bot Online!**\n✅ pytubefix OAuth method active")
except:
    pass

bot.polling(non_stop=True)
