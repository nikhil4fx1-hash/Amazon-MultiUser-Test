import asyncio
import os
import html
import json
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand
from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from aiohttp import web

# ----------------- ENVIRONMENT VARIABLES -----------------
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URI = os.environ.get('MONGO_URI')
AMAZON_AFFILIATE_TAG = os.environ.get('AFFILIATE_TAG', '')

if not BOT_TOKEN or not MONGO_URI:
    print("❌ ERROR: BOT_TOKEN or MONGO_URI is missing in Environment Variables!")
    exit(1)

AMAZON_NOW_URLS = [
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204924538031&title=Beverages",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=215540425031&title=Snacks+%26+Treats",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204992653031&title=Bath+%26+Body",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204952388031&title=Cleaners",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204952381031&title=Dishwash+%26+Detergents",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204869998031&title=Dairy+%26+Bread",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=220619214031&title=Fruits",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=218833871031&title=Vegetables"
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncIOMotorClient(MONGO_URI)
db = client['AmazonDealsBot']
users_collection = db['users']
prices_collection = db['prices']

# ----------------- HELPER FUNCTIONS -----------------
def parse_cookie_string(cookie_str):
    cookies = []
    cookie_str = cookie_str.strip()
    if cookie_str.startswith("[") and cookie_str.endswith("]"):
        try:
            json_cookies = json.loads(cookie_str)
            for c in json_cookies:
                if 'name' in c and 'value' in c:
                    cookies.append({"name": c['name'], "value": c['value'], "domain": ".amazon.in", "path": "/"})
            return cookies
        except: pass
    if cookie_str.lower().startswith("cookie:"): cookie_str = cookie_str[7:]
    parts = cookie_str.split(';')
    for part in parts:
        if '=' in part:
            k, v = part.split('=', 1)
            cookies.append({"name": k.strip(), "value": v.strip(), "domain": ".amazon.in", "path": "/"})
    return cookies

async def send_telegram_alert(user_id, title, new_price, old_price, link, img_url="", mrp=0, is_mega_deal=False):
    safe_title = html.escape(title)
    safe_link = html.escape(link)
    
    if is_mega_deal:
        discount_pct = round(((mrp - new_price) / mrp) * 100) if mrp > 0 else 50
        message = f"🔥 <b>MEGA DISCOUNT (50%+ OFF)</b> 🔥\n\n📦 {safe_title}\n💰 Deal Price: <b>₹{new_price}</b>\n❌ MRP: <s>₹{mrp}</s>\n🏷️ Discount: <b>{discount_pct}% OFF</b>\n\n🔗 🛒 <a href='{safe_link}'>Grab it Fast!</a>"
    else:
        drop_amount = round(old_price - new_price, 2)
        message = f"📉 <b>PRICE DROP ALERT</b> 📉\n\n📦 {safe_title}\n💰 New Price: <b>₹{new_price}</b> (Dropped by ₹{drop_amount})\n❌ Old Price: <s>₹{old_price}</s>\n\n🔗 🛒 <a href='{safe_link}'>Grab it Fast!</a>"
    
    try:
        if img_url and img_url.startswith('http'):
            await bot.send_photo(chat_id=user_id, photo=img_url, caption=message, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=user_id, text=message, parse_mode="HTML")
    except: pass

# ----------------- TELEGRAM BOT COMMANDS -----------------
async def set_bot_commands():
    commands = [BotCommand(command="start", description="Start Bot & Set Cookie")]
    await bot.set_my_commands(commands)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    if not await users_collection.find_one({"user_id": user_id}):
        await users_collection.insert_one({"user_id": user_id, "name": first_name, "cookie": None})
    
    welcome_msg = (
        f"Hello {first_name}! 👋\n\n"
        "Welcome to the **Amazon Fresh/Now Deals Bot**.\n"
        "To get localized alerts, please set your Amazon Location Cookie by clicking the button below."
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍪 Set Location Cookie", callback_data="set_cookie")],
        [InlineKeyboardButton(text="📖 How to get Cookie? (Guide)", callback_data="cookie_tutorial")]
    ])
    await message.answer(welcome_msg, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == 'set_cookie')
async def process_callback_set_cookie(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    msg = (
        "👇 **Please paste your Amazon Location Cookie below:**\n\n"
        "*(If you don't know how to extract it, click the 'How to get Cookie' button from the main menu)*"
    )
    await bot.send_message(callback_query.from_user.id, msg, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == 'cookie_tutorial')
async def process_callback_cookie_tutorial(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    tutorial_msg = (
        "🍪 **How to get your Amazon Location Cookie**\n\n"
        "📱 **Option 1: For Mobile Users (Android)**\n"
        "1. Download **Kiwi Browser** from the Play Store.\n"
        "2. Search and install the **Cookie Editor** extension in Kiwi.\n"
        "3. Open `amazon.in`, log in to your account, and set your delivery **Pincode** at the top.\n"
        "4. Click the 3-dot menu (⋮) and open **Cookie Editor** at the bottom.\n"
        "5. Find the cookie named `session-id`, copy its **Value**.\n"
        "6. Paste that copied value here in the bot!\n\n"
        "💻 **Option 2: For PC/Laptop Users**\n"
        "1. Open Amazon.in on Chrome/Firefox, log in, and set your Pincode.\n"
        "2. Right-click anywhere on the page and select **Inspect** (or press F12).\n"
        "3. Go to the **Application** tab (or **Storage** in Firefox).\n"
        "4. On the left sidebar, expand **Cookies** and click on `https://www.amazon.in`.\n"
        "5. In the list, find `session-id`, double-click its **Value**, and copy it.\n"
        "6. Paste that copied value here in the bot!\n\n"
        "*(Your session-id looks something like this: 260-1234567-8901234)*"
    )
    await bot.send_message(callback_query.from_user.id, tutorial_msg, parse_mode="Markdown")

@dp.message(lambda message: message.text and ("session-id" in message.text.lower() or message.text.strip().startswith("[")))
async def save_user_cookie(message: types.Message):
    await users_collection.update_one({"user_id": message.from_user.id}, {"$set": {"cookie": message.text}})
    await message.answer("✅ **Your Cookie has been successfully set!**\n\nThe bot will start scanning for deals in your location shortly.", parse_mode="Markdown")

# ----------------- BACKGROUND MULTI-USER SCRAPER -----------------
async def run_scraper_loop():
    await asyncio.sleep(10) 
    while True:
        try:
            users = await users_collection.find({"cookie": {"$ne": None}}).to_list(length=None)
            if not users:
                await asyncio.sleep(60)
                continue

            print(f"🔍 Scanning started for {len(users)} users...")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True, 
                    args=[
                        '--no-sandbox', 
                        '--disable-dev-shm-usage', 
                        '--disable-gpu', 
                        '--disable-blink-features=AutomationControlled'
                    ]
                )
                
                for user in users:
                    user_id = user['user_id']
                    parsed_cookies = parse_cookie_string(user['cookie'])
                    if not parsed_cookies: continue

                    user_db_record = await prices_collection.find_one({"user_id": user_id})
                    user_price_db = user_db_record['products'] if user_db_record else {}
                    updated_user_db = {}
                    
                    try:
                        context = await browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                            viewport={'width': 1920, 'height': 1080},
                            locale='en-IN',
                            timezone_id='Asia/Kolkata',
                            extra_http_headers={
                                'Accept-Language': 'en-IN,en;q=0.9',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                                'Upgrade-Insecure-Requests': '1'
                            }
                        )
                        
                        await context.add_cookies(parsed_cookies)
                        page = await context.new_page()
                        await stealth_async(page)
                        
                        for url in AMAZON_NOW_URLS:
                            try:
                                await asyncio.sleep(random.uniform(6.0, 10.0))
                                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                                await asyncio.sleep(random.uniform(3.0, 5.0))
                                
                                page_content = await page.content()
                                if "rush hour and traffic is piling up" in page_content or "Oops!" in page_content:
                                    print("⚠️ Amazon Traffic Block detected! Waiting 30 seconds...")
                                    await asyncio.sleep(30)
                                    continue 
                                
                                await page.evaluate("window.scrollBy(0, 1500);")
                                await asyncio.sleep(random.uniform(2.0, 4.0))
                                await page.evaluate("window.scrollBy(0, 1500);")
                                await asyncio.sleep(3)
                                
                                js_script = """
                                () => {
                                    let results = {};
                                    let elements = Array.from(document.querySelectorAll('span, div, p')).filter(el => el.children.length === 0 && el.innerText && el.innerText.includes('₹'));
                                    let processedCards = new Set();
                                    elements.forEach(el => {
                                        let card = el; let attempts = 0;
                                        while(card.parentElement && attempts < 10) {
                                            let parent = card.parentElement;
                                            if(parent.querySelectorAll('img').length > 1 || parent.innerText.length > 350) break; 
                                            card = parent; attempts++;
                                        }
                                        if(processedCards.has(card)) return; processedCards.add(card);
                                        let text = card.innerText; if(!text || text.length > 350) return;
                                        let lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                                        let allPrices = [...text.matchAll(/₹\\s*([0-9,]+(?:\\.[0-9]+)?)/g)].map(m => parseFloat(m[1].replace(/,/g, '')));
                                        if(allPrices.length === 0) return;
                                        let price = allPrices[0]; let mrp = allPrices.length > 1 ? Math.max(...allPrices) : price;
                                        let title = ""; let titleIndex = -1;
                                        for(let i=0; i<lines.length; i++) {
                                            let lower = lines[i].toLowerCase();
                                            if(lower.includes('★') || lower.includes('mins') || lines[i].match(/^[0-9.]+$/) || lower.includes('%') || lower.includes('₹') || lower === 'add' || lower === 'sponsored' || lower.includes('shop by') || lower.includes('delivery')) continue;
                                            if(lines[i].length > 7) { title = lines[i]; titleIndex = i; break; }
                                        }
                                        if (title) {
                                            let imgNode = null; let searchNode = card;
                                            for(let i=0; i<4; i++) {
                                                if(!searchNode) break;
                                                let imgs = searchNode.querySelectorAll('img');
                                                if(imgs.length > 0) {
                                                    let validImgs = Array.from(imgs).filter(img => !img.src.includes('stars') && !img.src.includes('sponsor') && img.src.startsWith('http'));
                                                    if(validImgs.length > 0) { imgNode = validImgs[0]; break; }
                                                }
                                                searchNode = searchNode.parentElement;
                                            }
                                            let imgUrl = imgNode ? imgNode.src : "";
                                            let linkEl = card.querySelector('a');
                                            let link = (linkEl && linkEl.href && !linkEl.href.includes('javascript') && !linkEl.href.endsWith('/')) ? linkEl.href : "https://www.amazon.in/s?k=" + encodeURIComponent(title);
                                            let uid = title.toLowerCase().replace(/[^a-z0-9]/g, '');
                                            if(uid.length > 5) results[uid] = { title: title, price: price, mrp: mrp, link: link, img: imgUrl };
                                        }
                                    });
                                    return results;
                                }
                                """
                                extracted_products = await page.evaluate(js_script)
                                
                                if not extracted_products:
                                    try:
                                        screenshot_path = "debug_screenshot.png"
                                        await page.screenshot(path=screenshot_path)
                                        await bot.send_photo(chat_id=user_id, photo=FSInputFile(screenshot_path), caption=f"⚠️ Products did not load on this page:\n{url}")
                                    except: pass
                                
                                for uid, data in extracted_products.items():
                                    title = data['title']; new_price = data['price']; mrp = data['mrp']; link = data['link']; img_url = data['img']
                                    if AMAZON_AFFILIATE_TAG: link = f"{link}{'&' if '?' in link else '?'}tag={AMAZON_AFFILIATE_TAG}"
                                    discount_pct = round(((mrp - new_price) / mrp) * 100) if mrp > new_price else 0
                                    mega_alert_sent = False

                                    if uid in user_price_db:
                                        old_price = user_price_db[uid]['price']
                                        mega_alert_sent = user_price_db[uid].get('mega_alert_sent', False)
                                        if new_price < old_price:
                                            is_mega = discount_pct >= 50
                                            await send_telegram_alert(user_id, title, new_price, old_price, link, img_url, mrp, is_mega)
                                            mega_alert_sent = is_mega
                                        elif new_price == old_price and discount_pct >= 50 and not mega_alert_sent:
                                            await send_telegram_alert(user_id, title, new_price, old_price, link, img_url, mrp, True)
                                            mega_alert_sent = True
                                    else:
                                        if discount_pct >= 50:
                                            await send_telegram_alert(user_id, title, new_price, mrp, link, img_url, mrp, True)
                                            mega_alert_sent = True
                                    
                                    updated_user_db[uid] = {"price": new_price, "mega_alert_sent": mega_alert_sent}
                            except Exception as inner_e: print(f"URL Error: {inner_e}"); continue
                        await context.close()
                        user_price_db.update(updated_user_db)
                        await prices_collection.update_one({"user_id": user_id}, {"$set": {"products": user_price_db}}, upsert=True)
                        
                    except Exception as e: print(f"User Error: {e}")
                
                await browser.close()
                
        except Exception as e: print(f"⚠️ Critical Loop Error: {e}")
        await asyncio.sleep(900)

# ----------------- WEB SERVER -----------------
async def handle_ping(request):
    return web.Response(text="Bot is awake!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await set_bot_commands() 
    await start_web_server()
    asyncio.create_task(run_scraper_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
