import asyncio
import os
import html
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright

# ----------------- കോൺഫിഗറേഷൻ (Render Environment Variables) -----------------
# Render-ൽ ഡിപ്ലോയ് ചെയ്യുമ്പോൾ ഈ ടോക്കണുകൾ Environment Variables ആയി കൊടുക്കുന്നതാണ് സുരക്ഷിതം. 
BOT_TOKEN = os.environ.get('BOT_TOKEN', '9190242279:AAEsAnht_kUykHnerqeTfwoLp8Lb3PZiK7U')
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://nikhil4fx_db_user:2B8qKm4kwS9X4bwR@cluster0.pp40quf.mongodb.net/?retryWrites=true&w=majority')
AMAZON_AFFILIATE_TAG = os.environ.get('AFFILIATE_TAG', 'flashsale069-21')

AMAZON_NOW_URLS = [
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204924538031&title=Beverages",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=215540425031&title=Snacks+%26+Treats",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204992653031&title=Bath+%26+Body",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204952388031&title=Cleaners",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204952381031&title=Dishwash+%26+Detergents",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=204869998031&title=Dairy+%26+Bread",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=220619214031&title=Fruits",
    "https://www.amazon.in/tez/browse/explore/collection?qcbrand=qqfsWw9RkO&nodeId=218833871031&title=Vegetables"
    # ആവശ്യമെങ്കിൽ ബാക്കി ലിങ്കുകൾ കൂടി ഇവിടെ ചേർക്കാം...
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ഡാറ്റാബേസ് കണക്ഷൻ
client = AsyncIOMotorClient(MONGO_URI)
db = client['AmazonDealsBot']
users_collection = db['users']
prices_collection = db['prices'] # ഓരോ യൂസറിന്റെയും പ്രൈസ് ട്രാക്ക് ചെയ്യാൻ

# ----------------- HELPER FUNCTIONS -----------------

def parse_cookie_string(cookie_str):
    """യൂസർ നൽകുന്ന കുക്കി ടെക്സ്റ്റിനെ Playwright ഫോർമാറ്റിലേക്ക് മാറ്റുന്നു"""
    cookies = []
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:]
    
    parts = cookie_str.split(';')
    for part in parts:
        if '=' in part:
            k, v = part.split('=', 1)
            cookies.append({
                "name": k.strip(),
                "value": v.strip(),
                "domain": ".amazon.in",
                "path": "/"
            })
    return cookies

async def send_telegram_alert(user_id, title, new_price, old_price, link, img_url="", mrp=0, is_mega_deal=False):
    """ഒരു പ്രത്യേക യൂസറിന് ഡീൽ അലേർട്ട് അയക്കുന്നു"""
    safe_title = html.escape(title)
    safe_link = html.escape(link)
    
    if is_mega_deal:
        discount_pct = round(((mrp - new_price) / mrp) * 100) if mrp > 0 else 50
        message = (
            f"🔥 <b>MEGA DISCOUNT (50%+ OFF)</b> 🔥\n\n"
            f"📦 {safe_title}\n"
            f"💰 Deal Price: <b>₹{new_price}</b>\n"
            f"❌ MRP: <s>₹{mrp}</s>\n"
            f"🏷️ Discount: <b>{discount_pct}% OFF</b>\n\n"
            f"🔗 🛒 <a href='{safe_link}'>Grab it Fast!</a>"
        )
    else:
        drop_amount = round(old_price - new_price, 2)
        message = (
            f"📉 <b>PRICE DROP ALERT</b> 📉\n\n"
            f"📦 {safe_title}\n"
            f"💰 New Price: <b>₹{new_price}</b> (Dropped by ₹{drop_amount})\n"
            f"❌ Old Price: <s>₹{old_price}</s>\n\n"
            f"🔗 🛒 <a href='{safe_link}'>Grab it Fast!</a>"
        )
    
    try:
        if img_url and img_url.startswith('http'):
            await bot.send_photo(chat_id=user_id, photo=img_url, caption=message, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=user_id, text=message, parse_mode="HTML", disable_web_page_preview=False)
    except Exception as e:
        print(f"Error sending alert to {user_id}: {e}")
        # ഫോട്ടോ അയക്കാൻ പറ്റിയില്ലെങ്കിൽ ടെക്സ്റ്റ് ആയി അയക്കാൻ ശ്രമിക്കുന്നു
        try:
            await bot.send_message(chat_id=user_id, text=message, parse_mode="HTML", disable_web_page_preview=False)
        except:
            pass

# ----------------- TELEGRAM BOT COMMANDS -----------------

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    user_exists = await users_collection.find_one({"user_id": user_id})
    if not user_exists:
        await users_collection.insert_one({
            "user_id": user_id,
            "name": first_name,
            "cookie": None
        })
    
    welcome_text = f"ഹലോ {first_name}!\nAmazon Fresh/Now ലൊക്കേഷൻ ഡീലുകൾ അറിയാൻ താഴെയുള്ള ബട്ടണിൽ ക്ലിക്ക് ചെയ്ത് Cookie സെറ്റ് ചെയ്യുക."
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍪 Set Location Cookie", callback_data="set_cookie")]
    ])
    await message.answer(welcome_text, reply_markup=markup)

@dp.callback_query(lambda c: c.data == 'set_cookie')
async def process_callback_set_cookie(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "നിങ്ങളുടെ ലൊക്കേഷൻ Cookie താഴെ പേസ്റ്റ് ചെയ്യുക:\n\n(session-id=... എന്ന് തുടങ്ങുന്ന ടെക്സ്റ്റ്)")

@dp.message(lambda message: message.text and "session-id" in message.text.lower())
async def save_user_cookie(message: types.Message):
    user_id = message.from_user.id
    cookie_data = message.text
    
    await users_collection.update_one({"user_id": user_id}, {"$set": {"cookie": cookie_data}})
    await message.answer("✅ നിങ്ങളുടെ Cookie വിജയകരമായി സെറ്റ് ചെയ്തു! സ്കാനിങ് ഉടൻ ആരംഭിക്കുന്നതായിരിക്കും.")

# ----------------- BACKGROUND MULTI-USER SCRAPER -----------------

async def run_scraper_loop():
    await asyncio.sleep(5) # ബോട്ട് സ്റ്റാർട്ട് ആയി കുറച്ചു നേരം കാത്തിരിക്കുന്നു
    
    while True:
        users = await users_collection.find({"cookie": {"$ne": None}}).to_list(length=None)
        
        if not users:
            print("കുക്കി നൽകിയ യൂസർമാർ ആരുമില്ല. 1 മിനിറ്റ് കാത്തിരിക്കുന്നു...")
            await asyncio.sleep(60)
            continue

        print(f"🔍 {len(users)} യൂസർമാർക്കായി സ്കാനിങ് തുടങ്ങുന്നു...")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                
                for user in users:
                    user_id = user['user_id']
                    cookie_text = user['cookie']
                    parsed_cookies = parse_cookie_string(cookie_text)
                    
                    if not parsed_cookies:
                        continue

                    # ഈ യൂസറിന്റെ മുൻപത്തെ പ്രൈസുകൾ ഡാറ്റാബേസിൽ നിന്നും എടുക്കുന്നു
                    user_db_record = await prices_collection.find_one({"user_id": user_id})
                    user_price_db = user_db_record['products'] if user_db_record else {}
                    updated_user_db = {}
                    
                    try:
                        context = await browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        )
                        context.set_default_timeout(60000)
                        await context.add_cookies(parsed_cookies)
                        
                        page = await context.new_page()
                        print(f"Scanning for User ID: {user_id}")
                        
                        for url in AMAZON_NOW_URLS:
                            try:
                                await page.goto(url, wait_until="networkidle")
                                await page.evaluate("window.scrollBy(0, 1000);")
                                await asyncio.sleep(2)
                                
                                # താങ്കളുടെ ഒറിജിനൽ JS Script
                                js_script = """
                                () => {
                                    let results = {};
                                    let elements = Array.from(document.querySelectorAll('span, div, p'))
                                        .filter(el => el.children.length === 0 && el.innerText && el.innerText.includes('₹'));
                                    let processedCards = new Set();
                                    elements.forEach(el => {
                                        let card = el;
                                        let attempts = 0;
                                        while(card.parentElement && attempts < 10) {
                                            let parent = card.parentElement;
                                            if(parent.querySelectorAll('img').length > 1 || parent.innerText.length > 350) break; 
                                            card = parent; attempts++;
                                        }
                                        if(processedCards.has(card)) return;
                                        processedCards.add(card);
                                        let text = card.innerText;
                                        if(!text || text.length > 350) return;
                                        let lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                                        let allPrices = [...text.matchAll(/₹\\s*([0-9,]+(?:\\.[0-9]+)?)/g)].map(m => parseFloat(m[1].replace(/,/g, '')));
                                        if(allPrices.length === 0) return;
                                        let price = allPrices[0];
                                        let mrp = allPrices.length > 1 ? Math.max(...allPrices) : price;
                                        let title = ""; let titleIndex = -1;
                                        for(let i=0; i<lines.length; i++) {
                                            let lower = lines[i].toLowerCase();
                                            if(lower.includes('★') || lower.includes('mins') || lines[i].match(/^[0-9.]+$/) || lower.includes('%') || lower.includes('₹') || lower === 'add' || lower === 'sponsored' || lower.includes('shop by') || lower.includes('delivery')) continue;
                                            if(lines[i].length > 7) { title = lines[i]; titleIndex = i; break; }
                                        }
                                        if (title) {
                                            if(titleIndex !== -1 && titleIndex + 1 < lines.length) {
                                                let nextLine = lines[titleIndex + 1];
                                                if(nextLine.length > 1 && nextLine.length < 15 && !nextLine.includes('₹') && !nextLine.includes('%')) {
                                                    title = title + " (" + nextLine + ")";
                                                }
                                            }
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
                                            if(uid.length > 5) {
                                                results[uid] = { title: title, price: price, mrp: mrp, link: link, img: imgUrl };
                                            }
                                        }
                                    });
                                    return results;
                                }
                                """
                                extracted_products = await page.evaluate(js_script)
                                
                                for uid, data in extracted_products.items():
                                    title = data['title']
                                    new_price = data['price']
                                    mrp = data['mrp']
                                    link = data['link']
                                    img_url = data['img']

                                    if AMAZON_AFFILIATE_TAG:
                                        separator = "&" if "?" in link else "?"
                                        link = f"{link}{separator}tag={AMAZON_AFFILIATE_TAG}"

                                    discount_pct = round(((mrp - new_price) / mrp) * 100) if mrp > new_price else 0
                                    mega_alert_sent = False

                                    if uid in user_price_db:
                                        old_price = user_price_db[uid]['price']
                                        mega_alert_sent = user_price_db[uid].get('mega_alert_sent', False)
                                        
                                        if new_price < old_price:
                                            if discount_pct >= 50:
                                                await send_telegram_alert(user_id, title, new_price, old_price, link, img_url, mrp, True)
                                                mega_alert_sent = True
                                            else:
                                                await send_telegram_alert(user_id, title, new_price, old_price, link, img_url)
                                                mega_alert_sent = False
                                        elif new_price == old_price:
                                            if discount_pct >= 50 and not mega_alert_sent:
                                                await send_telegram_alert(user_id, title, new_price, old_price, link, img_url, mrp, True)
                                                mega_alert_sent = True
                                    else:
                                        if discount_pct >= 50:
                                            await send_telegram_alert(user_id, title, new_price, mrp, link, img_url, mrp, True)
                                            mega_alert_sent = True
                                    
                                    updated_user_db[uid] = {
                                        "price": new_price, 
                                        "mega_alert_sent": mega_alert_sent
                                    }
                            except Exception as inner_e:
                                print(f"URL Error for {user_id}: {inner_e}")
                                continue
                        
                        await context.close()
                        
                        # യൂസറിന്റെ പുതിയ പ്രൈസുകൾ ഡാറ്റാബേസിൽ സേവ് ചെയ്യുന്നു
                        user_price_db.update(updated_user_db)
                        await prices_collection.update_one(
                            {"user_id": user_id}, 
                            {"$set": {"products": user_price_db}}, 
                            upsert=True
                        )
                        
                        await asyncio.sleep(3) # അടുത്ത യൂസറിലേക്ക് പോകുന്നതിന് മുൻപ് ബ്രേക്ക്
                        
                    except Exception as e:
                        print(f"Error processing user {user_id}: {e}")
                
                await browser.close()
        except Exception as e:
            print(f"Browser Launch Error: {e}")
            
        print("✅ എല്ലാ യൂസർമാരുടെയും സ്കാനിങ് കഴിഞ്ഞു. അടുത്ത സ്കാനിങ്ങിനായി 15 മിനിറ്റ് കാത്തിരിക്കുന്നു...")
        await asyncio.sleep(900)  # 15 മിനിറ്റ് (900 സെക്കൻഡ്)

# ----------------- MAIN ENTRY POINT -----------------

async def main():
    print("🤖 Multi-User Bot is starting...")
    asyncio.create_task(run_scraper_loop()) # സ്ക്രാപ്പർ ബാക്ക്ഗ്രൗണ്ടിൽ റൺ ചെയ്യാൻ തുടങ്ങുന്നു
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
