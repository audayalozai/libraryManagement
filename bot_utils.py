"""
الأدوات والدوال المساعدة للبوت
"""

import os
import random
from datetime import datetime, time as dt_time
from loguru import logger


# ==========================================
# --- إدارة الأذكار من الملفات ---
# ==========================================

def load_adhkars_from_file(file_path: str) -> list:
    """تحميل الأذكار من ملف نصي"""
    adhkars = []
    
    if not os.path.exists(file_path):
        logger.warning(f"⚠️ الملف غير موجود: {file_path}")
        return adhkars
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                # تقسيم الأذكار بناءً على الأسطر الفارغة
                adhkars = [z.strip() for z in content.split('\n\n') if z.strip()]
        
        logger.info(f"✅ تم تحميل {len(adhkars)} ذكر من {file_path}")
    except Exception as e:
        logger.error(f"❌ خطأ في قراءة الملف {file_path}: {e}")
    
    return adhkars


def get_random_adhkar(file_path: str) -> str:
    """الحصول على ذكر عشوائي من الملف"""
    adhkars = load_adhkars_from_file(file_path)
    return random.choice(adhkars) if adhkars else None


def save_adhkars_to_file(file_path: str, adhkars: list) -> bool:
    """حفظ الأذكار إلى ملف"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            content = '\n\n'.join(adhkars)
            f.write(content)
        logger.info(f"✅ تم حفظ {len(adhkars)} ذكر إلى {file_path}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ الملف {file_path}: {e}")
        return False


# ==========================================
# --- التحقق من الأوقات ---
# ==========================================

def is_in_time_range(start_time: str, end_time: str) -> bool:
    """التحقق من أن الوقت الحالي ضمن النطاق المحدد"""
    try:
        current_time = datetime.now().time()
        start = dt_time.fromisoformat(start_time)
        end = dt_time.fromisoformat(end_time)
        
        if start < end:
            return start <= current_time < end
        else:
            # إذا كان الوقت يعبر منتصف الليل (مثل 22:00 إلى 06:00)
            return current_time >= start or current_time < end
    except ValueError:
        logger.error(f"❌ صيغة وقت خاطئة: {start_time} - {end_time}")
        return False


def format_time(hours: int, minutes: int) -> str:
    """تنسيق الوقت إلى صيغة HH:MM"""
    return f"{hours:02d}:{minutes:02d}"


def parse_time(time_str: str) -> tuple:
    """تحليل صيغة الوقت HH:MM إلى (ساعات، دقائق)"""
    try:
        parts = time_str.split(':')
        return int(parts[0]), int(parts[1])
    except:
        return None, None


# ==========================================
# --- تنسيق الرسائل ---
# ==========================================

def format_adhkar_message(adhkar_text: str) -> str:
    """تنسيق نص الذكر للعرض"""
    if not adhkar_text:
        return ""
    
    lines = adhkar_text.split("\n")
    formatted_lines = [f"▫️ {line}" for line in lines if line.strip()]
    return "\n".join(formatted_lines)


def format_stats(total_adhkars: int, channels_count: int, users_count: int) -> str:
    """تنسيق رسالة الإحصائيات"""
    return (
        f"📊 <b>الإحصائيات</b>\n\n"
        f"📖 الأذكار: <code>{total_adhkars}</code>\n"
        f"📢 القنوات: <code>{channels_count}</code>\n"
        f"👥 المستخدمين: <code>{users_count}</code>"
    )


# ==========================================
# --- التحقق من الصلاحيات ---
# ==========================================

def is_admin(user_role: str) -> bool:
    """التحقق من أن المستخدم مشرف أو مالك"""
    return user_role in ["admin", "owner"]


def is_owner(user_role: str) -> bool:
    """التحقق من أن المستخدم مالك البوت"""
    return user_role == "owner"


# ==========================================
# --- التحقق من صحة المدخلات ---
# ==========================================

def is_valid_time_format(time_str: str) -> bool:
    """التحقق من صحة صيغة الوقت HH:MM"""
    if len(time_str) != 5 or time_str[2] != ':':
        return False
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours < 24 and 0 <= minutes < 60
    except:
        return False


def is_valid_interval(interval: int) -> bool:
    """التحقق من صحة فترة التكرار (دقائق)"""
    return isinstance(interval, int) and 1 <= interval <= 1000


def is_valid_user_id(user_id: str) -> bool:
    """التحقق من صحة معرف المستخدم"""
    try:
        uid = int(user_id.strip())
        return uid > 0
    except:
        return False


def is_valid_channel_id(channel_id: str) -> bool:
    """التحقق من صحة معرف القناة"""
    if channel_id.startswith('@'):
        return len(channel_id) > 1
    try:
        int(channel_id)
        return True
    except:
        return False


# ==========================================
# --- إدارة الملفات ---
# ==========================================

def ensure_file_exists(file_path: str, default_content: str = "ذكر"):
    """التأكد من وجود الملف وإنشاؤه إذا لم يكن موجوداً"""
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            logger.info(f"✅ تم إنشاء الملف: {file_path}")
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء الملف {file_path}: {e}")


def get_file_size(file_path: str) -> int:
    """الحصول على حجم الملف بالبايتات"""
    try:
        return os.path.getsize(file_path)
    except:
        return 0


# ==========================================
# --- معالجة الأخطاء والرسائل ---
# ==========================================

ERROR_MESSAGES = {
    "unauthorized": "❌ ليس لديك صلاحيات كافية.",
    "invalid_format": "❌ صيغة خاطئة. يرجى المحاولة مرة أخرى.",
    "not_found": "❌ لم يتم العثور على البيانات المطلوبة.",
    "database_error": "❌ حدث خطأ في قاعدة البيانات.",
    "file_error": "❌ حدث خطأ في معالجة الملف.",
}


def get_error_message(error_key: str) -> str:
    """الحصول على رسالة خطأ"""
    return ERROR_MESSAGES.get(error_key, "❌ حدث خطأ غير متوقع.")


SUCCESS_MESSAGES = {
    "saved": "✅ تم الحفظ بنجاح.",
    "deleted": "✅ تم الحذف بنجاح.",
    "updated": "✅ تم التحديث بنجاح.",
    "added": "✅ تم الإضافة بنجاح.",
}


def get_success_message(success_key: str) -> str:
    """الحصول على رسالة نجاح"""
    return SUCCESS_MESSAGES.get(success_key, "✅ تمت العملية بنجاح.")
