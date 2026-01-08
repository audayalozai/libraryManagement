"""
الملف الرئيسي لبوت الأذكار الاحترافي
يجمع جميع المكونات ويشغل البوت
"""

import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from loguru import logger

# استيراد المكونات
from database import DatabaseManager, init_db
from auto_poster import get_auto_poster
from commands import router as commands_router
from text_handlers import router as text_handlers_router
from callback_handlers import router as callback_handlers_router
from file_handlers import router as file_handlers_router
from bot_utils import ensure_file_exists

# تحميل متغيرات البيئة
load_dotenv()

# إعداد السجلات
logger.remove()
logger.add(
    "logs/bot.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
    encoding="utf-8"
)
logger.add(
    lambda msg: print(msg, end=""),
    format="{time:HH:mm:ss} | {level: <8} | {message}",
    level="INFO"
)

# الحصول على التوكن والإعدادات
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMINS_ID_STR = os.getenv('ADMINS_ID', '')
ADMINS_ID = [int(admin_id.strip()) for admin_id in ADMINS_ID_STR.split(',') if admin_id.strip().isdigit()]

if not TOKEN:
    logger.error("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في ملف .env")
    exit(1)

# إنشاء مجلد السجلات
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)


# ==========================================
# --- مهمة فحص القنوات (جديدة) ---
# ==========================================

async def check_and_remove_kicked_channels(bot: Bot):
    """
    وظيفة تعمل في الخلفية للتحقق من القنوات وحذف التي طُرد منها البوت
    """
    while True:
        try:
            logger.info("🔍 جاري فحص حالة البوت في القنوات...")
            channels = DatabaseManager.get_active_channels()
            removed_count = 0
            
            for channel in channels:
                try:
                    # محاولة جلب عضوية البوت في القناة
                    member = await bot.get_chat_member(channel.channel_id, bot.id)
                    
                    # التحقق من الحالة: نحذف فقط إذا غادر (left) أو طُرد (kicked)
                    # نحتفظ بالقناة إذا كان: administrator, creator, member
                    if member.status in ["left", "kicked"]:
                        logger.warning(f"⚠️ سيتم حذف القناة {channel.title} ({channel.channel_id}) - البوت ليس فيها.")
                        # استخدام الدالة الآمنة التي تعالج قاعدة البيانات بشكل صحيح
                        DatabaseManager.delete_channel_safe(channel.channel_id)
                        removed_count += 1
                
                except Exception as e:
                    # إذا فشل جلب العضوية (البوت محظور أو القناة محذوفة)
                    error_msg = str(e)
                    if "Bot was blocked" in error_msg or "Chat not found" in error_msg or "Forbidden" in error_msg:
                        logger.warning(f"⚠️ سيتم حذف القناة {channel.title} بسبب خطأ في الوصول: {error_msg}")
                        DatabaseManager.delete_channel_safe(channel.channel_id)
                        removed_count += 1
            
            if removed_count > 0:
                logger.success(f"🗑️ تم تنظيف القائمة وحذف {removed_count} قناة.")
            else:
                logger.info("✅ جميع القنوات صالحة.")
            
            # انتظار ساعة واحدة
            await asyncio.sleep(3600) 
            
        except Exception as main_e:
            logger.error(f"❌ خطأ في مهمة فحص القنوات: {main_e}")
            # انتظار 10 دقائق قبل إعادة المحاولة
            await asyncio.sleep(600)


# ==========================================
# --- تهيئة البوت ---
# ==========================================

async def setup_bot_commands(bot: Bot):
    """إعداد أوامر البوت"""
    commands = [
        BotCommand(command="start", description="بدء البوت")
    ]
    
    await bot.set_my_commands(commands)
    logger.info("✅ تم إعداد أوامر البوت")


async def init_database():
    """تهيئة قاعدة البيانات"""
    init_db()
    
    # تهيئة فئات الأذكار
    DatabaseManager.init_categories()
    
    # التأكد من وجود ملفات الأذكار
    categories = ["sabah", "masaa", "aam"]
    for category in categories:
        cat_obj = DatabaseManager.get_category(category)
        if cat_obj:
            ensure_file_exists(cat_obj.file_path)
    
    # إضافة المالك إلى قاعدة البيانات
    if ADMINS_ID:
        for admin_id in ADMINS_ID:
            user = DatabaseManager.get_user(admin_id)
            if not user:
                DatabaseManager.add_user(admin_id, "Owner", None, "owner")
            else:
                DatabaseManager.set_user_role(admin_id, "owner")
    
    logger.info("✅ تم تهيئة قاعدة البيانات")


async def main():
    """الدالة الرئيسية للبوت"""
    
    # إنشاء البوت والـ Dispatcher
    bot = Bot(token=TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # تهيئة قاعدة البيانات
    await init_database()
    
    # إعداد أوامر البوت
    await setup_bot_commands(bot)
    
    # تسجيل المعالجات (Routers)
    dp.include_router(commands_router)
    dp.include_router(text_handlers_router)
    dp.include_router(callback_handlers_router)
    dp.include_router(file_handlers_router)
    
    # ==========================================
    # تشغيل مهمة فحص القنوات في الخلفية
    # ==========================================
    loop = asyncio.get_event_loop()
    loop.create_task(check_and_remove_kicked_channels(bot))
    logger.info("🔄 تم تفعيل الفحص الدوري للقنوات (كل ساعة).")
    # ==========================================
    
    # بدء نظام النشر التلقائي
    auto_poster = get_auto_poster(bot)
    auto_poster_task = asyncio.create_task(auto_poster.start())
    
    logger.info("🚀 تم بدء تشغيل البوت بنجاح...")
    
    try:
        # بدء استقبال الرسائل
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            skip_updates=True
        )
    except KeyboardInterrupt:
        logger.info("⏸️ تم إيقاف البوت من قبل المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ في البوت: {e}")
    finally:
        # إيقاف نظام النشر التلقائي
        await auto_poster.stop()
        auto_poster_task.cancel()
        
        # إغلاق البوت
        await bot.session.close()
        logger.info("✅ تم إغلاق البوت بنجاح")


# ==========================================
# --- نقطة الدخول ---
# ==========================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ حرج: {e}")