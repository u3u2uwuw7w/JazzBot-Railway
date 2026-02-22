import os
import time
import threading
import queue
import logging
import re
import telebot
from playwright.sync_api import sync_playwright

# ------------------ PYTUBEFIX IMPORT WITH VERSION CHECK ------------------
try:
    from pytubefix import YouTube
    from pytubefix.cli import on_progress
    import inspect
    sig = inspect.signature(YouTube.__init__)
    HAS_CALLBACK = 'on_oauth_callback' in sig.parameters
    PYTUBEFIX_AVAILABLE = True
except ImportError:
    PYTUBEFIX_AVAILABLE = False
    HAS_CALLBACK = False

# ------------------ CONFIG ------------------
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

# ------------------ COMMANDS ------------------
@bot.message_handler(commands=['start'])
def start(m):
    status = f"pytubefix: {'✅' if PYTUBEFIX_AVAILABLE else '❌'}, Callback: {'✅' if HAS_CALLBACK else '❌'}"
    bot.reply_to(m, f"🤖 Bot Online!\n{status}\nSend YouTube/Direct link")

@bot.message_handler(commands=['continue'])
def continue_yt(m):
    if youtube_state["waiting_for"] == "continue":
        youtube_state["waiting_for"] = None
        youtube_state["event"].set()
        bot.reply_to(m, "✅ Continuing download...")
    else:
        bot.reply_to(m, "❌ No pending verification")

@bot.message_handler(commands=['login'])
def login(m):
    login_state["waiting_for"] = "number"
    bot.reply_to(m, "📱 Apna Jazz Number bhejein (03XXXXXXXXX):")

# ------------------ JAZZ LOGIN ------------------
@bot.message_handler(func=lambda m: login_state["waiting_for"] == "number")
def get_num(m):
    login_state["number"] = m.text
    login_state["waiting_for"] = "otp"
    bot.reply_to(m, "⏳ OTP bhej raha hoon...")
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
            time.sleep(3)
            page.fill("input[type='text']", login_state["number"])
            page.click("button:has-text('Get OTP')")
            bot.send_message(CHAT_ID, "📩 OTP bhej diya! Ab OTP likhein:")
            login_state["event"].wait(timeout=60)
            if login_state["otp"]:
                page.fill("input[type='text']", login_state["otp"])
                page.click("button:has-text('Verify')")
                time.sleep(3)
                browser.contexts[0].storage_state(path="state.json")
                bot.send_message(CHAT_ID, "🎉 Jazz Login Successful!")
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Login error: {e}")

# ------------------ LINK HANDLER ------------------
def is_youtube_link(text):
    return re.search(r'(youtube\.com|youtu\.be)', text) is not None

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_link(m):
    link = m.text.strip()
    if is_youtube_link(link) and PYTUBEFIX_AVAILABLE:
        task_queue.put(("youtube", link))
        bot.reply_to(m, f"✅ YouTube added! Position: {task_queue.qsize()}")
    elif is_youtube_link(link) and not PYTUBEFIX_AVAILABLE:
        bot.reply_to(m, "❌ YouTube disabled (pytubefix missing)")
        return
    else:
        task_queue.put(("direct", link))
        bot.reply_to(m, f"✅ Direct link added! Position: {task_queue.qsize()}")

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
                process_direct(task_data)
        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ Error: {e}")
        time.sleep(2)
    is_working = False

# ------------------ YOUTUBE PROCESSING ------------------
def process_youtube(url):
    try:
        bot.send_message(CHAT_ID, "▶️ Processing YouTube link...")

        if HAS_CALLBACK:
            def auth_callback(code, verification_url):
                bot.send_message(CHAT_ID,
                    f"🔐 **LOGIN REQUIRED**\n\n"
                    f"**URL:** {verification_url}\n"
                    f"**Code:** `{code}`\n\n"
                    f"Verify karo, phir /continue bhejo.")
                youtube_state["waiting_for"] = "continue"
                youtube_state["event"].clear()

            yt = YouTube(url,
                        use_oauth=True,
                        allow_oauth_cache=True,
                        on_oauth_callback=auth_callback)
        else:
            # Fallback: ask user to check console (should not happen if installation is correct)
            bot.send_message(CHAT_ID,
                "⚠️ Old pytubefix version detected. Please wait for code in console.\n"
                "After verification, send /continue")
            yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
            youtube_state["waiting_for"] = "continue"
            youtube_state["event"].clear()

        # Wait for verification if needed
        if youtube_state["waiting_for"] == "continue":
            youtube_state["event"].wait(timeout=300)
            if youtube_state["waiting_for"] is not None:
                bot.send_message(CHAT_ID, "❌ Timeout! Send link again.")
                return

        # Video info fetched
        bot.send_message(CHAT_ID, f"✅ Found: {yt.title}")

        # Ask for quality
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎬 Video (best)", callback_data=f"video_{url}"),
            telebot.types.InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"audio_{url}")
        )
        bot.send_message(CHAT_ID, "Choose format:", reply_markup=markup)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ YouTube error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("video_"):
        url = call.data[6:]
        threading.Thread(target=download_youtube, args=(url, call.message.chat.id, "video")).start()
        bot.answer_callback_query(call.id, "Downloading video...")
    elif call.data.startswith("audio_"):
        url = call.data[6:]
        threading.Thread(target=download_youtube, args=(url, call.message.chat.id, "audio")).start()
        bot.answer_callback_query(call.id, "Downloading audio...")

def download_youtube(url, chat_id, mode):
    try:
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)

        if mode == "audio":
            stream = yt.streams.get_audio_only()
            out_file = stream.download(output_path=DOWNLOAD_DIR)
            base, ext = os.path.splitext(out_file)
            new_file = base + ".mp3"
            os.rename(out_file, new_file)
            filename = new_file
        else:
            stream = yt.streams.get_highest_resolution()
            filename = stream.download(output_path=DOWNLOAD_DIR)

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        bot.send_message(chat_id, f"✅ Downloaded: {yt.title[:30]}... ({size_mb:.1f} MB)")
        upload_to_jazzdrive(filename)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Download error: {e}")

# ------------------ DIRECT LINK DOWNLOAD ------------------
def process_direct(link):
    filename = f"video_{int(time.time())}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    bot.send_message(CHAT_ID, "🌍 Downloading direct link...")
    os.system(f'aria2c -x 16 -d "{DOWNLOAD_DIR}" -o "{filename}" "{link}"')
    if os.path.exists(filepath):
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        bot.send_message(CHAT_ID, f"✅ Downloaded: {size_mb:.1f} MB")
        upload_to_jazzdrive(filepath)
    else:
        bot.send_message(CHAT_ID, "❌ Direct download failed.")

# ------------------ JAZZ DRIVE UPLOAD ------------------
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
                bot.send_message(CHAT_ID, "⚠️ Jazz Drive login expired! Use /login")
                browser.close()
                return

            # Upload file
            try:
                with page.expect_file_chooser() as fc_info:
                    page.click("text='Upload files'")
                fc_info.value.set_files(os.path.abspath(filepath))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filepath))

            time.sleep(5)

            # Handle large file warning if any
            try:
                page.click("button:has-text('Yes')", timeout=3000)
            except:
                pass

            bot.send_message(CHAT_ID, f"✅ Uploaded: {os.path.basename(filepath)}")
            os.remove(filepath)
            browser.close()
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Upload error: {e}")

# ------------------ START ------------------
if __name__ == "__main__":
    try:
        if HAS_CALLBACK:
            bot.send_message(CHAT_ID, "🟢 **Bot Online!** (Latest pytubefix with callback)")
        else:
            bot.send_message(CHAT_ID, "🟠 **Bot Online!** (Old pytubefix, may need manual code)")
    except:
        pass
    bot.polling(non_stop=True)
