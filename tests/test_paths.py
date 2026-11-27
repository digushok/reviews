import json

from reviews_app.paths import resolve_data_dir


def make_data(d, text="старый"):
    (d / "_исходники/0001").mkdir(parents=True)
    (d / "_исходники/0001/img001.webp").write_bytes(b"x")
    (d / "reviews.json").write_text(json.dumps({"reviews": [{"id": 1, "text": text}]}), encoding="utf-8")


def test_moves_legacy_data_to_documents(tmp_path):
    old = tmp_path / "exe_dir/ReviewsData"
    make_data(old)
    target = tmp_path / "Documents/ReviewsData"
    path, msg = resolve_data_dir(target, [old])
    assert path == target and msg
    assert (target / "_исходники/0001/img001.webp").exists()
    assert not old.exists()


def test_existing_documents_data_wins(tmp_path):
    old, target = tmp_path / "old", tmp_path / "new"
    make_data(old, "старый")
    make_data(target, "новый")
    path, msg = resolve_data_dir(target, [old])
    assert path == target and msg is None
    assert old.exists()  # ничего не трогаем


def test_fresh_install(tmp_path):
    path, msg = resolve_data_dir(tmp_path / "Documents/ReviewsData", [tmp_path / "nothing"])
    assert path == tmp_path / "Documents/ReviewsData" and msg is None
