import logging

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    """На счету Kodik Router недостаточно средств."""
    pass


class LLMAPIError(Exception):
    """Ошибка при вызове LLM API (DeepSeek / классификатор)."""
    pass


class ImageProcessingError(Exception):
    """Ошибка при загрузке или обработке изображения."""
    pass


class SanitizeError(Exception):
    pass