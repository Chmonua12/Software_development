from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from bot.feed import FeedService
from bot.feed_cache import get_cached_top, invalidate, publish_interaction_event, refresh_top_cache
from bot.metrics import active_users, get_metrics, log_interaction, update_rating_metric
from bot.minio_client import minio_client
from bot.rating import ensure_rating, recompute_all, recompute_for_profile
from bot.storage import Profile, SocialLink, UserStorage

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "bot.sqlite3"
ADMIN_IDS = {
    int(x)
    for x in os.getenv("ADMIN_TELEGRAM_IDS", "123456789").split(",")
    if x.strip().isdigit()
}

storage = UserStorage(DB_PATH)
feed_service = FeedService()
router = Router()


class RegistrationState(StatesGroup):
    name = State()
    age = State()
    city = State()
    bio = State()
    avatar = State()
    artworks = State()
    interests = State()
    social_platform = State()
    social_url = State()
    add_another_social = State()


class EditState(StatesGroup):
    field = State()
    value = State()


PLATFORMS = {
    "telegram": "Telegram",
    "instagram": "Instagram",
    "vk": "VK",
    "behance": "Behance",
    "other": "Другая",
}


def _social_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in PLATFORMS.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"social:{key}"))
    return builder.as_markup()


def _social_url_pattern(platform: str) -> str | None:
    patterns = {
        "telegram": r"^https?://t\.me/",
        "instagram": r"^https?://(www\.)?instagram\.com/",
        "vk": r"^https?://(www\.)?vk\.com/",
        "behance": r"^https?://(www\.)?behance\.net/",
    }
    return patterns.get(platform)


def _profile_caption(profile: Profile) -> str:
    interests = storage.get_interests_by_profile_id(profile.id)
    rating = ensure_rating(storage, profile)
    lines = [
        f"*{profile.display_name}*, {profile.age}, {profile.city}",
        profile.bio or "Без описания",
    ]
    if interests:
        lines.append(f"Направления: {', '.join(interests)}")
    lines.append(
        f"Рейтинг: {rating.combined_rating:.0%} "
        f"(анкета {rating.primary_rating:.0%}, активность {rating.behavior_rating:.0%})"
    )
    return "\n".join(lines)


def _profile_keyboard(profile_id: int, socials: list[SocialLink] | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Лайк для общения", callback_data=f"like:communication:{profile_id}"),
            InlineKeyboardButton(text="В избранное", callback_data=f"like:favorite:{profile_id}"),
        ],
        [InlineKeyboardButton(text="Пропустить", callback_data=f"like:skip:{profile_id}")],
    ]
    for link in socials or []:
        rows.append([InlineKeyboardButton(text=f"Открыть {PLATFORMS.get(link.platform, link.platform)}", callback_data=f"social_click:{link.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _answer_profile(message: Message, profile: Profile, with_actions: bool = False) -> None:
    photos = storage.get_photos_by_profile_id(profile.id)
    socials = storage.get_social_links_by_profile_id(profile.id)
    caption = _profile_caption(profile)
    markup = _profile_keyboard(profile.id, socials) if with_actions else _socials_only_keyboard(socials)
    valid_photos = [p for p in photos if p.file_id]
    if valid_photos and not with_actions:
        media_group = []
        for idx, photo in enumerate(valid_photos[:5]):
            media_group.append(
                InputMediaPhoto(
                    media=photo.file_id,
                    caption=caption if idx == 0 else None,
                    parse_mode="Markdown",
                )
            )
        await message.answer_media_group(media_group)
        if socials:
            await message.answer("Ссылки художника:", reply_markup=markup)
    elif valid_photos:
        await message.answer_photo(
            valid_photos[0].file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    else:
        await message.answer(caption, parse_mode="Markdown", reply_markup=markup)


def _socials_only_keyboard(socials: list[SocialLink]) -> InlineKeyboardMarkup | None:
    if not socials:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Открыть {PLATFORMS.get(s.platform, s.platform)}", callback_data=f"social_click:{s.id}")]
            for s in socials
        ]
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "*ArtConnect* — бот для арт-комьюнити.\n\n"
        "/start — регистрация или обновление анкеты\n"
        "/profile — моя анкета\n"
        "/edit — изменить анкету\n"
        "/delete — скрыть анкету\n"
        "/feed — лента художников\n"
        "/favorites — избранные анкеты\n"
        "/top — топ-10 художников\n"
        "/recalc — пересчёт рейтингов\n"
        "/metrics — метрики\n"
        "/cancel — отмена действия",
        parse_mode="Markdown",
    )


@router.message(Command("profile"))
async def profile_command(message: Message) -> None:
    if message.from_user is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Анкета пока не заполнена. Нажми /start.")
        return
    await _answer_profile(message, profile)


@router.message(Command("feed"))
async def feed_command(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    viewer = storage.get_profile_by_telegram_id(message.from_user.id)
    if viewer is None:
        await message.answer("Сначала заполни анкету через /start.")
        return
    active_users.inc()
    try:
        target = await feed_service.get_next_profile(storage, viewer.id)
    finally:
        active_users.dec()
    if target is None:
        await message.answer("Пока нет других анкет. Попробуй позже или пригласи друзей.")
        return
    await _answer_profile(message, target, with_actions=True)


@router.message(Command("top"))
async def top_command(message: Message) -> None:
    refresh_top_cache(storage)
    cached = get_cached_top()
    rows = storage.get_top_profiles(limit=10)
    if not rows:
        await message.answer("Нет данных для топа. Нужны заполненные анкеты и рейтинги.")
        return
    medals = ["1.", "2.", "3."]
    lines = ["*Топ-10 художников ArtConnect*\n"]
    for idx, (profile, rating) in enumerate(rows):
        prefix = medals[idx] if idx < 3 else f"{idx + 1}."
        lines.append(
            f"{prefix} *{profile.display_name}*, {profile.age}, {profile.city} — "
            f"{rating.combined_rating:.0%}, лайков: {rating.likes_count}, переходов: {rating.link_clicks_count}"
        )
        update_rating_metric(profile.id, rating.combined_rating, profile.display_name)
    if cached is not None:
        lines.append("\nКэш топа обновлён в Redis/in-memory на 5 минут.")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("favorites"))
async def favorites_command(message: Message) -> None:
    if message.from_user is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Сначала заполни анкету через /start.")
        return
    with storage._connect() as conn:
        rows = conn.execute(
            """SELECT p.* FROM profile_favorites f
               JOIN profiles p ON p.id = f.favorite_profile_id
               WHERE f.profile_id = ? AND p.deleted_at IS NULL
               ORDER BY f.created_at DESC
               LIMIT 10""",
            (profile.id,),
        ).fetchall()
    if not rows:
        await message.answer("Избранное пока пустое.")
        return
    lines = ["*Избранные художники*\n"]
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}. {row['display_name']}, {row['age']}, {row['city']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("recalc"))
async def recalc_command(message: Message) -> None:
    if message.from_user is None:
        return
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Пересчёт рейтингов доступен администратору.")
        return
    count = recompute_all(storage)
    await message.answer(f"Готово: пересчитано анкет — {count}.")


@router.message(Command("metrics"))
async def metrics_command(message: Message) -> None:
    if message.from_user is None:
        return
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Метрики доступны администратору.")
        return
    metrics_data = get_metrics().decode("utf-8")[:3900]
    await message.answer(f"```\n{metrics_data}\n```", parse_mode="Markdown")


@router.message(Command("delete"))
async def delete_command(message: Message) -> None:
    if message.from_user is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Активной анкеты нет.")
        return
    storage.soft_delete_profile(profile.id)
    invalidate(profile.id)
    await message.answer("Анкета скрыта из ленты. Вернуть её можно через /start.")


@router.message(Command("edit"))
async def edit_command(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Сначала создай анкету через /start.")
        return
    await state.set_state(EditState.field)
    await message.answer(
        "Что изменить?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Имя", callback_data="edit:name"), InlineKeyboardButton(text="Город", callback_data="edit:city")],
                [InlineKeyboardButton(text="Описание", callback_data="edit:bio"), InlineKeyboardButton(text="Интересы", callback_data="edit:interests")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("edit:"))
async def edit_field_callback(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]
    await state.set_data({"edit_field": field})
    await state.set_state(EditState.value)
    prompts = {
        "name": "Введи новое имя или псевдоним.",
        "city": "Введи новый город.",
        "bio": "Введи новое описание творчества.",
        "interests": "Введи интересы через запятую.",
    }
    if callback.message:
        await callback.message.answer(prompts.get(field, "Введи новое значение."))
    await callback.answer()


@router.message(EditState.value)
async def edit_value_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Анкета не найдена.")
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("edit_field")
    value = message.text.strip()
    if field == "name":
        storage.update_profile_fields(profile.id, display_name=value)
    elif field == "city":
        storage.update_profile_fields(profile.id, city=value)
    elif field == "bio":
        storage.update_profile_fields(profile.id, bio=value)
    elif field == "interests":
        tags = [t.strip() for t in value.split(",") if t.strip()]
        storage.replace_interests(profile.id, tags)
    updated = storage.get_profile_by_id(profile.id)
    if updated:
        recompute_for_profile(storage, updated)
    invalidate(profile.id)
    await state.clear()
    await message.answer("Готово, анкета обновлена.")


@router.callback_query(F.data.startswith("like:"))
async def handle_interaction(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        return
    _, action, raw_target = callback.data.split(":", 2)
    target_id = int(raw_target)
    viewer = storage.get_profile_by_telegram_id(callback.from_user.id)
    target = storage.get_profile_by_id(target_id)
    if viewer is None or target is None:
        await callback.answer("Анкета недоступна", show_alert=True)
        return

    created, mutual, _ = storage.add_interaction(viewer.id, target.id, action)
    if not created:
        await callback.answer("Ты уже оценил(а) эту анкету", show_alert=True)
        return

    event_map = {
        "communication": "profile_liked",
        "favorite": "profile_favorited",
        "skip": "profile_skipped",
    }
    publish_interaction_event(storage, event_map[action], viewer.id, target.id)
    log_interaction(action, viewer.id, target.id)
    recompute_for_profile(storage, target)
    invalidate(viewer.id)
    await callback.message.edit_reply_markup(reply_markup=None)

    if action == "communication" and mutual:
        await callback.message.answer(f"Это взаимно! Новый мэтч с {target.display_name}.")
        storage.record_event("match_created", viewer.id, target.id)
    elif action == "communication":
        await callback.message.answer(f"Лайк для общения отправлен: {target.display_name}.")
    elif action == "favorite":
        await callback.message.answer(f"{target.display_name} добавлен(а) в избранное.")
    else:
        await callback.message.answer("Пропущено.")
    await callback.answer()
    await feed_command(callback.message, state)


@router.callback_query(F.data.startswith("social_click:"))
async def social_click_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        return
    viewer = storage.get_profile_by_telegram_id(callback.from_user.id)
    if viewer is None:
        await callback.answer("Сначала заполни анкету", show_alert=True)
        return
    link_id = int(callback.data.split(":", 1)[1])
    link = storage.record_social_click(viewer.id, link_id)
    if link is None:
        await callback.answer("Ссылка недоступна", show_alert=True)
        return
    target = storage.get_profile_by_id(link.profile_id)
    if target:
        recompute_for_profile(storage, target)
    await callback.message.answer(f"{PLATFORMS.get(link.platform, link.platform)}: {link.url}")
    await callback.answer()


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, отменено. /start — начать заново.", reply_markup=ReplyKeyboardRemove())


@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: Message, state: FSMContext) -> None:
    referral_code = None
    if message.text:
        args = message.text.split(maxsplit=1)
        referral_code = args[1] if len(args) > 1 else None
    await _start_registration(message, state, referral_code)


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext) -> None:
    await _start_registration(message, state, None)


async def _start_registration(message: Message, state: FSMContext, referral_code: str | None) -> None:
    if message.from_user is None:
        return
    tg_user = message.from_user
    user, created = storage.register_or_update_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    if created and referral_code:
        with storage._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE referral_code = ?", (referral_code,)).fetchone()
            if row:
                inviter_profile = conn.execute("SELECT id FROM profiles WHERE user_id = ?", (row["id"],)).fetchone()
                if inviter_profile:
                    storage.record_referral(inviter_profile["id"], user.id)
    bot_username = (await message.bot.get_me()).username or "artconnect_bot"
    await state.set_data({"registered_user_id": user.id})
    await message.answer(
        f"{'Привет' if created else 'С возвращением'}! Заполним анкету художника.\n"
        f"Твоя реферальная ссылка: https://t.me/{bot_username}?start={user.referral_code}"
    )
    await message.answer("Как тебя зовут? Имя или творческий псевдоним.")
    await state.set_state(RegistrationState.name)


@router.message(RegistrationState.name)
async def process_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введи ещё раз.")
        return
    data = await state.get_data()
    data["profile_name"] = name
    await state.set_data(data)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegistrationState.age)


@router.message(RegistrationState.age)
async def process_age(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Возраст должен быть числом.")
        return
    age = int(message.text.strip())
    if age < 18 or age > 99:
        await message.answer("Допустимый возраст: 18-99.")
        return
    data = await state.get_data()
    data["profile_age"] = age
    await state.set_data(data)
    await message.answer("Из какого ты города?")
    await state.set_state(RegistrationState.city)


@router.message(RegistrationState.city)
async def process_city(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    city = message.text.strip()
    if len(city) < 2:
        await message.answer("Город слишком короткий.")
        return
    data = await state.get_data()
    data["profile_city"] = city
    await state.set_data(data)
    await message.answer("Расскажи о своём творчестве. Можно отправить «-».")
    await state.set_state(RegistrationState.bio)


@router.message(RegistrationState.bio)
async def process_bio(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    bio = message.text.strip()
    data = await state.get_data()
    data["profile_bio"] = None if bio == "-" else bio
    await state.set_data(data)
    await message.answer("Отправь аватарку. Если хочешь пропустить, отправь «-».")
    await state.set_state(RegistrationState.avatar)


@router.message(RegistrationState.avatar, F.photo)
async def process_avatar(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    data["avatar_file_id"] = message.photo[-1].file_id
    await state.set_data(data)
    await message.answer("Аватарка принята. Отправь до 5 работ или «-» для перехода дальше.")
    await state.set_state(RegistrationState.artworks)


@router.message(RegistrationState.avatar)
async def process_avatar_skip(message: Message, state: FSMContext) -> None:
    await message.answer("Ок, без аватарки. Теперь отправь до 5 работ или «-».")
    await state.set_state(RegistrationState.artworks)


@router.message(RegistrationState.artworks, F.photo)
async def process_artwork(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    artworks = data.get("artwork_file_ids", [])
    artworks.append(message.photo[-1].file_id)
    data["artwork_file_ids"] = artworks
    await state.set_data(data)
    if len(artworks) >= 5:
        await message.answer("Максимум 5 работ. Переходим к интересам.")
        await _ask_interests(message, state)
    else:
        await message.answer(f"Принято {len(artworks)} из 5. Отправь ещё работу или «-».")


@router.message(RegistrationState.artworks)
async def process_artwork_done(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "-":
        await _ask_interests(message, state)
    else:
        await message.answer("Отправь фото работы или «-».")


async def _ask_interests(message: Message, state: FSMContext) -> None:
    await message.answer("Какие направления тебе близки? Напиши через запятую или «-».")
    await state.set_state(RegistrationState.interests)


@router.message(RegistrationState.interests)
async def process_interests(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    raw = message.text.strip()
    tags = [] if raw == "-" else [t.strip() for t in raw.split(",") if t.strip()]
    data = await state.get_data()
    data["profile_interests"] = tags
    await state.set_data(data)
    await message.answer("Выбери основную соцсеть:", reply_markup=_social_keyboard())
    await state.set_state(RegistrationState.social_platform)


@router.callback_query(F.data.startswith("social:"))
async def process_social_platform(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    platform = callback.data.split(":", 1)[1]
    data = await state.get_data()
    data["social_platform"] = platform
    await state.set_data(data)
    await callback.message.answer(f"Введи ссылку на {PLATFORMS.get(platform, platform)}.")
    await state.set_state(RegistrationState.social_url)
    await callback.answer()


@router.message(RegistrationState.social_url)
async def process_social_url(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    url = message.text.strip()
    data = await state.get_data()
    platform = data.get("social_platform", "telegram")
    pattern = _social_url_pattern(platform)
    if pattern and not re.match(pattern, url, re.IGNORECASE):
        await message.answer(f"Ссылка не похожа на {PLATFORMS.get(platform, platform)}.")
        return
    data["socials"] = data.get("socials", []) + [{"platform": platform, "url": url}]
    await state.set_data(data)
    await message.answer(
        "Добавить ещё соцсеть?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Да", callback_data="add_social:yes"), InlineKeyboardButton(text="Завершить", callback_data="add_social:no")]
            ]
        ),
    )
    await state.set_state(RegistrationState.add_another_social)


@router.callback_query(F.data.startswith("add_social:"))
async def process_add_social(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        return
    choice = callback.data.split(":", 1)[1]
    if choice == "yes":
        await callback.message.answer("Выбери платформу:", reply_markup=_social_keyboard())
        await state.set_state(RegistrationState.social_platform)
    else:
        await _finalize_registration(callback.message, state)
    await callback.answer()


async def _maybe_upload_file(bot: Bot, profile_id: int, file_id: str, prefix: str) -> str | None:
    if not minio_client.enabled:
        return None
    buffer = io.BytesIO()
    await bot.download(file_id, destination=buffer)
    return await minio_client.upload_photo(profile_id, buffer.getvalue(), f"{prefix}.jpg")


async def _finalize_registration(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = data.get("registered_user_id")
    if user_id is None:
        await message.answer("Сессия устарела. Нажми /start.")
        await state.clear()
        return

    profile = storage.save_profile(
        user_id=user_id,
        display_name=data.get("profile_name", ""),
        age=data.get("profile_age", 18),
        city=data.get("profile_city", ""),
        bio=data.get("profile_bio"),
    )

    avatar_file_id = data.get("avatar_file_id")
    if avatar_file_id:
        url = await _maybe_upload_file(message.bot, profile.id, avatar_file_id, "avatar")
        storage.add_photo(profile.id, f"avatars/{profile.id}_avatar.jpg", avatar_file_id, True, url)

    for idx, file_id in enumerate(data.get("artwork_file_ids", [])):
        url = await _maybe_upload_file(message.bot, profile.id, file_id, f"artwork_{idx}")
        storage.add_photo(profile.id, f"artworks/{profile.id}_{idx}.jpg", file_id, False, url)

    for tag in data.get("profile_interests", []):
        storage.add_interest(profile.id, tag)

    for idx, social in enumerate(data.get("socials", [])):
        storage.add_social_link(
            profile.id,
            social["platform"],
            social["url"],
            is_primary=(idx == 0),
        )

    storage.init_rating(profile.id)
    recompute_for_profile(storage, profile)
    await message.answer(
        "Анкета готова. Теперь доступны /feed, /profile, /top и /favorites.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()


def get_bot_token() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")
    return token


def main() -> None:
    token = get_bot_token()
    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("ArtConnect bot started")
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
