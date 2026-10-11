"""Interface translations (English, Russian, Ukrainian). Language follows the system by default."""

from __future__ import annotations

import locale
import os
import sys

LANGUAGES = ("en", "ru", "uk")
LANGUAGE_NAMES = {"en": "English", "ru": "Русский", "uk": "Українська"}
# System language code -> interface language.
LOCALES = {"ru": "ru", "be": "ru", "kk": "ru", "uk": "uk"}
# Windows primary language IDs (LANGID & 0x3FF): Russian, Belarusian, Kazakh, Ukrainian.
LANGIDS = {0x19: "ru", 0x23: "ru", 0x3F: "ru", 0x22: "uk"}

_lang = "en"


def detect() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return LANGIDS.get(langid & 0x3FF, "en")
        except Exception:
            pass
    for value in (os.environ.get("LC_ALL"), os.environ.get("LANG"), locale.getlocale()[0]):
        if value:
            low = value.lower()
            if low.startswith("russian"):
                return "ru"
            if low.startswith("ukrainian"):
                return "uk"
            return LOCALES.get(low.split("_")[0].split(".")[0], "en")
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


def _s(en: str, ru: str, uk: str) -> dict[str, str]:
    return {"en": en, "ru": ru, "uk": uk}


STRINGS: dict[str, dict[str, str]] = {
    # Header / tabs / main button
    "app.subtitle": _s("3D printer status in Discord · v{version}", "Статус 3D-принтера в Discord · v{version}",
                       "Статус 3D-принтера в Discord · v{version}"),
    "tab.home": _s("Home", "Главная", "Головна"),
    "tab.settings": _s("Settings", "Настройки", "Налаштування"),
    "tab.log": _s("Log", "Журнал", "Журнал"),
    "btn.start": _s("▶   Start", "▶   Запустить", "▶   Запустити"),
    "btn.stop": _s("■   Stop", "■   Остановить", "■   Зупинити"),
    "btn.stopping": _s("Stopping…", "Останавливаю…", "Зупиняю…"),
    "update.available": _s("⬆  Update {version} is available — download", "⬆  Вышла версия {version} — скачать",
                           "⬆  Вийшла версія {version} — завантажити"),
    # Status pill
    "pill.stopped": _s("Stopped", "Остановлено", "Зупинено"),
    "pill.connecting": _s("Connecting…", "Подключение…", "Підключення…"),
    "pill.running": _s("Running", "Работает", "Працює"),
    "pill.no_printer": _s("Printer unreachable", "Нет связи с принтером", "Немає зв'язку з принтером"),
    "pill.no_discord": _s("Discord is not running", "Discord не запущен", "Discord не запущено"),
    "pill.fill_settings": _s("Check settings", "Заполни настройки", "Заповни налаштування"),
    # Home tab
    "tab.farm": _s("Printers", "Принтеры", "Принтери"),
    "strip.now": _s("NOW IN DISCORD", "СЕЙЧАС В DISCORD", "ЗАРАЗ У DISCORD"),
    "strip.off": _s("Discord status is off", "Статус в Discord выключен", "Статус у Discord вимкнено"),
    "card.add": _s("Add printer", "Добавить принтер", "Додати принтер"),
    "card.add_hint": _s("or find them on the network", "или найти в сети", "або знайти в мережі"),
    "card.edit": _s("Click to edit", "Нажми, чтобы изменить", "Натисни, щоб змінити"),
    "home.preview": _s("How Discord shows you", "Так тебя видят в Discord", "Так тебе бачать у Discord"),
    "home.playing": _s("PLAYING", "ИГРАЕТ В", "ГРАЄ В"),
    "home.press_start": _s("Press “Start” to show your status", "Нажми «Запустить», чтобы включить статус",
                           "Натисни «Запустити», щоб увімкнути статус"),
    "home.hidden": _s("Status hidden — printer is offline", "Статус скрыт — принтер не на связи",
                      "Статус приховано — принтер не на зв'язку"),
    "home.time_left": _s("⏱  {time} left", "⏱  осталось {time}", "⏱  залишилось {time}"),
    "home.printer": _s("Printer", "Принтер", "Принтер"),
    "home.others": _s("All printers", "Все принтеры", "Усі принтери"),
    "home.unreachable": _s("Printer unreachable", "Нет связи с принтером", "Немає зв'язку з принтером"),
    "home.not_started": _s("Not started", "Не запущено", "Не запущено"),
    "home.no_job": _s("No job", "Без задания", "Без завдання"),
    "home.calibration": _s("Calibration", "Калибровка", "Калібрування"),
    "home.filament": _s("Filament: {name}", "Филамент: {name}", "Філамент: {name}"),
    "state.offline": _s("Offline", "Не на связи", "Не на зв'язку"),
    "state.idle": _s("Idle", "Простаивает", "Простоює"),
    "state.preparing": _s("Preparing", "Готовится", "Готується"),
    "state.printing": _s("Printing", "Печатает", "Друкує"),
    "state.paused": _s("Paused", "Пауза", "Пауза"),
    "state.finished": _s("Finished", "Готово", "Готово"),
    "state.failed": _s("Failed", "Ошибка", "Помилка"),
    "tile.layer": _s("Layer", "Слой", "Шар"),
    "tile.left": _s("Time left", "Осталось", "Залишилось"),
    "tile.nozzle": _s("Nozzle", "Сопло", "Сопло"),
    "tile.bed": _s("Bed", "Стол", "Стіл"),
    "time.hm": _s("{h} h {m:02d} min", "{h} ч {m:02d} мин", "{h} год {m:02d} хв"),
    "time.m": _s("{m} min", "{m} мин", "{m} хв"),
    # Settings: printers
    "set.printers": _s("Printers", "Принтеры", "Принтери"),
    "set.add_printer": _s("+ Add", "+ Добавить", "+ Додати"),
    "set.remove_printer": _s("Remove", "Удалить", "Видалити"),
    "set.new_printer": _s("New printer", "Новый принтер", "Новий принтер"),
    "set.find": _s("🔍  Find printers on network", "🔍  Найти принтеры в сети", "🔍  Знайти принтери в мережі"),
    "set.searching": _s("🔍  Searching…", "🔍  Ищу…", "🔍  Шукаю…"),
    "set.listening": _s("Listening to the network for ~8 seconds", "Слушаю сеть ~8 секунд",
                        "Слухаю мережу ~8 секунд"),
    "set.not_found": _s(
        "Nothing found. Make sure the PC and printer are on the same network\nand allow the app in Windows Firewall.",
        "Не нашёл. Проверь, что ПК и принтер в одной сети,\nи разреши программу в брандмауэре Windows.",
        "Нічого не знайшов. Перевір, що ПК і принтер в одній мережі,\nі дозволь програму в брандмауері Windows.",
    ),
    "set.found": _s("Found: {n}, new added: {added}", "Найдено: {n}, добавлено новых: {added}",
                    "Знайдено: {n}, додано нових: {added}"),
    "set.host": _s("Printer IP", "IP принтера", "IP принтера"),
    "set.host_hint": _s("Found automatically, or: printer screen → Settings → WLAN",
                        "Находится автоматически, или: экран принтера → Настройки → WLAN",
                        "Знаходиться автоматично, або: екран принтера → Налаштування → WLAN"),
    "set.serial": _s("Serial number", "Серийный номер", "Серійний номер"),
    "set.serial_hint": _s("Found automatically, or: Bambu Studio → Device",
                          "Находится автоматически, или: Bambu Studio → Устройство",
                          "Знаходиться автоматично, або: Bambu Studio → Пристрій"),
    "set.code_hint": _s("The printer doesn't announce it — see its screen: Settings → WLAN → Access Code",
                        "Принтер его не сообщает — смотри на экране: Настройки → WLAN → Access Code",
                        "Принтер його не повідомляє — дивись на екрані: Налаштування → WLAN → Access Code"),
    "set.code_placeholder": _s("8 characters", "8 символов", "8 символів"),
    "set.name": _s("Name in Discord", "Имя в Discord", "Ім'я в Discord"),
    "set.name_hint": _s("Shown in the app and when hovering the picture in Discord. Empty = printer model",
                        "Видно в программе и при наведении на картинку в Discord. Пусто — модель принтера",
                        "Видно в програмі й при наведенні на картинку в Discord. Порожньо — модель принтера"),
    # Settings: Discord
    "set.default_app": _s("Standard design (icons ready to go)", "Стандартное оформление (иконки уже готовы)",
                          "Стандартне оформлення (іконки вже готові)"),
    "set.client_id": _s("Own Application ID", "Своё Application ID", "Власний Application ID"),
    "set.client_id_hint": _s("Only if you want your own icons and name — turn off the switch above",
                             "Только если хочешь свои иконки и название — выключи переключатель выше",
                             "Лише якщо хочеш свої іконки й назву — вимкни перемикач вище"),
    "set.custom_app_help": _s("How to create your own app →", "Как создать своё приложение →",
                              "Як створити власний застосунок →"),
    "set.hide_job": _s("Hide the file name in Discord", "Скрывать имя файла в Discord",
                       "Приховувати назву файлу в Discord"),
    "set.button": _s("“Get Print Presence” button in my status",
                     "Кнопка «Get Print Presence» в статусе",
                     "Кнопка «Get Print Presence» у статусі"),
    # Settings: behaviour
    "set.behaviour": _s("Behaviour", "Поведение", "Поведінка"),
    "set.show_idle": _s("Show status while the printer is idle", "Показывать статус, когда принтер простаивает",
                        "Показувати статус, коли принтер простоює"),
    "set.autostart": _s("Start automatically when the app opens", "Включать сразу при открытии программы",
                        "Вмикати одразу при відкритті програми"),
    "set.launch_windows": _s("Launch with Windows (in the tray)", "Запускать вместе с Windows (в трее)",
                             "Запускати разом з Windows (у треї)"),
    "set.close_to_tray": _s("Closing the window keeps the app in the tray",
                            "Закрытие окна сворачивает программу в трей",
                            "Закриття вікна згортає програму в трей"),
    "set.check_updates": _s("Check for updates", "Проверять обновления", "Перевіряти оновлення"),
    "set.ui_lang": _s("Interface language", "Язык программы", "Мова програми"),
    "set.status_lang": _s("Status language in Discord", "Язык статуса в Discord", "Мова статусу в Discord"),
    "lang.auto": _s("Auto", "Авто", "Авто"),
    "set.instructions": _s("Instructions on GitHub →", "Инструкция на GitHub →", "Інструкція на GitHub →"),
    # Tray
    "tray.open": _s("Open", "Открыть", "Відкрити"),
    "tray.start": _s("Start", "Запустить", "Запустити"),
    "tray.stop": _s("Stop", "Остановить", "Зупинити"),
    "tray.quit": _s("Quit", "Выход", "Вихід"),
    # Errors
    "err.client_id": _s("Enter the Application ID of your Discord app or turn on the standard design",
                        "Укажи Application ID своего Discord-приложения или включи стандартное оформление",
                        "Вкажи Application ID свого Discord-застосунку або увімкни стандартне оформлення"),
    "err.no_printers": _s("Add at least one printer", "Добавь хотя бы один принтер", "Додай хоча б один принтер"),
    "err.missing": _s("Fill in: {field}", "Заполни поле: {field}", "Заповни поле: {field}"),
    "field.host": _s("Printer IP", "IP принтера", "IP принтера"),
    "field.serial": _s("Serial number", "Серийный номер", "Серійний номер"),
    "field.access_code": _s("Access Code", "Access Code", "Access Code"),
    # Log
    "log.started": _s("Started", "Запущено", "Запущено"),
    "log.stopped": _s("Stopped", "Остановлено", "Зупинено"),
    "log.unexpected": _s("Unexpected error", "Непредвиденная ошибка", "Неочікувана помилка"),
    "log.selected": _s("Selected printer: {title}", "Выбран принтер: {title}", "Вибрано принтер: {title}"),
    "log.found": _s("Found printer: {title}", "Найден принтер: {title}", "Знайдено принтер: {title}"),
    "log.port_busy": _s("Port {port} is busy ({error}) — maybe Bambu Studio is open",
                        "Порт {port} занят ({error}) — возможно, открыт Bambu Studio",
                        "Порт {port} зайнятий ({error}) — можливо, відкрито Bambu Studio"),
    "log.connecting": _s("Connecting to {name} ({host})...", "Подключаюсь к {name} ({host})...",
                         "Підключаюся до {name} ({host})..."),
    "log.refused": _s(
        "Printer refused the connection: {reason}. Check the IP and Access Code; "
        "if they are correct, enable LAN Only + Developer Mode on the printer.",
        "Принтер отклонил подключение: {reason}. Проверь IP и Access Code; "
        "если они верные — включи на принтере LAN Only + Developer Mode.",
        "Принтер відхилив підключення: {reason}. Перевір IP та Access Code; "
        "якщо вони правильні — увімкни на принтері LAN Only + Developer Mode.",
    ),
    "log.connected": _s("Connected to {name}", "Подключено к {name}", "Підключено до {name}"),
    "log.disconnected": _s("Lost connection to {name} ({reason}), reconnecting...",
                           "Связь с {name} потеряна ({reason}), переподключаюсь...",
                           "Зв'язок з {name} втрачено ({reason}), перепідключаюся..."),
    "log.discord_unavailable": _s("Discord is not available ({error}), retrying in 30 s",
                                  "Discord недоступен ({error}), повтор через 30 с",
                                  "Discord недоступний ({error}), повтор через 30 с"),
    "log.discord_connected": _s("Connected to Discord", "Подключено к Discord", "Підключено до Discord"),
    "log.discord_lost": _s("Lost connection to Discord: {error}", "Связь с Discord потеряна: {error}",
                           "Зв'язок з Discord втрачено: {error}"),
    "log.presence": _s("Discord status: {summary}", "Статус в Discord: {summary}", "Статус у Discord: {summary}"),
    "log.presence_hidden": _s("hidden", "скрыт", "приховано"),
    "log.update": _s("Update available: {version}", "Доступно обновление: {version}",
                     "Доступне оновлення: {version}"),
}
