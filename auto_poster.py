"""
نظام النشر التلقائي للأذكار
يستخدم asyncio لضمان عدم حجب البوت أثناء النشر
"""

import asyncio
from datetime import datetime, time as dt_time
from aiogram import Bot
from database import DatabaseManager
from bot_utils import load_adhkars_from_file, is_in_time_range, format_adhkar_message
from loguru import logger


class AutoPoster:
    """نظام النشر التلقائي للأذكار"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
    
    async def start(self):
        """بدء نظام النشر التلقائي"""
        self.is_running = True
        logger.info("✅ تم بدء نظام النشر التلقائي")
        
        while self.is_running:
            try:
                await self._check_and_post()
                await asyncio.sleep(30)  # التحقق كل 30 ثانية
            except Exception as e:
                logger.error(f"❌ خطأ في نظام النشر التلقائي: {e}")
                await asyncio.sleep(60)
    
    async def stop(self):
        """إيقاف نظام النشر التلقائي"""
        self.is_running = False
        logger.info("⏸️ تم إيقاف نظام النشر التلقائي")
    
    async def _check_and_post(self):
        """التحقق من الفئات وإرسال الأذكار"""
        current_time = datetime.now()
        
        categories = ["sabah", "masaa", "aam"]
        
        for category_name in categories:
            category = DatabaseManager.get_category(category_name)
            
            if not category or not category.is_enabled:
                continue
            
            # التحقق من أن الوقت الحالي ضمن النطاق المحدد
            if category_name != "aam":
                if not is_in_time_range(category.start_time, category.end_time):
                    continue
            
            # التحقق من أن الفترة الزمنية قد مضت
            if category.last_posted_at:
                time_diff = (current_time - category.last_posted_at).total_seconds() / 60
                if time_diff < category.interval_minutes:
                    continue
            
            # الحصول على ذكر عشوائي
            adhkars = load_adhkars_from_file(category.file_path)
            if not adhkars:
                logger.warning(f"⚠️ لا توجد أذكار في {category.file_path}")
                continue
            
            import random
            adhkar = random.choice(adhkars)
            
            # الحصول على القنوات النشطة
            channels = DatabaseManager.get_active_channels()
            if not channels:
                logger.warning("⚠️ لا توجد قنوات نشطة")
                continue
            
            # إرسال الذكر لجميع القنوات
            await self._post_to_channels(adhkar, channels)
            
            # تحديث آخر وقت نشر
            DatabaseManager.update_category(category_name, last_posted_at=current_time)
    
    async def _post_to_channels(self, adhkar: str, channels: list):
        """إرسال الذكر لجميع القنوات"""
        formatted_text = format_adhkar_message(adhkar)
        
        tasks = []
        for channel in channels:
            task = self._send_to_channel(int(channel.channel_id), formatted_text)
            tasks.append(task)
        
        # إرسال جميع الرسائل بشكل متزامن
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # حساب عدد الرسائل المرسلة بنجاح
        success_count = sum(1 for r in results if r is True)
        logger.info(f"✅ تم إرسال الذكر لـ {success_count}/{len(channels)} قناة")
    
    async def _send_to_channel(self, channel_id: int, text: str) -> bool:
        """إرسال رسالة لقناة واحدة"""
        try:
            await self.bot.send_message(
                channel_id,
                text,
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الرسالة للقناة {channel_id}: {e}")
            return False


# إنشاء مثيل من النظام
auto_poster_instance = None


def get_auto_poster(bot: Bot) -> AutoPoster:
    """الحصول على مثيل النشر التلقائي"""
    global auto_poster_instance
    if auto_poster_instance is None:
        auto_poster_instance = AutoPoster(bot)
    return auto_poster_instance
