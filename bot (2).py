import os, hmac, hashlib, json, sqlite3, asyncio, logging
from urllib.parse import parse_qsl
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                           WebAppInfo, CallbackQuery, Message, BufferedInputFile)

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])          # የ bot ባለቤት Telegram ID
BASE_URL = os.environ["BASE_URL"]               # https://your-app.onrender.com
DB_PATH = os.environ.get("DB_PATH", "gym.db")

# ====== እዚህ ጋር የጂሙን መረጃ ቀይር ======
GYM = {
    "name": "ሴቶች ጂም",
    "phone": "+251911000000",
    "address": "አዲስ አበባ፣ ቦሌ",
    "map": "https://maps.google.com/?q=9.0108,38.7613",
    "support": "your_username",                 # Telegram username (ያለ @)
    "payments": [
        {"bank": "CBE", "name": "የሂሳብ ባለቤት ስም", "acc": "1000XXXXXXXXX"},
        {"bank": "Telebirr", "name": "የሂሳብ ባለቤት ስም", "acc": "09XXXXXXXX"},
    ],
}
PRICES = {  # ብር
    "regular": {1: 1000, 3: 2800, 6: 5200, 12: 9500},
    "vip":     {1: 2000, 2: 3900, 3: 5700, 4: 7400, 5: 9000, 6: 10500,
                7: 12000, 8: 13400, 9: 14700, 10: 15900, 11: 17000, 12: 18000},
}
# ======================================

bot = Bot(TOKEN)
dp = Dispatcher()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS members(tg_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, username TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, plan TEXT, months INTEGER,
  price INTEGER, status TEXT, receipt_hash TEXT UNIQUE, created TEXT, expires TEXT);
""")

def verify(init: str):
    d = dict(parse_qsl(init)); h = d.pop("hash", "")
    s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(key, s.encode(), hashlib.sha256).hexdigest(), h):
        return None
    return json.loads(d["user"])

def app_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💪 ጂሙን ክፈት", web_app=WebAppInfo(url=BASE_URL))],
        [InlineKeyboardButton(text="📞 ድጋፍ", url=f"https://t.me/{GYM['support']}")]])

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(f"እንኳን ወደ <b>{GYM['name']}</b> በደህና መጡ 🌸\nፓኬጅ ለመምረጥና ለመመዝገብ ከታች ይጫኑ።",
                   reply_markup=app_kb(), parse_mode="HTML")

@dp.message(Command("stats"), F.from_user.id == OWNER_ID)
async def stats(m: Message):
    q = lambda s: db.execute(s).fetchone()[0]
    await m.answer(f"📊 አባላት: {q('select count(*) from members')}\n"
                   f"✅ የተረጋገጡ: {q('select count(*) from orders where status=\"approved\"')}\n"
                   f"⏳ በመጠባበቅ ላይ: {q('select count(*) from orders where status=\"pending\"')}\n"
                   f"💰 ጠቅላላ ገቢ: {q('select coalesce(sum(price),0) from orders where status=\"approved\"')} ብር")

@dp.callback_query(F.data.regexp(r"^(ok|no):\d+$"))
async def decide(c: CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return await c.answer("ፈቃድ የለዎትም", show_alert=True)
    act, oid = c.data.split(":"); o = db.execute("select * from orders where id=?", (oid,)).fetchone()
    if not o or o["status"] != "pending":
        return await c.answer("ቀድሞ ተወስኗል")
    if act == "ok":
        exp = datetime.now() + timedelta(days=30 * o["months"])
        db.execute("update orders set status='approved', expires=? where id=?", (exp.isoformat(), oid)); db.commit()
        await bot.send_message(o["tg_id"], f"🎉 ክፍያዎ ተረጋግጧል!\n"
            f"{o['plan'].upper()} • {o['months']} ወር\n📅 እስከ {exp:%d/%m/%Y} ድረስ የሚያገለግል።\nእንኳን ደህና መጡ፣ እንገናኝ 💪🌸")
        note = f"✅ ጸድቋል #{oid} (እስከ {exp:%d/%m/%Y})"
    else:
        db.execute("update orders set status='rejected' where id=?", (oid,)); db.commit()
        await bot.send_message(o["tg_id"], f"😔 ደረሰኙ ሊረጋገጥ አልቻለም።\nእባክዎ በ ድጋፍ ያነጋግሩን: @{GYM['support']} ወይም {GYM['phone']}")
        note = f"❌ ውድቅ ተደርጓል #{oid}"
    await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{note}")
    await c.answer("ተፈጸመ")

async def api_config(_):
    return web.json_response({"gym": {k: GYM[k] for k in ("name", "phone", "address", "map", "support")},
                              "payments": GYM["payments"], "prices": PRICES})

async def api_order(req: web.Request):
    f = await req.post()
    u = verify(f.get("initData", ""))
    if not u: return web.json_response({"ok": False, "error": "auth"}, status=403)
    plan, months = f.get("plan"), int(f.get("months", 0))
    price = PRICES.get(plan, {}).get(months)
    img = f["receipt"].file.read() if "receipt" in f else b""
    if not price or not (1000 < len(img) < 8_000_000):
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    h = hashlib.sha256(img).hexdigest()
    if db.execute("select 1 from orders where receipt_hash=?", (h,)).fetchone():
        return web.json_response({"ok": False, "error": "duplicate"}, status=409)  # አውቶማቲክ ቼክ: ተደጋጋሚ ደረሰኝ
    name, phone, age = f["name"][:60], f["phone"][:20], int(f.get("age") or 0)
    db.execute("insert or replace into members values(?,?,?,?,?,?)",
               (u["id"], name, phone, age, u.get("username"), datetime.now().isoformat()))
    cur = db.execute("insert into orders(tg_id,plan,months,price,status,receipt_hash,created) values(?,?,?,?,?,?,?)",
                     (u["id"], plan, months, price, "pending", h, datetime.now().isoformat()))
    db.commit(); oid = cur.lastrowid
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ ትክክል", callback_data=f"ok:{oid}"),
        InlineKeyboardButton(text="❌ ውድቅ", callback_data=f"no:{oid}")]])
    await bot.send_photo(OWNER_ID, BufferedInputFile(img, "receipt.jpg"), reply_markup=kb, caption=(
        f"🆕 አዲስ ትዕዛዝ #{oid}\n👤 {name}\n📞 {phone}\n🎂 እድሜ: {age}\n"
        f"📦 {plan.upper()} • {months} ወር\n💰 {price} ብር\n🔗 @{u.get('username') or '-'} ({u['id']})"))
    await bot.send_message(u["id"], "🌸 ደረሰኝዎ ደርሶናል! ባለቤቱ አረጋግጦ በቅርቡ መልዕክት ይደርስዎታል። አመሰግናለሁ 🙏")
    return web.json_response({"ok": True})

async def reminders():  # በየቀኑ: ሊያልቅ 3 ቀን የቀረው አባል ማስታወሻ
    while True:
        lim = (datetime.now() + timedelta(days=3)).isoformat()
        for o in db.execute("select * from orders where status='approved' and expires<? and expires>?",
                            (lim, datetime.now().isoformat())):
            try:
                await bot.send_message(o["tg_id"], "⏰ ምዝገባዎ በቅርቡ ያበቃል። ለማደስ /start ይጫኑ 💪")
                await bot.send_message(OWNER_ID, f"⏰ የአባል #{o['tg_id']} ምዝገባ በቅርቡ ያበቃል")
            except Exception: pass
        await asyncio.sleep(86400)

async def main():
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.add_routes([web.get("/", lambda r: web.FileResponse("webapp/index.html")),
                    web.get("/api/config", api_config), web.post("/api/order", api_order)])
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    asyncio.create_task(reminders())
    await bot.send_message(OWNER_ID, "🤖 Bot ተነስቷል። /stats ይጠቀሙ።")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
