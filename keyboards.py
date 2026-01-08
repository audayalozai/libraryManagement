"""
تعريفات الأزرار والواجهات (Keyboards)
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import DatabaseManager


# ==========================================
# --- القائمة الرئيسية ---
# ==========================================

def get_main_keyboard(user_role: str) -> InlineKeyboardMarkup:
    """الحصول على لوحة المفاتيح الرئيسية بناءً على دور المستخدم"""
    markup = InlineKeyboardMarkup(inline_keyboard=[])
    
    # الأزرار العامة لجميع المستخدمين
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="📊 الإحصائيات", callback_data="stats"),
        # زر إدارة القنوات يظهر للجميع
        InlineKeyboardButton(text="📢 إدارة القنوات", callback_data="menu_channels")
    ])
    
    # الأزرار للمشرفين والمالك
    if user_role in ["admin", "owner"]:
        markup.inline_keyboard.append([
            # زر إعدادات الأذكار يظهر للمشرفين فقط
            InlineKeyboardButton(text="⚙️ إعدادات الأذكار", callback_data="settings_menu"),
            InlineKeyboardButton(text="📢 الإذاعة", callback_data="menu_broadcast")
        ])
        
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="➕ رفع ملفات", callback_data="menu_upload"),
            InlineKeyboardButton(text="🛡️ إدارة المشرفين", callback_data="menu_admins")
        ])
    
    # أزرار المالك فقط
    if user_role == "owner":
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="🔧 قناة التحقق", callback_data="menu_verification")
        ])
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 تحديث", callback_data="reload")
    ])
    
    return markup


# ==========================================
# --- قائمة الأذكار ---
# ==========================================

def get_adhkar_settings_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح اختيار فئة الأذكار"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="☀️ الصباح", callback_data="set_sabah"),
            InlineKeyboardButton(text="🌙 المساء", callback_data="set_masaa"),
            InlineKeyboardButton(text="📖 العام", callback_data="set_aam")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    return markup


def get_category_settings_keyboard(category: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح إعدادات فئة معينة"""
    markup = InlineKeyboardMarkup(inline_keyboard=[])
    
    # أزرار التعديل
    if category != "aam":
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="⏰ تعديل الأوقات", callback_data=f"edit_time_{category}")
        ])
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="⏱️ تعديل التكرار", callback_data=f"edit_interval_{category}")
    ])
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="📂 رفع ملف", callback_data=f"upload_{category}")
    ])
    
    # زر التفعيل/الإيقاف
    category_obj = DatabaseManager.get_category(category)
    if category_obj and category_obj.is_enabled:
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="⏸️ إيقاف", callback_data=f"toggle_{category}_off")
        ])
    else:
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="▶️ تفعيل", callback_data=f"toggle_{category}_on")
        ])
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 رجوع", callback_data="settings_menu")
    ])
    
    return markup


# ==========================================
# --- قائمة القنوات (مع التصفح - Pagination) ---
# ==========================================

def get_channels_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح إدارة القنوات"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ إضافة قناة", callback_data="add_channel"),
            InlineKeyboardButton(text="🗑️ حذف قناة", callback_data="delete_channel")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    return markup


def get_delete_channels_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    """
    لوحة مفاتيح حذف القنوات (للمشرفين: الكل، للمستخدمين: الخاصة بهم فقط)
    تدعم التصفح (Pagination) بعرض 10 قنوات في كل صفحة
    """
    markup = InlineKeyboardMarkup(inline_keyboard=[])
    
    user_role = DatabaseManager.get_user_role(user_id)
    
    channels = []
    if user_role in ["admin", "owner"]:
        channels = DatabaseManager.get_active_channels()
    else:
        channels = DatabaseManager.get_user_channels(user_id)
    
    # إعدادات التصفح
    items_per_page = 10
    total_channels = len(channels)
    max_pages = (total_channels + items_per_page - 1) // items_per_page
    
    # التأكد من أن رقم الصفحة صحيح
    if page < 0: page = 0
    if page >= max_pages and max_pages > 0: page = max_pages -1
    
    # تحديد القنوات المعروضة في الصفحة الحالية
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    current_channels = channels[start_index:end_index]
    
    if not channels:
        markup.inline_keyboard.append([
            InlineKeyboardButton(text="لا توجد قنوات مضافة", callback_data="menu_channels")
        ])
    else:
        # عرض القنوات
        for channel in current_channels:
            markup.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {channel.title[:25]}",
                    callback_data=f"del_ch_{channel.channel_id}"
                )
            ])
        
        # أزرار التنقل (السابق - التالي)
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ السابق", callback_data=f"channels_page_{page-1}"))
        
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{max_pages}", callback_data="ignore"))
        
        if page < max_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="التالي ➡️", callback_data=f"channels_page_{page+1}"))
        
        if nav_buttons:
            markup.inline_keyboard.append(nav_buttons)
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_channels")
    ])
    
    return markup


# ==========================================
# --- قائمة الإذاعة ---
# ==========================================

def get_broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح الإذاعة"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 للقنوات", callback_data="ask_broadcast_ch"),
            InlineKeyboardButton(text="📢 للخاص", callback_data="ask_broadcast_pm")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    return markup


# ==========================================
# --- قائمة المشرفين ---
# ==========================================

def get_admins_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح إدارة المشرفين"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ إضافة مشرف", callback_data="add_admin"),
            InlineKeyboardButton(text="🗑️ حذف مشرف", callback_data="delete_admin")
        ],
        [
            InlineKeyboardButton(text="👥 عرض المشرفين", callback_data="list_admins")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    return markup


def get_delete_admins_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح حذف المشرفين"""
    markup = InlineKeyboardMarkup(inline_keyboard=[])
    
    admins = DatabaseManager.get_admin_users()
    for admin in admins[:10]:  # عرض أول 10 مشرفين
        markup.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {admin.first_name}",
                callback_data=f"del_ad_{admin.user_id}"
            )
        ])
    
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_admins")
    ])
    
    return markup


# ==========================================
# --- قائمة التحقق ---
# ==========================================

def get_verification_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح قناة التحقق"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="تغيير القناة", callback_data="set_verification_channel")
        ],
        [
            InlineKeyboardButton(text="إزالة القناة", callback_data="remove_verification_channel")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    return markup


# ==========================================
# --- أزرار الإلغاء والرجوع ---
# ==========================================

def get_cancel_keyboard(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """لوحة مفاتيح الإلغاء والرجوع"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 إلغاء", callback_data=callback_data)
        ]
    ])
    return markup


def get_back_keyboard(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """لوحة مفاتيح الرجوع"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data=callback_data)
        ]
    ])
    return markup


# ==========================================
# --- أزرار الاشتراك ---
# ==========================================

def get_subscription_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح الاشتراك"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ اشترك هنا",
                url=f"https://t.me/{channel_username[1:] if channel_username.startswith('@') else channel_username}"
            )
        ],
        [
            InlineKeyboardButton(text="🔄 تحقق", callback_data="main_menu")
        ]
    ])
    return markup