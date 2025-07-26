import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from Models import User, TimeSlot, SlotStatus, UserRole
from Services import close_session_of_day, get_unique_slot_dates, get_slots_by_date, get_available_dates_for_new_slots, \
    get_free_slots_by_date, save_new_slot_comment, get_all_events, get_slots_to_close_day, close_single_slot, \
    get_or_create_user, search_phone, get_all_users
from dbcontext.db import Session
from datetime import date, datetime

# Состояния для ConversationHandler
ADMIN_MENU, SELECT_DATE_TO_CLOSE, CONFIRM_CLOSE_DATE, VIEW_USERS, SEND_NOTIFICATION = range(5)
ADD_SLOT_DATE, ADD_SLOT_TIME, ADD_SLOT_COMMENT, SELECT_EVENT = range(5, 9)
CLOSE_BOOKING_DATE, CLOSE_BOOKING_TIME, CONFIRM_CLOSE_SLOT = range(9, 12)
SEARCH_BY_PHONE = 20

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем chat_id
    chat_id = update.effective_chat.id

    keyboard = [
        [InlineKeyboardButton("❌ Закрыть день для записи", callback_data='admin_close_day')],
        [InlineKeyboardButton("❌ Закрыть определенную запись", callback_data='admin_close_booking')],
        [InlineKeyboardButton("🔍 Поиск по телефону", callback_data='admin_search_by_phone')],
        [InlineKeyboardButton("📢 Рассылка", callback_data='admin_send_notification')],
        [InlineKeyboardButton("📅 Расписание", callback_data='admin_view_timetable')],
        [InlineKeyboardButton("➕ Добавить запись с комментарием", callback_data='admin_add_slot_comment')],
        [InlineKeyboardButton("🎫 Выдать по сертификату", callback_data='admin_give_visit_sertificate')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем новое сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text="📋 Панель администратора:",
        reply_markup=reply_markup
    )

async def handle_close_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = await get_slots_to_close_day()
    
    if not dates:
        await query.edit_message_text("Нет доступных дат для закрытия.")
        return
    
    # Создаем кнопки для выбора даты
    keyboard = []
    for dt in dates:
        date_str = dt.strftime("%Y-%m-%d")  # просто strftime от date
        keyboard.append([InlineKeyboardButton(date_str, callback_data=f'admin_select_date_{date_str}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Выберите дату для закрытия:",
        reply_markup=reply_markup
    )
    return SELECT_DATE_TO_CLOSE

async def start_phone_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="Введите номер телефона для поиска (в формате 79...):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')]])
    )
    return SEARCH_BY_PHONE

async def handle_phone_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_input = update.message.text.strip()
    user = await search_phone(phone_input)

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


async def confirm_close_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    date_str = query.data.split('_')[-1]
    context.user_data['selected_date'] = date_str
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f'admin_confirm_close_{date_str}')],
        [InlineKeyboardButton("↩️ Назад", callback_data='admin_close_day')]
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
        # Получаем и деактивируем все слоты на выбранную дату
        times = await close_session_of_day(date_str)
        await query.edit_message_text(f"Дата {date_str} успешно закрыта для записи. Деактивировано {len(times)} слотов.")
    except Exception as e:
        await query.edit_message_text(f"Ошибка при закрытии даты: {str(e)}")

    await show_admin_menu(update, context)

    
async def handle_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    users = await get_all_users()
    
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
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Список пользователей:\n\n" + "\n".join(pages[current_page]),
        reply_markup=reply_markup
    )

async def handle_users_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='admin_close_day')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Список пользователей:\n\n" + "\n".join(pages[current_page]),
        reply_markup=reply_markup
    )

async def handle_send_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['notification_text'] = ""
    
    await query.edit_message_text(
        text="Введите текст рассылки:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')]])
    )
    
    return SEND_NOTIFICATION


async def process_notification_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    # Сохраняем текст и медиа в user_data
    context.user_data['notification_text'] = message.caption or message.text
    context.user_data['photo'] = message.photo[-1].file_id if message.photo else None
    context.user_data['video'] = message.video.file_id if message.video else None

    keyboard = [
        [InlineKeyboardButton("✅ Отправить", callback_data='admin_send_notification_confirm')],
        [InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    preview_text = context.user_data['notification_text']

    # Удаляем предыдущее сообщение с просьбой ввести текст
    try:
        await context.bot.delete_message(
            chat_id=message.chat_id,
            message_id=message.message_id - 1
        )
    except Exception as e:
        print(f"Ошибка удаления сообщения: {e}")

    # Предпросмотр сообщения с учетом медиа
    if context.user_data['photo']:
        await message.reply_photo(
            photo=context.user_data['photo'],
            caption=f"Текст рассылки:\n\n{preview_text}\n\nПодтвердите отправку:",
            reply_markup=reply_markup
        )
    elif context.user_data['video']:
        await message.reply_video(
            video=context.user_data['video'],
            caption=f"Текст рассылки:\n\n{preview_text}\n\nПодтвердите отправку:",
            reply_markup=reply_markup
        )
    else:
        await message.reply_text(
            text=f"Текст рассылки:\n\n{preview_text}\n\nПодтвердите отправку:",
            reply_markup=reply_markup
        )

    return SEND_NOTIFICATION

async def send_notification_to_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await get_or_create_user(update.effective_user.id)
    if not user or user.role != UserRole.ADMIN:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⛔ У вас нет прав для выполнения этой операции"
        )
        return ConversationHandler.END

    notification_text = context.user_data.get('notification_text', '')
    photo = context.user_data.get('photo')
    video = context.user_data.get('video')

    if not any([notification_text, photo, video]):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Нельзя отправить пустое сообщение. Добавьте текст, фото или видео."
        )
        return ConversationHandler.END

    try:
        users = await get_all_users()
        success = 0
        failed = 0

        for user in users:
            try:
                caption = f"📢 Рассылка от администратора:\n\n{notification_text}" if notification_text else None

                if photo:
                    await context.bot.send_photo(chat_id=user.telegram_id, photo=photo, caption=caption)
                elif video:
                    await context.bot.send_video(chat_id=user.telegram_id, video=video, caption=caption)
                else:
                    await context.bot.send_message(chat_id=user.telegram_id, text=caption)
                success += 1
            except Exception as e:
                print(f"Ошибка отправки пользователю {user.telegram_id}: {e}")
                failed += 1

        result_text = f"✅ Рассылка завершена:\nУспешно: {success}\nНе удалось: {failed}"

        # Удаляем старое сообщение (если оно было)
        if query and query.message:
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")

        # Отправляем новое сообщение с результатами и кнопками админки
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result_text
        )
        await show_admin_menu(update, context)

    finally:
        context.user_data.pop('notification_text', None)
        context.user_data.pop('photo', None)
        context.user_data.pop('video', None)

    return ConversationHandler.END


'''Обзор расписания'''
async def handle_view_timetable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dates = await get_unique_slot_dates()
    if not dates:
        await query.edit_message_text("Нет доступных дат.")
        return

    keyboard = []
    for date_str in dates:  # даты как строки
        callback_data = f"admin_timetable_date_{date_str}"
        keyboard.append([InlineKeyboardButton(date_str, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📅 Выберите дату для просмотра расписания:",
        reply_markup=reply_markup
    )

'''вывод расписания'''
async def show_timetable_for_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("admin_timetable_date_", "")
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    slots = await get_slots_by_date(selected_date)

    # Фильтруем слоты, у которых есть статус
    slots = [slot for slot in slots if slot.status is not None]
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data='admin_view_timetable')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if not slots:
        await query.edit_message_text(text="На {selected_date.strftime('%Y-%m-%d')} записей нет.", reply_markup=reply_markup)
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

    await query.edit_message_text(
        text=f"📋 Расписание на {selected_date.strftime('%Y-%m-%d')}:\n\n{text}",
        reply_markup=reply_markup
    )

'''запись по телефону'''
async def start_add_slot_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = await get_available_dates_for_new_slots()
    if not dates:
        await query.edit_message_text("Нет доступных дат для создания записи.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d.strftime("%Y-%m-%d"), callback_data=f"admin_add_slot_date_{d.strftime('%Y-%m-%d')}")]
        for d in dates
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="admin_cancel_add_slot")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Выберите дату для новой записи:", reply_markup=reply_markup)
    return ADD_SLOT_DATE

async def select_add_slot_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_str = query.data.replace("admin_add_slot_date_", "")
    context.user_data['add_slot_date'] = date_str

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    slots = await get_free_slots_by_date(date_obj)

    if not slots:
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Нет свободных слотов на дату {date_str}.",
            reply_markup=reply_markup
        )
        return ConversationHandler.END  # или верни нужное состояние, если хочешь

    keyboard = [
        [InlineKeyboardButton(slot.slot_datetime.strftime("%H:%M"), callback_data=f"admin_add_slot_time_{slot.id}")]
        for slot in slots
    ]
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='admin_back_to_admin_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"Выберите время для записи на {date_str}:",
        reply_markup=reply_markup
    )
    return ADD_SLOT_TIME

async def select_event_for_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = int(query.data.replace("admin_add_slot_time_", ""))
    context.user_data['admin_add_slot_time_id'] = slot_id

    events = await get_all_events()
    if not events:
        await query.edit_message_text("Нет доступных мероприятий.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(event.title, callback_data=f"admin_select_event_{event.id}")]
        for event in events
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="admin_cancel_add_slot")])
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

    slot_id = context.user_data.get('admin_add_slot_time_id')
    if not slot_id:
        await query.edit_message_text("Ошибка: слот не выбран.")
        return ConversationHandler.END

    data = query.data
    event_id = int(data.replace("admin_select_event_", ""))
    context.user_data['admin_selected_event_id'] = event_id

    context.user_data['admin_add_slot_time_id'] = slot_id

    await query.edit_message_text("Введите комментарий к записи:")
    return ADD_SLOT_COMMENT

async def save_slot_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[DEBUG] Ввод комментария: {update.message.text}")
    comment = update.message.text.strip()
    slot_id = context.user_data.get('admin_add_slot_time_id')
    event_id = context.user_data.get('admin_selected_event_id')
    print(f"[DEBUG] {slot_id}, {comment}, {event_id}")
    success = await save_new_slot_comment(slot_id, comment, event_id)
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
    if data == "admin_view_timetable":
        await handle_view_timetable(update, context)
    elif data.startswith('admin_timetable_date_'):
        await show_timetable_for_date(update, context)

'''выбор даты для закрытия записи(дата)'''
async def start_close_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = await get_unique_slot_dates()
    if not dates:
        await query.edit_message_text("Нет доступных дат.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(d, callback_data=f"admin_close_booking_date_{d}")]
        for d in dates
    ]
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back_to_admin_menu")])
    await query.edit_message_text("Выберите дату:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CLOSE_BOOKING_DATE
'''выбор времени для закрытия записи(время)'''
async def select_slot_to_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("admin_close_booking_date_", "")
    context.user_data['close_booking_date'] = date_str

    slots = await get_slots_by_date(datetime.strptime(date_str, "%Y-%m-%d").date())
    if not slots:
        await query.edit_message_text("На выбранную дату нет слотов.")
        return ConversationHandler.END

    keyboard = []
    for slot in slots:
        time_str = slot.slot_datetime.strftime("%H:%M")
        status = "🔒 Занят" if slot.event_id else "🟢 Свободен"
        keyboard.append([InlineKeyboardButton(f"{time_str} ({status})", callback_data=f"admin_close_booking_slot_{slot.id}")])

    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back_to_admin_menu")])
    await query.edit_message_text(f"Выберите слот на {date_str}:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CLOSE_BOOKING_TIME
'''подтверждение удаления'''
async def confirm_slot_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot_id = int(query.data.replace("admin_close_booking_slot_", ""))
    context.user_data['slot_to_close_id'] = slot_id

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="admin_confirm_close_slot")],
        [InlineKeyboardButton("↩️ Назад", callback_data="admin_back_to_admin_menu")]
    ]
    await query.edit_message_text("Вы уверены, что хотите закрыть эту запись?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_CLOSE_SLOT
async def confirm_slot_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot_id = int(query.data.replace("admin_close_booking_slot_", ""))
    context.user_data['slot_to_close_id'] = slot_id

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="admin_confirm_close_slot")],
        [InlineKeyboardButton("↩️ Назад", callback_data="admin_back_to_admin_menu")]
    ]
    await query.edit_message_text("Вы уверены, что хотите закрыть эту запись?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_CLOSE_SLOT
async def execute_close_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    slot_id = context.user_data.get("slot_to_close_id")
    msg = await close_single_slot(slot_id)

    await query.edit_message_text(msg)
    await show_admin_menu(update, context)
    return ConversationHandler.END
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "admin_view_timetable":
        await handle_view_timetable(update, context)
    elif data.startswith("admin_timetable_date_"):
        await show_timetable_for_date(update, context)
    elif data.startswith("admin_close_booking_date_"):
        await select_slot_to_close(update, context)
    elif data.startswith("admin_close_booking_slot_"):
        await confirm_slot_close(update, context)
    elif data == "admin_confirm_close_slot":
        await execute_close_slot(update, context)
    elif data == "admin_close_day":
        await handle_close_day(update, context)
    elif data.startswith("admin_select_date_"):
        await confirm_close_date(update, context)
    elif data.startswith("admin_confirm_close_"):
        await execute_close_date(update, context)
    elif data == "admin_back_to_admin_menu":
        await show_admin_menu(update, context)
    elif data == "admin_send_notification_confirm":
        await send_notification_to_users(update, context)
    elif data.startswith("admin_add_slot_date_"):
        await select_add_slot_time(update, context)
    elif data.startswith("admin_add_slot_time_"):
        await select_event_for_slot(update, context)
    elif data.startswith("admin_select_event_"):
        await handle_event_selection(update, context)
    elif data == "admin_cancel_add_slot":
        await cancel_add_slot(update, context)
    elif data.startswith("admin_add_slot_date_"):
        await select_add_slot_time(update, context)
    elif data.startswith("admin_search_by_phone"):
        await start_phone_search(update, context)

