import os
import sys
import time
import threading
import queue
import subprocess
import logging
import telebot
from playwright.sync_api import sync_playwright
from pytubefix import YouTube

# 🔑 APNI DETAILS
TOKEN = "8485872476:AAGt-C0JKjr6JpLwvIGtGWwMh-sFh0-PsC0" 
CHAT_ID = 7144917062 

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

task_queue = queue.Queue()
is_working = False

# 🧠 BOT KA NAYA DIMAAG
login_state = {
    "waiting_for": None, 
    "number": None, 
    "otp": None, 
    "event": threading.Event()
}

# 🚀 YOUTUBE OAUTH CATCHER (Terminal messages ko Telegram par bhejne ke liye)
class YTOauthCatcher:
    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.original_stdout = sys.stdout
        self.msg_sent = False

    def write(self, text):
        self.original_stdout.write(text)
        # Agar output mein google device link aaye to Telegram par bhej do
        if "google.com/device" in text and not self.msg_sent:
            self.bot.send_message(
                self.chat_id, 
                f"⚠️ **YOUTUBE VERIFICATION REQUIRED!** ⚠️\n\n{text.strip()}\n\n👆 **Uper diye gaye Link par jayen aur Code enter karein!** (Bot aapka intezar kar raha hai...)",
            )
            self.msg_sent = True

    def flush(self):
        self.original_stdout.flush()

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🤖 **JAZZ 24/7 UPLOADER**\n🟢 **Status:** Online\n📤 **Upload:** YT ya Direct Link bhejein\n🔐 **Login:** `/login` likhein")

@bot.message_handler(commands=['status'])
def check_status(message):
    state = "WORKING ⚠️" if is_working else "IDLE ✅"
    bot.reply_to(message, f"📊 **System Status**\nState: {state}\nPending Files: {task_queue.qsize()}")

# --- 🔐 JAZZ DRIVE LOGIN SYSTEM ---
@bot.message_handler(commands=['login'])
def start_login(message):
    login_state["waiting_for"] = "number"
    bot.reply_to(message, "📱 Apna Jazz Number bhejein (Jaise: 03001234567):")

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
        bot.send_message(CHAT_ID, f"❌ Login Error.\n`{str(e)[:150]}`")
        login_state["waiting_for"] = None

# --- 📥 UPLOAD SYSTEM (YouTube + Direct Links) ---
@bot.message_handler(func=lambda m: login_state["waiting_for"] is None and m.text.startswith("http"))
def handle_link(message):
    task_queue.put(message.text.strip())
    bot.reply_to(message, f"✅ Added to Queue! Position: {task_queue.qsize()}")
    global is_working
    if not is_working:
        threading.Thread(target=worker_loop).start()

def worker_loop():
    global is_working
    is_working = True
    while not task_queue.empty():
        process_task(task_queue.get())
    is_working = False

def process_task(link):
    filename = f"video_{int(time.time())}.mp4"
    try:
        # 🟢 YOUTUBE LOGIC
        if "youtube.com" in link or "youtu.be" in link:
            bot.send_message(CHAT_ID, "📺 YouTube Link detect hua! Processing shuru...")
            
            # Print output ko Telegram par bhejney ke liye interceptor lagaya
            old_stdout = sys.stdout
            sys.stdout = YTOauthCatcher(bot, CHAT_ID)
            
            try:
                yt = YouTube(link, use_oauth=True, allow_oauth_cache=True)
                bot.send_message(CHAT_ID, f"⬇️ Downloading YT Video: {yt.title}")
                ys = yt.streams.get_highest_resolution()
                ys.download(filename=filename)
            except Exception as e:
                bot.send_message(CHAT_ID, f"❌ YouTube Error: {e}")
                return
            finally:
                sys.stdout = old_stdout # Print system ko wapas normal kar diya
                
        # 🟢 DIRECT LINK LOGIC
        else:
            bot.send_message(CHAT_ID, "🌍 Direct Link Downloading...")
            os.system(f'aria2c -x 16 -s 16 -k 1M -o "{filename}" "{link}"')
        
        if not os.path.exists(filename):
            bot.send_message(CHAT_ID, "❌ Download Failed! File nahi mili.")
            return

        # 🟢 JAZZ DRIVE UPLOAD LOGIC
        bot.send_message(CHAT_ID, "⬆️ Checking Jazz Drive Login...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            
            try:
                page.goto("https://cloud.jazzdrive.com.pk/", timeout=90000)
                time.sleep(5)

                if page.locator("text='Sign Up/In'").is_visible() or page.locator("input[type='password']").is_visible():
                    bot.send_message(CHAT_ID, "⚠️ **Jazz Drive Login Expired!** ⚠️\nNaya login karne ke liye Telegram mein `/login` likhein.")
                    browser.close()
                    return 

                bot.send_message(CHAT_ID, "✅ Login theek hai! Uploading shuru...")
                
                try: page.click("button:has-text('Accept All')", timeout=3000)
                except: pass

                try: page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg')) b.click(); })")
                except: pass
                time.sleep(2)
                
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        page.click("text='Upload files'")
                    file_chooser = fc_info.value
                    file_chooser.set_files(os.path.abspath(filename))
                except:
                    page.set_input_files("input[type='file']", os.path.abspath(filename), timeout=15000)
                
                time.sleep(2)
                
                try:
                    page.click("button:has-text('Yes'), button:has-text('YES'), button:has-text('yes')", timeout=4000)
                    time.sleep(1)
                except: pass
                
                bot.send_message(CHAT_ID, "📁 File website par lag gayi hai. Har 1 minute baad progress update aayegi! ⏳")
                
                upload_done = False
                for i in range(25): 
                    try:
                        page.wait_for_selector("text=Uploads completed", timeout=60000)
                        upload_done = True
                        break 
                    except:
                        try:
                            page.screenshot(path="progress.png")
                            bot.send_photo(CHAT_ID, open("progress.png", "rb"), caption=f"⏳ Upload Progress: {i+1} min...")
                        except: pass
                
                if upload_done:
                    bot.send_message(CHAT_ID, f"🎉 SUCCESS! Video Jazz Drive par upload ho gayi hai.")
                else:
                    bot.send_message(CHAT_ID, "⚠️ 25 minute timeout! Upload poora nahi hua.")
                
            except Exception as e:
                bot.send_message(CHAT_ID, f"❌ Upload Error.\n`{str(e)[:150]}`")
            finally:
                browser.close()
                
    except Exception as e:
        logging.error(f"System Error: {e}")
    finally:
        if os.path.exists(filename): os.remove(filename)

try: bot.send_message(CHAT_ID, "🟢 **System Online!**\nWaiting for Links... 🚀")
except: pass

bot.polling(non_stop=True)
                
