"""
Multimodal DeepSeek client — kodikrouter / OpenAI-compatible SDK.

Принимает изображение (bytes), отправляет его мультимодальной
модели DeepSeek через Kodik Router и возвращает текстовое описание.

При пустом ответе — один автоматический ретрай.
"""

import asyncio
import base64
import logging

from openai import AsyncOpenAI, APIError, APIStatusError

from bot.config import KODIK_API_KEY, DEEPSEEK_MODEL, PHOTO_DESCRIPTION_PROMPT
from bot.models import InsufficientCreditsError, LLMAPIError, ImageProcessingError

logger = logging.getLogger(__name__)

_deepseek_client: AsyncOpenAI | None = None

# Альтернативный промпт для ретрая (короче, без лишних инструкций)
_RETRY_PROMPT = "Что изображено на фото? Назови предметы одним предложением."


def _get_client() -> AsyncOpenAI:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = AsyncOpenAI(
            api_key=KODIK_API_KEY,
            base_url="https://api.kodikrouter.ru/v1",
        )
    return _deepseek_client


async def _call_deepseek(base64_image: str, prompt: str) -> str | None:
    """Один вызов DeepSeek vision. Возвращает content или None."""
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=512,
        )
    except APIStatusError as e:
        if e.status_code == 402:
            raise InsufficientCreditsError("Insufficient credits on Kodik Router")
        logger.error("DeepSeek API error: %s", e)
        raise LLMAPIError(f"DeepSeek API error: {e}")
    except APIError as e:
        logger.error("DeepSeek API error: %s", e)
        raise LLMAPIError(f"DeepSeek API error: {e}")

    content = response.choices[0].message.content
    if content is not None:
        content = content.strip()
    return content if content else None


async def describe_photo(image_bytes: bytes) -> str:
    """Отправить изображение в DeepSeek и получить текстовое описание.

    При пустом ответе делает один ретрай с укороченным промптом.

    Args:
        image_bytes: сырые байты изображения (JPEG/PNG).

    Returns:
        Текстовое описание того, что на фото.

    Raises:
        ImageProcessingError: проблема с кодированием изображения.
        LLMAPIError: ошибка API DeepSeek.
        InsufficientCreditsError: не хватает средств на Kodik Router.
    """
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
    except Exception as e:
        raise ImageProcessingError(f"Failed to encode image: {e}")

    # Первая попытка
    content = await _call_deepseek(base64_image, PHOTO_DESCRIPTION_PROMPT)
    if content is not None:
        return content

    # Ретрай с укороченным промптом
    logger.warning("DeepSeek returned empty content, retrying with shorter prompt")
    await asyncio.sleep(0.5)
    content = await _call_deepseek(base64_image, _RETRY_PROMPT)
    if content is not None:
        return content

    logger.error("DeepSeek returned empty content after retry")
    raise LLMAPIError("DeepSeek returned empty content")