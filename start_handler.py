# start_handler.py
import os
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)

from Telegram_bot_user import *
from Telegram_bot_admin import *
from Models import *
from scheduler.scheduler import configure_scheduler, start_scheduler
from scheduler.scheduler_handler import button_callback_scheduler

#BOT_TOKEN = "8046347998:AAFfW0fWu-yFzh0BqzVnpjkiLrRRKOi4PSc"
BOT_TOKEN = "7610457298:AAHIpm3cB7SvSRO_Gp2tcFcVNygz1_tG6us"
BANYA_NAME = "Живой пар"
BANYA_ADDRESS = "Комсомольский проспект, 15, г. Краснокамск"
CONTACT_PHONE = "+7 (999) 123-45-67"
WELCOME_IMAGE = "для тг.jpg"

def run_bot():
    init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"Ошибка: {context.error}")
    application.add_error_handler(error_handler)

    # Объединённый ConversationHandler
    full_conv_handler = ConversationHandler(
        entry_points=[
            # USER
            CallbackQueryHandler(handle_procedure_selection, pattern=r'^procedure_\d+$'),
            CallbackQueryHandler(handle_selected_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$'),
            CallbackQueryHandler(handle_time_selection, pattern=r'^time_\d+$'),
            CallbackQueryHandler(confirm_booking, pattern='^confirm_booking$'),

            # ADMIN (с префиксом admin_)
            CallbackQueryHandler(handle_close_day, pattern=r'^admin_close_day$'),
            CallbackQueryHandler(start_close_booking, pattern=r'^admin_close_booking$'),
            CallbackQueryHandler(handle_view_users, pattern=r'^admin_view_users$'),
            CallbackQueryHandler(handle_send_notification, pattern=r'^admin_send_notification$'),
            CallbackQueryHandler(start_add_slot_comment, pattern=r'^admin_add_slot_comment$'),
        ],
        states={
            # USER
            SELECT_PROCEDURE: [CallbackQueryHandler(handle_procedure_selection, pattern=r'^procedure_\d+$')],
            SELECT_DATE: [CallbackQueryHandler(handle_selected_date, pattern=r'^select_date_\d{4}-\d{2}-\d{2}$')],
            SELECT_TIME: [CallbackQueryHandler(handle_time_selection, pattern=r'^time_\d+$')],
            CONFIRM_BOOKING: [CallbackQueryHandler(confirm_booking, pattern='^confirm_booking$')],

            # ADMIN
            SEARCH_BY_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_search)],
            CLOSE_BOOKING_DATE: [CallbackQueryHandler(select_slot_to_close, pattern=r'^admin_close_booking_date_\d{4}-\d{2}-\d{2}$')],
            CLOSE_BOOKING_TIME: [CallbackQueryHandler(confirm_slot_close, pattern=r'^admin_close_booking_slot_\d+$')],
            CONFIRM_CLOSE_SLOT: [CallbackQueryHandler(execute_close_slot, pattern=r'^admin_confirm_close_slot$')],
            SELECT_DATE_TO_CLOSE: [
                CallbackQueryHandler(confirm_close_date, pattern=r'^admin_select_date_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(show_admin_menu, pattern=r'^admin_back_to_admin_menu$')
            ],
            CONFIRM_CLOSE_DATE: [
                CallbackQueryHandler(execute_close_date, pattern=r'^admin_confirm_close_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(handle_close_day, pattern=r'^admin_close_day$')
            ],
            VIEW_USERS: [
                CallbackQueryHandler(handle_users_pagination, pattern=r'^(prev_page|next_page|page_info)$'),
                CallbackQueryHandler(show_admin_menu, pattern=r'^admin_back_to_admin_menu$')
            ],
            SEND_NOTIFICATION: [
                MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, process_notification_text),
                CallbackQueryHandler(send_notification_to_users, pattern='^admin_send_notification_confirm$'),
                CallbackQueryHandler(show_admin_menu, pattern='^admin_back_to_admin_menu$')
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(send_notification_to_users, pattern=r'^admin_send_notification_confirm$'),
                CallbackQueryHandler(show_admin_menu, pattern=r'^admin_back_to_admin_menu$')
            ],
            ADD_SLOT_DATE: [
                CallbackQueryHandler(select_add_slot_time, pattern=r'^admin_add_slot_date_\d{4}-\d{2}-\d{2}$'),
                CallbackQueryHandler(cancel_add_slot, pattern=r'^admin_cancel_add_slot$')
            ],
            ADD_SLOT_TIME: [
                CallbackQueryHandler(select_event_for_slot, pattern=r'^admin_add_slot_time_\d+$'),
                CallbackQueryHandler(cancel_add_slot, pattern=r'^admin_cancel_add_slot$')
            ],
            SELECT_EVENT: [
                CallbackQueryHandler(handle_event_selection, pattern=r'^admin_select_event_\d+$'),
                CallbackQueryHandler(cancel_add_slot, pattern=r'^admin_cancel_add_slot$')
            ],
            ADD_SLOT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_slot_comment),
                CallbackQueryHandler(cancel_add_slot, pattern=r'^admin_cancel_add_slot$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(start_phone_search, pattern=r'^admin_start_phone_search$'),
            CallbackQueryHandler(show_main_menu, pattern=r'^back_to_menu$'),
            CallbackQueryHandler(show_admin_menu, pattern=r'^admin_back_to_admin_menu$'),
            CallbackQueryHandler(cancel_add_slot, pattern=r'^admin_cancel_add_slot$'),
        ],
        allow_reentry=True
    )

    application.add_handler(full_conv_handler)

    # Универсальный обработчик callback_query — распределяет по ролям
    application.add_handler(CallbackQueryHandler(universal_button_handler, pattern='.*'))

    # Остальные хендлеры
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_message))
    application.add_handler(CallbackQueryHandler(button_callback_scheduler, pattern=r'^(confirmfinal_|cancelfinal_).+'))
    application.add_handler(CallbackQueryHandler(confirm_delete_booking, pattern=r"^confirm_delete_"))
    application.add_handler(CallbackQueryHandler(delete_booking, pattern=r"^delete_booking_"))
    application.add_handler(CallbackQueryHandler(ask_for_contact, pattern=r'^share_phone$'))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    configure_scheduler(application)
    application.post_init = on_startup
    application.run_polling()


async def universal_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await get_or_create_user(update.effective_user.id)

    is_admin_callback = query.data.startswith('admin_')

    if user and user.role == UserRole.ADMIN:
        if is_admin_callback:
            await admin_button_handler(update, context)
        else:
            await button_handler(update, context)
    else:
        if is_admin_callback:
            await query.message.reply_text("⛔ У вас нет доступа к админ-панели")
        else:
            await button_handler(update, context)

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('notification_text') is not None:
        return
    if context.user_data.get('_conversation'):
        return
    user = await get_or_create_user(update.effective_user.id)

    if user and user.phone:
        if user.role == UserRole.ADMIN:
            await show_admin_menu(update, context)
        else:
            await show_main_menu(update, context)
    else:
        await update.message.reply_text("Для начала работы с ботом нажмите /start")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id
    db_user = await get_or_create_user(tg_id)

    if db_user and db_user.phone:
        if db_user.role == UserRole.ADMIN:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Добро пожаловать в панель администратора")
            await show_admin_menu(update, context)
        else:
            await show_main_menu(update, context)
        return

    welcome_text = (
        f"Здравствуйте, {user.first_name}!\n\n"
        f"Это бот для онлайн-записи в баню \"{BANYA_NAME}\" "
        f"по адресу: {BANYA_ADDRESS}.\n\n"
        "Для начала записи, пожалуйста, поделитесь своим номером телефона:"
    )

    contact_button = KeyboardButton("📱 Поделиться номером", request_contact=True)
    reply_markup = ReplyKeyboardMarkup(
        [[contact_button]], resize_keyboard=True, one_time_keyboard=True
    )

    if os.path.exists(WELCOME_IMAGE):
        try:
            with open(WELCOME_IMAGE, "rb") as photo:
                if update.message:
                    await update.message.reply_photo(
                        photo=InputFile(photo),
                        caption=welcome_text,
                        reply_markup=reply_markup,
                    )
                else:
                    await update.callback_query.message.reply_photo(
                        photo=InputFile(photo),
                        caption=welcome_text,
                        reply_markup=reply_markup,
                    )
        except Exception as e:
            print(f"Ошибка при отправке изображения: {e}")
            await update.effective_chat.send_message(welcome_text, reply_markup=reply_markup)
    else:
        await update.effective_chat.send_message(welcome_text, reply_markup=reply_markup)


async def on_startup(application):
    start_scheduler()
