import re

# Управляющие символы (кроме \n, \r, \t)
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def escape_html(text: str) -> str:
    """Экранировать спецсимволы HTML для безопасного вывода."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sanitize_description(text: str, max_length: int = 1000) -> str:
    """Очистить текстовое описание перед вставкой в промпт.

    Удаляет управляющие символы, обрезает по длине.
    """
    if not text:
        return ""
    text = text.strip()[:max_length]
    text = _CONTROL_CHARS_RE.sub("", text)
    return text