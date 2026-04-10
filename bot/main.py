from __future__ import annotations
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.storage import UserStorage
from bot.feed import FeedService

logger = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "bot.sqlite3"
storage = UserStorage(DB_PATH)
feed_service = FeedService()

router = Router()


# ── States ──────────────────────────────────────────────────────
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


# ── Helpers ─────────────────────────────────────────────────────
PLATFORMS = {
    "telegram": "Telegram",
    "instagram": "Instagram",
    "vk": "VK",
    "behance": "Behance",
    "other": "Другая",
}

VALID_URL_RE = re.compile(r"^https?://.+\..+")


def _social_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in PLATFORMS.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"social:{key}"))
    return builder.as_markup()


def _social_url(platform: str) -> str | None:
    patterns = {
        "telegram": r"^https?://t\.me/",
        "instagram": r"^https?://(www\.)?instagram\.com/",
        "vk": r"^https?://(www\.)?vk\.com/",
        "behance": r"^https?://(www\.)?behance\.net/",
    }
    pat = patterns.get(platform)
    if pat:
        return pat
    return None


# ── Handlers ────────────────────────────────────────────────────

# ── Command handlers (must be above state handlers) ─────────────
@router.message(Command("profile"))
async def profile_command(message: Message) -> None:
    if message.from_user is None:
        return
    profile = storage.get_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("Анкета пока не заполнена. Нажми /start.")
        return
    photos = storage.get_photos_by_profile_id(profile.id)
    socials = storage.get_social_links_by_profile_id(profile.id)
    interests = storage.get_interests_by_profile_id(profile.id)

    lines = [
        f"₍^. .^₎Ⳋ*{profile.display_name}*, {profile.age}, {profile.city}",
        profile.bio or "—",
    ]
    if interests:
        lines.append(f"Направления: {', '.join(interests)}")
    if socials:
        links = "\n".join(f"[{s.platform}]({s.url})" for s in socials)
        lines.append(f"\nСоцсети:\n{links}")

    caption = "\n".join(lines)
    valid_photos = [p for p in photos if p.file_id]

    if valid_photos:
        media_group = []
        for idx, photo in enumerate(valid_photos):
            if idx == 0:
                media_group.append(
                    InputMediaPhoto(
                        media=photo.file_id,
                        caption=caption,
                        parse_mode="Markdown",
                    )
                )
            else:
                media_group.append(
                    InputMediaPhoto(media=photo.file_id)
                )
        await message.answer_media_group(media=media_group)
    else:
        await message.answer(caption, parse_mode="Markdown")


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await message.answer("Ок, отменил заполнение. Нажми /start для нового старта.")
    await state.clear()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "❣*ArtConnect* - бот для арт-комьюнити.\n\n"
        "Команды:\n"
        "/start — регистрация и заполнение анкеты\n"
        "/profile — показать свою анкету\n"
        "/feed — лента художников (не рабоч)\n"
        "/top — топ-10 по рейтингу(не рабоч)\n"
        "/cancel — отменить заполнение(не рабоч)\n"
        "/help — справка(не рабоч)",
        parse_mode="Markdown",
    )


# ── Registration handlers ──────────────────────────────────────
@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: Message, state: FSMContext) -> None:
    """Handle /start with referral code from deep link."""
    if message.from_user is None:
        return
    args = message.text.split(maxsplit=1)
    referral_code = args[1] if len(args) > 1 else None

    tg_user = message.from_user
    user, created = storage.register_or_update_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )

    # Check if this user was referred by someone
    if created and referral_code:
        inviter = None
        with storage._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE referral_code = ?", (referral_code,),
            ).fetchone()
            if row:
                inviter = row["id"]
                user_id = user.id
                # Get inviter's profile_id
                prof = conn.execute(
                    "SELECT id FROM profiles WHERE user_id = ?", (inviter,),
                ).fetchone()
                if prof:
                    storage.record_referral(prof["id"], user_id)

    await _start_common(message, state, user, created)


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    tg_user = message.from_user
    user, created = storage.register_or_update_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    await _start_common(message, state, user, created)


async def _start_common(
    message: Message, state: FSMContext, user, created: bool
) -> None:
    tg_user = message.from_user
    if created:
        text = (
            f"Привет, {tg_user.first_name or 'художник'}! \n"
            "Я зарегистрировал тебя в ArtConnect.\n\n"
            f"Твой Telegram ID: `{user.telegram_id}`\n"
            f"Реферальная ссылка: `https://t.me/{tg_user.username or 'artconnect_bot'}?start={user.referral_code}`\n\n"
            "Давай заполним анкету!"
        )
    else:
        text = (
            "С возвращением в ArtConnect\n\n"
            f"Твой Telegram ID: `{user.telegram_id}`\n"
            "Можно обновить анкету заново."
        )
    await message.answer(text, parse_mode="Markdown")
    await state.set_data({"registered_user_id": user.id})
    await message.answer("Как тебя зовут? (имя или псевдоним)")
    await state.set_state(RegistrationState.name)


@router.message(RegistrationState.name)
async def process_name(message: Message, state: FSMContext) -> None:
    if message.text is None:
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
    if message.text is None:
        return
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Возраст должен быть числом. Попробуй ещё раз.")
        return
    age = int(raw)
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
    if message.text is None:
        return
    city = message.text.strip()
    if len(city) < 2:
        await message.answer("Город слишком короткий. Попробуй ещё раз.")
        return
    data = await state.get_data()
    data["profile_city"] = city
    await state.set_data(data)
    await message.answer(
        "Расскажи немного о своём творчестве.\n"
        "Можно пропустить, отправив «-»."
    )
    await state.set_state(RegistrationState.bio)


@router.message(RegistrationState.bio)
async def process_bio(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    bio = message.text.strip()
    if bio == "-":
        bio = None
    data = await state.get_data()
    data["profile_bio"] = bio
    await state.set_data(data)
    await message.answer("Отправь аватарку (фото).")
    await state.set_state(RegistrationState.avatar)


@router.message(RegistrationState.avatar, F.photo)
async def process_avatar(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    data["avatar_file_id"] = file_id
    await state.set_data(data)
    await message.answer(
        "Аватарка принята! 📸\n\n"
        "Отправь до 3 фотографий своих работ.\n"
        "Отправь «-» чтобы пропустить."
    )
    await state.set_state(RegistrationState.artworks)


@router.message(RegistrationState.avatar)
async def process_avatar_skip(message: Message, state: FSMContext) -> None:
    await message.answer("Без аватарки анкета менее заметна. Введи /start, если передумал.")
    data = await state.get_data()
    await _after_artworks(message, state, data)


@router.message(RegistrationState.artworks, F.photo)
async def process_artworks(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    artworks = data.get("artwork_file_ids", [])
    artworks.append(message.photo[-1].file_id)
    if len(artworks) >= 3:
        data["artwork_file_ids"] = artworks
        await state.set_data(data)
        await message.answer("Максимум 3 работы. Переходим к интересам.")
        await _after_artworks(message, state, data)
        return
    data["artwork_file_ids"] = artworks
    await state.set_data(data)
    await message.answer(
        f"Принято {len(artworks)} из 3. Отправь ещё или «-» чтобы закончить."
    )


@router.message(RegistrationState.artworks)
async def process_artworks_done(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "-":
        data = await state.get_data()
        await message.answer("Хорошо, переходим к интересам.")
        await _after_artworks(message, state, data)
        return
    await message.answer("Отправь фото работы или «-» для завершения.")


async def _after_artworks(message: Message, state: FSMContext, data: dict) -> None:
    await message.answer(
        "Какие направления искусства тебе близки?\n"
        "Напиши через запятую (живопись, digital, скульптура…)\n"
        "Или отправь «-» чтобы пропустить."
    )
    await state.set_state(RegistrationState.interests)


async def process_no_photo(message: Message, state: FSMContext) -> None:
    await _after_artworks(message, state, await state.get_data())


@router.message(RegistrationState.artworks, ~F.photo)
async def process_artworks_not_photo(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "-":
        await process_artworks_done(message, state)
    else:
        await message.answer("Отправь фото работы или «-» для завершения.")


@router.message(RegistrationState.interests)
async def process_interests(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()
    if text == "-":
        tags = []
    else:
        tags = [t.strip() for t in text.split(",") if t.strip()]
    data = await state.get_data()
    data["profile_interests"] = tags
    await state.set_data(data)
    await message.answer(
        "Выбери основную соцсеть:",
        reply_markup=_social_keyboard(),
    )
    await state.set_state(RegistrationState.social_platform)


@router.callback_query(F.data.startswith("social:"))
async def process_social_platform(
    callback, state: FSMContext
) -> None:
    if callback.message is None:
        return
    platform = callback.data.split(":", 1)[1]
    data = await state.get_data()
    data["social_platform"] = platform
    await state.set_data(data)
    platform_label = PLATFORMS.get(platform, platform)
    await callback.message.answer(
        f"Введи ссылку на {platform_label}:\n"
        f"Например: https://t.me/username"
    )
    await state.set_state(RegistrationState.social_url)
    await callback.answer()


@router.message(RegistrationState.social_url)
async def process_social_url(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    url = message.text.strip()
    data = await state.get_data()
    platform = data.get("social_platform", "telegram")
    pattern = _social_url(platform)
    if pattern and not re.match(pattern, url, re.IGNORECASE):
        await message.answer(
            f"Ссылка не похожа на {PLATFORMS.get(platform, platform)}. Попробуй ещё раз."
        )
        return
    data["socials"] = data.get("socials", []) + [{"platform": platform, "url": url}]
    await state.set_data(data)
    await message.answer(
        "Добавить ещё одну соцсеть?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="add_social:yes"),
                    InlineKeyboardButton(text="Нет, завершить", callback_data="add_social:no"),
                ]
            ]
        ),
    )
    await state.set_state(RegistrationState.add_another_social)


@router.callback_query(F.data.startswith("add_social:"))
async def process_add_another_social(callback, state: FSMContext) -> None:
    if callback.message is None:
        return
    choice = callback.data.split(":", 1)[1]
    if choice == "yes":
        await callback.message.answer("Выбери платформу:", reply_markup=_social_keyboard())
        await state.set_state(RegistrationState.social_platform)
    else:
        await _finalize_registration(callback.message, state)
    await callback.answer()


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
        age=data.get("profile_age", 0),
        city=data.get("profile_city", ""),
        bio=data.get("profile_bio"),
    )

    # Аватарка (в реальном проекте — загрузка в Minio)
    avatar_file_id = data.get("avatar_file_id")
    if avatar_file_id:
        storage.add_photo(
            profile.id,
            f"minio:avatars/{profile.id}_avatar.jpg",
            file_id=avatar_file_id,
            is_avatar=True,
        )

    # Работы
    for idx, fid in enumerate(data.get("artwork_file_ids", [])):
        storage.add_photo(
            profile.id,
            f"minio:artworks/{profile.id}_{idx}.jpg",
            file_id=fid,
        )

    # Интересы
    for tag in data.get("profile_interests", []):
        storage.add_interest(profile.id, tag)

    # Соцсети
    socials = data.get("socials", [])
    for idx, s in enumerate(socials):
        storage.add_social_link(
            profile.id, s["platform"], s["url"], is_primary=(idx == 0 and s["platform"] == "telegram")
        )

    completeness = storage._calc_completeness_by_profile(profile.id)

    # Инициализация рейтинга (Уровень 1)
    storage.init_rating(profile.id)
    logger.info("Rating initialized for profile %d (primary=%.2f)", profile.id, completeness)

    await message.answer(
        "🎉 Анкета готова! Теперь ты появляешься в ленте.\n\n"
        f"Полнота профиля: {completeness:.0%}\n"
        "Команды:\n"
        "/profile — моя анкета\n"
        "/feed — лента художников\n"
        "/top — топ-10\n"
        "/cancel — отмена",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()


# ── Entry point ─────────────────────────────────────────────────
def get_bot_token() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Не задан TELEGRAM_BOT_TOKEN. Установи переменную окружения."
        )
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
