import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
KODIK_API_KEY: str = os.environ.get("KODIK_API_KEY", "")

# Модели (можно переопределить через .env)
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash-vision-exp")
CLASSIFIER_MODEL: str = os.environ.get("CLASSIFIER_MODEL", "~typesafe/jev-latest")

# Категории сортировки отходов для классификации (JEV enum)
# Категория "other" — всё, что не подошло под основные типы
WASTE_CATEGORIES = [
    "plastic",       # пластик (бутылки, упаковка, пакеты)
    "glass",         # стекло (бутылки, банки)
    "paper",         # бумага/картон (газеты, коробки, офисная бумага)
    "metal",         # металл (банки, фольга, крышки)
    "organic",       # органические отходы (еда, растительные остатки)
    "electronics",   # электроника (батарейки, лампочки, приборы)
    "hazardous",     # опасные отходы (химия, лекарства, краски)
    "textiles",      # текстиль (одежда, обувь)
    "mixed",         # смешанные / общий мусор
    "other",         # другое / не удалось определить
]

# Промпт для DeepSeek: описание содержимого фото
PHOTO_DESCRIPTION_PROMPT = (
    "Опиши одним-двумя предложениями, что изображено на фотографии. "
    "Если это предмет или несколько предметов — назови их. "
    "Не добавляй лишних комментариев."
)