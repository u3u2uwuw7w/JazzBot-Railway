import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from playwright.async_api import async_playwright

# 🔑 Aapka Bot Token
TOKEN = "8334787902:AAHrmpTxnBCmqhfCDBaAAdU4j7IB5Xdd1ks"
bot = AsyncTeleBot(TOKEN)

bot_state = "IDLE"
current_user_input = ""
user_input_event = None

def get_event():
    global user_input_event
    if user_input_event is None:
        user_input_event = asyncio.Event()
    return user_input_event

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    await bot.reply_to(message, "✨ **Jazz Drive Master Bot (Railway Edition)!** ✨\n\nBhai, direct link bhejo main upload kar dunga!", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
async def handle_all_messages(message):
    global bot_state, current_user_input
    chat_id = message.chat.id
    text = message.text.strip()

    if bot_state in ["WAITING_NUMBER", "WAITING_OTP"]:
        current_user_input = text
        bot_state = "PROCESSING"
        get_event().set()
        return
        
    if text.startswith("http"):
        if bot_state != "IDLE":
            await bot.send_message(chat_id, "⚠️ Bhai, ek file already process ho rahi hai. Wait karein!")
            return
            
        bot_state = "PROCESSING"
        await bot.send_message(chat_id, "📥 **Link receive ho gaya!** Downloading shuru...")
        asyncio.create_task(process_upload(chat_id, text))
    else:
        await bot.send_message(chat_id, "❌ Link ya OTP bhejein.")

async def get_input_from_user(chat_id, prompt_text, new_state):
    global bot_state, current_user_input
    await bot.send_message(chat_id, prompt_text, parse_mode="Markdown")
    bot_state = new_state
    evt = get_event()
    evt.clear() 
    try:
        await asyncio.wait_for(evt.wait(), timeout=120.0)
        return current_user_input
    except asyncio.TimeoutError:
        await bot.send_message(chat_id, "⏰ Timeout! Operation cancel ho gaya.")
        bot_state = "IDLE"
        return None

async def process_upload(chat_id, link):
    global bot_state
    file_name = "video.mp4"
    COOKIE_FILE = "jazz_cookies.json" 
    
    try:
        if os.path.exists(file_name): os.remove(file_name)
        
        # 🔥 THE FIX: aria2 ki jagah Railway-Approved 'curl' use kar rahe hain
        os.system(f"curl -L -o {file_name} '{link}'")
        
        if not os.path.exists(file_name):
            await bot.send_message(chat_id, "❌ Download Error! Link kharab hai.")
            bot_state = "IDLE"
            return
            
        await bot.send_message(chat_id, "✅ Download Complete! Jazz Drive khol raha hoon...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context(storage_state=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None)
            page = await context.new_page()
            
            await page.goto("https://cloud.jazzdrive.com.pk/")
            await page.wait_for_load_state("networkidle")

            is_logged_in = False
            try:
                await page.wait_for_selector("text=Let's give you the best experience possible", timeout=4000)
                is_logged_in = True
            except:
                if "highlights" in page.url or "files" in page.url:
                    is_logged_in = True

            if not is_logged_in:
                mobile_number = await get_input_from_user(chat_id, "⚠️ **Login Expire Hai!**\n📱 Apna Jazz Number (03...):", "WAITING_NUMBER")
                if not mobile_number: return 
                await page.locator("//*[@id='msisdn']").fill(mobile_number)
                await asyncio.sleep(1)
                await page.locator("//*[@id='signinbtn']").first.click(force=True)

                otp_code = await get_input_from_user(chat_id, "⏳ OTP bhej diya hai!\n📩 4-Digit OTP Code bhejein:", "WAITING_OTP")
                if not otp_code: return
                await page.locator("//input[@aria-label='Digit 1']").press_sequentially(otp_code, delay=100)
                await asyncio.sleep(1)
                
                try: await page.locator("//*[@id='signinbtn']").last.click(force=True, timeout=5000)
                except: pass
                    
                await bot.send_message(chat_id, "✅ Login Successful!")
                await page.wait_for_timeout(8000)
                await context.storage_state(path=COOKIE_FILE)

            await bot.send_message(chat_id, "🧹 File attach kar raha hoon...")
            try: await page.get_by_text("Accept All").click(timeout=3000)
            except: pass

            await page.evaluate("""
                let buttons = document.querySelectorAll('header button');
                for(let btn of buttons) {
                    if(btn.innerHTML.includes('path') || btn.innerHTML.includes('svg') || btn.innerHTML.includes('cloud')) { btn.click(); }
                }
            """)
            await asyncio.sleep(2) 
            
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await page.get_by_text("Upload files", exact=False).first.click(force=True)
                
            await fc_info.value.set_files(os.path.abspath(file_name)) 
            try: await page.get_by_text("Yes", exact=True).click(timeout=5000)
            except: pass

            await bot.send_message(chat_id, "🚀 **File Upload shuru!**")
            await page.get_by_text("Uploads completed", exact=False).wait_for(state="visible", timeout=0)
            await bot.send_message(chat_id, "🎉 **MUBARAK HO!**\n✅ File successfully upload ho gayi!")

    except Exception as ex:
        await bot.send_message(chat_id, f"❌ Error: {str(ex)[:100]}")
    finally:
        if 'browser' in locals(): await browser.close()
        if os.path.exists(file_name): os.remove(file_name)
        bot_state = "IDLE" 

if __name__ == '__main__':
    print("🤖 Railway Bot engine start ho raha hai...")
    asyncio.run(bot.polling(non_stop=True, request_timeout=90))
