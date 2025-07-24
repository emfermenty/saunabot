from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application

from Models import TimeSlot
from Services import take_only_admins, take_phone_by_timeslot


async def send_reminder_to_user(application: Application, telegram_id: int, slot: TimeSlot):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{slot.id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{slot.id}")]
    ])

    slot_time_str = slot.slot_datetime.strftime("%Y-%m-%d %H:%M")
    text = f"Напоминание: у вас запись на {slot_time_str}.\n Пожалуйста, подтвердите будете ли вы на записи"

    try:
        await application.bot.send_message(chat_id=telegram_id, text=text, reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка при отправке напоминания пользователю {telegram_id}: {e}")

def notify_admin_if_needed(application: Application, slot: TimeSlot):
    slot_time_str = slot.slot_datetime.strftime("%Y-%m-%d %H:%M")
    admins = take_only_admins()
    text = f"Человек с записью на {slot_time_str} не подтвердил присутствие\n Его номер {take_phone_by_timeslot(slot)}"
    for admin in admins:
        try:
            application.bot.send_message(chat_id=admin.telegram_id, text=text)
        except Exception as e:
            print(f"Не удалось отправить сообщение админу {admin.telegram_id}: {e}")

async def notify_admin_signed_3_times(application: Application, user_telegram_id: int, count: int, user_phone: int):
    admins = take_only_admins()
    message = f"Пользователь с ID {user_telegram_id} записался {count} раза за последние 5 минут.\n Его номер {user_phone}"
    for admin in admins:
        try:
            await application.bot.send_message(chat_id=admin.telegram_id, text=message)
        except Exception as e:
            print(f"Ошибка при отправке админу {admin.telegram_id}: {e}")