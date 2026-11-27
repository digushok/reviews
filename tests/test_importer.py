import base64
import io
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage

from reviews_app.importer import extract_images, snapshot


def webp_bytes(color=(10, 200, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), color).save(buf, "WEBP")
    return buf.getvalue()


def serve(directory):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_local_file(tmp_path):
    f = tmp_path / "a.webp"
    f.write_bytes(webp_bytes())
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(f))])
    paths, errors = extract_images(snapshot(m), tmp_path / "w")
    assert paths == [f] and not errors


def test_browser_drag_downloads_img_src_and_ignores_page_link(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "pic.webp").write_bytes(webp_bytes())
    (site / "page.html").write_text("<html>page</html>")
    srv, base = serve(site)
    try:
        m = QMimeData()
        # как Chrome: ссылка на страницу (картинка внутри <a>), html с <img>, текст = ссылка
        m.setUrls([QUrl(f"{base}/page.html")])
        m.setHtml(f'<a href="{base}/page.html"><img alt="x" src="{base}/pic.webp?a=1&amp;b=2"></a>')
        m.setText(f"{base}/page.html")
        d = snapshot(m)
        assert d.has_anything()
        paths, errors = extract_images(d, tmp_path / "w")
        assert len(paths) == 1 and paths[0].suffix == ".webp" and not errors
        with Image.open(paths[0]) as im:
            assert im.format == "WEBP"
    finally:
        srv.shutdown()


def test_plain_image_url_and_data_url(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "x").write_bytes(webp_bytes())  # без расширения — формат определяется по содержимому
    srv, base = serve(site)
    try:
        m = QMimeData()
        m.setUrls([QUrl(f"{base}/x")])
        paths, _ = extract_images(snapshot(m), tmp_path / "w1")
        assert len(paths) == 1 and paths[0].suffix == ".webp"
    finally:
        srv.shutdown()

    m = QMimeData()
    m.setHtml('<img src="data:image/webp;base64,' + base64.b64encode(webp_bytes()).decode() + '">')
    paths, _ = extract_images(snapshot(m), tmp_path / "w2")
    assert len(paths) == 1


def test_image_data_only_and_failures(tmp_path):
    img = QImage(8, 8, QImage.Format_RGB32)
    img.fill(0xFF3366)
    m = QMimeData()
    m.setImageData(img)
    paths, _ = extract_images(snapshot(m), tmp_path / "w")
    assert len(paths) == 1 and paths[0].suffix == ".png"

    m = QMimeData()
    m.setUrls([QUrl("http://127.0.0.1:9/nothing.webp")])
    paths, errors = extract_images(snapshot(m), tmp_path / "w2")
    assert paths == [] and errors

    m = QMimeData()
    m.setText("просто текст")
    assert not snapshot(m).has_anything()


def gif_1x1() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, "GIF")
    return "data:image/gif;base64," + base64.b64encode(buf.getvalue()).decode()


def test_lazy_placeholder_is_skipped_and_real_image_taken(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    big = io.BytesIO()
    Image.new("RGB", (300, 200), (1, 2, 3)).save(big, "WEBP")
    (site / "photo.jpeg").write_bytes(big.getvalue())  # как у Ozon: .jpeg, а внутри WebP
    (site / "small.webp").write_bytes(webp_bytes())
    srv, base = serve(site)
    try:
        m = QMimeData()
        m.setHtml(
            f'<div><img src="{gif_1x1()}" data-src="{base}/photo.jpeg" '
            f'srcset="{base}/small.webp 100w, {base}/photo.jpeg 800w"></div>'
        )
        paths, errors = extract_images(snapshot(m), tmp_path / "w")
        assert len(paths) == 1, paths
        with Image.open(paths[0]) as im:
            assert im.format == "WEBP" and im.size == (300, 200)
    finally:
        srv.shutdown()


def test_url_only_in_text_and_file_without_extension(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "p.jpeg").write_bytes(webp_bytes())
    srv, base = serve(site)
    try:
        m = QMimeData()
        m.setText(f"Фото: {base}/p.jpeg")
        paths, _ = extract_images(snapshot(m), tmp_path / "w")
        assert len(paths) == 1
    finally:
        srv.shutdown()

    f = tmp_path / "noext"
    f.write_bytes(webp_bytes())
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(f))])
    paths, _ = extract_images(snapshot(m), tmp_path / "w2")
    assert len(paths) == 1 and paths[0].suffix == ".webp"


def test_describe_for_diagnostics():
    m = QMimeData()
    m.setText("https://www.ozon.ru/product/123/")
    m.setHtml('<a href="https://www.ozon.ru/product/123/">товар</a>')
    text = snapshot(m).describe()
    assert "text/html" in text and "ozon.ru/product/123" in text
