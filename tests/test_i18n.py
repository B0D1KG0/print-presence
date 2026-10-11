from print_presence import i18n


def test_detect_from_env(monkeypatch):
    monkeypatch.setattr(i18n.sys, "platform", "linux")
    monkeypatch.setenv("LC_ALL", "ru_RU.UTF-8")
    assert i18n.detect() == "ru"
    monkeypatch.setenv("LC_ALL", "uk_UA.UTF-8")
    assert i18n.detect() == "uk"
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    assert i18n.detect() == "en"


def test_resolve_and_tr():
    assert i18n.resolve("en") == "en"
    assert i18n.resolve("ru") == "ru"
    i18n.set_language("ru")
    assert i18n.tr("set.found", n=2, added=1) == "Найдено: 2, добавлено новых: 1"
    i18n.set_language("uk")
    assert i18n.tr("tab.settings") == "Налаштування"
    i18n.set_language("en")
    assert i18n.tr("set.found", n=2, added=1) == "Found: 2, new added: 1"
    assert i18n.tr("no.such.key") == "no.such.key"


def test_every_string_has_both_languages():
    for key, entry in i18n.STRINGS.items():
        assert set(entry) == {"en", "ru", "uk"}, key
