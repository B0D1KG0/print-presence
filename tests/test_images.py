from PIL import Image

from print_presence import images


def test_to_tile_crops_and_rounds():
    im = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (80, 60), (238, 238, 238, 255)), (20, 20))
    tile = images.to_tile(im)
    assert tile.size == (80, 80)  # cropped to content and made square
    assert tile.getpixel((0, 0))[3] == 0  # rounded corner is transparent
    assert tile.getpixel((40, 40))[3] == 255


def test_ring_size():
    r = images.ring(36, "#00ae42", "#252a3a", size=96)
    assert r.size == (96, 96)
    assert r.getpixel((48, 48))[3] == 0  # hollow middle


def test_photo_falls_back_to_local_when_offline(tmp_path, monkeypatch):
    def offline(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(images, "_get", offline)
    local = tmp_path / "assets"
    local.mkdir()
    Image.new("RGBA", (10, 10), (1, 2, 3, 255)).save(local / "printer_p1s.png")
    art = images.PrinterArt(local, tmp_path / "cache", lambda: None)
    art.use_app("123")
    assert art.photo("printer_p1s").getpixel((5, 5)) == (1, 2, 3, 255)
    assert art.photo("unknown").size == (256, 256)  # neither remote nor local


def test_cached_photo_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_get", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    folder = tmp_path / "cache" / "123"
    folder.mkdir(parents=True)
    Image.new("RGBA", (50, 50), (9, 9, 9, 255)).save(folder / "printer_p1s-42.png")
    art = images.PrinterArt(tmp_path, tmp_path / "cache", lambda: None)
    art.use_app("123")
    assert art.photo("printer_p1s").getpixel((25, 25)) == (9, 9, 9, 255)
