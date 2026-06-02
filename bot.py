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

from sheets import append_incident, get_next_id, get_config, set_config
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

# Кэш настроек подчатов: {group_id: thread_id}
# Загружается при старте и обновляется командой /setup
_thread_config: dict = {}


def get_thread_id(group_id: int):
    """Возвращает thread_id для группы или None если не настроено."""
    return _thread_config.get(group_id)


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


async def post_media_to_chat(bot, chat_id: int, media: list, thread_id=None):
    for mtype, fid in media:
        try:
            if mtype == "photo":
                await bot.send_photo(chat_id=chat_id, photo=fid, message_thread_id=thread_id)
            elif mtype == "video":
                await bot.send_video(chat_id=chat_id, video=fid, message_thread_id=thread_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке медиа в {chat_id}: {e}")


# ── Хендлеры ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /setup — вызывается из нужного подчата группы.
    Бот запоминает: заявки из этой группы постить в этот подчат.
    """
    msg = update.message
    if not msg:
        return

    chat = msg.chat
    thread_id = msg.message_thread_id

    # Работает только в группах
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("⚠️ Команда /setup работает только в группах.")
        return

    if not thread_id:
        await msg.reply_text(
            "⚠️ Используйте /setup прямо внутри нужного подчата (топика), "
            "а не в основном чате."
        )
        return

    # Сохраняем в память и в Google Sheets
    _thread_config[chat.id] = thread_id
    set_config(chat.id, thread_id)

    await msg.reply_text(
        f"✅ Готово! Заявки из группы *{chat.title}* "
        f"будут отправляться в этот подчат.",
        parse_mode="Markdown",
    )
    logger.info("Setup: группа %s (%s) → подчат %s", chat.title, chat.id, thread_id)


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

    incident_id = get_next_id(data["gym"])
    summary = build_summary(data, incident_id)
    media = data.get("media", [])

    # 1. Постим карточку в группу
    group_id = data.get("group_id")
    if group_id:
        thread_id = get_thread_id(group_id)
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text=summary,
                parse_mode="Markdown",
                message_thread_id=thread_id,
            )
            await post_media_to_chat(context.bot, group_id, media, thread_id)
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

    # 3. Определяем название чата-источника
    source_chat = "-"
    if group_id:
        try:
            chat_info = await context.bot.get_chat(group_id)
            source_chat = chat_info.title or str(group_id)
        except Exception:
            source_chat = str(group_id)

    # 4. Записываем в Google Sheets
    try:
        append_incident(data["gym"], {
            "id": incident_id,
            "datetime": data["datetime"],
            "reporter": data["reporter"],
            "category": data["category"],
            "description": data["description"],
            "location": data.get("location", ""),
            "source_chat": source_chat,
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
            pass


# ── Запуск ─────────────────────────────────────────────────────────

def main():
    # Загружаем настройки подчатов из Google Sheets при старте
    global _thread_config
    try:
        _thread_config = get_config()
        logger.info("Загружены настройки подчатов: %s", _thread_config)
    except Exception as e:
        logger.warning("Не удалось загрузить настройки подчатов: %s", e)

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
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(conv)

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
