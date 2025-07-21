from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler, ApplicationBuilder
)
import os

from Services import get_available_dates, get_or_create_user, update_user_phone, get_user_bookings, \
    get_available_times_by_date, confirm_booking_bd, get_timeslots_by_date, get_event, get_all_events, \
    update_booking_status
from db import init_db

BOT_TOKEN = "8046347998:AAFfW0fWu-yFzh0BqzVnpjkiLrRRKOi4PSc"
BANYA_NAME = "Живой пар"
BANYA_ADDRESS = "Комсомольский проспект, 15, г. Краснокамск"
CONTACT_PHONE = "+7 (999) 123-45-67"
WELCOME_IMAGE = "для тг.jpg"

# Conversation states
SELECT_PROCEDURE, SELECT_DATE, SELECT_TIME, CONFIRM_BOOKING = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id)
    welcome_text = (
        f"Здравствуйте, {user.first_name}!\n\n"
        f"Это бот для онлайн-записи в баню \"{BANYA_NAME}\" "
        f"по адресу: {BANYA_ADDRESS}.\n\n"
        "Для начала записи, пожалуйста, поделитесь своим номером телефона:"
    )
    keyboard = [
        [InlineKeyboardButton("📱 Поделиться номером", callback_data='share_phone')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if os.path.exists(WELCOME_IMAGE):
        try:
            with open(WELCOME_IMAGE, 'rb') as photo:
                await update.message.reply_photo(photo=InputFile(photo), caption=welcome_text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка при отправке изображения: {e}")
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def ask_for_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    try:
        await update.callback_query.message.delete()
    except Exception as e:
        print(f"Не удалось удалить сообщение: {e}")

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

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user

    if contact.user_id != user.id:
        await update.message.reply_text("Пожалуйста, поделитесь своим собственным номером телефона.")
        return

    update_user_phone(user.id, contact.phone_number)
    await show_main_menu(update, context)

def get_procedure_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔥 Живой пар", callback_data='procedure_1')],
        [InlineKeyboardButton("💧 Синусоида", callback_data='procedure_2')]
    ]
    return InlineKeyboardMarkup(keyboard)



async def handle_procedure_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    procedure_id = int(query.data.split('_', 1)[1])
    context.user_data['procedure'] = procedure_id
    await select_date(update, context)

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dates = get_available_dates()
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


def get_dates_keyboard(dates, current_page, page_size=7):
    start = current_page * page_size
    end = start + page_size
    visible_dates = dates[start:end]

    keyboard = []

    for date in visible_dates:
        callback_data = f"select_date_{date.isoformat()}"
        keyboard.append([InlineKeyboardButton(date.strftime("%d.%m.%Y"), callback_data=callback_data)])

    nav_buttons = []
    if start > 0:
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

    date = query.data.split("_")[1]
    context.user_data["selected_date"] = date

    # Получаем доступные слоты
    slots = get_timeslots_by_date(date)

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

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = int(query.data.split("_")[1])
    context.user_data['slot_id'] = slot_id
    context.user_data['booking_time'] = context.user_data['available_slots'][slot_id]
    procedure_raw = context.user_data.get('procedure')
    event = get_event(procedure_raw)
    await query.edit_message_text(
        text=(
            f"🗓 Дата: {context.user_data['selected_date']}\n"
            f"🕒 Время: {context.user_data['booking_time']}\n"
            f"💆 Процедура: {event.title}\n\n"
            f"Подтвердите запись:"
        ),
        reply_markup=get_confirmation_keyboard()
    )
    return CONFIRM_BOOKING


async def show_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    bookings = get_user_bookings(user_id)

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
                callback_data=f'show_booking_{id}'
            )
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        bookings_text,
        reply_markup=reply_markup
    )



async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    date = context.user_data['selected_date']
    time = context.user_data['booking_time']
    procedure_raw = context.user_data.get('procedure')
    slot_id = context.user_data['slot_id']  # обязательно получаем slot_id

    # Обновляем слот в базе данных
    confirm_booking_bd(procedure_raw, user_id, slot_id)

    event = get_event(procedure_raw)
    date_formatted = date.strftime("%d.%m.%Y")

    await query.edit_message_text(
        f"✅ Вы успешно записаны!\n\nДата: {date_formatted}\nВремя: {time}\nПроцедура: {event.title}",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Выбрать дату для записи", callback_data='select_date')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_bookings')],
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
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
    await update.callback_query.edit_message_text(
        f"📞 Контакты бани \"{BANYA_NAME}\":\n\n"
        f"Телефон: {CONTACT_PHONE}\n"
        f"Адрес: {BANYA_ADDRESS}\n\n"
        "Мы работаем ежедневно с 10:00 до 22:00",
        reply_markup=get_main_menu()
    )

async def show_available_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dates = get_available_dates()
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
    slots = get_timeslots_by_date(selected_date.isoformat())

    if not slots:
        await query.edit_message_text(f"На {selected_date.strftime('%d.%m.%Y')} нет доступных слотов.")
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


async def handle_date_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    new_page = int(data.replace("change_date_page_", ""))
    dates = context.user_data.get("dates")

    if not dates:
        dates = get_available_dates()
        context.user_data["dates"] = dates

    context.user_data["date_page"] = new_page
    keyboard = get_dates_keyboard(dates, new_page)
    await query.edit_message_text("Выберите дату:", reply_markup=keyboard)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    user = get_or_create_user(user_id)

    if not user:
        await update.callback_query.edit_message_text(
            "Профиль не найден.",
            reply_markup=get_main_menu()
        )
        return

    await update.callback_query.edit_message_text(
        f"👤 Ваш профиль:\n\nтелеграмid: {user.telegram_id}\nТелефон: {user.phone}",
        reply_markup=get_main_menu()
    )


def get_confirmation_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_booking')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel_booking')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📅 Выбрать дату для записи", callback_data='select_date')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_bookings')],
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
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
    elif query.data.startswith('procedure_'):
        await handle_procedure_selection(update, context)
    elif query.data.startswith('select_date_'):  # <-- вот здесь было 'date_', исправил на 'select_date_'
        await handle_selected_date(update, context)
    elif query.data.startswith('time_'):
        await handle_time_selection(update, context)
    elif query.data == 'confirm_booking':
        await confirm_booking(update, context)
    elif query.data == 'cancel_booking':
        await show_main_menu(update, context)


def run_bot():
    init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    booking_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_procedure_selection, pattern=r'^procedure_\d+$'),
            CallbackQueryHandler(handle_selected_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$'),
            CallbackQueryHandler(handle_time_selection, pattern=r'^time_\d+$'),
            CallbackQueryHandler(confirm_booking, pattern='^confirm_booking$'),
        ],
        states={
            SELECT_PROCEDURE: [
                CallbackQueryHandler(handle_procedure_selection, pattern=r'^procedure_\d+$')
            ],
            SELECT_DATE: [
                CallbackQueryHandler(handle_selected_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$')
            ],
            SELECT_TIME: [
                CallbackQueryHandler(handle_time_selection, pattern=r'^time_\d+$')
            ],
            CONFIRM_BOOKING: [
                CallbackQueryHandler(confirm_booking, pattern='^confirm_booking$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(show_main_menu, pattern='^back_to_menu$')
        ],
        per_message=False,
        allow_reentry=True,
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(ask_for_contact, pattern='^share_phone$'))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))  # отдельно ловим контакт
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(booking_conv_handler)

    application.run_polling()
if __name__ == '__main__':
    run_bot()