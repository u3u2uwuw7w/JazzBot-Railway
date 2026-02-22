import os
import time
import threading
import queue
import logging
import telebot
from pytubefix import YouTube
from pytubefix.cli import on_progress
import subprocess

TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO)

task_queue = queue.Queue()
is_working = False

oauth_state = {
    "waiting_for": None,
    "url": None,
    "code": None,
    "event": threading.Event()
}

# ---------------------------
# COMMANDS
# ---------------------------
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
        "🤖 **JAZZ YT BOT (OAUTH)**\n\n"
        "✅ **OAuth TV Method**\n"
        "• YouTube link bhejo\n"
        "• Agar login manga to bot code dega\n"
        "• Code browser mein dalke verify karo\n"
        "• Phir `/continue` likho\n"
        "• Download + Jazz Drive upload")

@bot.message_handler(commands=['continue'])
def continue_yt(message):
    if oauth_state["waiting_for"] == "continue":
        oauth_state["waiting_for"] = None
        oauth_state["event"].set()
        bot.reply_to(message, "✅ Continuing download...")
    else:
        bot.reply_to(message, "❌ No pending verification")

@bot.message_handler(commands=['login'])
def jazz_login(message):
    bot.reply_to(message, "Jazz Drive login feature yahan add kar sakte ho (optional)")

# ---------------------------
# LINK HANDLER
# ---------------------------
@bot.message_handler(func=lambda m: m.text and ('youtube.com' in m.text or 'youtu.be' in m.text))
def handle_link(message):
    url = message.text.strip()
    task_queue.put(url)
    bot.reply_to(message, f"✅ Added to queue! Position: {task_queue.qsize()}")
    
    global is_working
    if not is_working:
        threading.Thread(target=worker).start()

def worker():
    global is_working
    is_working = True
    while not task_queue.empty():
        url = task_queue.get()
        process_youtube(url)
        time.sleep(2)
    is_working = False

# ---------------------------
# YOUTUBE PROCESSING
# ---------------------------
def process_youtube(url):
    try:
        def on_auth_code(code, verification_url):
            bot.send_message(CHAT_ID,
                f"🔐 **LOGIN REQUIRED**\n\n"
                f"**URL:** {verification_url}\n"
                f"**Code:** `{code}`\n\n"
                f"Ye code browser mein dalke verify karo\n"
                f"Phir `/continue` likho")
            
            oauth_state["waiting_for"] = "continue"
            oauth_state["event"].clear()

        bot.send_message(CHAT_ID, "🔄 Processing...")

        yt = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True,
            on_oauth_callback=on_auth_code
        )

        if oauth_state["waiting_for"] == "continue":
            oauth_state["event"].wait(timeout=300)
            if oauth_state["waiting_for"] is not None:
                bot.send_message(CHAT_ID, "❌ Timeout! Dobara link bhejo.")
                return

        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")

        # Quality options
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video (720p)", callback_data=f"video_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio MP3", callback_data=f"audio_{url}")
        )
        bot.send_message(CHAT_ID, "Choose quality:", reply_markup=markup)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:200]}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("video_"):
        url = call.data.replace("video_", "")
        threading.Thread(target=download_video, args=(url, call.message.chat.id)).start()
        bot.answer_callback_query(call.id, "Downloading video...")
    elif call.data.startswith("audio_"):
        url = call.data.replace("audio_", "")
        threading.Thread(target=download_audio, args=(url, call.message.chat.id)).start()
        bot.answer_callback_query(call.id, "Downloading audio...")

def download_video(url, chat_id):
    try:
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
        stream = yt.streams.get_highest_resolution()
        filename = stream.download(output_path=DOWNLOAD_DIR)
        
        size = os.path.getsize(filename) / (1024*1024)
        bot.send_message(chat_id, f"✅ Downloaded: {yt.title[:30]}... ({size:.1f}MB)")
        upload_to_jazzdrive(filename)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Download error: {str(e)[:100]}")

def download_audio(url, chat_id):
    try:
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
        stream = yt.streams.get_audio_only()
        out_file = stream.download(output_path=DOWNLOAD_DIR)
        
        base, ext = os.path.splitext(out_file)
        new_file = base + '.mp3'
        os.rename(out_file, new_file)
        
        size = os.path.getsize(new_file) / (1024*1024)
        bot.send_message(chat_id, f"✅ Downloaded: {yt.title[:30]}... ({size:.1f}MB)")
        upload_to_jazzdrive(new_file)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Download error: {str(e)[:100]}")

# ---------------------------
# JAZZ DRIVE UPLOAD
# ---------------------------
def upload_to_jazzdrive(filepath):
    try:
        bot.send_message(CHAT_ID, "⬆️ Uploading to Jazz Drive...")
        
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            
            page.goto("https://cloud.jazzdrive.com.pk/")
            time.sleep(5)
            
            if page.locator("text='Sign Up/In'").is_visible():
                bot.send_message(CHAT_ID, "⚠️ Jazz Drive login expired! Use /login")
                browser.close()
                return
            
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    page.click("text='Upload files'")
                file_chooser = fc_info.value
                file_chooser.set_files(os.path.abspath(filepath))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filepath), timeout=15000)
            
            time.sleep(5)
            
            try:
                page.click("button:has-text('Yes')", timeout=3000)
            except:
                pass
            
            bot.send_message(CHAT_ID, f"✅ Upload successful: {os.path.basename(filepath)}")
            os.remove(filepath)
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Upload error: {str(e)[:100]}")

# ---------------------------
# START
# ---------------------------
if __name__ == "__main__":
    try:
        bot.send_message(CHAT_ID, "🟢 Bot Online! OAuth TV Method Active ✅")
    except:
        pass
    bot.polling(non_stop=True)
