import os
import time
import schedule
import threading
import asyncio
import json
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.types import PeerChannel
from telethon.errors import UserNotParticipantError
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, MORNING_AZKAR_FILE, EVENING_AZKAR_FILE, GENERAL_AZKAR_FILE, CHANNELS_DB

# ----------------------------------------------------------------------
# 1. الإعدادات والتهيئة
# ----------------------------------------------------------------------

# ملف الإعدادات المتقدمة (أوقات النشر، الاشتراك الإجباري)
SETTINGS_FILE = "bot_settings.json"

def load_settings():
    default_settings = {
        "morning_time": "06:00",
        "evening_time": "18:00",
        "general_times": ["00:00", "03:00", "09:00", "12:00", "15:00", "21:00"],
        "force_channel": "", # معرف القناة للاشتراك الإجباري (مثلاً @MyChannel)
        "daily_report": True
    }
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f)
        return default_settings
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

settings = load_settings()

# تهيئة اليوزر بوت (UserBot)
user_client = TelegramClient('user_session', API_ID, API_HASH)

# تهيئة بوت التحكم (Controller Bot)
bot_client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ----------------------------------------------------------------------
# 2. وظائف إدارة الملفات وقاعدة البيانات
# ----------------------------------------------------------------------

def get_channels():
    if not os.path.exists(CHANNELS_DB): return []
    with open(CHANNELS_DB, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def add_channel(channel_id):
    channels = get_channels()
    if channel_id not in channels:
        with open(CHANNELS_DB, 'a', encoding='utf-8') as f:
            f.write(f"{channel_id}\n")
        return True
    return False

def remove_channel(channel_id):
    channels = get_channels()
    if channel_id in channels:
        channels.remove(channel_id)
        with open(CHANNELS_DB, 'w', encoding='utf-8') as f:
            f.write('\n'.join(channels) + '\n')
        return True
    return False

def get_content_lines(file_path):
    if not os.path.exists(file_path): return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

content_pointers = {MORNING_AZKAR_FILE: 0, EVENING_AZKAR_FILE: 0, GENERAL_AZKAR_FILE: 0}

# ----------------------------------------------------------------------
# 3. وظيفة النشر والتقارير
# ----------------------------------------------------------------------

async def post_scheduled_message(file_type):
    file_path = {"morning": MORNING_AZKAR_FILE, "evening": EVENING_AZKAR_FILE, "general": GENERAL_AZKAR_FILE}.get(file_type)
    if not file_path: return False

    content_lines = get_content_lines(file_path)
    if not content_lines: return False

    current_index = content_pointers.get(file_path, 0)
    message_to_post = content_lines[current_index]
    content_pointers[file_path] = (current_index + 1) % len(content_lines)

    channels = get_channels()
    if not channels: return False

    success_count = 0
    fail_count = 0
    
    async with user_client:
        for channel in channels:
            try:
                await user_client.send_message(channel, message_to_post)
                success_count += 1
            except Exception:
                fail_count += 1
    
    # إرسال تقرير للمدير
    if settings.get("daily_report"):
        report = (
            f"📊 **تقرير نشر ({file_type}):**\n"
            f"✅ تم بنجاح: `{success_count}`\n"
            f"❌ فشل: `{fail_count}`\n"
            f"🕒 الوقت: `{datetime.now().strftime('%H:%M')}`"
        )
        await bot_client.send_message(ADMIN_ID, report)
    
    return True

# ----------------------------------------------------------------------
# 4. وظيفة الجدولة (Scheduler)
# ----------------------------------------------------------------------

def run_async_task(file_type):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_scheduled_message(file_type))
    loop.close()

def start_scheduler():
    schedule.clear()
    # أذكار الصباح
    schedule.every().day.at(settings["morning_time"]).do(run_async_task, "morning")
    # أذكار المساء
    schedule.every().day.at(settings["evening_time"]).do(run_async_task, "evening")
    # الأذكار العامة
    for t in settings["general_times"]:
        schedule.every().day.at(t).do(run_async_task, "general")
    
    # نسخة احتياطية يومية الساعة 12 ليلاً
    schedule.every().day.at("00:00").do(lambda: asyncio.run(send_backup()))

    while True:
        schedule.run_pending()
        time.sleep(1)

async def send_backup():
    if os.path.exists(CHANNELS_DB):
        await bot_client.send_file(ADMIN_ID, CHANNELS_DB, caption="📦 **نسخة احتياطية لقائمة القنوات**")

# ----------------------------------------------------------------------
# 5. معالجات بوت التحكم
# ----------------------------------------------------------------------

async def check_force_join(user_id):
    if not settings["force_channel"]: return True
    try:
        await bot_client.get_permissions(settings["force_channel"], user_id)
        return True
    except UserNotParticipantError:
        return False
    except:
        return True

@bot_client.on(events.NewMessage(pattern='/start'))
async def handler_start(event):
    if event.sender_id == ADMIN_ID:
        await send_admin_panel(event.chat_id)
    else:
        if not await check_force_join(event.sender_id):
            return await event.respond(
                f"⚠️ **عذراً، يجب عليك الاشتراك في قناتنا أولاً لاستخدام البوت:**\n\n{settings['force_channel']}\n\nبعد الاشتراك، أرسل /start مرة أخرى.",
                buttons=[Button.url("اضغط هنا للاشتراك", f"https://t.me/{settings['force_channel'].replace('@','')}")]
            )
        await event.respond("🙏 **مرحبا بك في بوت نشر الأذكار التلقائي**\n\nلإضافة قناتك، استخدم الأمر:\n`/add_channel @YourChannel`")

async def send_admin_panel(chat_id, edit_message=None):
    channels = get_channels()
    message = (
        "🛠 **لوحة التحكم الاحترافية**\n\n"
        f"📊 **القنوات:** `{len(channels)}` | **التقرير:** `{'✅' if settings['daily_report'] else '❌'}`\n"
        f"📢 **الاشتراك الإجباري:** `{settings['force_channel'] or 'معطل'}`\n"
        f"⏰ **الصباح:** `{settings['morning_time']}` | **المساء:** `{settings['evening_time']}`\n"
    )
    buttons = [
        [Button.inline("📢 إدارة القنوات", data="manage_channels"), Button.inline("⏰ ضبط الأوقات", data="set_times")],
        [Button.inline("🔐 الاشتراك الإجباري", data="set_force"), Button.inline("📁 الملفات", data="upload_files")],
        [Button.inline("🚀 نشر فوري", data="post_now"), Button.inline("✉️ إعلان جماعي", data="broadcast_msg")],
        [Button.inline("📦 نسخة احتياطية", data="get_backup"), Button.inline("📊 التقرير: " + ("إيقاف" if settings['daily_report'] else "تفعيل"), data="toggle_report")]
    ]
    if edit_message: await edit_message.edit(message, buttons=buttons)
    else: await bot_client.send_message(chat_id, message, buttons=buttons)

@bot_client.on(events.CallbackQuery(data="admin_panel"))
async def cb_admin_panel(event):
    await send_admin_panel(event.chat_id, edit_message=event)

@bot_client.on(events.CallbackQuery(data="toggle_report"))
async def cb_toggle_report(event):
    settings["daily_report"] = not settings["daily_report"]
    save_settings(settings)
    await send_admin_panel(event.chat_id, edit_message=event)

@bot_client.on(events.CallbackQuery(data="get_backup"))
async def cb_backup(event):
    await send_backup()
    await event.answer("✅ تم إرسال النسخة الاحتياطية")

# --- ضبط الأوقات ---
@bot_client.on(events.CallbackQuery(data="set_times"))
async def cb_set_times(event):
    msg = (
        "⏰ **إعدادات أوقات النشر:**\n\n"
        f"🌅 الصباح: `{settings['morning_time']}`\n"
        f"🌃 المساء: `{settings['evening_time']}`\n\n"
        "لتغيير وقت الصباح أرسل: `صباح 07:00`\n"
        "لتغيير وقت المساء أرسل: `مساء 19:00`"
    )
    await event.edit(msg, buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

@bot_client.on(events.NewMessage(pattern=r'^(صباح|مساء) (\d{2}:\d{2})$'))
async def handle_time_change(event):
    if event.sender_id != ADMIN_ID: return
    type_time = event.pattern_match.group(1)
    new_time = event.pattern_match.group(2)
    if type_time == "صباح": settings["morning_time"] = new_time
    else: settings["evening_time"] = new_time
    save_settings(settings)
    # إعادة تشغيل المجدول لتحديث الأوقات
    threading.Thread(target=start_scheduler, daemon=True).start()
    await event.respond(f"✅ تم تحديث وقت {type_time} إلى {new_time}", buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

# --- الاشتراك الإجباري ---
@bot_client.on(events.CallbackQuery(data="set_force"))
async def cb_set_force(event):
    msg = (
        "🔐 **إعدادات الاشتراك الإجباري:**\n\n"
        f"القناة الحالية: `{settings['force_channel'] or 'لا يوجد'}`\n\n"
        "لتغيير القناة أرسل المعرف: `/force @MyChannel`\n"
        "لتعطيل الميزة أرسل: `/force off`"
    )
    await event.edit(msg, buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

@bot_client.on(events.NewMessage(pattern='/force (.*)'))
async def handle_force_set(event):
    if event.sender_id != ADMIN_ID: return
    val = event.pattern_match.group(1).strip()
    if val.lower() == "off": settings["force_channel"] = ""
    else: settings["force_channel"] = val
    save_settings(settings)
    await event.respond(f"✅ تم تحديث إعدادات الاشتراك الإجباري.", buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

# --- (باقي المعالجات السابقة مدمجة ومحسنة) ---
@bot_client.on(events.CallbackQuery(data="manage_channels"))
async def handler_manage_channels(event):
    channels = get_channels()
    msg = "**📢 إدارة القنوات:**\n\n" + ("\n".join([f"- `{c}`" for c in channels]) if channels else "لا توجد قنوات.")
    buttons = [[Button.inline("🗑 حذف قناة", data="del_mode")], [Button.inline("🔙 عودة", data="admin_panel")]]
    await event.edit(msg, buttons=buttons)

@bot_client.on(events.CallbackQuery(data="del_mode"))
async def cb_del_mode(event):
    channels = get_channels()
    buttons = [[Button.inline(f"❌ {c}", data=f"del_ch_{c}")] for c in channels[:10]]
    buttons.append([Button.inline("🔙 عودة", data="manage_channels")])
    await event.edit("اختر القناة لحذفها:", buttons=buttons)

@bot_client.on(events.CallbackQuery(pattern=r"del_ch_(.*)"))
async def cb_del_exec(event):
    ch = event.pattern_match.group(1).decode('utf-8')
    if remove_channel(ch): await event.answer(f"✅ تم حذف {ch}", alert=True)
    await handler_manage_channels(event)

@bot_client.on(events.CallbackQuery(data="post_now"))
async def cb_post_now(event):
    buttons = [[Button.inline("🌅 صباح", data="f_morning"), Button.inline("🌃 مساء", data="f_evening")], [Button.inline("📖 عام", data="f_general")], [Button.inline("🔙 عودة", data="admin_panel")]]
    await event.edit("🚀 نشر فوري الآن:", buttons=buttons)

@bot_client.on(events.CallbackQuery(pattern=r"f_(.*)"))
async def cb_force_exec(event):
    t = event.pattern_match.group(1).decode('utf-8')
    await event.answer("⏳ جاري النشر...")
    if await post_scheduled_message(t): await event.respond(f"✅ تم نشر {t} بنجاح.")
    else: await event.respond("❌ فشل النشر.")

@bot_client.on(events.CallbackQuery(data="broadcast_msg"))
async def cb_broadcast(event):
    await event.edit("✉️ أرسل: `/broadcast نص الرسالة`", buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

@bot_client.on(events.NewMessage(pattern='/broadcast (.*)'))
async def handle_broadcast(event):
    if event.sender_id != ADMIN_ID: return
    msg = event.pattern_match.group(1)
    channels = get_channels()
    count = 0
    async with user_client:
        for c in channels:
            try: await user_client.send_message(c, msg); count += 1
            except: pass
    await event.respond(f"✅ تم الإرسال إلى {count} قناة.")

@bot_client.on(events.CallbackQuery(data="upload_files"))
async def cb_upload(event):
    await event.edit("📁 أرسل ملف `.txt` لتحديث المحتوى.", buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

@bot_client.on(events.NewMessage(incoming=True, func=lambda e: e.file and e.file.name.endswith('.txt')))
async def handle_file(event):
    if event.sender_id != ADMIN_ID: return
    path = await event.download_media(file=os.getcwd())
    btns = [[Button.inline("🌅 صباح", data=f"s_{MORNING_AZKAR_FILE}_{path}"), Button.inline("🌃 مساء", data=f"s_{EVENING_AZKAR_FILE}_{path}")], [Button.inline("📖 عام", data=f"s_{GENERAL_AZKAR_FILE}_{path}")]]
    await event.respond(f"📥 ملف: `{os.path.basename(path)}`\nحدد النوع:", buttons=btns)

@bot_client.on(events.CallbackQuery(pattern=r"s_(.*)_(.*)"))
async def cb_set_file(event):
    target, temp = event.pattern_match.group(1).decode('utf-8'), event.pattern_match.group(2).decode('utf-8')
    os.rename(temp, target)
    await event.edit(f"✅ تم تحديث {target}", buttons=[[Button.inline("🔙 عودة", data="admin_panel")]])

@bot_client.on(events.NewMessage(pattern='/add_channel (.*)'))
async def handle_add_ch(event):
    if not await check_force_join(event.sender_id): return
    ch = event.pattern_match.group(1).strip()
    if add_channel(ch): await event.respond(f"✅ تمت إضافة {ch}")
    else: await event.respond("⚠️ مضافة مسبقاً.")

# ----------------------------------------------------------------------
# 6. التشغيل
# ----------------------------------------------------------------------

def main():
    print("🚀 بدء تشغيل النظام الاحترافي...")
    threading.Thread(target=start_scheduler, daemon=True).start()
    user_client.start()
    bot_client.run_until_disconnected()

if __name__ == '__main__':
    main()
