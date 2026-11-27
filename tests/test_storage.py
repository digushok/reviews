from pathlib import Path

from PIL import Image

from reviews_app.imaging import convert_to_jpeg
from reviews_app.storage import Store


def make_webp(path: Path, alpha: bool = False) -> Path:
    mode, color = ("RGBA", (255, 0, 0, 0)) if alpha else ("RGB", (0, 128, 255))
    Image.new(mode, (40, 30), color).save(path, "WEBP")
    return path


def test_roundtrip_and_conversion(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    a = make_webp(src / "a.webp")
    b = make_webp(src / "b.webp", alpha=True)

    store = Store(tmp_path / "data")
    r = store.create()
    r.text = "Отличный товар"
    assert store.add_images(r, [a, b, src / "missing.webp"]) == 2
    store.save()

    store2 = Store(tmp_path / "data")
    r2 = store2.get(r.id)
    assert r2.text == "Отличный товар"
    assert r2.images == ["img001.webp", "img002.webp"]

    jobs = store2.pending_conversions()
    assert len(jobs) == 2
    for s, d in jobs:
        convert_to_jpeg(s, d)
    assert store2.pending_conversions() == []

    jpg = store2.jpeg_path(r2, "img002.webp")
    with Image.open(jpg) as im:
        assert im.format == "JPEG"
        assert im.getpixel((5, 5)) == (255, 255, 255)  # прозрачность -> белый

    store2.remove_image(r2, "img001.webp")
    assert not store2.jpeg_path(r2, "img001.webp").exists()
    store2.add_images(r2, [a])
    assert r2.images == ["img002.webp", "img001.webp"]  # освободившееся имя переиспользуется

    store2.delete(r2)
    assert not store2.review_dir(r2).exists()
    assert Store(tmp_path / "data").reviews == []
