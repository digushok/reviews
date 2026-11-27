import json
from pathlib import Path

import pytest
from PIL import Image

from reviews_app.imaging import convert_to_jpeg
from reviews_app.storage import Store, safe_name


def make_webp(path: Path, color=(0, 128, 255), alpha: bool = False) -> Path:
    mode, c = ("RGBA", (255, 0, 0, 0)) if alpha else ("RGB", color)
    Image.new(mode, (40, 30), c).save(path, "WEBP")
    return path


def tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")}


def test_products_reviews_and_export_tree(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    imgs = [make_webp(src / f"{i}.webp", (i * 40, 10, 10)) for i in range(4)]
    clear = make_webp(src / "alpha.webp", alpha=True)

    store = Store(tmp_path / "data")
    kettle = store.add_product("Чайник Bosch")
    mug = store.add_product('Кружка 300 мл "Лес"')
    with pytest.raises(ValueError):
        store.add_product("чайник bosch")

    r1 = store.create(kettle)
    r1.text = "Отличный чайник"
    store.add_images(r1, [imgs[0], imgs[1]])
    r2 = store.create(kettle)
    r2.text = "Шумный"
    store.add_images(r2, [clear])
    r3 = store.create(mug)
    store.add_images(r3, [imgs[2], imgs[3]])
    store.create(kettle)  # пустой — в выгрузку не попадает
    store.save()

    assert store.export(convert_to_jpeg) == []
    out = store.export_root
    mug_dir = safe_name(mug.name)
    assert mug_dir == "Кружка 300 мл Лес"
    assert tree(out) == {
        "Чайник Bosch/Отзыв 1/Чайник Bosch 1.jpg",
        "Чайник Bosch/Отзыв 1/Чайник Bosch 2.jpg",
        "Чайник Bosch/Отзыв 1/Текст отзыва.txt",
        "Чайник Bosch/Отзыв 2/Чайник Bosch 1.jpg",
        "Чайник Bosch/Отзыв 2/Текст отзыва.txt",
        f"{mug_dir}/Отзыв 1/{mug_dir} 1.jpg",
        f"{mug_dir}/Отзыв 1/{mug_dir} 2.jpg",
    }
    assert (out / "Чайник Bosch/Отзыв 1/Текст отзыва.txt").read_text(encoding="utf-8-sig") == "Отличный чайник"
    with Image.open(out / "Чайник Bosch/Отзыв 2/Чайник Bosch 1.jpg") as im:
        assert im.format == "JPEG" and im.getpixel((5, 5)) == (255, 255, 255)
    assert store.pending_conversions() == []

    # удалили первый отзыв -> второй стал «Отзыв 1», содержимое пересобрано
    store.delete(r1)
    assert store.pending_conversions()  # номер сменился — нужно пересобрать
    store.export(convert_to_jpeg)
    assert {p for p in tree(out) if p.startswith("Чайник")} == {
        "Чайник Bosch/Отзыв 1/Чайник Bosch 1.jpg",
        "Чайник Bosch/Отзыв 1/Текст отзыва.txt",
    }
    with Image.open(out / "Чайник Bosch/Отзыв 1/Чайник Bosch 1.jpg") as im:
        assert im.getpixel((5, 5)) == (255, 255, 255)  # это картинка бывшего отзыва 2
    assert (out / "Чайник Bosch/Отзыв 1/Текст отзыва.txt").read_text(encoding="utf-8-sig") == "Шумный"

    # убрали фото -> нумерация сдвигается
    store.remove_image(r3, r3.images[0])
    store.rename_product(mug, "Кружка")
    store.export(convert_to_jpeg)
    assert {p for p in tree(out) if not p.startswith("Чайник")} == {"Кружка/Отзыв 1/Кружка 1.jpg"}

    # перезапуск — всё на месте
    s2 = Store(tmp_path / "data")
    assert [p.name for p in s2.products] == ["Чайник Bosch", "Кружка"]
    assert s2.pending_conversions() == []

    s2.delete_product(s2.products[1])
    assert not (out / "Кружка").exists()
    assert len(s2.reviews) == 2


def test_migrates_v1_data(tmp_path):
    root = tmp_path / "data"
    (root / "reviews/0001/source").mkdir(parents=True)
    make_webp(root / "reviews/0001/source/img001.webp")
    (root / "reviews.json").write_text(json.dumps(
        {"next_id": 2, "reviews": [{"id": 1, "text": "старый", "images": ["img001.webp"]}]}), encoding="utf-8")
    s = Store(root)
    assert [p.name for p in s.products] == ["Товар 1"]
    r = s.reviews[0]
    assert r.product_id == s.products[0].id and s.source_path(r, "img001.webp").exists()
    assert not (root / "reviews").exists()


def test_safe_name():
    assert safe_name('a/b:c*?"<>|') == "a b c"
    assert safe_name("  CON ") == "_CON"
    assert safe_name("...") == "Без названия"
