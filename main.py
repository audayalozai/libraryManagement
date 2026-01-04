import os
import json
import random
import asyncio
import logging
from pathlib import Path
from typing import Any, List, Dict
import tempfile
import shutil
import time
from functools import wraps
# ===== إضافات إصلاح =====
from html import escape  # FIX: لمنع فشل HTML الصامت

# ===== تحميل المكتبات =====
try:
    from dotenv import load_dotenv
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
        JobQueue,
    )
except ImportError as e:
    print("="*50)
    print(f"خطأ: المكتبات المطلوبة غير مثبتة: {e}")
    print("تثبيت: pip install python-telegram-bot==20.7 python-dotenv")
    print("="*50)
    exit(1)

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== تحميل المتغيرات =====
load_dotenv(override=True)

required_vars = ["BOT_TOKEN", "ADMIN_ID"]
for var in required_vars:
    value = os.getenv(var)
    if not value:
        logger.critical(f"❌ متغير البيئة المفقود: {var}")
        exit(1)

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except ValueError:
    logger.critical("❌ ADMIN_ID يجب أن يكون رقمًا")
    exit(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
QUOTES_DIR = Path(os.getenv("QUOTES_DIR", "data/quotes")).resolve()
CHANNELS_FILE = Path("data/channels.json").resolve()
SCHEDULE_FILE = Path("data/schedule.json").resolve()
POSTED_QUOTES_FILE = Path("data/posted_quotes.json").resolve()
MAX_POSTED_QUOTES = 5000

# إنشاء المجلدات
QUOTES_DIR.mkdir(parents=True, exist_ok=True)
CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ===== أدوات JSON =====
def load_json(file_path: Path, default_value: Any) -> Any:
    if not file_path.exists():
        return default_value
    
    try:
        with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
            content = f.read().strip()
            if not content:
                return default_value
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"❌ خطأ في قراءة {file_path.name}: {e}")
        backup_path = file_path.with_suffix(f'.json.bak.{int(time.time())}')
        shutil.copy2(file_path, backup_path)
        return default_value

def save_json(file_path: Path, data: Any) -> bool:
    try:
        temp_path = file_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=None)
        
        temp_path.replace(file_path)
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ {file_path.name}: {e}")
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        return False

# ===== إدارة القنوات والمجموعات =====
def load_channels_data() -> List[Dict]:
    """تحميل القنوات والمجموعات مع التوافقية مع البنية القديمة"""
    data = load_json(CHANNELS_FILE, [])
    
    # التحقق من البنية القديمة (قائمة من الأوتار)
    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], str):
        logger.info("🔄 تحويل بيانات القنوات من البنية القديمة...")
        new_data = [{"id": cid, "type": "channel", "title": "غير معروف"} for cid in data]
        save_json(CHANNELS_FILE, new_data)
        return new_data
    
    return data if isinstance(data, list) else []

def save_channels_data(data: List[Dict]) -> bool:
    return save_json(CHANNELS_FILE, data)

def add_chat_to_data(chat_info: Dict) -> bool:
    """إضافة قناة أو مجموعة إلى البيانات"""
    try:
        data = load_channels_data()
        chat_id_str = str(chat_info["id"])
        
        # التحقق من التكرار
        for item in data:
            if item["id"] == chat_id_str:
                return False
        
        data.append(chat_info)
        return save_channels_data(data)
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة الدردشة: {e}")
        return False

def remove_chat_from_data(chat_id: str) -> bool:
    """حذف قناة أو مجموعة من البيانات"""
    try:
        data = load_channels_data()
        initial_length = len(data)
        
        data = [item for item in data if item["id"] != chat_id]
        
        if len(data) < initial_length:
            return save_channels_data(data)
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في حذف الدردشة: {e}")
        return False

# ===== كاش الاقتباسات =====
class QuotesCache:
    def __init__(self, quotes_dir: Path):
        self.quotes_dir = quotes_dir
        self._cache: list[str] = []
        self._cache_time: float = 0
        self._file_times: dict[str, float] = {}
    
    async def get_all_quotes(self) -> list[str]:
        now = time.time()
        if now - self._cache_time > 300:  # 5 دقائق
            await self._reload_cache()
            self._cache_time = now
        return self._cache.copy()
    
    async def _reload_cache(self):
        current_files = {f.name: f.stat().st_mtime for f in self.quotes_dir.glob("*.txt") if f.is_file()}
        if self._file_times == current_files and self._cache:
            return
        
        logger.info("🔄 تحديث كاش الاقتباسات...")
        self._cache = []
        
        for filename, mtime in current_files.items():
            file = self.quotes_dir / filename
            try:
                loop = asyncio.get_event_loop()
                lines = await loop.run_in_executor(None, self._read_file, file)
                
                valid_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) <= 4096]
                self._cache.extend(valid_lines)
                self._file_times[filename] = mtime
            except Exception as e:
                logger.error(f"❌ خطأ في قراءة {filename}: {e}")
        
        logger.info(f"✅ {len(self._cache):,} أذكار جاهزه")
    
    @staticmethod
    def _read_file(file: Path) -> list[str]:
        try:
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()
        except:
            return []

quotes_cache = QuotesCache(QUOTES_DIR)

# ===== ديكور الأدمن فقط =====
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            if update.callback_query:
                await update.callback_query.answer("❌ للأدمن فقط!", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ===== معالج الأخطاء =====
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception:", exc_info=context.error)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ خطأ: {str(context.error)[:100]}", disable_notification=True)
    except:
        pass

# ===== البدء =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        # الحصول على حالة النشر التلقائي
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        is_enabled = schedule_settings.get("enabled", False)
        status_emoji = "🟢" if is_enabled else "🔴"
        status_text = "مفعل" if is_enabled else "معطل"

        keyboard = [
            [InlineKeyboardButton("📤 نشر رسالة", callback_data="post_custom")],
            [InlineKeyboardButton(f"{status_emoji} التلقائي ({status_text})", callback_data="toggle_schedule")],
            [InlineKeyboardButton("⏰ الفاصل", callback_data="set_interval")],
            [InlineKeyboardButton("📂 القنوات/المجموعات", callback_data="manage_channels")],
            [InlineKeyboardButton("➕ ملف اقتباسات", callback_data="add_quotes_file")],
            [InlineKeyboardButton("🗑️ مسح السجل", callback_data="reset_posted_log")],
        ]
        text = "<blockquote>Welcome to the panel Admin : 👤</blockquote>"

    else:
        keyboard = [
            [InlineKeyboardButton(
                "➕ أضفني إلى دردشة",
                url="https://t.me/q9gbot?startgroup=true"
            )]
        ]
        text = """
🌙 أهلا بك في بوت نشر الأذكار التلقائي 🌙

قم بإضافة البوت إلى قناتك أو مجموعتك لتفعيل خدمة الأذكار والآيات.
ارسل كلمة <b>تفعيل</b> للتفعيل في المجموعة.

<blockquote>البوت يرسل أذكار وآيات قرآنية كل 20 دقيقة</blockquote>

تواصل مع المدير @s_x_n
"""

    reply_markup = InlineKeyboardMarkup(keyboard)

    # إرسال الرسالة أو تعديلها
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

# ===== معالج الملفات =====
@admin_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # FIX: لا نقبل الملف إلا إذا كان الأدمن في وضع رفع الاقتباسات
    if context.user_data.get("action") != "awaiting_quotes_file":
        return

    doc = update.message.document
    ...
    context.user_data.clear()  # FIX: تنظيف الحالة بعد النجاح
    
    safe_filename = Path(doc.file_name).name
    path = QUOTES_DIR / safe_filename
    
    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(path)
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = sum(1 for line in f if line.strip())
        
        if lines == 0:
            path.unlink()
            await update.message.reply_text("⚠️ الملف فارغ!")
            return
        
        quotes_cache._cache_time = 0
        
        await update.message.reply_text(f"✅ تم حفظ: {safe_filename}\n📝 {lines:,} سطر")
        logger.info(f"✅ ملف: {safe_filename} ({lines:,} سطر)")
        await start(update, context)
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الملف: {e}")
        if path.exists():
            path.unlink()

# ===== معالج الرسائل العام =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    text = update.message.text

    # توجيه من القناة/مجموعة
    if update.message.forward_from_chat:
        forward_chat = update.message.forward_from_chat
        if forward_chat.type in ['channel', 'group', 'supergroup']:
            await add_channel_or_group_from_forward(update, context)
            return

    # أمر تفعيل (يدعم مع وبدون /)
    if text and text.strip().replace("/", "") == "تفعيل" and update.message.chat.type in ['channel', 'group', 'supergroup']:
        await activate_bot_in_channel_or_group(update, context)
        return

    # أوامر الأدمن
    if user_id != ADMIN_ID:
        if text:
            await update.message.reply_text("لإضافة قناتك أو مجموعتك، قم بتوجيه رسالة منها إلى البوت.")
        return

    user_action = context.user_data.get("action")
    
    if user_action == "awaiting_custom_message" and text:
        await receive_admin_message(update, context)
        context.user_data.clear()
    elif user_action == "awaiting_interval" and text and text.isdigit():
        await set_schedule_interval(update, context)
        context.user_data.clear()
    else:
        context.user_data.clear()
        await update.message.reply_text("ارجع إلى القائمة الرئيسية:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]]))

# ===== تفعيل البوت في القناة/مجموعة (الإصلاح الرئيسي) =====
async def activate_bot_in_channel_or_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    # التحقق من نوع الدردشة
    if chat.type not in ['channel', 'group', 'supergroup']:
        await update.message.reply_text("❌ يمكن التفعيل فقط في القنوات أو المجموعات!")
        return
    
    # محاولة إرسال رسالة اختبارية لاختبار الصلاحيات
    try:
        # إرسال رسالة اختبارية
        test_msg = await context.bot.send_message(
            chat_id=chat.id, 
            text="🔍 جاري التحقق من صلاحيات البوت...",
            disable_notification=True
        )
        
        # إذا نجح الإرسال، احذف الرسالة الاختبارية
        await context.bot.delete_message(chat_id=chat.id, message_id=test_msg.message_id)
        
    except Exception as e:
        logger.error(f"خطأ في إرسال رسالة اختبارية: {e}")
        
        # بناء رسالة خطأ واضحة
        error_parts = ["❌ البوت لا يملك الصلاحيات الكافية!\n", "تأكد من:\n"]
        
        if chat.type == 'channel':
            error_parts.append("1. إضافة البوت كمسؤول (Admin) في القناة\n")
            error_parts.append("2. تفعيل صلاحية 'نشر الرسائل'\n")
            error_parts.append("3. تفعيل صلاحية 'حذف الرسائل' (اختياري)")
        else:
            error_parts.append("1. إضافة البوت إلى المجموعة\n")
            error_parts.append("2. جعله مسؤولاً (Admin)\n")
            error_parts.append("3. تفعيل صلاحية 'إرسال الرسائل'\n")
            error_parts.append("4. تفعيل صلاحية 'حذف الرسائل' (اختياري)")
            
        await update.message.reply_text("".join(error_parts))
        return

    # إضافة إلى البيانات
    chat_info = {
        "id": str(chat.id),
        "type": chat.type,
        "title": chat.title or "غير معروف"
    }
    
    if add_chat_to_data(chat_info):
        type_name = "القناة" if chat.type == 'channel' else "المجموعة"
        emoji = "📢" if chat.type == 'channel' else "👥"
        await update.message.reply_text(f"✅ تم تفعيل {type_name} بنجاح!\n\n{emoji} {chat.title}")
        logger.info(f"✓ {type_name} جديدة: {chat.title} ({chat.id})")
    else:
        await update.message.reply_text("⚠️ القناة/المجموعة مضافة بالفعل.")

# ===== إضافة من توجيه (الإصلاح الرئيسي) =====
async def add_channel_or_group_from_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    forward_chat = msg.forward_from_chat

    if not forward_chat or forward_chat.type not in ['channel', 'group', 'supergroup']:
        await msg.reply_text("❌ الرجاء إعادة توجيه رسالة من قناة أو مجموعة فقط.")
        return

    # محاولة إرسال رسالة اختبارية لاختبار الصلاحيات
    try:
        test_msg = await context.bot.send_message(
            chat_id=forward_chat.id, 
            text="🔍 جاري التحقق من صلاحيات البوت...",
            disable_notification=True
        )
        await context.bot.delete_message(chat_id=forward_chat.id, message_id=test_msg.message_id)
        
    except Exception as e:
        logger.error(f"خطأ في إرسال رسالة اختبارية: {e}")
        
        error_parts = ["❌ البوت لا يملك الصلاحيات الكافية!\n", "تأكد من:\n"]
        
        if forward_chat.type == 'channel':
            error_parts.append("1. إضافة البوت كمسؤول (Admin) في القناة\n")
            error_parts.append("2. تفعيل صلاحية 'نشر الرسائل'\n")
        else:
            error_parts.append("1. إضافة البوت إلى المجموعة\n")
            error_parts.append("2. جعله مسؤولاً (Admin)\n")
            error_parts.append("3. تفعيل صلاحية 'إرسال الرسائل'\n")
            
        await msg.reply_text("".join(error_parts))
        return

    # إضافة إلى البيانات
    chat_info = {
        "id": str(forward_chat.id),
        "type": forward_chat.type,
        "title": forward_chat.title or "غير معروف"
    }
    
    if add_chat_to_data(chat_info):
        type_name = "القناة" if forward_chat.type == 'channel' else "المجموعة"
        emoji = "📢" if forward_chat.type == 'channel' else "👥"
        await msg.reply_text(f"✅ تم تفعيل {type_name}: {forward_chat.title}")
        logger.info(f"✓ {type_name} جديدة: {forward_chat.title} ({forward_chat.id})")
    else:
        await msg.reply_text("⚠️ القناة/المجموعة مضافة بالفعل.")

# ===== معالج الأزرار =====
@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    try:
        if action == "main_menu":
            await start(update, context)
        elif action == "post_custom":
            await query.edit_message_text("✏️ أرسل الرسالة:")
            context.user_data["action"] = "awaiting_custom_message"
        elif action == "add_quotes_file":
            await query.edit_message_text("📂 أرسل ملف .txt:")
            context.user_data["action"] = "awaiting_quotes_file"
        elif action == "manage_channels":
            await manage_channels_menu(update, context)
        elif action.startswith("remove_chat_"):
            chat_id = action.split("_", 2)[2]
            await remove_chat(update, context, chat_id)
        elif action == "toggle_schedule":
            await toggle_schedule(update, context)
        elif action == "set_interval":
            await query.edit_message_text("⏰ أرسل الفاصل بالدقائق (1-1440):")
            context.user_data["action"] = "awaiting_interval"
        elif action == "reset_posted_log":
            save_json(POSTED_QUOTES_FILE, [])
            await query.answer("✅ تم مسح سجل المنشورات", show_alert=True)
            logger.info("🗑️ تم مسح سجل المنشورات")
        elif action == "info_add_channel":
            await query.edit_message_text(
                "لإضافة قناة أو مجموعة:\n"
                "1. أضف البوت مسؤول في القناة/المجموعة\n"
                "2. أرسل `تفعيل` في القناة/المجموعة\n"
                "أو قم بتوجيه رسالة من القناة/المجموعة هنا",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]])
            )
    except Exception as e:
        logger.error(f"❌ خطأ في معالج الأزرار: {e}")

# ===== نشر رسالة مخصصة =====
async def receive_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    if not msg_text or len(msg_text) > 4096:
        await update.message.reply_text("❌ نص غير صالح!")
        return

    channels_data = load_channels_data()
    if not channels_data:
        await update.message.reply_text("❌ لا توجد قنوات أو مجموعات.")
        return

    results = []
    for item in channels_data:
        try:
            await context.bot.send_message(
    chat_id=int(item["id"]),
    text=f"<b>{msg_text}</b>",
    parse_mode="HTML"
)
            results.append(f"✅ {item['id']}")
        except Exception as e:
            results.append(f"❌ {item['id']}: {str(e)[:30]}")

    await update.message.reply_text("📢 النشر اكتمل:\n" + "\n".join(results[:20]))
    await start(update, context)

# ===== النشر التلقائي =====
async def scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    """النشر التلقائي مع تسجيل مفصل"""
    start_time = time.time()
    logger.info("⏰ بدء دورة النشر التلقائي")
    
    try:
        # تحميل القنوات/المجموعات
        channels_data = load_channels_data()
        if not channels_data:
            logger.warning("⚠️ لا توجد قنوات أو مجموعات مضافة")
            return
        
        # الحصول على جميع الاقتباسات من الكاش
        all_quotes = await quotes_cache.get_all_quotes()
        if not all_quotes:
            logger.warning("⚠️ لا توجد اقتباسات متاحة")
            return

        # تحميل سجل المنشورات
        posted_quotes = load_json(POSTED_QUOTES_FILE, [])
        available_quotes = [q for q in all_quotes if q not in posted_quotes]

        # إعادة تعيين السجل إذا نفدت الاقتباسات
        if not available_quotes:
            logger.info("🔔 إعادة تعيين سجل المنشورات...")
            posted_quotes = []
            available_quotes = all_quotes

        # اختيار اقتباس عشوائي
        message_text = random.choice(available_quotes)
        logger.info(f"💬 الاقتباس المختار: {message_text[:50]}...")

        # دالة إرسال الاقتباس لكل قناة/مجموعة مع حماية HTML
        async def send_to_chat(bot, chat_info: Dict, text: str) -> bool:
            try:
                safe_text = escape(text)
                await bot.send_message(
                    chat_id=int(chat_info["id"]),
                    text=f"<blockquote>{safe_text}</blockquote>",
                    parse_mode="HTML"
                )
                return True
            except Exception as e:
                chat_type = "قناة" if chat_info.get("type") == "channel" else "مجموعة"
                logger.error(f"❌ فشل النشر في {chat_type} {chat_info['id']}: {e}")
                return False

        # تجهيز المهام وتشغيلها بشكل متوازي
        tasks = [send_to_chat(context.bot, item, message_text) for item in channels_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # نحسب النجاح الحقيقي فقط
        success_count = sum(1 for r in results if isinstance(r, bool) and r)

        # تحديث سجل المنشورات
        posted_quotes.append(message_text)
        if len(posted_quotes) > MAX_POSTED_QUOTES:
            posted_quotes = posted_quotes[-MAX_POSTED_QUOTES:]
        save_json(POSTED_QUOTES_FILE, posted_quotes)

        # تسجيل الوقت المستغرق
        elapsed = time.time() - start_time
        logger.info(f"✅ اكتمل النشر إلى {success_count}/{len(channels_data)} دردشة في {elapsed:.2f} ثانية")

    except Exception as e:
        logger.error(f"❌ خطأ في النشر التلقائي: {e}", exc_info=True)

async def send_to_chat(bot, chat_info: Dict, message_text: str) -> bool:
    """نشر سريع إلى قناة أو مجموعة واحدة"""
    try:
        await bot.send_message(chat_id=int(chat_info["id"]), text=message_text)
        return True
    except Exception as e:
        chat_type = "قناة" if chat_info.get("type") == "channel" else "مجموعة"
        logger.error(f"❌ فشل النشر في {chat_type} {chat_info['id']}: {e}")
        return False

# ===== تبديل الجدولة =====
async def toggle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل النشر التلقائي مع حفظ فوري"""
    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
    
    # تبديل الحالة
    new_state = not schedule_settings.get("enabled", False)
    schedule_settings["enabled"] = new_state
    
    # حفظ فوري
    if not save_json(SCHEDULE_FILE, schedule_settings):
        await update.callback_query.answer("❌ فشل حفظ الإعدادات!", show_alert=True)
        return
    
    job_queue = context.application.job_queue
    if job_queue:
        # إيقاف جميع الـ jobs القديمة
        current_jobs = job_queue.get_jobs_by_name("scheduled_post")
        for job in current_jobs:
            job.schedule_removal()
            logger.info("⏹️ إيقاف job قديم")
    else:
        logger.warning("⚠️ JobQueue غير متوفر، لن يتم تعديل الجدولة")
    
    # إنشاء job جديد إذا مفعل
    if new_state and job_queue:
        interval = schedule_settings.get("interval", 3600)
        job_queue.run_repeating(
            scheduled_post,
            interval=interval,
            first=10,
            name="scheduled_post"
        )
        minutes = interval // 60
        await update.callback_query.answer(f"✅ تم تفعيل النشر كل {minutes} دقيقة", show_alert=True)
        logger.info(f"✅ إنشاء job جديد كل {minutes} دقيقة")
        
        # اختبار فوري
        asyncio.create_task(test_scheduled_post(context))
    elif not new_state:
        await update.callback_query.answer("❌ تم إيقاف النشر التلقائي", show_alert=True)
        logger.info("⏹️ تم إيقاف job النشر")
    
    await start(update, context)


# ===== تعيين الفاصل الزمني =====
async def set_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval_minutes = int(update.message.text)
        if not 1 <= interval_minutes <= 1440:
            await update.message.reply_text("❌ الفاصل يجب أن يكون بين 1-1440 دقيقة!")
            return
        
        interval_seconds = interval_minutes * 60
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        schedule_settings["interval"] = interval_seconds
        save_json(SCHEDULE_FILE, schedule_settings)
        
        await update.message.reply_text(f"✅ تم تعيين الفاصل إلى {interval_minutes} دقيقة")
        
        # إعادة تشغيل job إذا كان مفعلاً
        job_queue = context.application.job_queue
        if schedule_settings.get("enabled") and job_queue:
            current_jobs = job_queue.get_jobs_by_name("scheduled_post")
            for job in current_jobs:
                job.schedule_removal()
            
            job_queue.run_repeating(
                scheduled_post,
                interval=interval_seconds,
                first=10,
                name="scheduled_post"
            )
            logger.info(f"🔄 تم تحديث الفاصل إلى {interval_minutes} دقيقة")
        elif not job_queue:
            logger.warning("⚠️ JobQueue غير متوفر، لن يتم تعديل الجدولة")
            
    except ValueError:
        await update.message.reply_text("❌ أرسل رقماً فقط!")
    
    await start(update, context)
    
# ===== إدارة القنوات والمجموعات =====
async def manage_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels_data = load_channels_data()
    if not channels_data:
        await update.callback_query.edit_message_text("❌ لا توجد قنوات أو مجموعات مضافة.")
        return

    keyboard = []
    for item in channels_data[:50]:
        try:
            chat = await context.bot.get_chat(int(item["id"]))
            title = chat.title[:25] if chat.title else item["title"]
        except:
            title = f"غير معروف ({item['id'][-8:]})"
        
        type_emoji = "📢" if item["type"] == "channel" else "👥"
        callback_data = f"remove_chat_{item['id']}"
        
        keyboard.append([InlineKeyboardButton(f"{type_emoji} {title}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    
    await update.callback_query.edit_message_text(
        f"اضغط لحذف قناة أو مجموعة (الإجمالي: {len(channels_data)}):", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    if remove_chat_from_data(chat_id):
        await update.callback_query.answer("✅ تم الحذف بنجاح", show_alert=True)
        logger.info(f"✓ حذف الدردشة {chat_id}")
    else:
        await update.callback_query.answer("⚠️ لم يتم العثور على الدردشة", show_alert=True)
    
    await manage_channels_menu(update, context)

# ===== تحميل المهام عند البدء =====
def load_scheduled_jobs(job_queue: JobQueue):
    """تحميل المهام المجدولة عند بدء البوت"""
    try:
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        
        if schedule_settings.get("enabled"):
            interval = schedule_settings.get("interval", 3600)
            job_queue.run_repeating(
                scheduled_post,
                interval=interval,
                first=10,
                name="scheduled_post"
            )
            logger.info(f"✅ تم تحميل job النشر كل {interval/60:.1f} دقيقة")
        else:
            logger.info("⏸️ النشر التلقائي معطل")
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الجدولة: {e}", exc_info=True)

# ===== التشغيل =====
def main():
    logger.info("🚀 بدء تشغيل البوت...")
    logger.info(f"👨‍💼 ADMIN_ID: {ADMIN_ID}")

    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
    logger.info(f"📊 النشر التلقائي: {'مفعل' if schedule_settings.get('enabled') else 'معطل'}")

    channels_data = load_channels_data()
    channels_count = sum(1 for item in channels_data if item["type"] == "channel")
    groups_count = sum(1 for item in channels_data if item["type"] in ["group", "supergroup"])
    logger.info(f"📢 القنوات: {channels_count} | المجموعات: {groups_count}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    # تحميل الجدولة مرة واحدة فقط
    load_scheduled_jobs(app.job_queue)

    # المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.TXT & filters.User(ADMIN_ID), handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ البوت جاهز ويستمع للتحديثات...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
