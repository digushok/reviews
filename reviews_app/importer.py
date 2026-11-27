"""Достаём картинки из того, что перетащили или вставили (Ctrl+V).

Источники, по порядку:
1. файлы с диска (проводник);
2. «виртуальный файл» Windows (FileContents) — так отдают картинку некоторые браузеры;
3. ссылки на картинку: <img src> из HTML и URL из перетаскивания — скачиваем;
4. просто данные картинки (копирование в буфер, часть браузеров).
"""
from __future__ import annotations

import base64
import html as html_lib
import io
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .storage import is_image_file

FILECONTENTS = 'application/x-qt-windows-mime;value="FileContents"'
IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1", re.I | re.S)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_BYTES = 50 * 1024 * 1024
FMT_EXT = {"WEBP": ".webp", "JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "BMP": ".bmp"}


@dataclass
class DropData:
    """Снимок содержимого перетаскивания: берём всё нужное сразу, обрабатываем потом."""

    local_files: list[str] = field(default_factory=list)
    file_contents: bytes | None = None
    img_srcs: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    image: object | None = None  # QImage

    def has_anything(self, strict: bool = False) -> bool:
        if self.local_files or self.file_contents or self.img_srcs or self.image is not None:
            return True
        return bool(self.urls) and not strict


def _is_remote(u: str) -> bool:
    return u.lower().startswith(("http://", "https://", "data:image/"))


def snapshot(mime, read_payload: bool = True) -> DropData:
    """read_payload=False — только быстрая проверка (для dragEnter), без чтения данных."""
    d = DropData()
    if mime is None:
        return d
    if mime.hasUrls():
        for u in mime.urls():
            if u.isLocalFile():
                if is_image_file(u.toLocalFile()):
                    d.local_files.append(u.toLocalFile())
            elif _is_remote(u.toString()):
                d.urls.append(u.toString())
    if mime.hasText():
        t = mime.text().strip()
        if "\n" not in t and _is_remote(t) and t not in d.urls:
            d.urls.append(t)
    if mime.hasHtml():
        for _, src in IMG_SRC_RE.findall(mime.html()):
            src = html_lib.unescape(src.strip())
            if src.startswith("//"):
                src = "https:" + src
            if _is_remote(src) and src not in d.img_srcs:
                d.img_srcs.append(src)
    if FILECONTENTS in mime.formats():
        d.file_contents = b"?"  # отметка «есть»; сами байты читаем ниже
        if read_payload:
            try:
                d.file_contents = bytes(mime.data(FILECONTENTS)) or None
            except Exception:
                d.file_contents = None
    if mime.hasImage():
        d.image = True
        if read_payload:
            try:
                img = mime.imageData()
                d.image = img if img is not None and not img.isNull() else None
            except Exception:
                d.image = None
    return d


def save_bytes(data: bytes, workdir: Path, stem: str) -> Path | None:
    """Сохранить байты, если это картинка. Неизвестные форматы перекладываем в PNG."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            im.load()
            workdir.mkdir(parents=True, exist_ok=True)
            if fmt in FMT_EXT:
                p = workdir / f"{stem}{FMT_EXT[fmt]}"
                p.write_bytes(data)
            else:
                p = workdir / f"{stem}.png"
                im.save(p, "PNG")
            return p
    except Exception:
        return None


def download(url: str, timeout: float = 20) -> bytes:
    if url.lower().startswith("data:"):
        header, _, payload = url.partition(",")
        if ";base64" in header.lower():
            return base64.b64decode(payload)
        return urllib.parse.unquote_to_bytes(payload)
    parts = urllib.parse.urlsplit(url)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
            "Referer": f"{parts.scheme}://{parts.netloc}/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("файл слишком большой")
    return data


def extract_images(d: DropData, workdir: Path) -> tuple[list[Path], list[str]]:
    """Вернуть пути к картинкам, готовым для добавления, и список ошибок."""
    if d.local_files:
        return [Path(p) for p in d.local_files], []

    out: list[Path] = []
    errors: list[str] = []
    n = 0

    def keep(data: bytes) -> bool:
        nonlocal n
        n += 1
        p = save_bytes(data, workdir, f"drop{n:03d}")
        if p:
            out.append(p)
        return p is not None

    if isinstance(d.file_contents, bytes) and keep(d.file_contents):
        return out, errors

    def fetch(urls: list[str]) -> None:
        for u in urls:
            try:
                if not keep(download(u)):
                    errors.append(f"{u[:120]}: это не картинка")
            except Exception as e:
                errors.append(f"{u[:120]}: {e}")

    fetch(d.img_srcs)
    if not out:
        fetch([u for u in d.urls if u not in d.img_srcs])
    if not out and d.image is not None and hasattr(d.image, "save"):
        workdir.mkdir(parents=True, exist_ok=True)
        p = workdir / "clipboard.png"
        if d.image.save(str(p), "PNG"):
            out.append(p)
    if out:
        errors = []  # что-то получилось — частные неудачи (ссылка на страницу и т.п.) не важны
    return out, errors
