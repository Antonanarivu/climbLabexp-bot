import logging
import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from sheets import append_incident, get_next_id
from config import BOT_TOKEN, RESPONSIBLE_CHAT_ID

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Состояния диалога ──────────────────────────────────────────────
CHOOSE_GYM, CHOOSE_CATEGORY, ENTER_DESCRIPTION, ENTER_LOCATION, ATTACH_MEDIA = range(5)

# ── Категории ──────────────────────────────────────────────────────
CATEGORIES = [
    "⚡ Электрика/освещение",
    "💧 Протечки/вода",
    "🌀 Вентиляция/климат",
    "🚿 Сантехника",
    "🚪 Двери/замки",
    "🔧 Оборудование/инвентарь",
    "🔥 Противопожарное",
    "🏗 Строительство/ремонт",
    "📦 Другое",
]


# ── Утилиты ────────────────────────────────────────────────────────

def build_summary(data: dict, incident_id: int) -> str:
    now = data.get("datetime", datetime.now().strftime("%d.%m.%Y %H:%M"))
    media_count = len(data.get("media", []))
    media_line = f"\n📎 Медиафайлов: {media_count}" if media_count else ""
    return (
        f"🔧 *Заявка #{incident_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *{data['gym']}* | {data['category']}\n"
        f"🕐 {now} | {data['reporter']}\n\n"
        f"📝 {data['description']}\n\n"
        f"📌 Место: {data['location']}"
        f"{media_line}"
    )


async def post_media_to_chat(bot, chat_id: int, media: list):
    for mtype, fid in media:
        try:
            if mtype == "photo":
                await bot.send_photo(chat_id=chat_id, photo=fid)
            elif mtype == "video":
                await bot.send_video(chat_id=chat_id, video=fid)
        except Exception as e:
            logger.error(f"Ошибка при отправке медиа в {chat_id}: {e}")


# ── Хендлеры ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа. Запускается по deep link: /start <group_id>
    или напрямую в личке — тогда group_id не будет.
    """
    args = context.args
    if args:
        try:
            context.user_data["group_id"] = int(args[0])
        except ValueError:
            pass

    keyboard = [
        [InlineKeyboardButton("🧗 Бутырская", callback_data="gym_Бутырская")],
        [InlineKeyboardButton("🧗 Аминьевская", callback_data="gym_Аминьевская")],
    ]
    await update.message.reply_text(
        "📋 *Новая заявка об инциденте*\n\nВыберите скалодром:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_GYM


async def choose_gym(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gym = query.data.replace("gym_", "")
    context.user_data["gym"] = gym

    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{i}")] for i, cat in enumerate(CATEGORIES)]
    await query.edit_message_text(
        f"📍 Скалодром: *{gym}*\n\nВыберите категорию проблемы:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return CHOOSE_CATEGORY


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cat_idx = int(query.data.replace("cat_", ""))
    context.user_data["category"] = CATEGORIES[cat_idx]

    await query.edit_message_text(
        f"📍 *{context.user_data['gym']}* | {CATEGORIES[cat_idx]}\n\n"
        "✏️ Опишите проблему подробно (что случилось, что не работает):",
        parse_mode="Markdown",
    )
    return ENTER_DESCRIPTION


async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text
    await update.message.reply_text(
        "📌 Укажите место внутри скалодрома и любые уточнения:\n"
        "_(например: «тёмная сторона, у 3-й трассы» или «мужская раздевалка, правая раковина»)_",
        parse_mode="Markdown",
    )
    return ENTER_LOCATION


async def enter_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["location"] = update.message.text
    context.user_data.setdefault("media", [])

    keyboard = [[InlineKeyboardButton("➡️ Пропустить — отправить заявку", callback_data="media_done")]]
    await update.message.reply_text(
        "📎 Прикрепите фото или видео.\n"
        "Можно отправить несколько — по одному. Когда закончите, нажмите кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ATTACH_MEDIA


async def attach_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        context.user_data["media"].append(("photo", update.message.photo[-1].file_id))
        mtype = "Фото"
    elif update.message.video:
        context.user_data["media"].append(("video", update.message.video.file_id))
        mtype = "Видео"
    else:
        await update.message.reply_text("⚠️ Пожалуйста, отправьте фото или видео, либо нажмите кнопку «Пропустить».")
        return ATTACH_MEDIA

    count = len(context.user_data["media"])
    keyboard = [[InlineKeyboardButton(f"✅ Готово (прикреплено: {count})", callback_data="media_done")]]
    await update.message.reply_text(
        f"✔️ {mtype} получено ({count} шт.). Можно добавить ещё или завершить:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ATTACH_MEDIA


async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = context.user_data
    data["datetime"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    user = query.from_user
    data["reporter"] = f"@{user.username}" if user.username else user.full_name

    # Получаем номер заявки из таблицы
    incident_id = get_next_id(data["gym"])

    summary = build_summary(data, incident_id)
    media = data.get("media", [])

    # 1. Постим карточку в группу (если знаем group_id)
    group_id = data.get("group_id")
    if group_id:
        try:
            await context.bot.send_message(chat_id=group_id, text=summary, parse_mode="Markdown")
            await post_media_to_chat(context.bot, group_id, media)
        except Exception as e:
            logger.error(f"Ошибка публикации в группу {group_id}: {e}")

    # 2. Уведомляем ответственного
    try:
        await context.bot.send_message(
            chat_id=RESPONSIBLE_CHAT_ID,
            text=f"🔔 *Новая заявка!*\n\n{summary}",
            parse_mode="Markdown",
        )
        await post_media_to_chat(context.bot, RESPONSIBLE_CHAT_ID, media)
    except Exception as e:
        logger.error(f"Ошибка уведомления ответственного: {e}")

    # 3. Записываем в Google Sheets
    media_info = f"{len(media)} файл(ов)" if media else "—"
    try:
        append_incident(data["gym"], {
            "id": incident_id,
            "datetime": data["datetime"],
            "reporter": data["reporter"],
            "gym": data["gym"],
            "category": data["category"],
            "description": data["description"],
            "location": data["location"],
            "media": media_info,
        })
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")

    await query.edit_message_text(
        f"✅ *Заявка #{incident_id} зарегистрирована!*\n\nОтветственный уведомлён. Спасибо!",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Заявка отменена. Чтобы начать заново — нажмите кнопку в чате.")
    context.user_data.clear()
    return ConversationHandler.END


async def on_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Когда бота добавляют в группу — отправляет закреплённое сообщение с кнопкой."""
    my_id = context.bot.id
    chat = update.effective_chat
    member = update.my_chat_member

    if member.new_chat_member.status in ("member", "administrator"):
        group_id = chat.id
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start={group_id}"

        msg = await context.bot.send_message(
            chat_id=group_id,
            text=(
                "👷 *Бот учёта инцидентов Climb Lab подключён*\n\n"
                "Если вы обнаружили неисправность — нажмите кнопку ниже, "
                "чтобы зафиксировать заявку. Это займёт 1 минуту.\n\n"
                "После заполнения заявка появится в этом чате и уйдёт ответственному."
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Сообщить о проблеме", url=deep_link)
            ]]),
            parse_mode="Markdown",
        )
        try:
            await context.bot.pin_chat_message(chat_id=group_id, message_id=msg.message_id, disable_notification=True)
        except Exception:
            pass  # Нет прав на закреп — не страшно


# ── Запуск ─────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_GYM: [CallbackQueryHandler(choose_gym, pattern=r"^gym_")],
            CHOOSE_CATEGORY: [CallbackQueryHandler(choose_category, pattern=r"^cat_")],
            ENTER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description)],
            ENTER_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_location)],
            ATTACH_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO, attach_media),
                CallbackQueryHandler(finalize, pattern=r"^media_done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

    from telegram.ext import ChatMemberHandler
    app.add_handler(ChatMemberHandler(on_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(conv)

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
