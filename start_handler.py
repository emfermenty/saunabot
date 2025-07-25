# start_handler.py
import os
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from telegram import InputFile
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from Telegram_bot_user import *
from Models import *
from scheduler.scheduler import configure_scheduler, start_scheduler
from scheduler.scheduler_handler import button_callback_scheduler

from Telegram_bot_admin import show_admin_menu
from Telegram_bot_admin import setup_admin_handlers

BOT_TOKEN = "8046347998:AAFfW0fWu-yFzh0BqzVnpjkiLrRRKOi4PSc"
BANYA_NAME = "Живой пар"
BANYA_ADDRESS = "Комсомольский проспект, 15, г. Краснокамск"
CONTACT_PHONE = "+7 (999) 123-45-67"
WELCOME_IMAGE = "для тг.jpg"

def run_bot():
    init_db()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"Ошибка: {context.error}")
    
    application.add_error_handler(error_handler)
    
    setup_admin_handlers(application)

    configure_scheduler(application)
    application.post_init = on_startup
    
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
        per_message=True,
        allow_reentry=True,
    )

    application.add_handler(CallbackQueryHandler(button_callback_scheduler, pattern=r'^(confirmfinal_|cancelfinal_).+'))
    application.add_handler(CallbackQueryHandler(confirm_delete_booking, pattern="^confirm_delete_"))
    application.add_handler(CallbackQueryHandler(delete_booking, pattern="^delete_booking_"))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(ask_for_contact, pattern='^share_phone$'))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(booking_conv_handler)
    
    # Добавляем обработчик для любых сообщений в самом конце
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_message))

    application.run_polling()

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли у пользователя номер телефона
    user = get_or_create_user(update.effective_user.id)
    
    if user and user.phone:
        # Если номер есть, показываем главное меню
        await show_main_menu(update, context)
    else:
        # Если номера нет, просим начать с /start
        await update.message.reply_text("Для начала работы с ботом нажмите /start")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id

    db_user = get_or_create_user(tg_id)

    # Если у пользователя есть номер телефона
    if db_user and db_user.phone:
        if db_user.role == UserRole.ADMIN:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Добро пожаловать в панель администратора"
            )
            await show_admin_menu(update, context)
        else:
            await show_main_menu(update, context)
        return

    # Если пользователь администратор, но без номера телефона
    if db_user.role == UserRole.ADMIN:
        print("Админ без номера телефона")

    # Для всех остальных - просим номер телефона
    welcome_text = (
    f"Здравствуйте, {user.first_name}!\n\n"
    "Для начала записи, пожалуйста, поделитесь своим номером телефона:"
)

    keyboard = [
    [KeyboardButton("📱 Поделиться номером", request_contact=True)]
]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


    if os.path.exists(WELCOME_IMAGE):
        try:
            with open(WELCOME_IMAGE, 'rb') as photo:
                if update.message:
                    await update.message.reply_photo(photo=InputFile(photo), caption=welcome_text, reply_markup=reply_markup)
                else:
                    await update.callback_query.message.reply_photo(photo=InputFile(photo), caption=welcome_text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка при отправке изображения: {e}")
            if update.message:
                await update.message.reply_text(welcome_text, reply_markup=reply_markup)
            else:
                await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)
    else:
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)

async def on_startup(application):
    start_scheduler()