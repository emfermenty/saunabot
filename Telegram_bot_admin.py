#Telegram_bot_admin.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

from Models import User, SlotStatus
from Services import (
    close_session_of_day,
    get_unique_slot_dates,
    get_slots_by_date,
    get_all_events,
    get_slots_to_close_day,
    close_single_slot,
    save_new_slot_comment,
    get_available_dates_for_new_slots,
    get_free_slots_by_date
)
from dbcontext.db import Session
from datetime import datetime


# Conversation states
ADMIN_MENU, SELECT_DATE_TO_CLOSE, CONFIRM_CLOSE_DATE, VIEW_USERS, SEND_NOTIFICATION = range(5)
ADD_SLOT_DATE, ADD_SLOT_TIME, ADD_SLOT_COMMENT, SELECT_EVENT = range(5, 9)
CLOSE_BOOKING_DATE, CLOSE_BOOKING_TIME, CONFIRM_CLOSE_SLOT = range(9, 12)
SEARCH_BY_PHONE = 20

# === Панель администратора ===
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        chat_id = query.message.chat_id
        message_id = query.message.message_id
    else:
        chat_id = update.effective_chat.id
        message_id = None

    keyboard = [
    [InlineKeyboardButton("❌ Закрыть день для записи", callback_data='close_day')],
    [InlineKeyboardButton("❌ Закрыть отдельную запись", callback_data='close_booking')],
    [InlineKeyboardButton("🔍 Поиск по телефону", callback_data='search_by_phone')],
    [InlineKeyboardButton("📢 Рассылка", callback_data='send_notification')],
    [InlineKeyboardButton("📅 Расписание", callback_data='view_timetable')],
    [InlineKeyboardButton("➕ Добавить запись с комментарием", callback_data='add_slot_comment')],
    [InlineKeyboardButton("🎫 Выдать по сертификату", callback_data='give_visit_sertificate')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👮 Панель администратора:"
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# === Закрытие дня ===
async def handle_close_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = get_slots_to_close_day()
    if not dates:
        await query.edit_message_text("Нет доступных дат для закрытия.")
        return

    keyboard = [[InlineKeyboardButton(d.strftime("%Y-%m-%d"), callback_data=f'select_date_{d.strftime("%Y-%m-%d")}')] for d in dates]
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])

    await query.edit_message_text("Выберите дату для закрытия:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_DATE_TO_CLOSE

async def confirm_close_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    date_str = query.data.split('_')[-1]
    context.user_data['selected_date'] = date_str
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f'confirm_close_{date_str}')],
        [InlineKeyboardButton("↩️ Назад", callback_data='close_day')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"Вы уверены, что хотите закрыть дату {date_str} для записи?",
        reply_markup=reply_markup
    )
    return CONFIRM_CLOSE_DATE

async def execute_close_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = context.user_data['selected_date']
    try:
        times = close_session_of_day(date_str)
        await query.edit_message_text(f"✅ Дата {date_str} закрыта. Деактивировано {len(times)} слотов.")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при закрытии даты: {str(e)}")

    await show_admin_menu(update, context)

# === Просмотр пользователей ===  
'''async def handle_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    session = Session()
    users = session.query(User).order_by(User.telegram_id).all()
    session.close()
    
    if not users:
        await query.edit_message_text("Нет зарегистрированных пользователей.")
        return
    
    # Разбиваем пользователей на страницы (по 10 на страницу)
    users_list = [f"{user.telegram_id}: {user.phone or 'нет номера'} ({user.role})" for user in users]
    page_size = 10
    pages = [users_list[i:i + page_size] for i in range(0, len(users_list), page_size)]
    current_page = 0
    
    context.user_data['users_pages'] = pages
    context.user_data['current_page'] = current_page
    
    keyboard = []
    if len(pages) > 1:
        keyboard.append([
            InlineKeyboardButton("◀️", callback_data='prev_page'),
            InlineKeyboardButton(f"{current_page + 1}/{len(pages)}", callback_data='page_info'),
            InlineKeyboardButton("▶️", callback_data='next_page')
        ])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Список пользователей:\n\n" + "\n".join(pages[current_page]),
        reply_markup=reply_markup
    )'''

async def start_phone_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="Введите номер телефона для поиска (в формате 79...):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')]])
    )
    return SEARCH_BY_PHONE

'''async def handle_users_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    pages = context.user_data['users_pages']
    current_page = context.user_data['current_page']
    
    if action == 'prev_page' and current_page > 0:
        current_page -= 1
    elif action == 'next_page' and current_page < len(pages) - 1:
        current_page += 1
    
    context.user_data['current_page'] = current_page
    
    keyboard = []
    if len(pages) > 1:
        keyboard.append([
            InlineKeyboardButton("◀️", callback_data='prev_page'),
            InlineKeyboardButton(f"{current_page + 1}/{len(pages)}", callback_data='page_info'),
            InlineKeyboardButton("▶️", callback_data='next_page')
        ])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Список пользователей:\n\n" + "\n".join(pages[current_page]),
        reply_markup=reply_markup
    )'''

async def handle_phone_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_input = update.message.text.strip()
    
    session = Session()
    user = session.query(User).filter(User.phone == phone_input).first()
    session.close()

    if phone_input.startswith("8"):
        phone_input = "+7" + phone_input[1:]

    if user:
        info = f"""
🆔 <b>Telegram ID:</b> {user.telegram_id}  
📞 <b>Телефон:</b> {user.phone}  
🔐 <b>Роль:</b> {"Администратор" if user.role == "admin" else "Пользователь"}
"""
    else:
        info = f"❌ Пользователь с номером {phone_input} не найден."

    await update.message.reply_text(
        text=info,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')]])
    )
    return ConversationHandler.END


async def handle_send_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['notification_text'] = ""
    
    await query.edit_message_text(
        text="Введите текст рассылки:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')]])
    )
    
    return SEND_NOTIFICATION

async def process_notification_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notification_text = update.message.text
    context.user_data['notification_text'] = notification_text
    
    keyboard = [
        [InlineKeyboardButton("✅ Отправить", callback_data='send_notification_confirm')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=f"Текст рассылки:\n\n{notification_text}\n\nПодтвердите отправку:",
        reply_markup=reply_markup
    )
    
    return ADMIN_MENU

async def send_notification_to_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    notification_text = context.user_data['notification_text']
    
    session = Session()
    users = session.query(User).filter(User.telegram_id.isnot(None)).all()
    session.close()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"📢 Рассылка от администратора:\n\n{notification_text}"
            )
            success += 1
        except Exception as e:
            print(f"Ошибка отправки сообщения пользователю {user.telegram_id}: {str(e)}")
            failed += 1
    
    await query.edit_message_text(
        text=f"Рассылка завершена:\nУспешно: {success}\nНе удалось: {failed}"
    )
    
    await show_admin_menu(update, context)

'''Обзор расписания'''
async def handle_view_timetable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dates = get_unique_slot_dates()
    if not dates:
        await query.edit_message_text("Нет доступных дат.")
        return

    keyboard = []
    for date_str in dates:  # даты как строки
        callback_data = f"timetable_date_{date_str}"
        keyboard.append([InlineKeyboardButton(date_str, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📅 Выберите дату для просмотра расписания:",
        reply_markup=reply_markup
    )

'''вывод расписания'''
async def show_timetable_for_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("timetable_date_", "")
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    slots = get_slots_by_date(selected_date)

    # Фильтруем слоты, у которых есть статус
    slots = [slot for slot in slots if slot.status is not None]

    if not slots:
        await query.edit_message_text(f"На {selected_date.strftime('%Y-%m-%d')} записей нет.")
        return

    lines = []
    for slot in slots:
        event_title = slot.event.title if slot.event else "Нет мероприятия"
        time_str = slot.slot_datetime.strftime("%H:%M")

        if slot.comment:
            lines.append(f"🕒 {time_str} | 💬 Комментарий: {slot.comment} | 🎯 {event_title} ")
            continue  # пропускаем остальную информацию

        # Если комментария нет — продолжаем обычную логику
        if slot.user:
            try:
                chat = await context.bot.get_chat(slot.user.telegram_id)
                full_name = f"{chat.first_name or ''} {chat.last_name or ''}".strip()
                username = f"@{chat.username}" if chat.username else "не указан"
            except Exception:
                full_name = "Неизвестно"
                username = "не удалось получить"
            phone = slot.user.phone if slot.user.phone else "не указан"
            user_info = f"{username} | 📞 {phone}"
        else:
            user_info = "Нет данных о пользователе"


        if slot.status == SlotStatus.CONFIRMED:
            status_emoji = "🟢"
        elif slot.status == SlotStatus.PENDING:
            status_emoji = "🟡"
        elif slot.status == SlotStatus.CANCELED:
            status_emoji = "🔴"
        else:
            status_emoji = "❓"
        status_text = slot.status.value

        lines.append(f"🕒 {time_str} | 👤 {user_info} | 🎯 {event_title} | {status_emoji} {status_text}")

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = "\n\n".join(lines[:30]) + "\n\n⚠️ Слишком много данных. Показаны только первые 30."

    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data='view_timetable')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"📋 Расписание на {selected_date.strftime('%Y-%m-%d')}:\n\n{text}",
        reply_markup=reply_markup
    )

'''запись по телефону'''
async def start_add_slot_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = get_available_dates_for_new_slots()
    if not dates:
        await query.edit_message_text("Нет доступных дат для создания записи.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d.strftime("%Y-%m-%d"), callback_data=f"add_slot_date_{d.strftime('%Y-%m-%d')}")]
        for d in dates
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_add_slot")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Выберите дату для новой записи:", reply_markup=reply_markup)
    return ADD_SLOT_DATE

async def select_add_slot_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("add_slot_date_", "")
    context.user_data['add_slot_date'] = date_str

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    slots = get_free_slots_by_date(date_obj)

    if not slots:
        await query.edit_message_text(f"Нет свободных слотов на дату {date_str}.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(slot.slot_datetime.strftime("%H:%M"), callback_data=f"add_slot_time_{slot.id}")]
        for slot in slots
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_add_slot")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"Выберите время для записи на {date_str}:", reply_markup=reply_markup)
    return ADD_SLOT_TIME

async def select_event_for_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = int(query.data.replace("add_slot_time_", ""))
    context.user_data['add_slot_time_id'] = slot_id

    events = get_all_events()
    if not events:
        await query.edit_message_text("Нет доступных мероприятий.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(event.title, callback_data=f"select_event_{event.id}")]
        for event in events
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_add_slot")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Выберите мероприятие для записи:", reply_markup=reply_markup)
    return SELECT_EVENT

async def cancel_add_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Добавление записи отменено.")
    await show_admin_menu(update, context)
    return ConversationHandler.END

async def handle_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.replace("select_event_", ""))
    context.user_data['selected_event_id'] = event_id

    await query.edit_message_text("Введите комментарий для записи:")
    return ADD_SLOT_COMMENT

async def save_slot_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip()
    slot_id = context.user_data.get('add_slot_time_id')
    event_id = context.user_data.get('selected_event_id')

    success = save_new_slot_comment(slot_id, comment, event_id)
    if not success:
        await update.message.reply_text("Ошибка: выбранный слот не найден.")
        return ConversationHandler.END

    await update.message.reply_text("Запись успешно создана.")
    await show_admin_menu(update, context)
    return ConversationHandler.END
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "view_timetable":
        await handle_view_timetable(update, context)
    elif data.startswith('timetable_date_'):
        await show_timetable_for_date(update, context)

'''выбор даты для закрытия записи(дата)'''
async def start_close_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = get_unique_slot_dates()
    if not dates:
        await query.edit_message_text("Нет доступных дат.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d, callback_data=f"close_booking_date_{d}")]
        for d in dates
    ]
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="back_to_admin_menu")])
    await query.edit_message_text("Выберите дату:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CLOSE_BOOKING_DATE
'''выбор времени для закрытия записи(время)'''
async def select_slot_to_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("close_booking_date_", "")
    context.user_data['close_booking_date'] = date_str

    slots = get_slots_by_date(datetime.strptime(date_str, "%Y-%m-%d").date())
    if not slots:
        await query.edit_message_text("На выбранную дату нет слотов.")
        return ConversationHandler.END

    keyboard = []
    for slot in slots:
        time_str = slot.slot_datetime.strftime("%H:%M")
        status = "🔒 Занят" if slot.event_id else "🟢 Свободен"
        keyboard.append([InlineKeyboardButton(f"{time_str} ({status})", callback_data=f"close_booking_slot_{slot.id}")])

    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="back_to_admin_menu")])
    await query.edit_message_text(f"Выберите слот на {date_str}:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CLOSE_BOOKING_TIME
'''подтверждение удаления'''
async def confirm_slot_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot_id = int(query.data.replace("close_booking_slot_", ""))
    context.user_data['slot_to_close_id'] = slot_id

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_close_slot")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_admin_menu")]
    ]
    await query.edit_message_text("Вы уверены, что хотите закрыть эту запись?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_CLOSE_SLOT
async def confirm_slot_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot_id = int(query.data.replace("close_booking_slot_", ""))
    context.user_data['slot_to_close_id'] = slot_id

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_close_slot")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_admin_menu")]
    ]
    await query.edit_message_text("Вы уверены, что хотите закрыть эту запись?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_CLOSE_SLOT
async def execute_close_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = context.user_data.get("slot_to_close_id")
    msg = close_single_slot(slot_id)

    await query.edit_message_text(msg)
    await show_admin_menu(update, context)
    return ConversationHandler.END
def setup_admin_handlers(application):
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_close_day, pattern='^close_day$'),
            CallbackQueryHandler(start_close_booking, pattern="^close_booking$"),
            #CallbackQueryHandler(handle_view_users, pattern='^view_users$'),
            CallbackQueryHandler(start_phone_search, pattern='^search_by_phone$'),
            CallbackQueryHandler(handle_send_notification, pattern='^send_notification$'),
            CallbackQueryHandler(start_add_slot_comment, pattern='^add_slot_comment$'),
        ],
        states={
            CLOSE_BOOKING_DATE: [
                CallbackQueryHandler(select_slot_to_close, pattern=r'^close_booking_date_\d{4}-\d{2}-\d{2}$')],
            CLOSE_BOOKING_TIME: [CallbackQueryHandler(confirm_slot_close, pattern=r'^close_booking_slot_\d+$')],
            CONFIRM_CLOSE_SLOT: [CallbackQueryHandler(execute_close_slot, pattern="^confirm_close_slot$")],
            SELECT_DATE_TO_CLOSE: [
                CallbackQueryHandler(confirm_close_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            CONFIRM_CLOSE_DATE: [
                CallbackQueryHandler(execute_close_date, pattern=r'^confirm_close_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(handle_close_day, pattern='^close_day$')
            ],
            #VIEW_USERS: [
             #   CallbackQueryHandler(handle_users_pagination, pattern='^(prev_page|next_page|page_info)$'),
             #   CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
           # ],
            SEARCH_BY_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_search),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            SEND_NOTIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_notification_text),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(send_notification_to_users, pattern='^send_notification_confirm$'),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],

            # Новые состояния для добавления записи
            ADD_SLOT_DATE: [
                CallbackQueryHandler(select_add_slot_time, pattern=r'^add_slot_date_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(cancel_add_slot, pattern='^cancel_add_slot$')
            ],
            ADD_SLOT_TIME: [
                CallbackQueryHandler(select_event_for_slot, pattern=r'^add_slot_time_\d+$'),
                CallbackQueryHandler(cancel_add_slot, pattern='^cancel_add_slot$')
            ],
            SELECT_EVENT: [
                CallbackQueryHandler(handle_event_selection, pattern=r'^select_event_\d+$'),
                CallbackQueryHandler(cancel_add_slot, pattern='^cancel_add_slot$')
            ],
            ADD_SLOT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_slot_comment),
                CallbackQueryHandler(cancel_add_slot, pattern='^cancel_add_slot$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$'),
            CallbackQueryHandler(cancel_add_slot, pattern='^cancel_add_slot$')
        ],
        allow_reentry=True
    )

    application.add_handler(admin_conv_handler)
    application.add_handler(CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$'))
    application.add_handler(CallbackQueryHandler(admin_button_handler, pattern='.*'))
