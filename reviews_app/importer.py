"""Достаём картинки из того, что перетащили или вставили (Ctrl+V).

Источники, по порядку:
1. файлы с диска (проводник; браузер тоже иногда отдаёт временный файл);
2. «виртуальный файл» Windows (FileContents) — так отдают картинку некоторые браузеры;
3. ссылки на картинку: src / data-src / srcset из HTML, URL и текст-ссылка — скачиваем;
4. просто данные картинки (копирование в буфер, часть браузеров).

Если ничего не вышло — describe() рассказывает, что именно пришло (для диагностики).
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

from .storage import IMAGE_EXTS

FILECONTENTS = 'application/x-qt-windows-mime;value="FileContents"'
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
ATTR_RE = re.compile(r"""\b(src|data-src|data-original|data-lazy-src|srcset|data-srcset)\s*=\s*(["'])(.*?)\2""", re.I | re.S)
URL_IN_TEXT_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_BYTES = 50 * 1024 * 1024
MIN_SIDE = 40  # меньше — это иконка/заглушка/счётчик, если есть что-то крупнее
FMT_EXT = {"WEBP": ".webp", "JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "BMP": ".bmp"}


@dataclass
class DropData:
    """Снимок содержимого перетаскивания: берём всё нужное сразу, обрабатываем потом."""

    local_files: list[str] = field(default_factory=list)  # картинки по расширению
    other_files: list[str] = field(default_factory=list)  # прочие файлы — проверим по содержимому
    file_contents: bytes | None = None
    img_srcs: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    image: object | None = None  # QImage
    # для диагностики
    formats: list[str] = field(default_factory=list)
    text: str = ""
    html: str = ""

    def has_anything(self, strict: bool = False) -> bool:
        if self.local_files or self.file_contents or self.img_srcs or self.image is not None:
            return True
        return bool(self.urls or self.other_files) and not strict

    def describe(self) -> str:
        lines = ["Форматы: " + (", ".join(self.formats) or "—")]
        for title, items in (("Файлы", self.local_files + self.other_files), ("Ссылки на картинки из HTML", self.img_srcs),
                             ("Ссылки", self.urls)):
            if items:
                lines.append(f"{title}:")
                lines += [f"  {x[:300]}" for x in items[:10]]
        if self.file_contents:
            lines.append(f"FileContents: {len(self.file_contents)} байт")
        if self.image is not None:
            lines.append("Есть данные картинки (image)")
        if self.text:
            lines.append("Текст: " + self.text[:300].replace("\n", " ⏎ "))
        if self.html:
            lines.append("HTML: " + re.sub(r"\s+", " ", self.html)[:1500])
        return "\n".join(lines)


def _is_remote(u: str) -> bool:
    return u.lower().startswith(("http://", "https://", "data:image/"))


def _norm(u: str) -> str:
    u = html_lib.unescape(u.strip())
    return "https:" + u if u.startswith("//") else u


def img_candidates(html: str) -> list[str]:
    """Все адреса картинок из тегов <img>: src, data-src, srcset (самый крупный — первым)."""
    out: list[str] = []
    for tag in IMG_TAG_RE.findall(html):
        found: list[str] = []
        for name, _, value in ATTR_RE.findall(tag):
            if "srcset" in name.lower():
                best, best_w = None, -1.0
                for part in value.split(","):
                    bits = part.strip().split()
                    if not bits:
                        continue
                    w = 1.0
                    if len(bits) > 1:
                        try:
                            w = float(bits[1].rstrip("wxWX"))
                        except ValueError:
                            pass
                    if w > best_w:
                        best, best_w = bits[0], w
                if best:
                    found.insert(0, best)
            else:
                found.append(value)
        for u in found:
            u = _norm(u)
            if _is_remote(u) and u not in out:
                out.append(u)
    return out


def snapshot(mime, read_payload: bool = True) -> DropData:
    """read_payload=False — только быстрая проверка (для dragEnter), без чтения данных."""
    d = DropData()
    if mime is None:
        return d
    try:
        d.formats = list(mime.formats())
    except Exception:
        pass
    if mime.hasUrls():
        for u in mime.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if Path(p).suffix.lower() in IMAGE_EXTS:
                    d.local_files.append(p)
                elif Path(p).is_file():
                    d.other_files.append(p)
            elif _is_remote(u.toString()):
                d.urls.append(u.toString())
    if mime.hasText():
        d.text = mime.text()
        for t in URL_IN_TEXT_RE.findall(d.text)[:5]:
            if t not in d.urls:
                d.urls.append(t)
    if mime.hasHtml():
        d.html = mime.html()
        d.img_srcs = img_candidates(d.html)
    if FILECONTENTS in d.formats:
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


def image_info(data: bytes) -> tuple[str, int, int] | None:
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            return (im.format or "").upper(), im.width, im.height
    except Exception:
        return None


def save_bytes(data: bytes, workdir: Path, stem: str) -> Path | None:
    """Сохранить байты, если это картинка. Неизвестные форматы перекладываем в PNG."""
    info = image_info(data)
    if info is None:
        return None
    fmt = info[0]
    workdir.mkdir(parents=True, exist_ok=True)
    if fmt in FMT_EXT:
        p = workdir / f"{stem}{FMT_EXT[fmt]}"
        p.write_bytes(data)
    else:
        p = workdir / f"{stem}.png"
        with Image.open(io.BytesIO(data)) as im:
            im.save(p, "PNG")
    return p


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

    found: list[tuple[bytes, int]] = []  # (данные, меньшая сторона)
    errors: list[str] = []

    def take(data: bytes | None) -> bool:
        info = image_info(data) if data else None
        if info is None:
            return False
        found.append((data, min(info[1], info[2])))
        return True

    for p in d.other_files:  # файл без «картиночного» расширения — смотрим по содержимому
        try:
            take(Path(p).read_bytes())
        except OSError as e:
            errors.append(f"{p}: {e}")

    if not found and isinstance(d.file_contents, bytes):
        take(d.file_contents)

    def fetch(urls: list[str]) -> None:
        for u in urls:
            try:
                if not take(download(u)):
                    errors.append(f"{u[:150]}: по ссылке не картинка (страница сайта?)")
            except Exception as e:
                errors.append(f"{u[:150]}: {e}")

    if not any(side >= MIN_SIDE for _, side in found):
        fetch(d.img_srcs)
    if not any(side >= MIN_SIDE for _, side in found):
        fetch([u for u in d.urls if u not in d.img_srcs])
    if not any(side >= MIN_SIDE for _, side in found) and d.image is not None and hasattr(d.image, "save"):
        from PySide6.QtCore import QBuffer, QIODevice

        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        d.image.save(buf, "PNG")
        take(bytes(buf.data()))

    # крошечные картинки (заглушки, иконки) выбрасываем, если есть нормальные
    if any(side >= MIN_SIDE for _, side in found):
        found = [(b, s) for b, s in found if s >= MIN_SIDE]
    out: list[Path] = []
    seen: set[bytes] = set()
    for i, (data, _) in enumerate(found, 1):
        key = data[:4096] + len(data).to_bytes(8, "little")
        if key in seen:
            continue
        seen.add(key)
        p = save_bytes(data, workdir, f"drop{i:03d}")
        if p:
            out.append(p)
    if out:
        errors = []  # что-то получилось — частные неудачи (ссылка на страницу и т.п.) не важны
    return out, errors
