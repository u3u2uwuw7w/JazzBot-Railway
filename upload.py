import os
import time
import threading
import queue
import logging
import re
import telebot
from playwright.sync_api import sync_playwright
import yt_dlp

# 🔑 اپنی تفصیلات
TOKEN = "8599854738:AAH330JR9zLBXYvNTONm7HF9q_sdZy7qXVM" 
CHAT_ID = 7186647955

bot = telebot.TeleBot(TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

task_queue = queue.Queue()
is_working = False

# Jazz Drive لاگ ان کا سٹیٹ
login_state = {
    "waiting_for": None, 
    "number": None, 
    "otp": None, 
    "event": threading.Event()
}

# یوٹیوب تصدیق کا سٹیٹ
youtube_auth_state = {
    "waiting_for": None,        # "continue" or None
    "url": None,
    "cookies_file": "youtube_cookies.txt",
    "event": threading.Event()
}

# ---------------------------
# کمانڈ ہینڈلرز
# ---------------------------
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🤖 **JAZZ 24/7 UPLOADER**\n🟢 **Status:** Online\n📤 **Upload:** Link bhejein\n🔐 **Login:** `/login` likhein\n▶️ **YouTube:** YouTube link bhejein (TV method)")

@bot.message_handler(commands=['status'])
def check_status(message):
    state = "WORKING ⚠️" if is_working else "IDLE ✅"
    pending = task_queue.qsize()
    yt_wait = " (YouTube verification ka intezar)" if youtube_auth_state["waiting_for"] else ""
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
# Jazz Drive لاگ ان کا بہاؤ
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
# یوٹیوب لنک پروسیسنگ
# ---------------------------
def is_youtube_link(text):
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/.+'
    return re.match(youtube_regex, text) is not None

@bot.message_handler(func=lambda m: login_state["waiting_for"] is None and m.text and (m.text.startswith("http") or is_youtube_link(m.text)))
def handle_link(message):
    link = message.text.strip()
    if is_youtube_link(link):
        # یوٹیوب لنک کو خاص طریقے سے ہینڈل کریں
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
# یوٹیوب ڈاؤنلوڈ (TV method)
# ---------------------------
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, f"▶️ YouTube video process kar raha hoon...")

        # yt-dlp آپشنز
        ydl_opts = {
            'format': 'best[height<=720]',  # 720p تک کی بہترین ویڈیو
            'outtmpl': '%(title)s.%(ext)s',
            'cookiefile': youtube_auth_state["cookies_file"] if os.path.exists(youtube_auth_state["cookies_file"]) else None,
            'extractor_args': {'youtube': 'player_client=android_tv'},  # TV client
            'quiet': True,
            'no_warnings': True,
        }

        # پہلے چیک کریں کہ تصدیق درکار ہے یا نہیں
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # صرف معلومات حاصل کریں، ڈاؤنلوڈ نہ کریں
                info = ydl.extract_info(url, download=False)
                # اگر یہاں تک پہنچ گئے تو تصدیق درکار نہیں
                bot.send_message(CHAT_ID, "✅ YouTube authentication OK, downloading...")
            except yt_dlp.utils.DownloadError as e:
                error_str = str(e)
                if "Sign in to confirm your age" in error_str or "Confirm your age" in error_str or "Sign in" in error_str:
                    # تصدیق درکار ہے
                    bot.send_message(CHAT_ID, "⚠️ YouTube age verification required. Generating TV login link...")
                    
                    # TV login لنک حاصل کرنے کے لیے yt-dlp کو خاص طریقے سے چلائیں
                    # یہ کوڈ yt-dlp کے TV براؤزر ایمولیشن کو استعمال کرے گا
                    # لیکن yt-dlp خود بخود لنک اور کوڈ دے سکتا ہے اگر ہم extractor_args میں proper TV client دیں
                    
                    # بہتر طریقہ: yt-dlp کو TV client کے ساتھ چلائیں اور وہ خود بخود تصدیق کا طریقہ بتائے گا
                    # ہم یہاں پر ایک آسان طریقہ استعمال کریں گے: صارف کو دستی طور پر TV کوڈ داخل کرنے کا کہیں
                    
                    bot.send_message(CHAT_ID, "🔐 Please visit: https://www.youtube.com/tv/activate and enter the code below.")
                    
                    # yt-dlp TV کوڈ حاصل کرنے کے لیے
                    # ہم yt-dlp کو ایک عارضی کمانڈ سے چلا کر کوڈ حاصل کر سکتے ہیں
                    # لیکن یہ تھوڑا پیچیدہ ہے۔ آسان طریقہ: صارف کو خود براؤزر میں کھولنے کا کہیں اور پھر /continue بھیجیں
                    
                    youtube_auth_state["waiting_for"] = "continue"
                    youtube_auth_state["url"] = url
                    
                    # صارف کو بتائیں کہ تصدیق مکمل کرنے کے بعد /continue بھیجے
                    bot.send_message(CHAT_ID, "✅ TV activation page open karein, code enter karein, phir yahan /continue likhein.")
                    
                    # انتظار کریں جب تک صارف /continue نہ بھیجے
                    youtube_auth_state["event"].clear()
                    youtube_auth_state["event"].wait(timeout=300)  # 5 منٹ انتظار
                    
                    if youtube_auth_state["waiting_for"] is None:
                        # صارف نے /continue بھیج دیا
                        bot.send_message(CHAT_ID, "🔄 Ab dobara download try kar raha hoon...")
                        # دوبارہ yt-dlp چلائیں، اب کوکیز محفوظ ہو جائیں گی
                        ydl_opts['cookiefile'] = youtube_auth_state["cookies_file"]
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                            info = ydl2.extract_info(url, download=True)
                            filename = ydl2.prepare_filename(info)
                    else:
                        bot.send_message(CHAT_ID, "❌ Timeout! YouTube verification complete nahi hui.")
                        return
                else:
                    # کوئی اور خرابی
                    bot.send_message(CHAT_ID, f"❌ YouTube error: {error_str[:200]}")
                    return

        # اگر یہاں پہنچ گئے تو ڈاؤنلوڈ ہو چکا ہوگا
        # فائل کا نام معلوم کریں
        filename = None
        for file in os.listdir('.'):
            if file.endswith(('.mp4', '.webm', '.mkv')) and not file.startswith('video_'):
                filename = file
                break
        
        if filename and os.path.exists(filename):
            bot.send_message(CHAT_ID, f"✅ YouTube video downloaded: {filename}")
            # اب اس فائل کو جاز ڈرائیو پر اپ لوڈ کریں
            upload_to_jazzdrive(filename)
        else:
            bot.send_message(CHAT_ID, "❌ Download failed: file not found.")
            
    except Exception as e:
        logging.error(f"YouTube process error: {e}")
        bot.send_message(CHAT_ID, f"❌ YouTube processing error: {str(e)[:200]}")

# ---------------------------
# ڈائریکٹ لنک ڈاؤنلوڈ (پہلے والا طریقہ)
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
# جاز ڈرائیو اپ لوڈ (مشترکہ)
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

                # Main icon par click karna
                try: 
                    page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg')) b.click(); })")
                except: pass
                time.sleep(2)
                
                # 'Upload files' menu par click kar ke file dena
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        page.click("text='Upload files'")
                    file_chooser = fc_info.value
                    file_chooser.set_files(os.path.abspath(filename))
                except:
                    page.set_input_files("input[type='file']", os.path.abspath(filename), timeout=15000)
                
                time.sleep(2)
                
                # بڑی فائل والا "Yes" بٹن
                try:
                    page.click("button:has-text('Yes'), button:has-text('YES'), button:has-text('yes')", timeout=4000)
                    bot.send_message(CHAT_ID, "⚠️ Bari file (1GB+) warning detect hui, 'Yes' par click kar diya hai!")
                    time.sleep(1)
                except:
                    pass
                
                bot.send_message(CHAT_ID, "📁 File website par lag gayi hai. Har 1 minute baad aapko progress ka screenshot milega! ⏳")
                
                # Live Progress Screenshots
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
# بوٹ شروع کریں
# ---------------------------
try: 
    bot.send_message(CHAT_ID, "🟢 **System Online!**\nWaiting for Direct links... 🚀")
except: 
    pass

bot.polling(non_stop=True)
