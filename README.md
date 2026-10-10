# print-presence

Discord Rich Presence для 3D-принтеров: друзья в Discord видят, что ты печатаешь, на каком слое, сколько процентов готово и сколько осталось.

```
Играет в Bambu Lab P1S
Печатает: benchy
Слой 87/240 · 36%
⏱ осталось 01:12:00
```

Сейчас поддерживаются принтеры **Bambu Lab** (проверяется на P1S) через локальную сеть. Другие принтеры можно добавить отдельным модулем в `print_presence/printers/`.

> Неофициальный проект, не связан с Bambu Lab или Discord.

## Что нужно

- Windows (на macOS/Linux тоже работает, запуск через `python -m print_presence`)
- [Python 3.11+](https://www.python.org/downloads/) — при установке поставь галочку **Add python.exe to PATH**
- Discord **десктоп-приложение** (в браузере Rich Presence не работает), запущенное на том же ПК
- Принтер и ПК в одной локальной сети

## Настройка

### 1. Discord-приложение

1. Открой <https://discord.com/developers/applications> → **New Application**.
2. Имя приложения — это то, что видно после «Играет в», например `Bambu Lab P1S`.
3. На странице **General Information** скопируй **Application ID**.
4. **Rich Presence → Art Assets** — загрузи картинки (минимум 512×512) с такими именами:

   | Имя ассета | Что это |
   |---|---|
   | `printer` | большая картинка — фото принтера |
   | `printing` | значок «печатает» |
   | `paused` | значок «пауза» |
   | `finished` | значок «готово» |
   | `failed` | значок «ошибка» |
   | `idle` | значок «простой» |

   После загрузки Discord иногда показывает картинки только через 5–10 минут.

### 2. Данные принтера

- **IP и Access Code**: на экране принтера *Settings → WLAN* (значок Wi-Fi).
- **Серийный номер**: Bambu Studio → *Device* → *Update*, или на экране принтера.

### 3. Запуск

1. Скачай проект и запусти `start.bat`.
2. При первом запуске он создаст окружение, установит зависимости и откроет `config.toml` — заполни его и сохрани.
3. Запусти `start.bat` ещё раз.

`config.toml` хранится только у тебя и не попадает в git — там Access Code принтера.

## Если не подключается

- **`Printer refused connection` / `Not authorized`** — проверь IP и Access Code. Access Code меняется, если на принтере его обновить.
- Если данные точно верные, а принтер всё равно не пускает (новые прошивки Bambu ограничивают сторонний доступ): на принтере включи **LAN Only Mode**, а затем **Developer Mode**. Учти, что в LAN Only не работает облако и приложение Bambu Handy.
- **`Discord is not available`** — запусти Discord-приложение. Программа сама переподключится.
- Подробный лог: `start.bat -v`.

## Для разработки

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt pytest
python -m pytest
python -m print_presence -c config.toml -v
```

Добавить новый принтер: создай класс-наследник `Printer` в `print_presence/printers/`, который возвращает `PrinterStatus`, и зарегистрируй его в `printers/__init__.py`.

## Лицензия

MIT
