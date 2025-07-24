from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    CallbackQueryHandler, 
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from Models import User, TimeSlot, UserRole
from Services import get_or_create_user
from db import Session
from datetime import datetime, date, timedelta

WEEKDAYS_RU = {
    "Monday": "Понедельник",
    "Tuesday": "Вторник",
    "Wednesday": "Среда",
    "Thursday": "Четверг",
    "Friday": "Пятница",
    "Saturday": "Суббота",
    "Sunday": "Воскресенье"
}

# Состояния для ConversationHandler
ADMIN_MENU, SELECT_DATE_TO_CLOSE, CONFIRM_CLOSE_DATE, VIEW_USERS, SEND_NOTIFICATION = range(5)


async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, это callback query или обычное сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        message_id = query.message.message_id
    else:
        chat_id = update.effective_chat.id
        message_id = None
    
    keyboard = [
        [InlineKeyboardButton("❌ Закрыть день для записи", callback_data='close_day')],
        [InlineKeyboardButton("👥 Посмотреть пользователей", callback_data='view_users')],
        [InlineKeyboardButton("📢 Сделать рассылку", callback_data='send_notification')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Панель администратора:"
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )

async def handle_close_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Получаем список дат, которые можно закрыть (будущие даты с активными слотами)
    session = Session()
    today = date.today()
    dates = session.query(
        TimeSlot.slot_datetime
    ).filter(
        TimeSlot.slot_datetime >= today,
        TimeSlot.isActive == True
    ).distinct().all()
    
    if not dates:
        await query.edit_message_text("Нет доступных дат для закрытия.")
        return
    
    # Создаем кнопки для выбора даты
    keyboard = []
    for dt in dates:
        date_str = dt[0].strftime("%Y-%m-%d")
        keyboard.append([InlineKeyboardButton(date_str, callback_data=f'select_date_{date_str}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="Выберите дату для закрытия:",
        reply_markup=reply_markup
    )

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

async def execute_close_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    date_str = context.user_data['selected_date']
    
    session = Session()
    try:
        # Получаем и деактивируем все слоты на выбранную дату
        times = get_available_times_by_date(date_str)
        
        # Подтверждаем изменения
        session.commit()
        await query.edit_message_text(f"Дата {date_str} успешно закрыта для записи. Деактивировано {len(times)} слотов.")
    except Exception as e:
        session.rollback()
        await query.edit_message_text(f"Ошибка при закрытии даты: {str(e)}")
    finally:
        session.close()
    
    await show_admin_menu(update, context)

    
async def handle_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_admin_menu')])
    
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

def setup_admin_handlers(application):
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_close_day, pattern='^close_day$'),
            CallbackQueryHandler(handle_view_users, pattern='^view_users$'),
            CallbackQueryHandler(handle_send_notification, pattern='^send_notification$')
        ],
        states={
            SELECT_DATE_TO_CLOSE: [
                CallbackQueryHandler(confirm_close_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            CONFIRM_CLOSE_DATE: [
                CallbackQueryHandler(execute_close_date, pattern=r'^confirm_close_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(handle_close_day, pattern='^close_day$')
            ],
            VIEW_USERS: [
                CallbackQueryHandler(handle_users_pagination, pattern='^(prev_page|next_page|page_info)$'),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            SEND_NOTIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_notification_text),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(send_notification_to_users, pattern='^send_notification_confirm$'),
                CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$')
        ],
        allow_reentry=True
    )
    
    application.add_handler(admin_conv_handler)
    application.add_handler(CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$'))