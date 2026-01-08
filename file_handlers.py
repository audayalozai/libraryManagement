"""
معالجات الملفات والرسائل الخاصة
"""

import os
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import DatabaseManager
from keyboards import (
    get_main_keyboard, 
    get_verification_menu_keyboard, 
    get_delete_channels_keyboard,
    get_channels_menu_keyboard
)
from bot_utils import load_adhkars_from_file, save_adhkars_to_file
from loguru import logger

router = Router()


# ==========================================
# تعريف حالات FSM (للتعامل مع القنوات)
# ==========================================

class VerificationChannelState(StatesGroup):
    waiting_for_channel = State()

# ==========================================
# معالجات الأزرار (Callback Handlers)
# ==========================================

@router.callback_query(F.data == "menu_channels")
async def show_channels_menu(call: types.CallbackQuery):
    """عرض قائمة إدارة القنوات"""
    user_id = call.from_user.id
    markup = get_channels_menu_keyboard()
    
    try:
        await call.message.edit_text("📢 **إدارة القنوات**", reply_markup=markup)
    except Exception as e:
        # في حال كان الرسالة قديمة لا يمكن تعديلها، نرسل رسالة جديدة
        logger.error(f"Error editing message: {e}")
        await call.message.answer("📢 **إدارة القنوات**", reply_markup=markup)


@router.callback_query(F.data == "delete_channel")
async def show_delete_channels_list(call: types.CallbackQuery):
    """عرض قائمة القنوات لحذفها (تعرض قنوات المستخدم فقط)"""
    user_id = call.from_user.id
    
    # التعديل المهم: تمرير user_id لعرض قنوات المستخدم فقط
    markup = get_delete_channels_keyboard(user_id)
    
    try:
        await call.message.edit_text("🗑️ **اختر قناة للحذف:**", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error editing delete list: {e}")


@router.callback_query(F.data == "set_verification_channel")
async def ask_for_verification_channel(call: types.CallbackQuery, state: FSMContext):
    """
    طلب معرف قناة الاشتراك الإجباري عند الضغط على زر التغيير
    """
    # تم حذف السطر الذي يسبب خطأ "الفئة غير موجودة"
    # لأننا نغير قناة التحقق، وليس فئة أذكار
    
    await call.message.delete()
    
    msg = await call.message.answer(
        "🔗 **أرسل معرف القناة (Username) الآن لتعيينه كاشتراك إجباري:**\n"
        "مثال: @MyChannel",
        parse_mode="Markdown"
    )
    
    # تفعيل الحالة لانتظار الرد من المستخدم
    await VerificationChannelState.waiting_for_channel.set()


@router.callback_query(F.data == "remove_verification_channel")
async def remove_verification_channel(call: types.CallbackQuery):
    """إزالة قناة الاشتراك الإجباري"""
    try:
        DatabaseManager.set_config('verification_channel', '')
        await call.answer("✅ تم إزالة قناة الاشتراك الإجباري.", show_alert=True)
        # إعادة تحميل القائمة
        markup = get_verification_menu_keyboard()
        await call.message.edit_text("🔧 **قناة التحقق**", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error removing verification channel: {e}")


# ==========================================
# معالجات الرسائل النصية (Message Handlers)
# ==========================================

@router.message(VerificationChannelState.waiting_for_channel, F.text)
async def save_verification_channel(message: types.Message, state: FSMContext):
    """
    حفظ القناة التي أرسلها المستخدم في قاعدة البيانات
    """
    channel_username = message.text.strip()
    
    # التحقق البسيط من الصيغة
    if not channel_username.startswith("@"):
        await message.answer("❌ يرجى إرسال المعرف بشكل صحيح يبدأ بـ @\nمثال: @MyChannel")
        return

    try:
        # حفظ القناة في قاعدة البيانات
        DatabaseManager.set_config('verification_channel', channel_username)
        
        await message.answer(f"✅ **تم حفظ قناة الاشتراك الإجباري بنجاح!**\nالقناة: {channel_username}")
        
        # إنهاء الحالة
        await state.finish()
        
        # إرسال قائمة التحقق مرة أخرى
        markup = get_verification_menu_keyboard()
        await message.answer("🔧 **قناة التحقق:**", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error saving verification channel: {e}")
        await message.answer(f"❌ حدث خطأ أثناء الحفظ: {e}")
        await state.finish()


@router.message(F.document)
async def handle_file_upload(message: types.Message, state: FSMContext):
    """معالجة رفع الملفات"""
    user_role = DatabaseManager.get_user_role(message.from_user.id)
    
    if user_role not in ["admin", "owner"]:
        await message.reply("❌ ليس لديك صلاحيات كافية.")
        return
    
    # التحقق من حالة المستخدم
    state_data = await state.get_data()
    upload_category = state_data.get("upload_category")
    
    if not upload_category:
        await message.reply("❌ لم يتم تحديد الفئة. يرجى المحاولة مرة أخرى.")
        return
    
    # التحقق من أن الملف هو .txt
    if not message.document.file_name.endswith(".txt"):
        await message.reply(
            "❌ الملف يجب أن يكون بصيغة .txt",
            reply_markup=get_main_keyboard(user_role)
        )
        return
    
    try:
        # تحميل الملف
        file_info = await message.bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        
        # تنزيل محتوى الملف
        file_content = await message.bot.download_file(file_path)
        
        # الحصول على مسار الملف المستهدف
        category = DatabaseManager.get_category(upload_category)
        if not category:
            await message.reply("❌ الفئة غير موجودة.")
            return
        
        target_file = category.file_path
        
        # حفظ الملف
        with open(target_file, "wb") as f:
            f.write(file_content.getvalue())
        
        # عد الأذكار
        adhkars = load_adhkars_from_file(target_file)
        adhkar_count = len(adhkars)
        
        await message.reply(
            f"✅ تم رفع الملف بنجاح!\n\n"
            f"📊 عدد الأذكار: {adhkar_count}",
            reply_markup=get_main_keyboard(user_role)
        )
        
        logger.info(f"✅ تم رفع ملف الأذكار: {target_file} ({adhkar_count} ذكر)")
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفع الملف: {e}")
        await message.reply(
            "❌ حدث خطأ في رفع الملف. يرجى المحاولة مرة أخرى.",
            reply_markup=get_main_keyboard(user_role)
        )
    
    await state.clear()


@router.message(F.text)
async def handle_text_message(message: types.Message):
    """معالجة الرسائل النصية العامة"""
    user_id = message.from_user.id
    
    # إضافة المستخدم إلى قاعدة البيانات إذا لم يكن موجوداً
    DatabaseManager.add_user(
        user_id,
        message.from_user.first_name,
        message.from_user.username
    )
    
    # الرد على الرسائل غير المتوقعة
    if message.text.startswith("/"):
        # معالجة الأوامر في ملف منفصل
        return
    
    # الرد على الرسائل العامة
    user_role = DatabaseManager.get_user_role(user_id)
    
    await message.reply(
        "👋 مرحباً! استخدم الأزرار أدناه للتنقل:",
        reply_markup=get_main_keyboard(user_role)
    )