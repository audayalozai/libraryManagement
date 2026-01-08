"""
معالجات الأزرار (Callback Queries)
"""

import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import DatabaseManager
from keyboards import (
    get_main_keyboard, get_adhkar_settings_keyboard, get_category_settings_keyboard,
    get_channels_menu_keyboard, get_delete_channels_keyboard, get_broadcast_menu_keyboard,
    get_admins_menu_keyboard, get_delete_admins_keyboard, get_verification_menu_keyboard,
    get_cancel_keyboard, get_back_keyboard, get_subscription_keyboard
)
from bot_utils import format_stats, format_adhkar_message, load_adhkars_from_file, is_admin, is_owner
from loguru import logger

router = Router()

# تعريف الحالات هنا لضمان عدم وجود تضارب في الاستيراد
class AddChannelState(StatesGroup):
    waiting_for_channel_id = State()

class AddAdminState(StatesGroup):
    waiting_for_user_id = State()

class EditTimeState(StatesGroup):
    waiting_for_start_time = State()
    waiting_for_end_time = State()
    waiting_for_interval = State()

class EditIntervalState(StatesGroup):
    waiting_for_interval = State()

class BroadcastState(StatesGroup):
    waiting_for_broadcast_channels = State()
    waiting_for_broadcast_private = State()

class VerificationState(StatesGroup):
    waiting_for_verification_channel = State()


# ==========================================
# --- معالجات عامة ---
# ==========================================

@router.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    """القائمة الرئيسية"""
    user_role = DatabaseManager.get_user_role(callback.from_user.id)
    
    text = f"👋 مرحباً {callback.from_user.first_name}\n\nاختر من القائمة:"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_main_keyboard(user_role)
    )


@router.callback_query(F.data == "reload")
async def reload(callback: types.CallbackQuery):
    """تحديث القائمة"""
    await callback.answer("🔄 تم التحديث")


@router.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    """عرض الإحصائيات"""
    # حساب إجمالي الأذكار
    total_adhkars = 0
    for category_name in ["sabah", "masaa", "aam"]:
        category = DatabaseManager.get_category(category_name)
        if category:
            adhkars = load_adhkars_from_file(category.file_path)
            total_adhkars += len(adhkars)
    
    channels_count = len(DatabaseManager.get_active_channels())
    users_count = len(DatabaseManager.get_all_users())
    
    text = format_stats(total_adhkars, channels_count, users_count)
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_back_keyboard("main_menu")
    )


# ==========================================
# --- معالجات الأذكار ---
# ==========================================

@router.callback_query(F.data == "settings_menu")
async def settings_menu(callback: types.CallbackQuery):
    """قائمة إعدادات الأذكار"""
    await callback.message.edit_text(
        "⚙️ اختر الفئة:",
        reply_markup=get_adhkar_settings_keyboard()
    )


@router.callback_query(F.data.startswith("set_"))
async def show_category_settings(callback: types.CallbackQuery):
    """عرض إعدادات فئة معينة"""
    category = callback.data.split("_")[1]
    category_obj = DatabaseManager.get_category(category)
    
    if not category_obj:
        await callback.answer("❌ الفئة غير موجودة", show_alert=True)
        return
    
    cat_names = {"sabah": "الصباح", "masaa": "المساء", "aam": "العام"}
    cat_name = cat_names.get(category, category)
    
    text = f"⚙️ <b>إعدادات {cat_name}</b>\n\n"
    if category != "aam":
        text += f"الوقت: <code>{category_obj.start_time} - {category_obj.end_time}</code>\n"
    text += f"التكرار: كل <code>{category_obj.interval_minutes}</code> دقيقة\n"
    text += f"الحالة: {'✅ مفعل' if category_obj.is_enabled else '❌ معطل'}"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_category_settings_keyboard(category)
    )


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_category(callback: types.CallbackQuery):
    """تفعيل/إيقاف فئة أذكار"""
    parts = callback.data.split("_")
    category = parts[1]
    new_state = parts[2] == "on"
    
    DatabaseManager.update_category(category, is_enabled=new_state)
    await show_category_settings(callback)


@router.callback_query(F.data.startswith("edit_time_"))
async def edit_time(callback: types.CallbackQuery, state: FSMContext):
    """تعديل أوقات الفئة"""
    category = callback.data.split("_")[2]
    
    await state.set_state(EditTimeState.waiting_for_start_time)
    await state.update_data(category=category)
    
    await callback.message.edit_text(
        "أدخل وقت البداية (HH:MM):",
        reply_markup=get_cancel_keyboard(f"set_{category}")
    )


@router.callback_query(F.data.startswith("edit_interval_"))
async def edit_interval(callback: types.CallbackQuery, state: FSMContext):
    """تعديل فترة التكرار"""
    category = callback.data.split("_")[2]
    
    await state.set_state(EditIntervalState.waiting_for_interval)
    await state.update_data(category=category)
    
    await callback.message.edit_text(
        "أدخل فترة التكرار (دقائق) من 1 إلى 1000:",
        reply_markup=get_cancel_keyboard(f"set_{category}")
    )


@router.callback_query(F.data.startswith("upload_"))
async def upload_file(callback: types.CallbackQuery, state: FSMContext):
    """طلب رفع ملف الأذكار"""
    category = callback.data.split("_")[1]
    
    await state.update_data(upload_category=category)
    
    await callback.message.edit_text(
        f"أرسل ملف .txt يحتوي على الأذكار:\n\n"
        f"<i>يجب أن تكون الأذكار مفصولة بأسطر فارغة</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(f"set_{category}" if category != "aam" else "set_aam")
    )


# ==========================================
# --- معالجات القنوات ---
# ==========================================

@router.callback_query(F.data == "menu_channels")
async def menu_channels(callback: types.CallbackQuery):
    """قائمة إدارة القنوات"""
    await callback.message.edit_text(
        "📢 <b>إدارة القنوات</b>\n\nاختر عملية:",
        parse_mode="HTML",
        reply_markup=get_channels_menu_keyboard()
    )


@router.callback_query(F.data == "add_channel")
async def add_channel(callback: types.CallbackQuery, state: FSMContext):
    """إضافة قناة جديدة"""
    await state.set_state(AddChannelState.waiting_for_channel_id)
    
    await callback.message.edit_text(
        "أرسل <b>معرف القناة</b> (@Name) أو <b>الرقم</b> (-100...) أو قم بتوجيه رسالة:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard("menu_channels")
    )


@router.callback_query(F.data == "delete_channel")
async def delete_channel(callback: types.CallbackQuery):
    """حذف قناة"""
    user_id = callback.from_user.id
    # نبدأ دائماً من الصفحة 0 عند فتح القائمة
    markup = get_delete_channels_keyboard(user_id, page=0)
    
    await callback.message.edit_text(
        "🗑️ <b>حذف قناة:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )


@router.callback_query(F.data.startswith("del_ch_"))
async def confirm_delete_channel(callback: types.CallbackQuery):
    """تأكيد حذف قناة"""
    channel_id = callback.data.split("_")[2]
    
    DatabaseManager.delete_channel(channel_id)
    await callback.answer("✅ تم حذف القناة", show_alert=True)
    
    # إعادة عرض القناة في الصفحة الأولى بعد الحذف
    user_id = callback.from_user.id
    markup = get_delete_channels_keyboard(user_id, page=0)
    
    await callback.message.edit_text(
        "🗑️ <b>حذف قناة:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )


@router.callback_query(F.data.startswith("channels_page_"))
async def channels_page_navigate(callback: types.CallbackQuery):
    """التنقل بين صفحات القنوات (التالي/السابق)"""
    user_id = callback.from_user.id
    
    # استخراج رقم الصفحة من البيانات
    page = int(callback.data.split("_")[2])
    
    # إعادة بناء الكيبورد بناءً على الصفحة الجديدة
    markup = get_delete_channels_keyboard(user_id, page)
    
    await callback.message.edit_reply_markup(reply_markup=markup)


# ==========================================
# --- معالجات الإذاعة ---
# ==========================================

@router.callback_query(F.data == "menu_broadcast")
async def menu_broadcast(callback: types.CallbackQuery):
    """قائمة الإذاعة"""
    await callback.message.edit_text(
        "اختر نوع البث:",
        reply_markup=get_broadcast_menu_keyboard()
    )


@router.callback_query(F.data == "ask_broadcast_ch")
async def ask_broadcast_channels(callback: types.CallbackQuery, state: FSMContext):
    """طلب نص البث للقنوات"""
    await state.set_state(BroadcastState.waiting_for_broadcast_channels)
    
    await callback.message.edit_text(
        "أرسل نص البث للقنوات:",
        reply_markup=get_cancel_keyboard("menu_broadcast")
    )


@router.callback_query(F.data == "ask_broadcast_pm")
async def ask_broadcast_private(callback: types.CallbackQuery, state: FSMContext):
    """طلب نص البث للرسائل الخاصة"""
    await state.set_state(BroadcastState.waiting_for_broadcast_private)
    
    await callback.message.edit_text(
        "أرسل نص البث للرسائل الخاصة:",
        reply_markup=get_cancel_keyboard("menu_broadcast")
    )


# ==========================================
# --- معالجات المشرفين ---
# ==========================================

@router.callback_query(F.data == "menu_admins")
async def menu_admins(callback: types.CallbackQuery):
    """قائمة إدارة المشرفين"""
    user_role = DatabaseManager.get_user_role(callback.from_user.id)
    
    if not is_owner(user_role):
        await callback.answer("❌ للمالك فقط", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🛡️ إدارة المشرفين:",
        reply_markup=get_admins_menu_keyboard()
    )


@router.callback_query(F.data == "add_admin")
async def add_admin(callback: types.CallbackQuery, state: FSMContext):
    """إضافة مشرف جديد"""
    await state.set_state(AddAdminState.waiting_for_user_id)
    
    await callback.message.edit_text(
        "أرسل <b>ID المستخدم</b>:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard("menu_admins")
    )


@router.callback_query(F.data == "delete_admin")
async def delete_admin(callback: types.CallbackQuery):
    """حذف مشرف"""
    user_role = DatabaseManager.get_user_role(callback.from_user.id)
    
    if not is_owner(user_role):
        await callback.answer("❌ للمالك فقط", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🗑️ حذف مشرف:\n\n",
        reply_markup=get_delete_admins_keyboard()
    )


@router.callback_query(F.data.startswith("del_ad_"))
async def confirm_delete_admin(callback: types.CallbackQuery):
    """تأكيد حذف مشرف"""
    user_role = DatabaseManager.get_user_role(callback.from_user.id)
    
    if not is_owner(user_role):
        await callback.answer("❌ للمالك فقط", show_alert=True)
        return
    
    target_id = int(callback.data.split("_")[2])
    
    DatabaseManager.set_user_role(target_id, "user")
    await callback.answer("✅ تم حذف المشرف", show_alert=True)
    
    await callback.message.edit_text(
        "🗑️ حذف مشرف:\n\n",
        reply_markup=get_delete_admins_keyboard()
    )


@router.callback_query(F.data == "list_admins")
async def list_admins(callback: types.CallbackQuery):
    """عرض قائمة المشرفين"""
    admins = DatabaseManager.get_admin_users()
    
    text = "👥 <b>قائمة المشرفين:</b>\n\n"
    if not admins:
        text += "لا يوجد مشرفين"
    else:
        for admin in admins:
            role_emoji = "👑" if admin.role == "owner" else "🛡️"
            text += f"{role_emoji} {admin.first_name} (ID: {admin.user_id})\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_admins")
    )


# ==========================================
# --- معالجات قناة التحقق ---
# ==========================================

@router.callback_query(F.data == "menu_verification")
async def menu_verification(callback: types.CallbackQuery):
    """قائمة قناة التحقق"""
    user_role = DatabaseManager.get_user_role(callback.from_user.id)
    
    if not is_owner(user_role):
        await callback.answer("❌ للمطور فقط", show_alert=True)
        return
    
    verification_channel = DatabaseManager.get_config("verification_channel")
    
    text = f"🔧 <b>قناة التحقق</b>\n\n"
    text += f"القناة الحالية: {verification_channel or 'لا يوجد'}"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_verification_menu_keyboard()
    )


@router.callback_query(F.data == "set_verification_channel")
async def set_verification_channel(callback: types.CallbackQuery, state: FSMContext):
    """تعيين قناة التحقق"""
    await state.set_state(VerificationState.waiting_for_verification_channel)
    
    await callback.message.edit_text(
        "أرسل معرف القناة (@...):",
        reply_markup=get_cancel_keyboard("menu_verification")
    )


@router.callback_query(F.data == "remove_verification_channel")
async def remove_verification_channel(callback: types.CallbackQuery):
    """إزالة قناة التحقق"""
    DatabaseManager.set_config("verification_channel", None)
    
    await callback.message.edit_text(
        "✅ تمت إزالة قناة التحقق",
        reply_markup=get_back_keyboard("menu_verification")
    )


# ==========================================
# --- معالجات رفع الملفات ---
# ==========================================

@router.callback_query(F.data == "menu_upload")
async def menu_upload(callback: types.CallbackQuery):
    """قائمة رفع الملفات"""
    from keyboards import InlineKeyboardMarkup, InlineKeyboardButton
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="☀️ صباح", callback_data="upload_sabah"),
            InlineKeyboardButton(text="🌙 مساء", callback_data="upload_masaa"),
            InlineKeyboardButton(text="📖 عام", callback_data="upload_aam")
        ],
        [
            InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")
        ]
    ])
    
    await callback.message.edit_text(
        "اختر الفئة:",
        reply_markup=markup
    )