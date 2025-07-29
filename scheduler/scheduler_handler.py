from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from Models import TimeSlot
from Services import take_only_admins, take_phone_by_timeslot, confirm_timeslot, canceled_timeslot
from Telegram_bot_user import get_main_menu


async def send_reminder_to_user(application: Application, telegram_id: int, slot: TimeSlot):
    print(slot.id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirmfinal_{slot.id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"cancelfinal_{slot.id}")]
    ])

    slot_time_str = slot.slot_datetime.strftime("%Y-%m-%d %H:%M")
    text = f"Напоминание: у вас запись на {slot_time_str}.\n Пожалуйста, подтвердите будете ли вы на записи"

    try:
        await application.bot.send_message(chat_id=telegram_id, text=text, reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка при отправке напоминания пользователю {telegram_id}: {e}")

async def notify_admin_if_needed(application: Application, slot: TimeSlot):
    slot_time_str = slot.slot_datetime.strftime("%Y-%m-%d %H:%M")
    user = slot.user_id
    admins = await take_only_admins()
    text = f"Человек с записью на {slot_time_str} не подтвердил присутствие\n Его номер {await take_phone_by_timeslot(slot)}\n Профиль: [@{user}](tg://user?id={user})"
    for admin in admins:
        try:
            await application.bot.send_message(chat_id=admin.telegram_id, text=text)
        except Exception as e:
            print(f"Не удалось отправить сообщение админу {admin.telegram_id}: {e}")


async def notify_admin_signed_3_times(application: Application, user_telegram_id: int, count: int, user_phone: int):
    admins = await take_only_admins()
    message = f"Пользователь [@{user_telegram_id}](tg://user?id={user_telegram_id}) записался {count} раза за последние 5 минут.\nЕго номер: {user_phone}"

    for admin in admins:
        try:
            await application.bot.send_message(
                chat_id=admin.telegram_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"экзепшен в шэдулер хендлер) {admin.telegram_id}: {e}")


async def button_callback_scheduler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    print("callback received:", data)

    try:
        if data.startswith("confirmfinal_"):
            slot_id = int(data.split("_")[1])
            print(f"[confirmfinal_] обработка слота {slot_id}")
            await confirm_timeslot(slot_id)
            await query.edit_message_text(text="✅ Вы подтвердили запись!")
        elif data.startswith("cancelfinal_"):
            slot_id = int(data.split("_")[1])
            print(f"[cancelfinal_] обработка слота {slot_id}")
            await canceled_timeslot(slot_id)
            await query.edit_message_text(text="❌ Вы отменили запись!", reply_markup=get_main_menu())
    except Exception as e:
        print(f"[button_callback_scheduler] Ошибка при обработке callback: {e}")
        await query.edit_message_text(text="⚠️ Произошла ошибка. Попробуйте позже.")
