"""
معالجات الرسائل النصية والحالات (States)
تم تعديله لقبول توجيه الرسائل وحل مشاكل رفع الملفات
"""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import DatabaseManager
from keyboards import (
    get_main_keyboard, get_cancel_keyboard, get_back_keyboard,
    get_verification_menu_keyboard
)
from bot_utils import (
    is_valid_time_format, is_valid_interval, is_valid_user_id,
    is_valid_channel_id, get_error_message, get_success_message,
    load_adhkars_from_file  # تأكد من وجود هذا الاستيراد
)
from loguru import logger

router = Router()


# ==========================================
# --- تعريف الحالات (States) ---
# ==========================================

class AddChannelState(StatesGroup):
    """حالات إضافة قناة"""
    waiting_for_channel_id = State()


class AddAdminState(StatesGroup):
    """حالات إضافة مشرف"""
    waiting_for_user_id = State()


class EditTimeState(StatesGroup):
    """حالات تعديل الأوقات"""
    waiting_for_start_time = State()
    waiting_for_end_time = State()
    waiting_for_interval = State()


class EditIntervalState(StatesGroup):
    """حالات تعديل فترة التكرار"""
    waiting_for_interval = State()


class BroadcastState(StatesGroup):
    """حالات البث"""
    waiting_for_broadcast_channels = State()
    waiting_for_broadcast_private = State()


class VerificationState(StatesGroup):
    """حالات قناة التحقق"""
    waiting_for_verification_channel = State()


# ==========================================
# --- (1) معالجات قناة التحقق ---
# ==========================================

@router.message(VerificationState.waiting_for_verification_channel)
async def process_verification_channel(message: types.Message, state: FSMContext):
    """معالجة تعيين قناة التحقق"""
    channel_id = message.text.strip()
    
    if not channel_id.startswith("@"):
        await message.reply(
            "❌ يجب أن يبدأ معرف القناة بـ @\n"
            "مثال: @my_channel",
            reply_markup=get_cancel_keyboard("menu_verification")
        )
        return
    
    try:
        # التحقق من أن القناة موجودة
        chat = await message.bot.get_chat(channel_id)
        
        if chat.type != "channel":
            await message.reply(
                "❌ هذا ليس قناة.",
                reply_markup=get_cancel_keyboard("menu_verification")
            )
            return
        
        # حفظ قناة التحقق
        DatabaseManager.set_config("verification_channel", channel_id)
        
        await message.reply(
            f"✅ تم تعيين قناة التحقق: {channel_id}",
            reply_markup=get_main_keyboard("owner")
        )
        
        # إعادة إرسال قائمة التحقق لسهولة التعديل مرة أخرى
        markup = get_verification_menu_keyboard()
        await message.answer("🔧 قناة التحقق:", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"❌ خطأ في تعيين قناة التحقق: {e}")
        await message.reply(
            "❌ فشل في تعيين القناة. تأكد من أن البوت عضو في القناة.",
            reply_markup=get_cancel_keyboard("menu_verification")
        )
    
    await state.clear()


# ==========================================
# --- (2) معالجات إضافة القناة (مصححة للفوروارد والصلاحيات) ---
# ==========================================

@router.message(AddChannelState.waiting_for_channel_id)
async def process_add_channel(message: types.Message, state: FSMContext):
    """
    معالجة إضافة قناة جديدة (تقبل ID أو Forwarded Message)
    وتتحقق من صلاحيات البوت قبل الإضافة
    """
    channel_id = None
    channel_title = "قناة بدون اسم"

    # الحالة 1: إذا قام المستخدم بتوجيه رسالة من القناة (Forward)
    if message.forward_from_chat:
        chat = message.forward_from_chat
        
        if chat.type != "channel":
            await message.reply(
                "❌ يجب أن تكون الرسالة الموجهة من <b>قناة</b> وليست من مجموعة أو مستخدم.",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard("menu_channels")
            )
            return
        
        channel_id = str(chat.id)
        channel_title = chat.title or "قناة بدون اسم"

    # الحالة 2: إذا قام المستخدم بإرسال نص (ID أو Username)
    elif message.text:
        text = message.text.strip()
        
        if not is_valid_channel_id(text):
            await message.reply(
                "❌ صيغة غير صحيحة.\n"
                "يرجى إرسال معرف القناة (@channel_name) أو رقم ID أو قم بتوجيه رسالة من القناة.",
                reply_markup=get_cancel_keyboard("menu_channels")
            )
            return
        
        channel_id = text
        # إذا كان نص، سنحاول جلب العنوان لاحقاً
    
    else:
        # إذا لم يكن موجه ولا نص (مثلاً أرسل صورة عادية بدون توجيه)
        await message.reply(
            "❌ لم يتم إدخال بيانات. يرجى إرسال ID أو قم بتوجيه رسالة من القناة.",
            reply_markup=get_cancel_keyboard("menu_channels")
        )
        return
    
    try:
        # 1. جلب معلومات القناة
        chat_info = await message.bot.get_chat(channel_id)
        channel_title = chat_info.title
        
        # 2. التحقق مما إذا كان البوت مشرفاً في القناة
        try:
            bot_member = await message.bot.get_chat_member(channel_id, message.bot.id)
            
            if bot_member.status not in ["administrator", "creator"]:
                await message.reply(
                    "❌ <b>البوت ليس مشرفاً في هذه القناة!</b>\n"
                    "يرجى رفع البوت مشرفاً أولاً ثم حاول الإضافة مرة أخرى.",
                    parse_mode="HTML",
                    reply_markup=get_cancel_keyboard("menu_channels")
                )
                return
        
        except Exception as perm_error:
            # إذا حدث خطأ هنا، يعني أن البوت محظور أو ليس عضواً
            logger.error(f"فشل التحقق من الصلاحيات: {perm_error}")
            await message.reply(
                "❌ <b>فشل التحقق من صلاحيات البوت.</b>\n"
                "تأكد أن البوت عضو في القناة ومشرف.",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard("menu_channels")
            )
            return
        
        # 3. إضافة القناة إلى قاعدة البيانات (إذا اجتاز التحقق)
        DatabaseManager.add_channel(
            str(chat_info.id),
            channel_title,
            message.from_user.id
        )
        
        await message.reply(
            f"✅ تم إضافة القناة بنجاح!\n\n"
            f"📢 الاسم: {channel_title}\n"
            f"🆔 المعرف: {channel_id}",
            reply_markup=get_main_keyboard(DatabaseManager.get_user_role(message.from_user.id))
        )
        
        # --- إضافة: إشعار المطور عند إضافة قناة جديدة ---
        try:
            owner_id = None
            # نجلب ID المطور من قاعدة البيانات
            all_users = DatabaseManager.get_all_users()
            for user in all_users:
                if user.role == "owner":
                    owner_id = user.user_id
                    break
            
            if owner_id:
                await message.bot.send_message(
                    owner_id,
                    f"🔔 <b>إشعار جديد</b>\n\n"
                    f"تم إضافة قناة جديدة بواسطة: {message.from_user.first_name}\n"
                    f"📢 القناة: {channel_title}\n"
                    f"🆔 ID: {channel_id}",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"فشل إرسال الإشعار للمطور: {e}")
        # -----------------------------------------------------

    except Exception as e:
        logger.error(f"❌ خطأ في إضافة القناة: {e}")
        await message.reply(
            "❌ فشل في إضافة القناة. تأكد من أن البوت عضو في القناة وأن البيانات صحيحة.",
            reply_markup=get_cancel_keyboard("menu_channels")
        )
    
    await state.clear()


# ==========================================
# --- (4) معالجات تعديل الأوقات ---
# ==========================================

@router.message(EditTimeState.waiting_for_start_time)
async def process_start_time(message: types.Message, state: FSMContext):
    """معالجة إدخال وقت البداية"""
    start_time = message.text.strip()
    
    if not is_valid_time_format(start_time):
        await message.reply(
            "❌ صيغة خاطئة.\n"
            "يرجى إرسال الوقت بصيغة HH:MM (مثال: 06:00)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(start_time=start_time)
    await state.set_state(EditTimeState.waiting_for_end_time)
    await message.reply(
        "✅ تم حفظ البداية.\n"
        "الآن أدخل وقت النهاية (HH:MM):",
        reply_markup=get_cancel_keyboard()
    )


@router.message(EditTimeState.waiting_for_end_time)
async def process_end_time(message: types.Message, state: FSMContext):
    """معالجة إدخال وقت النهاية"""
    end_time = message.text.strip()
    
    if not is_valid_time_format(end_time):
        await message.reply(
            "❌ صيغة خاطئة.\n"
            "يرجى إرسال الوقت بصيغة HH:MM (مثال: 12:00)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(end_time=end_time)
    await state.set_state(EditTimeState.waiting_for_interval)
    await message.reply(
        "✅ تم حفظ النهاية.\n"
        "الآن أدخل فترة التكرار (دقائق) من 1 إلى 1000:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(EditTimeState.waiting_for_interval)
async def process_time_interval(message: types.Message, state: FSMContext):
    """معالجة إدخال فترة التكرار"""
    interval_str = message.text.strip()
    
    if not interval_str.isdigit():
        await message.reply(
            "❌ أرقام فقط.\n"
            "يرجى إرسال رقم صحيح من 1 إلى 1000",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    interval = int(interval_str)
    if not is_valid_interval(interval):
        await message.reply(
            "❌ الفترة يجب أن تكون بين 1 و 1000 دقيقة.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    data = await state.get_data()
    category = data.get('category')
    
    # تحديث الفئة في قاعدة البيانات
    DatabaseManager.update_category(
        category,
        start_time=data['start_time'],
        end_time=data['end_time'],
        interval_minutes=interval,
        is_enabled=True
    )
    
    await message.reply(
        "✅ تم حفظ الإعدادات بنجاح!",
        reply_markup=get_main_keyboard(DatabaseManager.get_user_role(message.from_user.id))
    )
    
    await state.clear()


# ==========================================
# --- (5) معالجات تعديل فترة التكرار ---
# ==========================================

@router.message(EditIntervalState.waiting_for_interval)
async def process_edit_interval(message: types.Message, state: FSMContext):
    """معالجة تعديل فترة التكرار"""
    interval_str = message.text.strip()
    
    if not interval_str.isdigit():
        await message.reply(
            "❌ أرقام فقط.\n"
            "يرجى إرسال رقم صحيح من 1 إلى 1000",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    interval = int(interval_str)
    if not is_valid_interval(interval):
        await message.reply(
            "❌ الفترة يجب أن تكون بين 1 و 1000 دقيقة.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    data = await state.get_data()
    category = data.get('category')
    
    # تحديث الفئة
    DatabaseManager.update_category(category, interval_minutes=interval)
    
    await message.reply(
        f"✅ تم تحديث فترة التكرار إلى {interval} دقيقة",
        reply_markup=get_main_keyboard(DatabaseManager.get_user_role(message.from_user.id))
    )
    
    await state.clear()


# ==========================================
# --- (6) معالجات البث ---
# ==========================================

@router.message(BroadcastState.waiting_for_broadcast_channels)
async def process_broadcast_channels(message: types.Message, state: FSMContext):
    """معالجة البث للقنوات"""
    broadcast_text = message.text or message.caption
    
    if not broadcast_text:
        await message.reply("❌ الرسالة فارغة. يرجى إرسال نص البث.")
        return
    
    channels = DatabaseManager.get_active_channels()
    sent_count = 0
    
    for channel in channels:
        try:
            await message.bot.send_message(
                int(channel.channel_id),
                broadcast_text,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الرسالة للقناة {channel.channel_id}: {e}")
    
    await message.reply(
        f"✅ تم إرسال الرسالة لـ {sent_count} قناة",
        reply_markup=get_main_keyboard(DatabaseManager.get_user_role(message.from_user.id))
    )
    
    await state.clear()


@router.message(BroadcastState.waiting_for_broadcast_private)
async def process_broadcast_private(message: types.Message, state: FSMContext):
    """معالجة البث للرسائل الخاصة"""
    broadcast_text = message.text or message.caption
    
    if not broadcast_text:
        await message.reply("❌ الرسالة فارغة. يرجى إرسال نص البث.")
        return
    
    users = DatabaseManager.get_all_users()
    sent_count = 0
    
    for user in users:
        try:
            await message.bot.send_message(
                user.user_id,
                broadcast_text,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الرسالة للمستخدم {user.user_id}: {e}")
    
    await message.reply(
        f"✅ تم إرسال الرسالة لـ {sent_count} مستخدم",
        reply_markup=get_main_keyboard(DatabaseManager.get_user_role(message.from_user.id))
    )
    
    await state.clear()


# ==========================================
# --- (7) معالجات رفع الملفات (محمية من التداخل) ---
# ==========================================

# معالج خاص لمنع التداخل عند إضافة قناة
@router.message(F.document, AddChannelState.waiting_for_channel_id)
async def ignore_docs_in_add_channel(message: types.Message):
    """
    تجاهل المستندات إذا كان المستخدم في حالة إضافة قناة
    """
    await message.reply(
        "❌ أنت في وضع إضافة قناة حالياً. يرجى إرسال ID القناة أو توجيه رسالة.\n"
        "للإلغاء اضغط على زر 'إلغاء'.",
        reply_markup=get_cancel_keyboard("menu_channels")
    )


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
        await message.reply("❌ لم يتم تحديد الفئة. يرجى الذهاب إلى القائمة واختيار 'رفع ملفات'.")
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