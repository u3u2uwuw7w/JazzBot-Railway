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
logging.basicConfig(filename='bot.log', level=logging.INFO)

task_queue = queue.Queue()
is_working = False

youtube_auth_state = {
    "waiting_for": None,
    "url": None,
    "cookies_file": "youtube_cookies.txt",
    "event": threading.Event()
}

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 Bot online! Auto TV code active ✅")

@bot.message_handler(commands=['continue'])
def continue_yt(message):
    if youtube_auth_state["waiting_for"] == "continue":
        youtube_auth_state["waiting_for"] = None
        youtube_auth_state["event"].set()
        bot.reply_to(message, "✅ Continuing download...")

# ==================== LINK HANDLER ====================
@bot.message_handler(func=lambda m: m.text and 'youtube.com' in m.text)
def handle_link(message):
    url = message.text.strip()
    task_queue.put(("youtube", url))
    bot.reply_to(message, f"✅ Added! Position: {task_queue.qsize()}")
    
    global is_working
    if not is_working:
        threading.Thread(target=worker).start()

def worker():
    global is_working
    is_working = True
    while not task_queue.empty():
        _, url = task_queue.get()
        process_youtube(url)
    is_working = False

# ==================== YOUTUBE PROCESSING ====================
def process_youtube(url):
    # Check cookies
    if os.path.exists(youtube_auth_state["cookies_file"]):
        if download_with_cookies(url):
            return
    
    # No cookies → Get TV code
    code = get_tv_code()
    
    if code:
        bot.send_message(CHAT_ID, 
            f"🔐 **TV ACTIVATION CODE**\n\n"
            f"**Code:** `{code}`\n"
            f"**Link:** https://www.youtube.com/tv/activate\n\n"
            f"Ye code browser mein dalke verify karo\n"
            f"Phir /continue likho")
        
        youtube_auth_state["waiting_for"] = "continue"
        youtube_auth_state["url"] = url
        youtube_auth_state["event"].clear()
        youtube_auth_state["event"].wait(timeout=300)
        
        if youtube_auth_state["waiting_for"] is None:
            download_with_cookies(url)
    else:
        bot.send_message(CHAT_ID, "❌ Code generate nahi ho saka. Dobara try karo.")

def get_tv_code():
    """Playwright se TV code nikalta hai"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.youtube.com/tv/activate")
            time.sleep(8)
            
            # Code dhundho
            selectors = ["code", ".code", "span[dir='auto']", ".ytv-code"]
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        code = el.text_content().strip()
                        if code and len(code) >= 5:
                            browser.close()
                            return code
                except:
                    continue
            
            browser.close()
            return None
    except:
        return None

def download_with_cookies(url):
    try:
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'cookiefile': youtube_auth_state["cookies_file"],
            'extractor_args': {'youtube': 'player_client=android_tv'},
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(info['title']):
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            bot.send_message(CHAT_ID, f"✅ Downloaded: {info['title'][:30]}")
            
            # Upload to Jazz Drive (your existing upload code)
            # upload_to_jazzdrive(filename)
            return True
    except:
        return False

bot.polling(non_stop=True)
