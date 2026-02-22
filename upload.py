import os
import time
import threading
import queue
import logging
import re
import telebot
from playwright.sync_api import sync_playwright
import yt_dlp
import json

# 🔑 APNE NAYE DETAILS DALO
TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM"
CHAT_ID = 7186647955

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

youtube_auth_state = {
    "waiting_for": None,        # "code" ya "continue"
    "url": None,
    "cookies_file": "youtube_cookies.txt",
    "event": threading.Event(),
    "temp_code": None
}

# ---------------------------
# COMMANDS
# ---------------------------
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🤖 **JAZZ 24/7 UPLOADER**\n🟢 **Status:** Online\n📤 **Upload:** Link bhejein\n🔐 **Login:** `/login` likhein\n▶️ **YouTube:** YouTube link bhejein (TV method)")

@bot.message_handler(commands=['status'])
def check_status(message):
    state = "WORKING ⚠️" if is_working else "IDLE ✅"
    pending = task_queue.qsize()
    yt_wait = ""
    if youtube_auth_state["waiting_for"] == "code":
        yt_wait = " (YouTube code ka intezar)"
    elif youtube_auth_state["waiting_for"] == "continue":
        yt_wait = " (YouTube verification ka intezar)"
    bot.reply_to(message, f"📊 **System Status**\nState: {state}{yt_wait}\nPending Files: {pending}")

@bot.message_handler(commands=['login'])
def start_login(message):
    login_state["waiting_for"] = "number"
    bot.reply_to(message, "📱 Apna Jazz Number bhejein (Jaise: 03001234567):")

@bot.message_handler(commands=['continue'])
def continue_youtube(message):
    if youtube_auth_state["waiting_for"] == "continue":
        youtube_auth_state["waiting_for"] = None
        youtube_auth_state["event"].set()
        bot.reply_to(message, "✅ Verification complete! Continuing download...")
    else:
        bot.reply_to(message, "❌ No pending YouTube verification.")

# ---------------------------
# JAZZ LOGIN (PEHLE JAISA)
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
                bot.send_message(CHAT_ID, "🎉 **LOGIN SUCCESSFUL!** 🎉\nBot ne naya VIP Pass khud bana kar save kar liya hai. Ab apne Links bhejein!")
            else:
                bot.send_message(CHAT_ID, "❌ Timeout! Dobara `/login` likhein.")
                login_state["waiting_for"] = None
            browser.close()
    except Exception as e:
        try:
            page.screenshot(path="login_failed.png")
            bot.send_photo(CHAT_ID, open("login_failed.png", "rb"), caption=f"❌ Login Error!\n`{str(e)[:150]}`", parse_mode="Markdown")
        except:
            bot.send_message(CHAT_ID, f"❌ Login Error: Website ne response nahi diya.\n`{str(e)[:150]}`")
        login_state["waiting_for"] = None

# ---------------------------
# YOUTUBE LINK DETECTION
# ---------------------------
def is_youtube_link(text):
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/.+'
    return re.match(youtube_regex, text) is not None

@bot.message_handler(func=lambda m: login_state["waiting_for"] is None and m.text and (m.text.startswith("http") or is_youtube_link(m.text)))
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
    is_working = False

# ---------------------------
# YOUTUBE PROCESSING (TV METHOD - FIXED)
# ---------------------------
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, f"▶️ YouTube video process kar raha hoon...")

        # Pehle check karein cookies exist karti hain ya nahi
        cookies_exist = os.path.exists(youtube_auth_state["cookies_file"])
        
        if not cookies_exist:
            # Naya TV activation code lene ke liye
            bot.send_message(CHAT_ID, "⚠️ YouTube age verification required. TV activation code generate kar raha hoon...")
            
            # Playwright se TV code hasil karein
            code = get_tv_activation_code()
            
            if code:
                youtube_auth_state["temp_code"] = code
                youtube_auth_state["waiting_for"] = "continue"
                youtube_auth_state["url"] = url
                
                bot.send_message(
                    CHAT_ID, 
                    f"🔐 **TV ACTIVATION CODE:** `{code}`\n\n"
                    f"1. Ye website kholo: https://www.youtube.com/tv/activate\n"
                    f"2. Yeh code `{code}` wahan enter karo\n"
                    f"3. Verify karne ke baad yahan `/continue` likho"
                )
                
                # Intezar karein jab tak user /continue na bheje
                youtube_auth_state["event"].clear()
                youtube_auth_state["event"].wait(timeout=300)  # 5 minute wait
                
                if youtube_auth_state["waiting_for"] is None:
                    # User ne continue kar diya, ab cookies save karo
                    bot.send_message(CHAT_ID, "🔄 Cookies save kar raha hoon...")
                    time.sleep(5)  # Thoda intezar ke YouTube cookies save ho jayein
                    # Yahan cookies automatically save ho jayengi jab hum dobara yt-dlp chalayenge
                else:
                    bot.send_message(CHAT_ID, "❌ Timeout! Dobara YouTube link bhejein.")
                    return
            else:
                bot.send_message(CHAT_ID, "❌ TV activation code generate nahi ho saka.")
                return
        
        # Ab download karo (cookies exist karti hain ya abhi save hui hain)
        bot.send_message(CHAT_ID, "⬇️ YouTube video download ho raha hai...")
        
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': '%(title)s.%(ext)s',
            'cookiefile': youtube_auth_state["cookies_file"] if os.path.exists(youtube_auth_state["cookies_file"]) else None,
            'extractor_args': {'youtube': 'player_client=android_tv'},
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Extension fix
            if not os.path.exists(filename):
                # Kuch videos mein extension alag hoti hai
                for file in os.listdir('.'):
                    if file.startswith(info['title']) and file.endswith(('.mp4', '.webm', '.mkv')):
                        filename = file
                        break
        
        if os.path.exists(filename):
            bot.send_message(CHAT_ID, f"✅ Download complete: {filename}")
            upload_to_jazzdrive(filename)
        else:
            bot.send_message(CHAT_ID, "❌ Download failed: file not found.")
            
    except Exception as e:
        logging.error(f"YouTube error: {e}")
        bot.send_message(CHAT_ID, f"❌ YouTube error: {str(e)[:200]}")

def get_tv_activation_code():
    """Playwright se YouTube TV ka activation code hasil karein"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            
            bot.send_message(CHAT_ID, "🌐 YouTube TV page khul raha hai...")
            page.goto("https://www.youtube.com/tv/activate", timeout=60000)
            time.sleep(5)
            
            # Code selector - YouTube TV par code dikhta hai
            code_element = page.locator("code, .code, .activation-code, .setup-code").first
            if code_element.is_visible():
                code = code_element.text_content().strip()
                browser.close()
                return code
            
            # Agar code na mile to screenshot le kar dekhein
            page.screenshot(path="tv_code.png")
            bot.send_photo(CHAT_ID, open("tv_code.png", "rb"), caption="Code nahi mila, manual check karein:")
            
            browser.close()
            return None
    except Exception as e:
        logging.error(f"TV code error: {e}")
        return None

# ---------------------------
# DIRECT LINK DOWNLOAD (ARIA2)
# ---------------------------
def process_direct_link(link):
    filename = f"video_{int(time.time())}.mp4"
    try:
        bot.send_message(CHAT_ID, "🌍 Link Downloading...")
        os.system(f'aria2c -x 16 -s 16 -k 1M -o "{filename}" "{link}"')
        
        if not os.path.exists(filename):
            bot.send_message(CHAT_ID, "❌ Download Failed!")
            return

        upload_to_jazzdrive(filename)
    except Exception as e:
        logging.error(f"Direct download error: {e}")
        bot.send_message(CHAT_ID, f"❌ Download error: {str(e)[:200]}")
    finally:
        if os.path.exists(filename): os.remove(filename)

# ---------------------------
# JAZZ DRIVE UPLOAD (PEHLE JAISA)
# ---------------------------
def upload_to_jazzdrive(filename):
    try:
        bot.send_message(CHAT_ID, "⬆️ Checking Jazz Drive Login...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            
            try:
                page.goto("https://cloud.jazzdrive.com.pk/", timeout=90000)
                time.sleep(5)

                if page.locator("text='Sign Up/In'").is_visible() or page.locator("input[type='password']").is_visible() or page.locator("text='Please Enter Jazz Number'").is_visible():
                    bot.send_message(CHAT_ID, "⚠️ **Jazz Drive Login Expired!** ⚠️\nNaya login karne ke liye Telegram mein `/login` likhein.")
                    browser.close()
                    return 

                bot.send_message(CHAT_ID, "✅ Login theek hai! Uploading shuru...")
                
                # Cookie popup hatana
                try:
                    page.click("button:has-text('Accept All')", timeout=3000)
                    time.sleep(1)
                except: pass

                # Main icon par click
                try: 
                    page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg')) b.click(); })")
                except: pass
                time.sleep(2)
                
                # Upload files click
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        page.click("text='Upload files'")
                    file_chooser = fc_info.value
                    file_chooser.set_files(os.path.abspath(filename))
                except:
                    page.set_input_files("input[type='file']", os.path.abspath(filename), timeout=15000)
                
                time.sleep(2)
                
                # 1GB+ warning
                try:
                    page.click("button:has-text('Yes'), button:has-text('YES'), button:has-text('yes')", timeout=4000)
                    bot.send_message(CHAT_ID, "⚠️ Bari file (1GB+) warning detect hui, 'Yes' par click kar diya hai!")
                    time.sleep(1)
                except:
                    pass
                
                bot.send_message(CHAT_ID, "📁 File website par lag gayi hai. Har 1 minute baad progress screenshot milega! ⏳")
                
                # Progress screenshots
                upload_done = False
                for i in range(25): 
                    try:
                        page.wait_for_selector("text=Uploads completed", timeout=60000)
                        upload_done = True
                        break 
                    except:
                        try:
                            page.screenshot(path="progress.png")
                            bot.send_photo(CHAT_ID, open("progress.png", "rb"), caption=f"⏳ Upload Progress: {i+1} minute guzar gaye...")
                        except: pass
                
                if upload_done:
                    bot.send_message(CHAT_ID, f"🎉 SUCCESS! {filename} mukammal upload ho gayi hai.")
                else:
                    bot.send_message(CHAT_ID, "⚠️ 25 minute timeout! Upload poora nahi hua.")
                
            except Exception as e:
                logging.error(f"Upload error: {e}")
                try:
                    page.screenshot(path="upload_error.png")
                    bot.send_photo(CHAT_ID, open("upload_error.png", "rb"), caption=f"❌ Upload Error! Screen dekhein:\n`{str(e)[:150]}`", parse_mode="Markdown")
                except:
                    bot.send_message(CHAT_ID, f"❌ Upload Error: Site Stuck ya File mili nahi.")
            finally:
                browser.close()
    except Exception as e:
        logging.error(f"System Error: {e}")
    finally:
        if os.path.exists(filename): os.remove(filename)

# ---------------------------
# START BOT
# ---------------------------
try: 
    bot.send_message(CHAT_ID, "🟢 **System Online!**\nYouTube TV code support enabled! 🚀")
except: 
    pass

bot.polling(non_stop=True)
