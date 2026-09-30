"""
EcoDecision Bot — MVP экологического хакатона.

Пайплайн:
1. Пользователь отправляет фото
2. DeepSeek (multimodal) → текстовое описание
3. JEV-классификатор (structured output) → категория сортировки отходов
4. Ответ пользователю
"""

import asyncio
import logging
import signal
import sys
from io import BytesIO

from aiogram import Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from bot.bot_instance import bot
from bot.config import TELEGRAM_BOT_TOKEN, WASTE_CATEGORIES
from bot.models import InsufficientCreditsError, LLMAPIError, ImageProcessingError
from bot.llm.deepseek_client import describe_photo
from bot.llm.classifier_client import classify_waste

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

router = Router()
dp = Dispatcher()

# Иконки и русские названия для каждой категории отходов
CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "plastic":     ("♳", "Пластик"),
    "glass":       ("♴", "Стекло"),
    "paper":       ("♵", "Бумага / Картон"),
    "metal":       ("♶", "Металл"),
    "organic":     ("♻", "Органика"),
    "electronics": ("♽", "Электроника"),
    "hazardous":   ("☠", "Опасные отходы"),
    "textiles":    ("👕", "Текстиль"),
    "mixed":       ("🗑", "Смешанный мусор"),
    "other":       ("❓", "Не определено"),
}

CATEGORY_TIPS: dict[str, str] = {
    "plastic":     "ПЭТ-бутылки и пластиковую упаковку — в контейнер для пластика. "
                   "Перед этим ополосни.",
    "glass":       "Стеклянные бутылки и банки — в контейнер для стекла. "
                   "Крышки можно сдать отдельно как металл.",
    "paper":       "Макулатуру сдают в сухом виде, без скрепок и пластиковых окошек.",
    "metal":       "Алюминиевые банки и жесть — в контейнер для металла. "
                   "Сильно скомкай перед сдачей.",
    "organic":     "Органику можно компостировать. "
                   "Не смешивай с пластиком.",
    "electronics": "Батарейки, лампочки и технику нельзя в общий мусор — "
                   "их принимают в спецпунктах приёма.",
    "hazardous":   "Краски, растворители, лекарства — только в пункты "
                   "приёма опасных отходов!",
    "textiles":    "Старую одежду и обувь можно сдать в контейнеры "
                   "для вещей или секонд-хенд.",
    "mixed":       "Всё остальное — в общий мусор. "
                   "По возможности разделяй вторсырьё!",
    "other":       "Попробуй сфотографировать предмет крупным планом на однородном фоне.",
}


def format_result(category: str, confidence: float) -> str:
    """Отформатировать результат классификации для отправки пользователю."""
    icon, label = CATEGORY_LABELS.get(category, ("❓", category.capitalize()))
    tip = CATEGORY_TIPS.get(category, "")

    confidence_pct = round(confidence * 100)

    lines = [
        f"<b>{icon} {label}</b>",
        f"📊 Уверенность: {confidence_pct}%",
    ]
    if tip:
        lines.extend(["", f"💡 <b>Совет:</b> {tip}"])
    lines.extend([
        "",
        "📸 <i>Отправь ещё одно фото для сортировки.</i>",
    ])

    return "\n".join(lines)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветствие + инструкция."""
    text = (
        "♻ <b>EcoDecision Bot</b>\n\n"
        "Пришли фотографию предмета, и я определю, "
        "к какой категории отходов его отнести "
        "и как правильно утилизировать.\n\n"
        "Просто отправь фото 📸"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 <b>Помощь</b>\n\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/categories — список всех категорий сортировки\n\n"
        "Просто отправь фото любого предмета."
    )
    await message.answer(text)


@router.message(Command("categories"))
async def cmd_categories(message: types.Message):
    """Показать все доступные категории сортировки."""
    lines = ["<b>♻ Категории сортировки:</b>\n"]
    for cat in WASTE_CATEGORIES:
        icon, label = CATEGORY_LABELS.get(cat, ("❓", cat.capitalize()))
        tip = CATEGORY_TIPS.get(cat, "")
        lines.append(f"{icon} <b>{label}</b>")
        if tip:
            lines.append(f"   {tip}")
        lines.append("")
    await message.answer("\n".join(lines))


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    """Health-check."""
    await message.answer("🟢 Бот работает.")


@router.message(lambda msg: msg.photo is not None)
async def on_photo(message: types.Message):
    """Обработка входящего фото: DeepSeek → JEV → ответ."""
    user_id = str(message.from_user.id)
    logger.info("Processing photo from user %s", user_id)

    # Показываем индикатор "печатает"
    await bot.send_chat_action(chat_id=user_id, action="typing")

    # 1. Скачиваем фото
    try:
        photo = message.photo[-1]  # самое большое разрешение
        file = await bot.download(photo)
        image_bytes = file.read()
    except Exception as e:
        logger.error("Failed to download photo from user %s: %s", user_id, e)
        await message.reply("Не удалось загрузить фото. Попробуй ещё раз.")
        return

    # 2. DeepSeek multimodal → текстовое описание
    try:
        description = await describe_photo(image_bytes)
        logger.info("DeepSeek description for user %s: %s", user_id, description[:100])
    except ImageProcessingError as e:
        logger.error("Image processing error for user %s: %s", user_id, e)
        await message.reply("Ошибка при обработке изображения. Попробуй другое фото.")
        return
    except InsufficientCreditsError as e:
        logger.error("Insufficient credits for user %s: %s", user_id, e)
        await message.reply("Сервис временно недоступен. Попробуй позже.")
        return
    except LLMAPIError as e:
        logger.error("DeepSeek API error for user %s: %s", user_id, e)
        await message.reply("Не удалось распознать содержимое фото. Попробуй ещё раз.")
        return

    # 3. JEV-классификатор → категория
    try:
        result = await classify_waste(description)
        category = result.get("category", "other")
        confidence = result.get("confidence", 0.0)
        logger.info(
            "Classification for user %s: category=%s, confidence=%.2f",
            user_id, category, confidence,
        )
    except InsufficientCreditsError as e:
        logger.error("Insufficient credits for user %s: %s", user_id, e)
        await message.reply("Сервис временно недоступен. Попробуй позже.")
        return
    except LLMAPIError as e:
        logger.error("Classifier API error for user %s: %s", user_id, e)
        await message.reply("Не удалось классифицировать предмет. Попробуй ещё раз.")
        return

    # 4. Ответ пользователю
    response_text = format_result(category, confidence)
    await message.reply(response_text)


@router.message()
async def on_unknown(message: types.Message):
    """Любое текстовое сообщение — напоминаем про фото."""
    if message.text and not message.text.startswith("/"):
        await message.reply(
            "Отправь 📸 <b>фотографию</b> предмета, "
            "и я определю его категорию сортировки."
        )


async def shutdown():
    """Корректное завершение работы."""
    logger.info("Shutting down...")
    try:
        await dp.stop_polling()
    except Exception:
        pass
    try:
        await bot.session.close()
    except Exception:
        pass
    logger.info("Shutdown complete.")


def main():
    """Точка входа."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)

    dp.include_router(router)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
            except NotImplementedError:
                # Windows: сигналы только для SIGINT в основном потоке
                signal.signal(sig, lambda s, f: asyncio.ensure_future(shutdown()))

        logger.info("Starting EcoDecision Bot...")
        try:
            await dp.start_polling(bot)
        finally:
            await shutdown()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()