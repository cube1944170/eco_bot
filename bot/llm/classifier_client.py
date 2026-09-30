"""
JEV-классификатор — через Decisions API на kodikrouter.

Формат: state + questions{}. 
Типы вопросов: noul (вероятность), choice (категория), score (оценка).
"""

import logging

import httpx

from bot.config import (
    KODIK_API_KEY,
    CLASSIFIER_MODEL,
    WASTE_CATEGORIES,
)
from bot.models import InsufficientCreditsError, LLMAPIError
from bot.sanitize import sanitize_description

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://api.kodikrouter.ru/v1/decisions"


async def classify_waste(description: str) -> dict:
    """Классифицировать описание предмета в категорию отходов через JEV.

    Args:
        description: текстовое описание предмета (результат DeepSeek).

    Returns:
        Словарь с ключами:
            - category (str): выбранная категория
            - confidence (float): уверенность модели (0..1)

    Raises:
        LLMAPIError: ошибка API классификатора.
        InsufficientCreditsError: не хватает средств на Kodik Router.
    """
    safe_description = sanitize_description(description)
    if not safe_description:
        return {"category": "other", "confidence": 0.0}

    # state — контекст для оценки (обязательное поле)
    # questions — объект {id: {type, instructions, criteria}}
    criteria = {cat: None for cat in WASTE_CATEGORIES}

    payload = {
        "model": CLASSIFIER_MODEL,
        "state": {"photo_description": safe_description},
        "questions": {
            "category": {
                "type": "choice",
                "instructions": (
                    "Определи категорию отходов для предмета, "
                    "описанного в photo_description."
                ),
                "criteria": criteria,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                DECISIONS_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {KODIK_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException:
        logger.error("Classifier request timed out")
        raise LLMAPIError("Classifier request timed out")
    except httpx.RequestError as e:
        logger.error("Classifier request error: %s", e)
        raise LLMAPIError(f"Classifier request error: {e}")

    if resp.status_code == 402:
        raise InsufficientCreditsError("Insufficient credits on Kodik Router")
    if resp.status_code != 200:
        logger.error("Classifier API error: %s %s", resp.status_code, resp.text)
        raise LLMAPIError(f"Classifier API error: {resp.status_code}")

    body = resp.json()
    answers = body.get("answers") or {}

    category_answer = answers.get("category", {})
    chosen = (
        category_answer.get("choice")
        or category_answer.get("value")
        or category_answer.get("result")
    )
    confidence = category_answer.get("confidence") or 0.0

    if not chosen or chosen not in WASTE_CATEGORIES:
        logger.warning("Unexpected category '%s', falling back to 'other'", chosen)
        chosen = "other"

    return {
        "category": str(chosen).strip().lower(),
        "confidence": float(confidence),
    }