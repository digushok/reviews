"""Работа с картинками: WebP/PNG/... -> JPEG и миниатюры для интерфейса."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageOps

JPEG_QUALITY = 92


def _to_rgb(im: Image.Image) -> Image.Image:
    """Прозрачность заливаем белым: в JPEG альфа-канала нет."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def open_image(path: str | Path) -> Image.Image:
    with Image.open(path) as im:
        im.seek(0)  # у анимированных webp берём первый кадр
        im.load()
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        return im.copy()


def convert_to_jpeg(src: str | Path, dst: str | Path, quality: int = JPEG_QUALITY) -> None:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = _to_rgb(open_image(src))
    tmp = dst.with_name(dst.name + ".tmp")
    im.save(tmp, "JPEG", quality=quality, optimize=True)
    os.replace(tmp, dst)


def load_qimage(path: str | Path, max_side: int):
    """Миниатюра в виде QImage (через Pillow, чтобы не зависеть от плагинов Qt)."""
    from PySide6.QtGui import QImage

    im = open_image(path)
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    return QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()
