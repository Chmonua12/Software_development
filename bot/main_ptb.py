from __future__ import annotations

import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.feed_cache import (
    invalidate,
    pop_next_id,
    publish_interaction_event,
    refill_if_needed,
)
from bot.rating import ensure_rating, recompute_for_profile
from bot.storage import UserStorage


logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "bot.sqlite3"
storage = UserStorage(DB_PATH)

(
    PROFILE_NAME,
    PROFILE_AGE,
    PROFILE_GENDER,
    PROFILE_CITY,
    PROFILE_BIO,
    PROFILE_INTERESTS,
    PREF_GENDER,
    PREF_AGE,
) = range(8)

DELETE_ASK, DELETE_CONFIRM = 100, 101
(EDIT_BIO, EDIT_INTERESTS, EDIT_CITY) = 200, 201, 202


def _get_viewer_profile(update: Update):
    if update.effective_user is None:
        return None
    return storage.get_profile_by_telegram_id(update.effective_user.id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    tg_user = update.effective_user
    user, created = storage.register_or_update_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )

    if created:
        text = (
            "Привет! Я зарегистрировал тебя в системе.\n\n"
            f"Твой Telegram ID: `{user.telegram_id}`\n"
            "Давай заполним анкету (этап 3: ранжирование и лента)."
        )
    else:
        text = (
            "С возвращением! Данные обновлены.\n\n"
            f"Твой Telegram ID: `{user.telegram_id}`\n"
            "Заполни анкету"
        )

    await update.message.reply_text(text=text, parse_mode="Markdown")
    await update.message.reply_text("Как тебя зовут?")
    context.user_data["registered_user_id"] = user.id
    return PROFILE_NAME


async def profile_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_NAME
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Имя слишком короткое. Введи имя еще раз.")
        return PROFILE_NAME
    context.user_data["profile_name"] = name
    await update.message.reply_text("Сколько тебе лет?")
    return PROFILE_AGE


async def profile_age_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_AGE
    age_raw = update.message.text.strip()
    if not age_raw.isdigit():
        await update.message.reply_text("Возраст должен быть числом. Попробуй еще раз.")
        return PROFILE_AGE
    age = int(age_raw)
    if age < 18 or age > 99:
        await update.message.reply_text("Допустимый возраст: 18-99. Попробуй еще раз.")
        return PROFILE_AGE
    context.user_data["profile_age"] = age
    await update.message.reply_text("Укажи пол: м / ж")
    return PROFILE_GENDER


async def profile_gender_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_GENDER
    gender_raw = update.message.text.strip().lower()
    allowed = {"м": "male", "ж": "female", "male": "male", "female": "female"}
    if gender_raw not in allowed:
        await update.message.reply_text("Можно указать только: м или ж.")
        return PROFILE_GENDER
    context.user_data["profile_gender"] = allowed[gender_raw]
    await update.message.reply_text("Из какого ты города?")
    return PROFILE_CITY


async def profile_city_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_CITY
    city = update.message.text.strip()
    if len(city) < 2:
        await update.message.reply_text("Город слишком короткий. Попробуй еще раз.")
        return PROFILE_CITY
    context.user_data["profile_city"] = city
    await update.message.reply_text(
        "Коротко о себе (1–2 предложения). Можно пропустить, отправь «-»."
    )
    return PROFILE_BIO


async def profile_bio_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_BIO
    t = update.message.text.strip()
    if t == "-":
        context.user_data["profile_bio"] = ""
    else:
        context.user_data["profile_bio"] = t
    await update.message.reply_text("Интересы через запятую. Пропустить: «-»")
    return PROFILE_INTERESTS


async def profile_interests_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PROFILE_INTERESTS
    t = update.message.text.strip()
    if t == "-":
        context.user_data["profile_interests"] = ""
    else:
        context.user_data["profile_interests"] = t
    await update.message.reply_text("Кого ищешь: м / ж / все (любой пол)")
    return PREF_GENDER


async def pref_gender_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PREF_GENDER
    raw = update.message.text.strip().lower()
    m = {
        "м": "male",
        "ж": "female",
        "все": "any",
        "all": "any",
        "any": "any",
        "всё": "any",
    }
    if raw not in m:
        await update.message.reply_text("Варианты: м / ж / все")
        return PREF_GENDER
    context.user_data["pref_gender"] = m[raw]
    await update.message.reply_text("Возраст партнёра: «от-до», например 20-32. Пропустить: «-» (будет 18-99).")
    return PREF_AGE


async def pref_age_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return PREF_AGE
    t = update.message.text.strip()
    if t == "-":
        amin, amax = 18, 99
    else:
        if "-" in t:
            a, b = t.split("-", 1)
            a, b = a.strip(), b.strip()
            if not a.isdigit() or not b.isdigit():
                await update.message.reply_text("Формат: 20-30 или «-»")
                return PREF_AGE
            amin, amax = int(a), int(b)
        else:
            await update.message.reply_text("Нужен диапазон, например 20-32")
            return PREF_AGE
        if amin > amax or amin < 18 or amax > 99:
            await update.message.reply_text("Проверь границы: 18-99, слева меньше")
            return PREF_AGE
    context.user_data["age_min"] = amin
    context.user_data["age_max"] = amax

    user_id = context.user_data.get("registered_user_id")
    if user_id is None:
        await update.message.reply_text("Сессия сброшена. /start")
        return ConversationHandler.END
    d = context.user_data
    profile = storage.save_profile(
        user_id=user_id,
        name=d["profile_name"],
        age=d["profile_age"],
        gender=d["profile_gender"],
        city=d["profile_city"],
        bio=d.get("profile_bio", ""),
        interests=d.get("profile_interests", ""),
        preferred_gender=d.get("pref_gender", "any"),
        age_min=amin,
        age_max=amax,
        photo_count=0,
    )
    recompute_for_profile(storage, profile)
    await update.message.reply_text(
        "Анкета сохранена! Первичный и комбинированный рейтинг пересчитаны.\n"
        f"Имя: {profile.name}, {profile.age}, {profile.city}\n"
        f"Про себя: {profile.bio or '—'}\n"
        f"Интересы: {profile.interests or '—'}\n\n"
        "Команды: /profile — просмотр, /feed — лента, /edit — правки, /delete — удалить анкету."
    )
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено. Используй /start для начала.")
    return ConversationHandler.END


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer = _get_viewer_profile(update)
    if not viewer:
        await update.message.reply_text("Сначала создай анкету: /start")
        return
    rating = ensure_rating(storage, viewer)
    await update.message.reply_text(
        f"👤 *Твоя анкета*\n\n"
        f"📍 {viewer.name}, {viewer.age}, {viewer.city}\n"
        f"🔍 {viewer.gender} | Ищу: {viewer.preferred_gender} ({viewer.age_min}-{viewer.age_max})\n"
        f"📝 {viewer.bio or '—'}\n"
        f"🏷 {viewer.interests or '—'}\n\n"
        f"⭐ Рейтинг: {rating.combined_rating:.2f} (первичный: {rating.primary_rating:.2f}, "
        f"поведенческий: {rating.behavior_rating:.2f})\n"
        f"❤️ {rating.likes_in} лайков | 🚫 {rating.skips_in} пропусков | 🎯 {rating.matches_in} мэтчей",
        parse_mode="Markdown",
    )


async def feed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer = _get_viewer_profile(update)
    if not viewer:
        await update.message.reply_text("Сначала создай анкету: /start")
        return
    refill_if_needed(storage, viewer)
    await _send_next_profile(update, viewer)


async def _send_next_profile(update: Update, viewer):
    next_id = pop_next_id(viewer.id)
    if not next_id:
        await update.message.reply_text("Анкеты закончились. Попробуй позже!")
        return
    target = storage.get_profile_by_id(next_id)
    if not target:
        await feed_command(update, None)  
        return
    rating = ensure_rating(storage, target)
    text = (
        f"👤 {target.name}, {target.age}, {target.city}\n"
        f"📝 {target.bio or '—'}\n"
        f"🏷 {target.interests or '—'}\n\n"
        f"⭐ Рейтинг: {rating.combined_rating:.2f}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️", callback_data=f"like_{target.id}"),
         InlineKeyboardButton("🚫", callback_data=f"skip_{target.id}")],
    ])
    await update.message.reply_photo(
        photo="https://picsum.photos/400/600?random=" + str(target.id),
        caption=text,
        reply_markup=keyboard,
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    viewer = _get_viewer_profile(update)
    if not viewer:
        await query.edit_message_text("Сессия устарела. /start")
        return
    action, target_id_str = query.data.split("_", 1)
    target_id = int(target_id_str)
    target = storage.get_profile_by_id(target_id)
    if not target:
        await query.edit_message_text("Анкета недоступна.")
        return
    is_like = action == "like"
    interaction = storage.save_interaction(viewer.id, target_id, is_like)
    publish_interaction_event(interaction)
    recompute_for_profile(storage, viewer)
    recompute_for_profile(storage, target)
    if is_like and storage.is_mutual_like(viewer.id, target_id):
        storage.create_match(viewer.id, target_id)
        await query.edit_message_text(
            f"**Мэтч!**\n\nУ тебя мэтч с {target.name}, {target.age}!\n"
            f" {target.bio or '—'}\n\n"
            "Теперь вы можете общаться!",
            parse_mode="Markdown",
        )
    else:
        await _send_next_profile(update, viewer)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_name_step)],
            PROFILE_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_age_step)],
            PROFILE_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_gender_step)],
            PROFILE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_city_step)],
            PROFILE_BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_bio_step)],
            PROFILE_INTERESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_interests_step)],
            PREF_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, pref_gender_step)],
            PREF_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pref_age_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("feed", feed_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.run_polling()


if __name__ == "__main__":
    main()
