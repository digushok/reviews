"""Хранение товаров и отзывов.

Папка с данными:
    reviews.json                       — товары, отзывы, тексты
    _исходники/0007/img001.webp        — картинки как их добавили (служебная папка)
    Отзывы/                            — результат «Преобразовать в JPEG»:
        <Товар>/
            Отзыв 1/
                <Товар> 1.jpg
                <Товар> 2.jpg
                Текст отзыва.txt
            Отзыв 2/ ...

Папку «Отзывы» программа поддерживает в актуальном виде сама: номера и имена
пересчитываются, лишние .jpg/.txt удаляются.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

IMAGE_EXTS = {".webp", ".jpg", ".jpeg", ".png", ".bmp", ".gif"}
SOURCES_DIR = "_исходники"
EXPORT_DIR = "Отзывы"
TEXT_NAME = "Текст отзыва.txt"
MANIFEST = ".manifest.json"
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def is_image_file(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in IMAGE_EXTS


def safe_name(name: str) -> str:
    """Имя, допустимое для папки/файла в Windows."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    s = re.sub(r"\s+", " ", s).strip().rstrip(". ")
    if not s:
        s = "Без названия"
    if s.split(".")[0].upper() in _WIN_RESERVED:
        s = "_" + s
    return s[:80].rstrip(". ")


@dataclass
class Product:
    id: int
    name: str


@dataclass
class Review:
    id: int
    product_id: int = 0
    text: str = ""
    images: list[str] = field(default_factory=list)  # имена файлов в _исходники/<id>/
    created: float = field(default_factory=time.time)

    def is_empty(self) -> bool:
        return not self.text.strip() and not self.images


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "reviews.json"
        self.products: list[Product] = []
        self.reviews: list[Review] = []
        self.next_id = 1
        self.next_product_id = 1
        self.load()

    # ---------- файл базы ----------
    def load(self) -> None:
        data = {}
        if self.db_path.exists():
            data = json.loads(self.db_path.read_text(encoding="utf-8"))
        self.next_id = int(data.get("next_id", 1))
        self.next_product_id = int(data.get("next_product_id", 1))
        self.products = [Product(int(p["id"]), p["name"]) for p in data.get("products", [])]
        self.reviews = [
            Review(
                id=int(r["id"]),
                product_id=int(r.get("product_id", 0)),
                text=r.get("text", ""),
                images=list(r.get("images", [])),
                created=float(r.get("created", time.time())),
            )
            for r in data.get("reviews", [])
        ]
        if self.reviews:
            self.next_id = max(self.next_id, max(r.id for r in self.reviews) + 1)
        if self.products:
            self.next_product_id = max(self.next_product_id, max(p.id for p in self.products) + 1)
        self._migrate()

    def _migrate(self) -> None:
        """Данные версии 1.0.0: отзывы без товара, картинки в reviews/NNNN/source."""
        changed = False
        orphans = [r for r in self.reviews if self.product(r.product_id) is None]
        if orphans:
            p = self.products[0] if self.products else self._new_product("Товар 1")
            for r in orphans:
                r.product_id = p.id
            changed = True
        old = self.root / "reviews"
        if old.is_dir():
            for r in self.reviews:
                src = old / f"{r.id:04d}" / "source"
                if src.is_dir():
                    dst = self.source_dir(r)
                    dst.mkdir(parents=True, exist_ok=True)
                    for f in src.iterdir():
                        if not (dst / f.name).exists():
                            shutil.move(str(f), dst / f.name)
            shutil.rmtree(old, ignore_errors=True)
            changed = True
        if changed:
            self.save()

    def save(self) -> None:
        data = {
            "version": 2,
            "next_id": self.next_id,
            "next_product_id": self.next_product_id,
            "products": [asdict(p) for p in self.products],
            "reviews": [asdict(r) for r in self.reviews],
        }
        tmp = self.db_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.db_path)

    # ---------- товары ----------
    def product(self, product_id: int) -> Product | None:
        return next((p for p in self.products if p.id == product_id), None)

    def _check_name(self, name: str, exclude: Product | None = None) -> str:
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            raise ValueError("Название товара не может быть пустым")
        folder = safe_name(name).lower()
        for p in self.products:
            if p is not exclude and safe_name(p.name).lower() == folder:
                raise ValueError(f"Товар «{p.name}» уже есть")
        return name

    def _new_product(self, name: str) -> Product:
        p = Product(self.next_product_id, name)
        self.next_product_id += 1
        self.products.append(p)
        return p

    def add_product(self, name: str) -> Product:
        p = self._new_product(self._check_name(name))
        self.save()
        return p

    def rename_product(self, p: Product, name: str) -> None:
        p.name = self._check_name(name, exclude=p)
        self.save()

    def delete_product(self, p: Product) -> None:
        for r in self.reviews_of(p):
            shutil.rmtree(self.source_dir(r), ignore_errors=True)
            self.reviews.remove(r)
        self.products.remove(p)
        shutil.rmtree(self.export_root / safe_name(p.name), ignore_errors=True)
        self.save()

    def ensure_product(self) -> Product:
        if not self.products:
            self._new_product("Товар 1")
            self.save()
        return self.products[0]

    # ---------- отзывы ----------
    def get(self, review_id: int) -> Review | None:
        return next((r for r in self.reviews if r.id == review_id), None)

    def reviews_of(self, p: Product | int) -> list[Review]:
        pid = p.id if isinstance(p, Product) else p
        return [r for r in self.reviews if r.product_id == pid]

    def number(self, review: Review) -> int:
        """Номер отзыва внутри своего товара (с 1)."""
        return self.reviews_of(review.product_id).index(review) + 1

    def create(self, product: Product) -> Review:
        r = Review(id=self.next_id, product_id=product.id)
        self.next_id += 1
        self.reviews.append(r)
        self.save()
        return r

    def delete(self, review: Review) -> None:
        shutil.rmtree(self.source_dir(review), ignore_errors=True)
        self.reviews.remove(review)
        self.save()

    # ---------- пути ----------
    @property
    def export_root(self) -> Path:
        return self.root / EXPORT_DIR

    def source_dir(self, review: Review) -> Path:
        return self.root / SOURCES_DIR / f"{review.id:04d}"

    def source_path(self, review: Review, name: str) -> Path:
        return self.source_dir(review) / name

    def export_dir(self, review: Review) -> Path:
        p = self.product(review.product_id)
        return self.export_root / safe_name(p.name if p else "") / f"Отзыв {self.number(review)}"

    def jpeg_path(self, review: Review, name: str) -> Path:
        p = self.product(review.product_id)
        k = review.images.index(name) + 1
        return self.export_dir(review) / f"{safe_name(p.name if p else '')} {k}.jpg"

    # ---------- картинки ----------
    def add_images(self, review: Review, paths: list[str | Path]) -> int:
        src_dir = self.source_dir(review)
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
        self.source_path(review, name).unlink(missing_ok=True)
        self.save()

    # ---------- выгрузка в папку «Отзывы» ----------
    def _manifest(self) -> dict[str, str]:
        try:
            return json.loads((self.export_root / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_manifest(self, m: dict[str, str]) -> None:
        self.export_root.mkdir(parents=True, exist_ok=True)
        (self.export_root / MANIFEST).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")

    def _plan(self, reviews: list[Review] | None = None) -> list[tuple[Path, Path, str]]:
        """(исходник, jpeg, ключ). Ключ меняется, если поменялся исходник."""
        plan = []
        for r in reviews if reviews is not None else self.reviews:
            if r.is_empty():
                continue
            for name in r.images:
                src = self.source_path(r, name)
                if not src.exists():
                    continue
                st = src.stat()
                plan.append((src, self.jpeg_path(r, name), f"{r.id}/{name}/{st.st_mtime_ns}/{st.st_size}"))
        return plan

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.export_root).as_posix()

    def pending_conversions(self, reviews: list[Review] | None = None) -> list[tuple[Path, Path, str]]:
        m = self._manifest()
        return [(s, d, k) for s, d, k in self._plan(reviews) if m.get(self._rel(d)) != k or not d.exists()]

    def export(
        self,
        convert: Callable[[Path, Path], None],
        reviews: list[Review] | None = None,
        progress: Callable[[int, int], bool] | None = None,
    ) -> list[str]:
        """Привести папку «Отзывы» в порядок. reviews=None — всё, с уборкой лишнего.

        progress(i, total) -> False, чтобы прервать. Возвращает список ошибок.
        """
        errors: list[str] = []
        m = self._manifest()
        jobs = self.pending_conversions(reviews)
        for i, (src, dst, key) in enumerate(jobs):
            if progress and progress(i, len(jobs)) is False:
                break
            try:
                convert(src, dst)
                m[self._rel(dst)] = key
            except Exception as e:  # битый файл не должен ронять всё
                m.pop(self._rel(dst), None)
                errors.append(f"{src.name}: {e}")
        if progress:
            progress(len(jobs), len(jobs))

        # тексты отзывов
        for r in reviews if reviews is not None else self.reviews:
            if r.is_empty():
                continue
            t = self.export_dir(r) / TEXT_NAME
            content = r.text.strip()
            if content:
                old = t.read_text(encoding="utf-8-sig") if t.exists() else None
                if old != content:
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_text(content, encoding="utf-8-sig")
            else:
                t.unlink(missing_ok=True)

        if reviews is None:
            self._cleanup(m)
        self._save_manifest(m)
        return errors

    def _cleanup(self, m: dict[str, str]) -> None:
        """Удалить из «Отзывы» наши .jpg/.txt, которых больше не должно быть, и пустые папки."""
        expected = {d for _, d, _ in self._plan()}
        expected |= {self.export_dir(r) / TEXT_NAME for r in self.reviews if not r.is_empty() and r.text.strip()}
        root = self.export_root
        if not root.exists():
            return
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in (".jpg", ".txt") and f not in expected:
                f.unlink(missing_ok=True)
        for rel in list(m):
            if (root / rel) not in expected:
                del m[rel]
        for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                d.rmdir()  # только пустые
            except OSError:
                pass
