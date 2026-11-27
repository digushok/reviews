from reviews_app import updater


def test_versions():
    assert updater.parse_version("v1.2.0") == (1, 2, 0)
    assert updater.parse_version("1.10") == (1, 10, 0)
    assert updater.is_newer("v1.10.0", "1.9.3")
    assert not updater.is_newer("v1.2.0", "1.2.0")
    assert not updater.is_newer("1.1.9", "1.2.0")


def test_parse_release():
    rel = updater.parse_release({
        "tag_name": "v1.3.0", "html_url": "https://x/rel", "body": " Новое ",
        "assets": [{"name": "other.zip", "browser_download_url": "z"},
                   {"name": "Reviews.exe", "browser_download_url": "https://x/Reviews.exe", "size": 5}],
    })
    assert (rel.version, rel.url, rel.size, rel.notes) == ("1.3.0", "https://x/Reviews.exe", 5, "Новое")
    assert updater.parse_release({"tag_name": "v2", "assets": []}).url is None


def test_swap_files(tmp_path):
    exe = tmp_path / "Reviews.exe"
    exe.write_bytes(b"MZold")
    new = updater.new_path(exe)
    new.write_bytes(b"MZnew")
    updater.old_path(exe).write_bytes(b"stale")
    updater.swap_files(exe, new)
    assert exe.read_bytes() == b"MZnew"
    assert updater.old_path(exe).read_bytes() == b"MZold"
    assert not new.exists()


def test_download_local(tmp_path):
    src = tmp_path / "f.exe"
    src.write_bytes(b"MZ" + b"x" * 300000)
    seen = []
    dst = tmp_path / "out.exe"
    updater.download(src.as_uri(), dst, progress=lambda d, t: seen.append(d))
    assert dst.read_bytes() == src.read_bytes() and seen[-1] == 300002

    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"<html>")
    try:
        updater.download(bad.as_uri(), tmp_path / "o2.exe")
        assert False
    except IOError:
        pass
    assert not (tmp_path / "o2.exe").exists()
