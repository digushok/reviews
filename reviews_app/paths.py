"""Где хранятся данные: «Документы\\ReviewsData» (с переносом старой папки рядом с exe)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DATA_NAME = "ReviewsData"


def documents_dir() -> Path:
    """Настоящая папка «Документы» (учитывает перенос в OneDrive и т.п.)."""
    try:
        from PySide6.QtCore import QStandardPaths

        loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if loc:
            return Path(loc)
    except Exception:
        pass
    return Path.home() / "Documents"


def legacy_dirs() -> list[Path]:
    """Где данные лежали в версиях до 1.2.0 — рядом с exe."""
    if getattr(sys, "frozen", False):
        return [Path(sys.executable).resolve().parent / DATA_NAME]
    return []


def resolve_data_dir(target: Path, legacy: list[Path]) -> tuple[Path, str | None]:
    """Вернуть папку данных и сообщение, если старые данные были перенесены."""
    if (target / "reviews.json").exists():
        return target, None
    for old in legacy:
        if not (old / "reviews.json").exists() or old.resolve() == target.resolve():
            continue
        if target.exists() and any(target.iterdir()):
            return target, None  # там уже что-то есть — не трогаем
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(old, target, dirs_exist_ok=True)
        except OSError as e:
            shutil.rmtree(target, ignore_errors=True)
            return old, f"Не удалось перенести данные в «{target}» ({e}). Пока работаем со старой папкой «{old}»."
        shutil.rmtree(old, ignore_errors=True)
        return target, f"Ваши отзывы перенесены в папку:\n{target}\n\nТеперь exe можно держать где угодно."
    return target, None


def default_data_dir() -> tuple[Path, str | None]:
    return resolve_data_dir(documents_dir() / DATA_NAME, legacy_dirs())
