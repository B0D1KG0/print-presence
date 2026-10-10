"""Interface translations (English and Russian). Language follows the system by default."""

from __future__ import annotations

import locale
import os
import sys

LANGUAGES = ("en", "ru")
# System languages that get the Russian interface.
RUSSIAN_LOCALES = {"ru", "be", "kk"}
# Windows primary language IDs (LANGID & 0x3FF) for the same languages.
RUSSIAN_LANGIDS = {0x19, 0x23, 0x3F}

_lang = "en"


def detect() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "ru" if (langid & 0x3FF) in RUSSIAN_LANGIDS else "en"
        except Exception:
            pass
    for value in (os.environ.get("LC_ALL"), os.environ.get("LANG"), locale.getlocale()[0]):
        if value:
            code = value.split("_")[0].split(".")[0].lower()
            return "ru" if code in RUSSIAN_LOCALES or value.lower().startswith("russian") else "en"
    return "en"


def resolve(choice: str | None) -> str:
    """"auto" (or anything unknown) -> system language."""
    return choice if choice in LANGUAGES else detect()


def set_language(choice: str | None) -> str:
    global _lang
    _lang = resolve(choice)
    return _lang


def current() -> str:
    return _lang


def tr(key: str, **kw: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_lang) or entry["en"]
    return text.format(**kw) if kw else text


STRINGS: dict[str, dict[str, str]] = {
    # Header / tabs / main button
    "app.subtitle": {"en": "3D printer status in Discord · v{version}", "ru": "Статус 3D-принтера в Discord · v{version}"},
    "tab.home": {"en": "Home", "ru": "Главная"},
    "tab.settings": {"en": "Settings", "ru": "Настройки"},
    "tab.log": {"en": "Log", "ru": "Журнал"},
    "btn.start": {"en": "▶   Start", "ru": "▶   Запустить"},
    "btn.stop": {"en": "■   Stop", "ru": "■   Остановить"},
    "btn.stopping": {"en": "Stopping…", "ru": "Останавливаю…"},
    # Status pill
    "pill.stopped": {"en": "Stopped", "ru": "Остановлено"},
    "pill.connecting": {"en": "Connecting…", "ru": "Подключение…"},
    "pill.running": {"en": "Running", "ru": "Работает"},
    "pill.no_printer": {"en": "Printer unreachable", "ru": "Нет связи с принтером"},
    "pill.no_discord": {"en": "Discord is not running", "ru": "Discord не запущен"},
    "pill.fill_settings": {"en": "Check settings", "ru": "Заполни настройки"},
    # Home tab
    "home.preview": {"en": "How Discord shows you", "ru": "Так тебя видят в Discord"},
    "home.playing": {"en": "PLAYING", "ru": "ИГРАЕТ В"},
    "home.press_start": {"en": "Press “Start” below", "ru": "Нажми «Запустить» внизу"},
    "home.hidden": {"en": "Status hidden — printer is offline", "ru": "Статус скрыт — принтер не на связи"},
    "home.time_left": {"en": "⏱  {time} left", "ru": "⏱  осталось {time}"},
    "home.printer": {"en": "Printer", "ru": "Принтер"},
    "home.unreachable": {"en": "Printer unreachable", "ru": "Нет связи с принтером"},
    "home.not_started": {"en": "Not started", "ru": "Не запущено"},
    "home.no_job": {"en": "No job", "ru": "Без задания"},
    "home.calibration": {"en": "Calibration", "ru": "Калибровка"},
    "tile.layer": {"en": "Layer", "ru": "Слой"},
    "tile.left": {"en": "Time left", "ru": "Осталось"},
    "tile.nozzle": {"en": "Nozzle", "ru": "Сопло"},
    "tile.bed": {"en": "Bed", "ru": "Стол"},
    "time.hm": {"en": "{h} h {m:02d} min", "ru": "{h} ч {m:02d} мин"},
    "time.m": {"en": "{m} min", "ru": "{m} мин"},
    # Settings: printer
    "set.printer": {"en": "Printer", "ru": "Принтер"},
    "set.find": {"en": "🔍  Find printer on network", "ru": "🔍  Найти принтер в сети"},
    "set.searching": {"en": "🔍  Searching…", "ru": "🔍  Ищу…"},
    "set.listening": {"en": "Listening to the network for ~8 seconds", "ru": "Слушаю сеть ~8 секунд"},
    "set.not_found": {
        "en": "Nothing found. Make sure the PC and printer are on the same network\nand allow the app in Windows Firewall.",
        "ru": "Не нашёл. Проверь, что ПК и принтер в одной сети,\nи разреши программу в брандмауэре Windows.",
    },
    "set.found": {"en": "Printers found: {n}", "ru": "Найдено принтеров: {n}"},
    "set.host": {"en": "Printer IP", "ru": "IP принтера"},
    "set.host_hint": {"en": "Found automatically, or: printer screen → Settings → WLAN",
                      "ru": "Находится автоматически, или: экран принтера → Настройки → WLAN"},
    "set.serial": {"en": "Serial number", "ru": "Серийный номер"},
    "set.serial_hint": {"en": "Found automatically, or: Bambu Studio → Device",
                        "ru": "Находится автоматически, или: Bambu Studio → Устройство"},
    "set.code_hint": {"en": "The printer doesn't announce it — see its screen: Settings → WLAN → Access Code",
                      "ru": "Принтер его не сообщает — смотри на экране: Настройки → WLAN → Access Code"},
    "set.code_placeholder": {"en": "8 characters", "ru": "8 символов"},
    "set.name": {"en": "Name in Discord", "ru": "Имя в Discord"},
    "set.name_hint": {"en": "Leave empty to use the printer model", "ru": "Оставь пустым — подставится модель принтера"},
    # Settings: Discord
    "set.default_app": {"en": "Standard design (icons ready to go)", "ru": "Стандартное оформление (иконки уже готовы)"},
    "set.client_id": {"en": "Own Application ID", "ru": "Своё Application ID"},
    "set.client_id_hint": {"en": "Only if you want your own icons and name — turn off the switch above",
                           "ru": "Только если хочешь свои иконки и название — выключи переключатель выше"},
    "set.custom_app_help": {"en": "How to create your own app →", "ru": "Как создать своё приложение →"},
    # Settings: behaviour
    "set.behaviour": {"en": "Behaviour", "ru": "Поведение"},
    "set.show_idle": {"en": "Show status while the printer is idle", "ru": "Показывать статус, когда принтер простаивает"},
    "set.autostart": {"en": "Start automatically when the app opens", "ru": "Включать сразу при открытии программы"},
    "set.ui_lang": {"en": "Interface language", "ru": "Язык программы"},
    "set.status_lang": {"en": "Status language in Discord", "ru": "Язык статуса в Discord"},
    "lang.auto": {"en": "Auto", "ru": "Авто"},
    "set.instructions": {"en": "Instructions on GitHub →", "ru": "Инструкция на GitHub →"},
    # Errors
    "err.client_id": {"en": "Enter the Application ID of your Discord app or turn on the standard design",
                      "ru": "Укажи Application ID своего Discord-приложения или включи стандартное оформление"},
    "err.missing": {"en": "Fill in: {field}", "ru": "Заполни поле: {field}"},
    "field.host": {"en": "Printer IP", "ru": "IP принтера"},
    "field.serial": {"en": "Serial number", "ru": "Серийный номер"},
    "field.access_code": {"en": "Access Code", "ru": "Access Code"},
    # Log
    "log.started": {"en": "Started", "ru": "Запущено"},
    "log.stopped": {"en": "Stopped", "ru": "Остановлено"},
    "log.unexpected": {"en": "Unexpected error", "ru": "Непредвиденная ошибка"},
    "log.selected": {"en": "Selected printer: {title}", "ru": "Выбран принтер: {title}"},
    "log.found": {"en": "Found printer: {title}", "ru": "Найден принтер: {title}"},
    "log.port_busy": {"en": "Port {port} is busy ({error}) — maybe Bambu Studio is open",
                      "ru": "Порт {port} занят ({error}) — возможно, открыт Bambu Studio"},
    "log.connecting": {"en": "Connecting to {name} ({host})...", "ru": "Подключаюсь к {name} ({host})..."},
    "log.refused": {
        "en": "Printer refused the connection: {reason}. Check the IP and Access Code; "
              "if they are correct, enable LAN Only + Developer Mode on the printer.",
        "ru": "Принтер отклонил подключение: {reason}. Проверь IP и Access Code; "
              "если они верные — включи на принтере LAN Only + Developer Mode.",
    },
    "log.connected": {"en": "Connected to {name}", "ru": "Подключено к {name}"},
    "log.disconnected": {"en": "Lost connection to {name} ({reason}), reconnecting...",
                         "ru": "Связь с {name} потеряна ({reason}), переподключаюсь..."},
    "log.discord_unavailable": {"en": "Discord is not available ({error}), retrying in 30 s",
                                "ru": "Discord недоступен ({error}), повтор через 30 с"},
    "log.discord_connected": {"en": "Connected to Discord", "ru": "Подключено к Discord"},
    "log.discord_lost": {"en": "Lost connection to Discord: {error}", "ru": "Связь с Discord потеряна: {error}"},
    "log.presence": {"en": "Discord status: {summary}", "ru": "Статус в Discord: {summary}"},
    "log.presence_hidden": {"en": "hidden", "ru": "скрыт"},
}
