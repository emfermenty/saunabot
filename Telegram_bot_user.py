# Telegram_bot_user.py
import re
from telegram import ReplyKeyboardRemove
from datetime import datetime

from Telegram_bot_admin import show_admin_menu
from dbcontext.db import Session

WEEKDAYS_RU = {
    "Monday": "Понедельник",
    "Tuesday": "Вторник",
    "Wednesday": "Среда",
    "Thursday": "Четверг",
    "Friday": "Пятница",
    "Saturday": "Суббота",
    "Sunday": "Воскресенье"
}

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler
)

from Services import get_available_dates, get_or_create_user, update_user_phone, get_user_bookings, \
    get_available_times_by_date, confirm_booking_bd, get_event, clear_booking, load_sertificate, get_sertificate, \
    take_only_admins, bind_sertificate_and_user, confirm_booking_bd_with_sertificate
from Models import UserRole

ADMIN_PANEL, ADMIN_VIEW_BOOKINGS, ADMIN_VIEW_USERS, ADMIN_EDIT_BOOKING = range(4, 8)
BOT_TOKEN = "8046347998:AAFfW0fWu-yFzh0BqzVnpjkiLrRRKOi4PSc"
BANYA_NAME = "Живой пар"
BANYA_ADDRESS = "Комсомольский проспект, 15, г. Краснокамск"
CONTACT_PHONE = "+7 (999) 123-45-67"
WELCOME_IMAGE = "для тг.jpg"

# Conversation states
SELECT_PROCEDURE, SELECT_DATE, SELECT_TIME, CONFIRM_BOOKING = range(4)

async def ask_for_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    try:
        await update.callback_query.message.delete()
    except Exception as e:
        print(f"Не удалось удалить сообщение: {e}")

    user_id = update.callback_query.from_user.id
    user = await get_or_create_user(user_id)
    
    # Проверяем, есть ли уже номер телефона
    if user and user.phone:
        await show_main_menu(update, context)
        return SELECT_PROCEDURE

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.callback_query.message.chat.send_message(
        "Пожалуйста, отправьте свой номер телефона, используя кнопку ниже.",
        reply_markup=keyboard
    )
    return SELECT_PROCEDURE

from telegram import ReplyKeyboardRemove

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user

    if contact.user_id != user.id:
        await update.message.reply_text("Пожалуйста, поделитесь своим собственным номером телефона.")
        return

    await update_user_phone(user.id, contact.phone_number)
    
    # Удаляем клавиатуру с кнопкой "Поделиться номером"
    await update.message.reply_text("Спасибо! Номер получен ✅", reply_markup=ReplyKeyboardRemove())

    # Проверяем роль пользователя после сохранения номера
    db_user = await get_or_create_user(user.id)
    if db_user.role == UserRole.ADMIN:
        await show_admin_menu(update, context)
    else:
        await show_main_menu(update, context)

def get_procedure_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔥 Живой пар", callback_data='procedure_1')],
        [InlineKeyboardButton("💧 Синусоида", callback_data='procedure_2')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_menu')]  # Добавлена кнопка назад
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_procedure_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    procedure_id = int(query.data.split('_', 1)[1])
    context.user_data['procedure'] = procedure_id
    await select_date(update, context)

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dates = await get_available_dates()
    if not dates:
        await update.callback_query.edit_message_text("Нет доступных дат для записи.")
        return SELECT_PROCEDURE  # или показать меню

    context.user_data["dates"] = dates
    context.user_data["date_page"] = 0

    keyboard = get_dates_keyboard(dates, 0)
    await update.callback_query.edit_message_text(
        "Выберите дату для записи:",
        reply_markup=keyboard
    )
    return SELECT_DATE


def get_dates_keyboard(dates, current_page):
    keyboard = []

    dates_per_page = 7
    start = current_page * dates_per_page
    end = start + dates_per_page
    visible_dates = dates[start:end]

    for date in visible_dates:
        callback_data = f"select_date_{date.isoformat()}"  # Используем isoformat() для даты
        date_str = date.strftime("%d.%m.%Y")
        weekday_en = date.strftime("%A")
        weekday_ru = WEEKDAYS_RU.get(weekday_en, weekday_en)
        button_text = f"{date_str} ({weekday_ru})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"change_date_page_{current_page - 1}"))
    if end < len(dates):
        nav_buttons.append(InlineKeyboardButton("➡️ Далее", callback_data=f"change_date_page_{current_page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⬅️ В меню", callback_data="back_to_menu")])

    return InlineKeyboardMarkup(keyboard)

async def handle_new_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Выберите процедуру:",
        reply_markup=get_procedure_keyboard()
    )
    return SELECT_PROCEDURE

async def handle_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.split("_")[2]  # Изменено с [1] на [2], так как данные в формате "select_date_YYYY-MM-DD"
    selected_date = datetime.fromisoformat(date_str).date()
    context.user_data["selected_date"] = selected_date  # Сохраняем объект date, а не строку

    # Получаем доступные слоты, передавая строку в формате YYYY-MM-DD
    slots = await get_available_times_by_date(date_str)

    # Сохраняем доступные слоты: id → время
    context.user_data["available_slots"] = {
        slot.id: slot.slot_datetime.strftime("%H:%M") for slot in slots
    }

    # Формируем клавиатуру
    keyboard = [
        [InlineKeyboardButton(slot.slot_datetime.strftime("%H:%M"), callback_data=f"time_{slot.id}")]
        for slot in slots
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_menu')])

    await query.edit_message_text(
        text="Выберите время для записи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TIME

async def handle_selected_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("select_date_", "")
    selected_date = datetime.fromisoformat(date_str).date()
    context.user_data["selected_date"] = selected_date  # Сохраняем объект date

    # Вызываем показ слотов времени, передавая строку в формате YYYY-MM-DD
    slots = await get_available_times_by_date(date_str)

    if not slots:
        await query.edit_message_text(text=f"На {selected_date.strftime('%d.%m.%Y')} нет доступных слотов.",
                                    reply_markup=get_main_menu())
        return SELECT_DATE

    context.user_data["available_slots"] = {
        slot.id: slot.slot_datetime.strftime("%H:%M") for slot in slots
    }

    keyboard = [
        [InlineKeyboardButton(slot.slot_datetime.strftime("%H:%M"), callback_data=f"time_{slot.id}")]
        for slot in slots
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='select_date')])

    await query.edit_message_text(
        text=f"Вы выбрали дату: {selected_date.strftime('%d.%m.%Y')}\n\nВыберите время:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TIME

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = int(query.data.split("_")[1])
    context.user_data['slot_id'] = slot_id
    context.user_data['booking_time'] = context.user_data['available_slots'][slot_id]
    procedure_raw = context.user_data.get('procedure')
    event = await get_event(procedure_raw)
    user = await get_or_create_user(query.from_user.id)
    await query.edit_message_text(
        text=(
            f"🗓 Дата: {context.user_data['selected_date']}\n"
            f"🕒 Время: {context.user_data['booking_time']}\n"
            f"💆 Процедура: {event.title}\n\n"
            f"Подтвердите запись:"
        ),
        reply_markup=get_confirmation_keyboard(user, procedure_raw)
    )
    return CONFIRM_BOOKING


async def show_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    bookings = await get_user_bookings(user_id)

    if not bookings:
        await update.callback_query.edit_message_text(
            "У вас пока нет активных записей.",
            reply_markup=get_main_menu()
        )
        return

    bookings_text = "📋 Ваши записи:\n\n"
    keyboard = []

    for booking in bookings:
        id, slot_datetime, procedure, is_active = booking
        date_formatted = slot_datetime.strftime("%d.%m.%Y")
        time_formatted = slot_datetime.strftime("%H:%M")
        status_text = "✅ Активна" if is_active else "❌ Завершена"

        bookings_text += f"🔹 {date_formatted} в {time_formatted} ({procedure}) - {status_text}\n"

        keyboard.append([
            InlineKeyboardButton(
                f"{date_formatted} в {time_formatted} ({procedure} - {status_text})",
                callback_data=f'confirm_delete_{id}'
            )
        ])
    bookings_text += "\n Если вы хотите отменить запись, нажмите на нее"
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        bookings_text,
        reply_markup=reply_markup
    )

async def confirm_delete_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    booking_id = int(query.data.replace("confirm_delete_", ""))

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f'delete_booking_{booking_id}'),
            InlineKeyboardButton("❌ Отмена", callback_data='my_bookings')
        ]
    ]
    await query.edit_message_text(
        "❗ Вы уверены, что хотите отменить эту запись?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    selected_date = context.user_data['selected_date']  # Это объект date
    time = context.user_data['booking_time']
    procedure_raw = context.user_data.get('procedure')
    slot_id = context.user_data['slot_id']
    by_certificate = context.user_data.get("by_certificate", False)

    user = await get_or_create_user(user_id)
    event = await get_event(procedure_raw)
    date_formatted = selected_date.strftime("%d.%m.%Y")

    try:
        if by_certificate:
            await confirm_booking_bd_with_sertificate(procedure_raw, user_id, slot_id, event.id)
        else:
            await confirm_booking_bd(procedure_raw, user_id, slot_id)

        await query.edit_message_text(
            f"✅ Вы успешно записаны!\n\nДата: {date_formatted}\nВремя: {time}\nПроцедура: {event.title}" +
            (f"\n(по сертификату, оставшееся количество записей по сертификату вы можете посмотреть в профиле)" if by_certificate else ""),
            reply_markup=get_main_menu()
        )
    except Exception as e:
        await query.edit_message_text(f"⚠️ Произошла ошибка при подтверждении записи: {e}", reply_markup=get_main_menu())

    return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_or_create_user(user_id)
    
    # Если у пользователя нет номера телефона, перенаправляем на его запрос
    if not user or not user.phone:
        return await ask_for_contact(update, context)
    
    keyboard = [
        [InlineKeyboardButton("📅 Выбрать дату для записи", callback_data='select_date')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_bookings')],
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("Приобрести сертификат", callback_data='sertificate')],
        [InlineKeyboardButton("📞 Связаться с нами", callback_data='contact_us')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Главное меню:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=reply_markup
        )

async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_username = "@itrustedyou"  # Замените на реальный username администратора
    
    await update.callback_query.edit_message_text(
        f"📞 Контакты бани \"{BANYA_NAME}\":\n\n"
        f"Телефон: {CONTACT_PHONE}\n"
        f"Адрес: {BANYA_ADDRESS}\n\n"
        f"Мы работаем ежедневно с 10:00 до 22:00\n\n"
        f"По всем вопросам обращайтесь к администратору: {admin_username}",
        reply_markup=get_main_menu()
    )

async def ask_booking_id_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "Введите ID записи, которую хотите изменить:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='admin_all_bookings')]])
    )
    return ADMIN_EDIT_BOOKING

async def show_available_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dates = await get_available_dates()
    page = 0

    if not dates:
        await query.edit_message_text("Нет доступных дат.")
        return

    context.user_data["dates"] = dates  # сохраняем список в context
    context.user_data["date_page"] = page

    keyboard = get_dates_keyboard(dates, page)
    await query.edit_message_text("Выберите дату:", reply_markup=keyboard)

async def handle_selected_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("select_date_", "")
    selected_date = datetime.fromisoformat(date_str).date()
    context.user_data["selected_date"] = selected_date

    # Вызываем показ слотов времени, как в handle_date_selection
    slots = await get_available_times_by_date(selected_date.isoformat())

    if not slots:
        await query.edit_message_text(text=f"На {selected_date.strftime('%d.%m.%Y')} нет доступных слотов.",
                                      reply_markup=get_main_menu())
        return SELECT_DATE

    context.user_data["available_slots"] = {
        slot.id: slot.slot_datetime.strftime("%H:%M") for slot in slots
    }

    keyboard = [
        [InlineKeyboardButton(slot.slot_datetime.strftime("%H:%M"), callback_data=f"time_{slot.id}")]
        for slot in slots
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='select_date')])

    await query.edit_message_text(
        text=f"Вы выбрали дату: {selected_date.strftime('%d.%m.%Y')}\n\nВыберите время:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TIME
async def delete_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    booking_id = int(query.data.replace("delete_booking_", ""))
    await clear_booking(booking_id)
    await query.answer("Запись отменена ❌")
    await show_bookings(update, context)

async def handle_date_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    new_page = int(data.replace("change_date_page_", ""))
    dates = context.user_data.get("dates")

    if not dates:
        dates = await get_available_dates()
        context.user_data["dates"] = dates

    context.user_data["date_page"] = new_page
    keyboard = get_dates_keyboard(dates, new_page)
    await query.edit_message_text("Выберите дату:", reply_markup=keyboard)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    user = await get_or_create_user(user_id)

    if not user:
        await update.callback_query.edit_message_text(
            "Профиль не найден.",
            reply_markup=get_main_menu()
        )
        return

    # Получаем информацию о пользователе Telegram
    tg_user = update.callback_query.from_user
    first_name = tg_user.first_name or ""
    last_name = tg_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{tg_user.username}" if tg_user.username else "не указан"
    
    await update.callback_query.edit_message_text(
        f"👤 Ваш профиль:\n\n"
        f"Имя: {full_name}\n"
        f"Username: {username}\n"
        f"Телефон: {user.phone if user.phone else 'не указан'}\n"
        f"Количество занятий по сертификату:\n"
        f"   Синусойда: {user.count_of_session_sinusoid if user.count_of_session_sinusoid else 0}"
        f"   Живой пар: {user.count_of_sessions_alife_steam if user.count_of_sessions_alife_steam else 0} ",
        reply_markup=get_main_menu()
    )
'''кнопка выбора сертификата'''
async def obtainment_sertificate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sertificates = await load_sertificate()

    if not sertificates:
        await query.edit_message_text("Сертификатов пока нет.")
        return

    keyboard = [
        [InlineKeyboardButton(text=sub.title, callback_data=f"sert_{sub.id}")]
        for sub in sertificates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_menu')])
    await query.edit_message_text(
        text="Для приобритения сертификата обратитесь к администратору\n Нажмите на кнопку, после чего попросите администратора активировать сертификат после оплаты",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
'''отправка сообщения администратору'''
async def handle_selected_sertificate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_id = int(query.data.split("_")[1])
    sert = await get_sertificate(sub_id)
    print(sub_id)
    if sert:
        text = f"Вы выбрали {sert.title}\nНажмите на кнопку, после чего администратору придет сообщение с подтверждением"
    else:
        text = "Сертификат не найден."

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f'send_to_admin_sertificate_{sub_id}')],
        [InlineKeyboardButton("❌ Отменить", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def send_sertificate_request_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        sub_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.edit_message_text("Ошибка при обработке данных.")
        return

    user_id = query.from_user.id

    # Отправка админам
    await notify_admins_about_certificate(update, context, user_id, sub_id)

    await query.edit_message_text(
        "✅ Ваша заявка на сертификат отправлена администратору.\nОжидайте подтверждения.",
        reply_markup=get_main_menu()
    )

'''сообщение администратору с сертификатом'''
async def notify_admins_about_certificate(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: int):
    sert = await get_sertificate(sub_id)
    user = await get_or_create_user(user_id)
    admins = await take_only_admins()

    key = f"sert_request_{sub_id}_{user_id}"
    context.bot_data[key] = []
    text = (f"[Пользователь](tg://user?id={user.telegram_id})\n"
            f" с номером {user.phone}\n "
            f"запрашивает сертификат: {sert.title}\n"
            f"Подтвердите выдачу.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f'confirm_sert_{sub_id}_{user_id}')],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f'deny_sert_{sub_id}_{user_id}')]
    ])
    for admin in admins:
        try:
            msg = await context.bot.send_message(
                chat_id=admin.telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            # Сохраняем chat_id и message_id
            context.bot_data[key].append((admin.telegram_id, msg.message_id))
        except Exception as e:
            print(f"Ошибка отправки админу {admin.telegram_id}: {e}")

async def accepting_setificate(update: Update, context: ContextTypes, user_id: int, sub_id: int):
    await bind_sertificate_and_user(user_id, sub_id)
    sert = await get_sertificate(sub_id)
    count = sert.countofsessions_alife_steam or sert.countofsessions_sinusoid or 0
    await context.bot.send_message(
        chat_id=user_id,
        text=f"Вам успешно одобрен сертификат!\n\nКоличество занятий по сертификату: {count}"
    )
    key = f"sert_request_{sub_id}_{user_id}"
    messages_to_edit = context.bot_data.get(key, [])
    for chat_id, message_id in messages_to_edit:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="✅ Сертификат подтвержден"
            )
        except Exception as e:
            print(f"Не удалось изменить сообщение у {chat_id}: {e}")

    context.bot_data.pop(key, None)

def get_confirmation_keyboard(user=None, procedure_id=None):
    buttons = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_booking')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel_booking')]
    ]

    if user and procedure_id:
        if procedure_id == 1 and user.count_of_sessions_alife_steam > 0:
            buttons.insert(0, [InlineKeyboardButton("🎫 Записаться по сертификату", callback_data='confirm_booking_certificate')])
        elif procedure_id == 2 and user.count_of_session_sinusoid > 0:
            buttons.insert(0, [InlineKeyboardButton("🎫 Записаться по сертификату", callback_data='confirm_booking_certificate')])

    return InlineKeyboardMarkup(buttons)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📅 Выбрать дату для записи", callback_data='select_date')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_bookings')],
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("Приобрести сертификат", callback_data='sertificate')],
        [InlineKeyboardButton("📞 Связаться с нами", callback_data='contact_us')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'select_date':
        await query.edit_message_text(
            "Выберите процедуру:",
            reply_markup=get_procedure_keyboard())
    elif query.data == 'my_bookings':
        await show_bookings(update, context)
    elif query.data == 'profile':
        await show_profile(update, context)
    elif query.data == 'contact_us':
        await contact_us(update, context)
    elif query.data == 'back_to_menu':
        await show_main_menu(update, context)
    elif query.data == "sertificate":
        await obtainment_sertificate(update, context)
    elif query.data.startswith('procedure_'):
        await handle_procedure_selection(update, context)
    elif query.data.startswith('select_date_'):
        await handle_selected_date(update, context)
    elif query.data.startswith('time_'):
        await handle_time_selection(update, context)
    elif query.data == 'confirm_booking':
        await confirm_booking(update, context)
    elif query.data == 'cancel_booking':
        await show_main_menu(update, context)
    elif query.data.startswith('sert_'):
        await handle_selected_sertificate(update, context)
    elif query.data.startswith('change_date_page_'):
        await handle_date_pagination(update, context)
    elif query.data.startswith('confirm_delete_'):
        await confirm_delete_booking(update, context)
    elif query.data.startswith('delete_booking_'):
        await delete_booking(update, context)
    elif query.data.startswith("send_to_admin_sertificate_"):
        await send_sertificate_request_to_admin(update, context)
    elif query.data.startswith("confirm_sert_"):
        match = re.match(r"^confirm_sert_(\d+)_(\d+)$", query.data)
        if match:
            sub_id = int(match.group(1))
            user_id = int(match.group(2))
            print(f"{sub_id} +  + {user_id}")
            await accepting_setificate(update, context, user_id, sub_id)
    elif query.data.startswith("deny_sert_"):
        match = re.match(r"^deny_sert_(\d+)_(\d+)$", query.data)
        if match:
            sub_id = int(match.group(1))
            user_id = int(match.group(2))
            await context.bot.send_message(chat_id=user_id, text="Ваш запрос на сертификат был отклонён.")
            await query.message.delete()
    #для сертификата
    elif query.data == 'confirm_booking_certificate':
        context.user_data['by_certificate'] = True
        await confirm_booking(update, context)

