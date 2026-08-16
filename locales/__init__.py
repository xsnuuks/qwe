from . import ru, en, de

LOCALES = {
    "ru": ru.TEXTS,
    "en": en.TEXTS,
    "de": de.TEXTS,
}


def get_text(lang: str, key: str, **kwargs) -> str:
    texts = LOCALES.get(lang, LOCALES["ru"])
    text = texts.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
