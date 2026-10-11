"""Human-readable filament colour names."""

from __future__ import annotations

# (name per language, RGB)
COLORS: list[tuple[dict[str, str], tuple[int, int, int]]] = [
    ({"en": "Black", "ru": "Чёрный", "uk": "Чорний"}, (20, 20, 20)),
    ({"en": "White", "ru": "Белый", "uk": "Білий"}, (245, 245, 245)),
    ({"en": "Grey", "ru": "Серый", "uk": "Сірий"}, (128, 128, 128)),
    ({"en": "Silver", "ru": "Серебристый", "uk": "Сріблястий"}, (192, 192, 196)),
    ({"en": "Red", "ru": "Красный", "uk": "Червоний"}, (210, 30, 40)),
    ({"en": "Orange", "ru": "Оранжевый", "uk": "Помаранчевий"}, (245, 125, 30)),
    ({"en": "Yellow", "ru": "Жёлтый", "uk": "Жовтий"}, (245, 215, 30)),
    ({"en": "Gold", "ru": "Золотой", "uk": "Золотий"}, (200, 160, 50)),
    ({"en": "Green", "ru": "Зелёный", "uk": "Зелений"}, (40, 170, 70)),
    ({"en": "Dark green", "ru": "Тёмно-зелёный", "uk": "Темно-зелений"}, (20, 90, 45)),
    ({"en": "Cyan", "ru": "Бирюзовый", "uk": "Бірюзовий"}, (30, 190, 200)),
    ({"en": "Blue", "ru": "Синий", "uk": "Синій"}, (30, 80, 200)),
    ({"en": "Light blue", "ru": "Голубой", "uk": "Блакитний"}, (120, 180, 235)),
    ({"en": "Navy", "ru": "Тёмно-синий", "uk": "Темно-синій"}, (20, 35, 90)),
    ({"en": "Purple", "ru": "Фиолетовый", "uk": "Фіолетовий"}, (120, 50, 170)),
    ({"en": "Pink", "ru": "Розовый", "uk": "Рожевий"}, (240, 120, 170)),
    ({"en": "Brown", "ru": "Коричневый", "uk": "Коричневий"}, (110, 65, 35)),
    ({"en": "Beige", "ru": "Бежевый", "uk": "Бежевий"}, (225, 205, 165)),
]
TRANSPARENT = {"en": "Clear", "ru": "Прозрачный", "uk": "Прозорий"}


def parse_hex(value: str | None) -> tuple[int, int, int, int] | None:
    """"RRGGBB" or "RRGGBBAA" -> (r, g, b, a)."""
    if not value:
        return None
    value = value.strip().lstrip("#")
    if len(value) not in (6, 8):
        return None
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        a = int(value[6:8], 16) if len(value) == 8 else 255
    except ValueError:
        return None
    return r, g, b, a


def color_name(value: str | None, lang: str = "en") -> str | None:
    rgba = parse_hex(value)
    if rgba is None:
        return None
    r, g, b, a = rgba
    if a < 64:
        return TRANSPARENT.get(lang, TRANSPARENT["en"])

    def dist(c: tuple[int, int, int]) -> float:
        # Weighted RGB distance — close enough to human perception for naming.
        return 2 * (r - c[0]) ** 2 + 4 * (g - c[1]) ** 2 + 3 * (b - c[2]) ** 2

    names, _ = min(COLORS, key=lambda item: dist(item[1]))
    return names.get(lang, names["en"])


def filament_label(material: str | None, color: str | None, lang: str = "en") -> str | None:
    """"PLA Basic · Black" — whatever parts are known."""
    parts = [p for p in (material, color_name(color, lang)) if p]
    return " · ".join(parts) or None
