"""
OLIVE WOMEN'S WELLNESS — Telegram Mini App Bot
Stack: Python + aiogram 3 + aiohttp + SQLite (ነፃ) | Deploy: Render Web Service
"""
import os, hmac, hashlib, json, sqlite3, asyncio, logging
from urllib.parse import parse_qsl
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
                           CallbackQuery, Message, BufferedInputFile, FSInputFile)
 
logging.basicConfig(level=logging.INFO)
 
# ───────────── Environment variables (Render ላይ ይሞላሉ) ─────────────
TOKEN    = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])          # የ bot ባለቤት Telegram ID
BASE_URL = os.environ["BASE_URL"]               # https://olive-bot.onrender.com
DB_PATH  = os.environ.get("DB_PATH", "olive.db")
 
# ───────────── የጂሙ መረጃ (እዚህ ቀይር ወይም በ Render env ሙላ) ─────────────
GYM = {
    "name":    "OLIVE WOMEN'S WELLNESS",
    "tagline": "Premium All-Female Transformation Studio",
    "phone":   os.environ.get("GYM_PHONE", "    try:"),
    "address": os.environ.get("GYM_ADDRESS", "Addis Ababa, Ethiopia"),
    "map":     os.environ.get("GYM_MAP", "https://maps.google.com/?q=9.0108,38.7613"),
    "support": os.environ.get("SUPPORT_USERNAME", "your_username"),   # ያለ @
}
PAYMENTS = [   # የባንክ / Telebirr መረጃ
    {"bank": "CBE",      "name": "የሂሳብ ባለቤት ስም", "acc": "1000XXXXXXXXX"},
    {"bank": "Telebirr", "name": "የሂሳብ ባለቤት ስም", "acc": "09XXXXXXXX"},
]
 
PACKAGES = {
  "group": {
    "title": "Sisterhood Group Classes", "icon": "🌸", "badge": "★ MOST POPULAR",
    "desc": "Energetic, supportive, expert-guided training focused on Core Reconnection, Posture & Glute Sculpting.",
    "prices": {1: 16000, 3: 39000, 6: 66000, 12: 108000},
    "features": ["Specialized Female Fitness Group Classes", "Initial Physical & Lifestyle Assessment",
                 "Structured Female-Focused Meal Plan Guidance", "Weekly Progress & Measurement Check-Ins",
                 "100% Female Privacy & Supportive Women's Community"]},
  "vip": {
    "title": "VIP All-Inclusive Personal Training", "icon": "👑", "badge": "1-on-1 PT",
    "desc": "Fully customized transformation program for your body type and goals. Includes Gym Access + Personal Trainer Fee.",
    "prices": {1: 28000, 3: 75000},
    "sessions": {1: 12, 3: 36},
    "features": ["Dedicated 1-on-1 Personal Trainer", "Tailored Meal Plan Guidance (adjusted to your progress)",
                 "Weekly Deep Body Measurement & Progress Tracking", "1-on-1 Mindset & Lifestyle Habit Coaching",
                 "Core Stabilization, Posture Alignment & Body Sculpting"]},
  "open": {
    "title": "Freedom Open Gym", "icon": "🏋🏼‍♀️", "badge": "",
    "desc": "Access all gym facilities and train independently at your own pace.",
    "prices": {1: 12000, 3: 30000, 6: 51000, 12: 84000},
    "features": ["Full gym facility access", "Initial Assessment", "Monthly Progress Check"]},
}
GROUP_DISCOUNT_PCT = 10            # 5+ አባላት ሲመዘገቡ
GROUP_MIN_PEOPLE = 5
GROUP_DISCOUNT_PACKAGES = {"group", "open"}   # VIP (1-on-1) ላይ አይተገበርም — ከፈለግህ "vip" ጨምር
 
def final_price(pkg: str, months: int, people: int):
    base = PACKAGES.get(pkg, {}).get("prices", {}).get(months)
    if not base: return None
    if people >= GROUP_MIN_PEOPLE and pkg in GROUP_DISCOUNT_PACKAGES:
        return round(base * (100 - GROUP_DISCOUNT_PCT) / 100)
    return base
 
# ───────────── Database (SQLite) ─────────────
bot = Bot(TOKEN)
dp = Dispatcher()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS members(
  tg_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, username TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, pkg TEXT, months INTEGER, people INTEGER,
  price INTEGER, status TEXT, receipt_hash TEXT UNIQUE, created TEXT, expires TEXT);
""")
 
async def backup(caption="🗄 Database backup"):
    """Render free disk ስለሚጠፋ DB ለባለቤቱ በ Telegram ይላካል"""
    try:
        db.commit()
        await bot.send_document(OWNER_ID, FSInputFile(DB_PATH), caption=caption)
    except Exception as e:
        logging.warning("backup failed: %s", e)
 
def verify(init: str):
    d = dict(parse_qsl(init)); h = d.pop("hash", "")
    s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(key, s.encode(), hashlib.sha256).hexdigest(), h):
        return None
    return json.loads(d["user"])
 
# ───────────── Bot handlers ─────────────
def app_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌿 OLIVE ን ክፈት", web_app=WebAppInfo(url=BASE_URL))],
        [InlineKeyboardButton(text="🛟 ድጋፍ", url=f"https://t.me/{GYM['support']}"),
         InlineKeyboardButton(text="📍 አድራሻ", url=GYM["map"])]])
 
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(f"🌿 <b>{GYM['name']}</b>\n<i>{GYM['tagline']}</i>\n\n"
                   "እንኳን በደህና መጡ! ፓኬጅዎን ለመምረጥና ለመመዝገብ ከታች ይጫኑ 👇\n"
                   "🎁 ለአዲስ አባላት የመጀመሪያ ቀን Body & Nutrition Consultation ነፃ ነው!",
                   reply_markup=app_kb(), parse_mode="HTML")
 
def q1(sql, *a): return db.execute(sql, a).fetchone()[0]
 
@dp.message(Command("stats"), F.from_user.id == OWNER_ID)
async def stats(m: Message):
    await m.answer(
        f"📊 <b>Stats</b>\n👥 አባላት: {q1('select count(*) from members')}\n"
        f"✅ ንቁ አባላት: {q1('select count(*) from orders where status=? and expires>?', 'approved', datetime.now().isoformat())}\n"
        f"⏳ በመጠባበቅ: {q1('select count(*) from orders where status=?', 'pending')}\n"
        f"💰 ጠቅላላ ገቢ: {q1('select coalesce(sum(price),0) from orders where status=?', 'approved'):,} ብር", parse_mode="HTML")
 
@dp.message(Command("members"), F.from_user.id == OWNER_ID)
async def members(m: Message):
    rows = db.execute("""select m.name,m.phone,o.pkg,o.months,o.expires from orders o join members m on m.tg_id=o.tg_id
                         where o.status='approved' and o.expires>? order by o.expires limit 50""",
                      (datetime.now().isoformat(),)).fetchall()
    if not rows: return await m.answer("ንቁ አባል የለም")
    await m.answer("👥 <b>ንቁ አባላት</b>\n" + "\n".join(
        f"• {r['name']} | {r['phone']} | {r['pkg']} {r['months']}ወር | እስከ {r['expires'][:10]}" for r in rows), parse_mode="HTML")
 
@dp.message(Command("backup"), F.from_user.id == OWNER_ID)
async def cmd_backup(m: Message): await backup()
 
@dp.message(F.document, F.from_user.id == OWNER_ID, F.caption == "/restore")
async def restore(m: Message):
    """የ backup ፋይሉን በ caption '/restore' ከላኩ DB ይመለሳል"""
    await bot.download(m.document, "restore.db")
    src = sqlite3.connect("restore.db"); src.backup(db); src.close()
    await m.answer("✅ Database ተመልሷል። /stats ይሞክሩ።")
 
@dp.callback_query(F.data.regexp(r"^(ok|no):\d+$"))
async def decide(c: CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return await c.answer("ፈቃድ የለዎትም", show_alert=True)
    act, oid = c.data.split(":")
    o = db.execute("select * from orders where id=?", (oid,)).fetchone()
    if not o or o["status"] != "pending":
        return await c.answer("ቀድሞ ተወስኗል")
    pk = PACKAGES[o["pkg"]]
    if act == "ok":
        exp = datetime.now() + timedelta(days=30 * o["months"])
        db.execute("update orders set status='approved', expires=? where id=?", (exp.isoformat(), oid)); db.commit()
        await bot.send_message(o["tg_id"],
            f"🎉 <b>ክፍያዎ ተረጋግጧል!</b>\n\n{pk['icon']} {pk['title']}\n📅 {o['months']} ወር — እስከ <b>{exp:%d/%m/%Y}</b>\n\n"
            "🎁 የመጀመሪያ ቀንዎ ነፃ Body & Nutrition Consultation ያካትታል።\n"
            f"እንኳን ወደ OLIVE ቤተሰብ በደህና መጡ 🌿💚\n📞 {GYM['phone']}", parse_mode="HTML")
        note = f"✅ ጸድቋል (እስከ {exp:%d/%m/%Y})"
    else:
        db.execute("update orders set status='rejected' where id=?", (oid,)); db.commit()
        await bot.send_message(o["tg_id"],
            f"😔 ደረሰኝዎ ሊረጋገጥ አልቻለም።\nእባክዎ ያነጋግሩን: @{GYM['support']} ወይም {GYM['phone']}")
        note = "❌ ውድቅ ተደርጓል"
    await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{note}")
    await c.answer("ተፈጸመ")
    await bot.send_message(OWNER_ID, f"📝 ትዕዛዝ #{oid}: {note}")
    await backup(f"🗄 Backup (ትዕዛዝ #{oid})")
 
# ───────────── Web API (Mini App) ─────────────
async def api_config(_):
    return web.json_response({
        "gym": GYM, "payments": PAYMENTS, "packages": PACKAGES,
        "discount": {"pct": GROUP_DISCOUNT_PCT, "min": GROUP_MIN_PEOPLE, "packages": list(GROUP_DISCOUNT_PACKAGES)}})
 
async def api_order(req: web.Request):
    f = await req.post()
    u = verify(f.get("initData", ""))
    if not u: return web.json_response({"ok": False, "error": "auth"}, status=403)
    try:
        pkg, months = f["pkg"], int(f["months"]); people = max(1, min(int(f.get("people") or 1), 50))
        name, phone, age = f["name"].strip()[:60], f["phone"].strip()[:20], int(f.get("age") or 0)
        img = f["receipt"].file.read()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    price = final_price(pkg, months, people)
    if not price or not name or not (1000 < len(img) < 8_000_000):
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    h = hashlib.sha256(img).hexdigest()
    if db.execute("select 1 from orders where receipt_hash=?", (h,)).fetchone():   # አውቶ ቼክ፦ ተደጋጋሚ ደረሰኝ
        return web.json_response({"ok": False, "error": "duplicate"}, status=409)
    db.execute("insert or replace into members values(?,?,?,?,?,?)",
               (u["id"], name, phone, age, u.get("username"), datetime.now().isoformat()))
    oid = db.execute("insert into orders(tg_id,pkg,months,people,price,status,receipt_hash,created) values(?,?,?,?,?,?,?,?)",
                     (u["id"], pkg, months, people, price, "pending", h, datetime.now().isoformat())).lastrowid
    db.commit()
    pk = PACKAGES[pkg]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ ትክክል", callback_data=f"ok:{oid}"),
        InlineKeyboardButton(text="❌ ውድቅ", callback_data=f"no:{oid}")]])
    disc = f" (🎁 {GROUP_DISCOUNT_PCT}% Group Discount)" if people >= GROUP_MIN_PEOPLE and pkg in GROUP_DISCOUNT_PACKAGES else ""
    await bot.send_photo(OWNER_ID, BufferedInputFile(img, "receipt.jpg"), reply_markup=kb, caption=(
        f"🆕 አዲስ ትዕዛዝ #{oid}\n👤 {name}\n📞 {phone}\n🎂 እድሜ: {age}\n👥 ሰዎች: {people}\n"
        f"📦 {pk['title']} • {months} ወር\n💰 {price:,} ብር{disc}\n"
        f"🔗 @{u.get('username') or '-'} ({u['id']})\n\nደረሰኙን ያረጋግጡ 👇"))
    await bot.send_message(u["id"], "🌿 ደረሰኝዎ ደርሶናል! ባለቤቱ አረጋግጦ በቅርቡ መልዕክት ይልክልዎታል። አመሰግናለሁ 🙏")
    return web.json_response({"ok": True})
 
async def reminders():
    """በየቀኑ፦ ሊያልቅ 3 ቀን የቀረው አባል ማስታወሻ + DB backup"""
    while True:
        now = datetime.now()
        for o in db.execute("select * from orders where status='approved' and expires<? and expires>?",
                            ((now + timedelta(days=3)).isoformat(), now.isoformat())).fetchall():
            try:
                await bot.send_message(o["tg_id"], "⏰ ምዝገባዎ በቅርቡ ያበቃል። ለማደስ /start ይጫኑ 🌿")
                await bot.send_message(OWNER_ID, f"⏰ የአባል (ID {o['tg_id']}) ምዝገባ በቅርቡ ያበቃል")
            except Exception: pass
        await backup("🗄 Daily backup")
        await asyncio.sleep(86400)
 
async def main():
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.add_routes([web.get("/", lambda r: web.FileResponse("webapp/index.html")),
                    web.get("/health", lambda r: web.Response(text="ok")),
                    web.get("/api/config", api_config), web.post("/api/order", api_order)])
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    asyncio.create_task(reminders())
    empty = q1("select count(*) from members") == 0
    try: 
        await bot.send_message(OWNER_ID, "🤖 Bot ተነስቷል።\n/stats • /members • /backup" +
            ("\n\n⚠️ Database ባዶ ነው። ዳታ ከጠፋ የመጨረሻውን backup ፋይል በ caption «/restore» ይላኩ።" if empty else ""))
    except Exception as e:
        logging.warning("Owner notify failed (OWNER_ID ወይም /start ያረጋግጡ): %s", e)
 
if __name__ == "__main__":
    asyncio.run(main())
 
