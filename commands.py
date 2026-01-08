"""
معالجات الأوامر (Commands)
"""

from aiogram import Router, types, F
from aiogram.filters import Command
from database import DatabaseManager
from keyboards import get_main_keyboard
from loguru import logger

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """معالج أمر /start"""
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    # إضافة المستخدم إلى قاعدة البيانات
    user = DatabaseManager.add_user(user_id, first_name, username)
    
    user_role = user.role
    
    welcome_text = (
        f"👋 مرحباً {first_name}!\n\n"
        f"🤖 أنا بوت الأذكار الإسلامية\n\n"
        f"✨ يمكنني نشر الأذكار تلقائياً في قنواتك\n\n"
        f"📖 اختر من القائمة أدناه للبدء:"
    )
    
    await message.reply(
        welcome_text,
        reply_markup=get_main_keyboard(user_role)
    )
    
    logger.info(f"✅ مستخدم جديد: {user_id} ({first_name})")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """معالج أمر /help"""
    help_text = (
        "📚 <b>مساعدة البوت</b>\n\n"
        
        "<b>الأوامر الأساسية:</b>\n"
        "/start - بدء البوت\n"
        "/help - عرض هذه الرسالة\n"
        "/stats - عرض الإحصائيات\n\n"
        
        "<b>الميزات:</b>\n"
        "📊 <b>الإحصائيات:</b> عرض عدد الأذكار والقنوات والمستخدمين\n"
        "⚙️ <b>إعدادات الأذكار:</b> تخصيص أوقات ومدة النشر\n"
        "📢 <b>إدارة القنوات:</b> إضافة وحذف القنوات\n"
        "📢 <b>الإذاعة:</b> إرسال رسائل جماعية\n"
        "➕ <b>رفع الملفات:</b> تحديث ملفات الأذكار\n"
        "🛡️ <b>إدارة المشرفين:</b> تعيين المشرفين\n\n"
        
        "<b>نصائح مهمة:</b>\n"
        "💡 تأكد من أن البوت عضو في القنوات المراد النشر فيها\n"
        "💡 ملفات الأذكار يجب أن تكون بصيغة .txt\n"
        "💡 الأذكار يجب أن تكون مفصولة بأسطر فارغة\n"
    )
    
    await message.reply(help_text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """معالج أمر /stats"""
    from bot_utils import format_stats, load_adhkars_from_file
    
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
    
    await message.reply(text, parse_mode="HTML")


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """معالج أمر /admin - للمشرفين فقط"""
    user_role = DatabaseManager.get_user_role(message.from_user.id)
    
    if user_role not in ["admin", "owner"]:
        await message.reply("❌ هذا الأمر للمشرفين فقط.")
        return
    
    admin_text = (
        "🛡️ <b>لوحة المشرفين</b>\n\n"
        
        "<b>الأوامر المتاحة:</b>\n"
        "/broadcast_channels - إرسال رسالة لجميع القنوات\n"
        "/broadcast_users - إرسال رسالة لجميع المستخدمين\n"
        "/list_channels - عرض جميع القنوات\n"
        "/list_admins - عرض جميع المشرفين\n\n"
        
        "<b>ملاحظة:</b>\n"
        "💡 استخدم الأزرار أدناه للتنقل بسهولة"
    )
    
    await message.reply(admin_text, parse_mode="HTML")


@router.message(Command("owner"))
async def cmd_owner(message: types.Message):
    """معالج أمر /owner - للمالك فقط"""
    user_role = DatabaseManager.get_user_role(message.from_user.id)
    
    if user_role != "owner":
        await message.reply("❌ هذا الأمر للمالك فقط.")
        return
    
    owner_text = (
        "👑 <b>لوحة المالك</b>\n\n"
        
        "<b>الأوامر الخاصة:</b>\n"
        "/add_admin - إضافة مشرف جديد\n"
        "/remove_admin - إزالة مشرف\n"
        "/set_verification - تعيين قناة التحقق\n"
        "/remove_verification - إزالة قناة التحقق\n\n"
        
        "<b>ملاحظة:</b>\n"
        "💡 استخدم الأزرار أدناه للتنقل بسهولة"
    )
    
    await message.reply(owner_text, parse_mode="HTML")


@router.message(Command("list_channels"))
async def cmd_list_channels(message: types.Message):
    """عرض قائمة القنوات"""
    user_role = DatabaseManager.get_user_role(message.from_user.id)
    
    if user_role not in ["admin", "owner"]:
        await message.reply("❌ هذا الأمر للمشرفين فقط.")
        return
    
    channels = DatabaseManager.get_active_channels()
    
    if not channels:
        await message.reply("📢 لا توجد قنوات مضافة حالياً.")
        return
    
    text = "📢 <b>قائمة القنوات:</b>\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. {channel.title} (ID: {channel.channel_id})\n"
    
    await message.reply(text, parse_mode="HTML")


@router.message(Command("list_admins"))
async def cmd_list_admins(message: types.Message):
    """عرض قائمة المشرفين"""
    user_role = DatabaseManager.get_user_role(message.from_user.id)
    
    if user_role not in ["admin", "owner"]:
        await message.reply("❌ هذا الأمر للمشرفين فقط.")
        return
    
    admins = DatabaseManager.get_admin_users()
    
    if not admins:
        await message.reply("👥 لا يوجد مشرفين حالياً.")
        return
    
    text = "👥 <b>قائمة المشرفين:</b>\n\n"
    for admin in admins:
        role_emoji = "👑" if admin.role == "owner" else "🛡️"
        text += f"{role_emoji} {admin.first_name} (ID: {admin.user_id})\n"
    
    await message.reply(text, parse_mode="HTML")
