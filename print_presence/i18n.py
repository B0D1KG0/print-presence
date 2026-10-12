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
    "desc.default_app": _s('Icons and printer photos are ready — nothing to set up', 'Иконки и фото принтеров уже готовы — ничего настраивать не нужно', 'Іконки й фото принтерів уже готові — нічого налаштовувати не треба'),
    "desc.hide_job": _s('Friends see “Printing”, but not the model name', 'Друзья увидят «Печатает», но не имя модели', 'Друзі побачать «Друкує», але не назву моделі'),
    "desc.button": _s('Lets friends download the app from your profile. Discord never shows it to you', 'Друзья смогут скачать программу из твоего профиля. Тебе Discord её не показывает', 'Друзі зможуть завантажити програму з твого профілю. Тобі Discord її не показує'),
    "desc.show_idle": _s('Keep the status in your profile when nothing is printing', 'Статус останется в профиле, даже когда ничего не печатается', 'Статус залишиться в профілі, навіть коли нічого не друкується'),
    "desc.launch_windows": _s('Starts minimised in the tray and turns the status on', 'Стартует свёрнутой в трей и сама включает статус', 'Стартує згорнутою в трей і сама вмикає статус'),
    "desc.close_to_tray": _s('The close button hides the window, the status keeps working', 'Крестик прячет окно, а статус продолжает работать', 'Хрестик ховає вікно, а статус продовжує працювати'),
    "desc.autostart": _s('No need to press Start every time', 'Не нужно каждый раз нажимать «Запустить»', 'Не треба щоразу натискати «Запустити»'),
    "desc.check_updates": _s("We'll tell you when a new version is on GitHub", 'Сообщим, когда на GitHub выйдет новая версия', 'Повідомимо, коли на GitHub вийде нова версія'),
    "desc.ui_lang": _s('Language of this window', 'Язык окна программы', 'Мова вікна програми'),
    "desc.status_lang": _s('The language your friends see', 'На каком языке друзья видят статус', 'Якою мовою друзі бачать статус'),
    "nav.about": _s('About', 'О программе', 'Про програму'),
    "page.printers": _s('Your printers and what Discord shows', 'Твои принтеры и то, что видно в Discord', 'Твої принтери й те, що видно в Discord'),
    "page.settings": _s('Printers, Discord and app behaviour', 'Принтеры, Discord и поведение программы', 'Принтери, Discord і поведінка програми'),
    "page.log": _s("What's happening inside the app", 'Что происходит внутри программы', 'Що відбувається всередині програми'),
    "page.about": _s('Version, links and help', 'Версия, ссылки и помощь', 'Версія, посилання й допомога'),
    "sec.language": _s('Language', 'Язык', 'Мова'),
    "sec.printer_edit": _s('Printer settings', 'Настройки принтера', 'Налаштування принтера'),
    "chip.need_code": _s('Needs Access Code', 'Нужен Access Code', 'Потрібен Access Code'),
    "chip.ready": _s('Ready', 'Готов', 'Готовий'),
    "empty.title": _s('No printers yet', 'Пока нет принтеров', 'Поки немає принтерів'),
    "empty.text": _s('Find them on your network or add one by hand', 'Найди их в сети или добавь вручную', 'Знайди їх у мережі або додай вручну'),
    "hero.printing": _s('Printing now', 'Печатают сейчас', 'Друкують зараз'),
    "hero.discord": _s('Discord', 'Discord', 'Discord'),
    "hero.connected": _s('Connected', 'Подключён', 'Підключено'),
    "hero.not_connected": _s('Not connected', 'Не подключён', 'Не підключено'),
    "hero.of": _s('{a} of {b}', '{a} из {b}', '{a} з {b}'),
    "log.copy": _s('Copy', 'Копировать', 'Копіювати'),
    "log.clear": _s('Clear', 'Очистить', 'Очистити'),
    "log.folder": _s('Settings folder', 'Папка настроек', 'Тека налаштувань'),
    "log.copied": _s('Copied', 'Скопировано', 'Скопійовано'),
    "about.desc": _s("Discord Rich Presence for 3D printers: friends see what you're printing, the layer, progress and time left.", 'Discord Rich Presence для 3D-принтеров: друзья видят, что ты печатаешь, слой, прогресс и сколько осталось.', 'Discord Rich Presence для 3D-принтерів: друзі бачать, що ти друкуєш, шар, прогрес і скільки залишилось.'),
    "about.github": _s('Open on GitHub', 'Открыть на GitHub', 'Відкрити на GitHub'),
    "about.bug": _s('Report a problem', 'Сообщить об ошибке', 'Повідомити про помилку'),
    "about.check": _s('Check for updates', 'Проверить обновления', 'Перевірити оновлення'),
    "about.checking": _s('Checking…', 'Проверяю…', 'Перевіряю…'),
    "about.latest": _s('You have the latest version', 'У тебя последняя версия', 'У тебе остання версія'),
    "about.legal": _s('MIT license · Unofficial project, not affiliated with Bambu Lab or Discord', 'Лицензия MIT · Неофициальный проект, не связан с Bambu Lab и Discord', "Ліцензія MIT · Неофіційний проєкт, не пов'язаний з Bambu Lab і Discord"),
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
    "set.default_app": _s('Standard design', 'Стандартное оформление', 'Стандартне оформлення'),
    "set.client_id": _s("Own Application ID", "Своё Application ID", "Власний Application ID"),
    "set.client_id_hint": _s("Only if you want your own icons and name — turn off the switch above",
                             "Только если хочешь свои иконки и название — выключи переключатель выше",
                             "Лише якщо хочеш свої іконки й назву — вимкни перемикач вище"),
    "set.custom_app_help": _s("How to create your own app →", "Как создать своё приложение →",
                              "Як створити власний застосунок →"),
    "set.hide_job": _s('Hide the file name', 'Скрывать имя файла', 'Приховувати назву файлу'),
    "set.button": _s('“Get Print Presence” button', 'Кнопка «Get Print Presence»', 'Кнопка «Get Print Presence»'),
    "set.behaviour": _s("Behaviour", "Поведение", "Поведінка"),
    "set.show_idle": _s('Show status while idle', 'Показывать, когда принтер простаивает', 'Показувати, коли принтер простоює'),
    "set.autostart": _s('Turn the status on at launch', 'Включать статус при открытии', 'Вмикати статус при відкритті'),
    "set.launch_windows": _s('Launch with Windows', 'Запускать вместе с Windows', 'Запускати разом з Windows'),
    "set.close_to_tray": _s('Keep running in the tray', 'Сворачивать в трей при закрытии', 'Згортати в трей при закритті'),
    "set.check_updates": _s("Check for updates", "Проверять обновления", "Перевіряти оновлення"),
    "set.ui_lang": _s("Interface language", "Язык программы", "Мова програми"),
    "set.status_lang": _s("Status language in Discord", "Язык статуса в Discord", "Мова статусу в Discord"),
    "lang.auto": _s("Auto", "Авто", "Авто"),
    "set.instructions": _s("Instructions on GitHub →", "Инструкция на GitHub →", "Інструкція на GitHub →"),
    # Rich Presence constructor
    "nav.constructor": _s("Constructor", "Конструктор", "Конструктор"),
    "page.constructor": _s("Build your own status — changes reach Discord in seconds",
                           "Собери свой статус — изменения доходят до Discord за секунды",
                           "Збери свій статус — зміни доходять до Discord за секунди"),
    "cons.custom": _s("Own status template", "Свой шаблон статуса", "Власний шаблон статусу"),
    "desc.cons_custom": _s("When off, the standard status is used", "Когда выключено — стандартный статус",
                           "Коли вимкнено — стандартний статус"),
    "cons.show": _s("Show as", "Показать как", "Показати як"),
    "sample.printing": _s("Printing", "Печать", "Друк"),
    "sample.paused": _s("Paused", "Пауза", "Пауза"),
    "sample.finished": _s("Done", "Готово", "Готово"),
    "sample.idle": _s("Idle", "Простой", "Простій"),
    "cons.lines": _s("Status lines", "Строки статуса", "Рядки статусу"),
    "cons.details": _s("First line", "Первая строка", "Перший рядок"),
    "cons.state": _s("Second line", "Вторая строка", "Другий рядок"),
    "cons.large_text": _s("Printer picture tooltip", "Подсказка на картинке принтера", "Підказка на картинці принтера"),
    "cons.small_text": _s("Status badge tooltip", "Подсказка на значке статуса", "Підказка на значку статусу"),
    "cons.hover_hint": _s("Shown when hovering the picture in Discord", "Видно при наведении на картинку в Discord",
                          "Видно при наведенні на картинку в Discord"),
    "cons.vars": _s("Variables", "Переменные", "Змінні"),
    "cons.vars_hint": _s(
        "Click to insert into the selected line. A part in [square brackets] is hidden when a variable "
        "inside it is empty, e.g. [ · {progress}]",
        "Нажми, чтобы вставить в выбранную строку. Часть в [квадратных скобках] скрывается, если переменная "
        "в ней пустая, например [ · {progress}]",
        "Натисни, щоб вставити у вибраний рядок. Частина в [квадратних дужках] ховається, якщо змінна "
        "в ній порожня, наприклад [ · {progress}]"),
    "cons.timer": _s("Countdown to the end", "Обратный отсчёт до конца", "Зворотний відлік до кінця"),
    "desc.cons_timer": _s("Discord shows “1:23:00 left” while printing", "Discord показывает «осталось 1:23:00» во время печати",
                          "Discord показує «залишилось 1:23:00» під час друку"),
    "cons.reset": _s("Reset", "Сбросить", "Скинути"),
    "cons.preview": _s("Live preview", "Живой предпросмотр", "Живий попередній перегляд"),
    "cons.live_on": _s("● Live — changes are sent to Discord right away",
                       "● Вживую — изменения сразу уходят в Discord",
                       "● Наживо — зміни одразу йдуть у Discord"),
    "cons.live_off": _s("Changes will be used after you press Start", "Изменения применятся после запуска",
                        "Зміни застосуються після запуску"),
    "cons.sent": _s("✓ Sent to Discord", "✓ Отправлено в Discord", "✓ Надіслано в Discord"),
    "cons.now": _s("Now", "Сейчас", "Зараз"),
    "cons.sample": _s("Sample data", "Пример данных", "Приклад даних"),
    "cons.hover_large": _s("Picture: {text}", "Картинка: {text}", "Картинка: {text}"),
    "cons.hover_small": _s("Badge: {text}", "Значок: {text}", "Значок: {text}"),
    "var.status": _s("Status", "Статус", "Статус"),
    "var.job": _s("File", "Файл", "Файл"),
    "var.layer": _s("Layer 87/240", "Слой 87/240", "Шар 87/240"),
    "var.layer_num": _s("Layer №", "№ слоя", "№ шару"),
    "var.total_layers": _s("Total layers", "Всего слоёв", "Усього шарів"),
    "var.progress": _s("Progress %", "Прогресс %", "Прогрес %"),
    "var.remaining": _s("Time left", "Осталось", "Залишилось"),
    "var.eta": _s("Done at", "Готово в", "Готово о"),
    "var.filament": _s("Filament", "Филамент", "Філамент"),
    "var.material": _s("Material", "Материал", "Матеріал"),
    "var.color": _s("Color", "Цвет", "Колір"),
    "var.nozzle": _s("Nozzle °C", "Сопло °C", "Сопло °C"),
    "var.bed": _s("Bed °C", "Стол °C", "Стіл °C"),
    "var.temps": _s("Temperatures", "Температуры", "Температури"),
    "var.printer": _s("Printer name", "Имя принтера", "Ім'я принтера"),
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
