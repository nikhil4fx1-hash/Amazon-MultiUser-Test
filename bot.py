import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright

# ടോക്കണുകൾ (Render Environment Variables വഴി കൊടുക്കുന്നതാണ് സുരക്ഷിതം. തൽക്കാലം ഇവിടെ നേരിട്ട് കൊടുക്കാം)
BOT_TOKEN = "9190242279:AAEsAnht_kUykHnerqeTfwoLp8Lb3PZiK7U"
MONGO_URI = "mongodb+srv://nikhil4fx_db_user:2B8qKm4kwS9X4bwR@cluster0.pp40quf.mongodb.net/?retryWrites=true&w=majority"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ഡാറ്റാബേസ് കണക്ഷൻ
client = AsyncIOMotorClient(MONGO_URI)
db = client['AmazonDealsBot']
users_collection = db['users']

# ----------------- TELEGRAM BOT LOGIC -----------------

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
    
    welcome_text = f"ഹലോ {first_name}!\nAmazon ലൊക്കേഷൻ ഡീലുകൾ അറിയാൻ താഴെയുള്ള ബട്ടണിൽ ക്ലിക്ക് ചെയ്ത് Cookie സെറ്റ് ചെയ്യുക."
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍪 Set Location Cookie", callback_data="set_cookie")]
    ])
    await message.answer(welcome_text, reply_markup=markup)

@dp.callback_query(lambda c: c.data == 'set_cookie')
async def process_callback_set_cookie(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "നിങ്ങളുടെ Cookie താഴെ പേസ്റ്റ് ചെയ്യുക:")

@dp.message(lambda message: message.text and "session-id" in message.text.lower())
async def save_user_cookie(message: types.Message):
    user_id = message.from_user.id
    cookie_data = message.text
    
    await users_collection.update_one({"user_id": user_id}, {"$set": {"cookie": cookie_data}})
    await message.answer("✅ നിങ്ങളുടെ Cookie വിജയകരമായി സെറ്റ് ചെയ്തു! സ്കാനിങ് ആരംഭിക്കുന്നു.")


# ----------------- BACKGROUND SCRAPER LOGIC -----------------

async def run_scraper_loop():
    # ബോട്ട് സ്റ്റാർട്ട് ആയി കുറച്ചു നേരം കാത്തിരിക്കുന്നു
    await asyncio.sleep(10) 
    
    while True:
        users = await users_collection.find({"cookie": {"$ne": None}}).to_list(length=None)
        
        if not users:
            print("കുക്കി നൽകിയ യൂസർമാർ ആരുമില്ല. 2 മിനിറ്റ് കാത്തിരിക്കുന്നു...")
            await asyncio.sleep(120)
            continue

        print(f"🔍 {len(users)} യൂസർമാർക്കായി സ്കാനിങ് തുടങ്ങുന്നു...")
        
        try:
            # ഒരൊറ്റ ബ്രൗസർ മാത്രം ഓപ്പൺ ചെയ്യുന്നു (RAM ലാഭിക്കാൻ)
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
                
                for user in users:
                    user_id = user['user_id']
                    cookie_text = user['cookie']
                    
                    try:
                        # ഓരോ യൂസർക്കും പുതിയൊരു ടാബ് (Context)
                        context = await browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        )
                        
                        # കുക്കി സെറ്റ് ചെയ്യാനുള്ള ലോജിക് (താങ്കളുടെ പഴയ സ്ക്രിപ്റ്റിലെ പോലെ കുക്കി ഫോർമാറ്റ് ചെയ്യുക)
                        # await context.add_cookies([{"name": "...", "value": "...", "domain": ".amazon.in", "path": "/"}])
                        
                        page = await context.new_page()
                        print(f"User {user_id} ന്റെ അക്കൗണ്ട് സ്കാൻ ചെയ്യുന്നു...")
                        
                        # ==========================================
                        # 🚀 ഇവിടെ താങ്കളുടെ പഴയ ആമസോൺ സ്ക്രാപ്പിംഗ് കോഡ് ചേർക്കുക
                        # await page.goto("https://www.amazon.in/...")
                        # 
                        # ഡീൽ ഉണ്ടെങ്കിൽ:
                        # await bot.send_message(chat_id=user_id, text="🔥 പുതിയ ഡീൽ വന്നിട്ടുണ്ട്!")
                        # ==========================================
                        
                        await context.close()
                        await asyncio.sleep(5) # അടുത്ത യൂസറിലേക്ക് പോകുന്നതിന് മുൻപ് ചെറിയൊരു ബ്രേക്ക്
                        
                    except Exception as e:
                        print(f"Error for user {user_id}: {e}")
                
                await browser.close()
                
        except Exception as e:
            print(f"Browser Error: {e}")
            
        print("✅ ഒരു റൗണ്ട് സ്കാനിങ് പൂർത്തിയായി. അടുത്തതിനായി 10 മിനിറ്റ് കാത്തിരിക്കുന്നു...")
        await asyncio.sleep(600)

# ----------------- MAIN FUNCTION -----------------

async def main():
    print("🤖 Bot is starting...")
    asyncio.create_task(run_scraper_loop()) # ബാക്ക്ഗ്രൗണ്ട് ലൂപ്പ് സ്റ്റാർട്ട് ചെയ്യുന്നു
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
