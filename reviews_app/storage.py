"""Хранение отзывов: reviews.json + папка с картинками для каждого отзыва.

Структура папки с данными:
    reviews.json
    reviews/0001/source/img001.webp      — исходники, как их добавили
    reviews/0001/jpeg/review0001_img001.jpg — результат преобразования
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

IMAGE_EXTS = {".webp", ".jpg", ".jpeg", ".png", ".bmp", ".gif"}


def is_image_file(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in IMAGE_EXTS


@dataclass
class Review:
    id: int
    text: str = ""
    images: list[str] = field(default_factory=list)  # имена файлов в source/
    created: float = field(default_factory=time.time)

    def is_empty(self) -> bool:
        return not self.text.strip() and not self.images


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "reviews.json"
        self.reviews: list[Review] = []
        self.next_id = 1
        self.load()

    # ---------- файл базы ----------
    def load(self) -> None:
        if not self.db_path.exists():
            return
        data = json.loads(self.db_path.read_text(encoding="utf-8"))
        self.next_id = int(data.get("next_id", 1))
        self.reviews = [
            Review(
                id=int(r["id"]),
                text=r.get("text", ""),
                images=list(r.get("images", [])),
                created=float(r.get("created", time.time())),
            )
            for r in data.get("reviews", [])
        ]
        if self.reviews:
            self.next_id = max(self.next_id, max(r.id for r in self.reviews) + 1)

    def save(self) -> None:
        data = {"next_id": self.next_id, "reviews": [asdict(r) for r in self.reviews]}
        tmp = self.db_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.db_path)

    # ---------- отзывы ----------
    def get(self, review_id: int) -> Review | None:
        return next((r for r in self.reviews if r.id == review_id), None)

    def number(self, review: Review) -> int:
        return self.reviews.index(review) + 1

    def create(self) -> Review:
        r = Review(id=self.next_id)
        self.next_id += 1
        self.reviews.append(r)
        self.save()
        return r

    def delete(self, review: Review) -> None:
        shutil.rmtree(self.review_dir(review), ignore_errors=True)
        self.reviews.remove(review)
        self.save()

    # ---------- пути ----------
    def review_dir(self, review: Review) -> Path:
        return self.root / "reviews" / f"{review.id:04d}"

    def source_path(self, review: Review, name: str) -> Path:
        return self.review_dir(review) / "source" / name

    def jpeg_path(self, review: Review, name: str) -> Path:
        stem = Path(name).stem
        return self.review_dir(review) / "jpeg" / f"review{review.id:04d}_{stem}.jpg"

    # ---------- картинки ----------
    def add_images(self, review: Review, paths: list[str | Path]) -> int:
        src_dir = self.review_dir(review) / "source"
        src_dir.mkdir(parents=True, exist_ok=True)
        used = {Path(n).stem for n in review.images}
        n = 1
        added = 0
        for p in paths:
            p = Path(p)
            if not is_image_file(p):
                continue
            while f"img{n:03d}" in used:
                n += 1
            name = f"img{n:03d}{p.suffix.lower()}"
            used.add(f"img{n:03d}")
            shutil.copy2(p, src_dir / name)
            review.images.append(name)
            added += 1
        if added:
            self.save()
        return added

    def remove_image(self, review: Review, name: str) -> None:
        if name in review.images:
            review.images.remove(name)
        for p in (self.source_path(review, name), self.jpeg_path(review, name)):
            p.unlink(missing_ok=True)
        self.save()

    # ---------- преобразование ----------
    def pending_conversions(self) -> list[tuple[Path, Path]]:
        """Картинки, у которых JPEG ещё нет или он старее исходника."""
        result = []
        for r in self.reviews:
            for name in r.images:
                src, dst = self.source_path(r, name), self.jpeg_path(r, name)
                if not src.exists():
                    continue
                if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                    result.append((src, dst))
        return result
