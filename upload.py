import os
import threading
import queue
import logging
import telebot
from pytubefix import YouTube
import time

TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

bot = telebot.TeleBot(TOKEN)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

task_queue = queue.Queue()
is_working = False

# OAuth state
oauth_state = {
    "waiting_for": None,  # "code" or "continue"
    "url": None,
    "code": None,
    "event": threading.Event(),
    "yt_object": None
}

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
        "🤖 **YT DOWNLOADER**\n\n"
        "✅ **OAuth Method Active**\n"
        "• YouTube link bhejo\n"
        "• Agar login manga to code milega\n"
        "• Code dalke verify karo\n"
        "• Phir download hoga")

@bot.message_handler(commands=['continue'])
def continue_download(message):
    if oauth_state["waiting_for"] == "continue":
        oauth_state["waiting_for"] = None
        oauth_state["event"].set()
        bot.reply_to(message, "✅ Continuing download...")

# ==================== LINK HANDLER ====================
@bot.message_handler(func=lambda m: m.text and ('youtube.com' in m.text or 'youtu.be' in m.text))
def handle_link(message):
    url = message.text.strip()
    task_queue.put(url)
    bot.reply_to(message, f"✅ Queue mein add! Position: {task_queue.qsize()}")
    
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

# ==================== YOUTUBE PROCESSING ====================
def process_youtube(url):
    try:
        # Custom callback for OAuth code
        def on_auth_code(code, url):
            bot.send_message(CHAT_ID,
                f"🔐 **LOGIN REQUIRED**\n\n"
                f"**URL:** {url}\n"
                f"**Code:** `{code}`\n\n"
                f"Ye code browser mein dalke verify karo\n"
                f"Phir `/continue` likho")
            
            oauth_state["waiting_for"] = "continue"
            oauth_state["event"].clear()
        
        # Try with OAuth
        bot.send_message(CHAT_ID, "🔄 Processing...")
        
        # PyTubeFix with OAuth
        yt = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True,
            on_oauth_callback=on_auth_code  # ✅ YEH automatically code dega
        )
        
        # Wait if OAuth required
        if oauth_state["waiting_for"] == "continue":
            oauth_state["event"].wait(timeout=300)
            if oauth_state["waiting_for"] is not None:
                bot.send_message(CHAT_ID, "❌ Timeout!")
                return
        
        # Download
        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")
        
        # Quality options
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video (720p)", callback_data=f"video_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio MP3", callback_data=f"audio_{url}")
        )
        bot.send_message(CHAT_ID, "Choose quality:", reply_markup=markup)
        
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:100]}")

# ==================== CALLBACK HANDLER ====================
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
        
        # Upload to Jazz Drive (your existing code)
        # upload_to_jazzdrive(filename)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)[:100]}")

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
        
        # Upload to Jazz Drive
        # upload_to_jazzdrive(new_file)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)[:100]}")

# ==================== START ====================
bot.polling(non_stop=True)
