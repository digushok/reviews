"""Обновление программы из релизов GitHub.

Работающий exe в Windows нельзя перезаписать, но можно переименовать. Поэтому:
скачиваем Reviews.new.exe → текущий переименовываем в Reviews.old.exe →
новый ставим на место Reviews.exe → запускаем его и закрываемся.
Reviews.old.exe удаляется при следующем запуске.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = "digushok/reviews"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_NAME = "Reviews.exe"
USER_AGENT = "reviews-app-updater"


@dataclass
class Release:
    version: str  # «1.3.0»
    tag: str  # «v1.3.0»
    url: str | None  # ссылка на Reviews.exe
    size: int
    page: str
    notes: str


def parse_version(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def parse_release(data: dict) -> Release:
    tag = data.get("tag_name", "")
    asset = next((a for a in data.get("assets", []) if a.get("name", "").lower() == ASSET_NAME.lower()), None)
    return Release(
        version=tag.lstrip("vV"),
        tag=tag,
        url=asset.get("browser_download_url") if asset else None,
        size=int(asset.get("size", 0)) if asset else 0,
        page=data.get("html_url", RELEASES_PAGE),
        notes=(data.get("body") or "").strip(),
    )


def fetch_latest(timeout: float = 15) -> Release:
    req = urllib.request.Request(
        API_LATEST, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_release(json.loads(resp.read().decode("utf-8")))


def download(url: str, dst: Path, progress: Callable[[int, int], None] | None = None,
             cancelled: Callable[[], bool] | None = None, timeout: float = 30) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dst.with_name(dst.name + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise InterruptedError("отменено")
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if total and done != total:
        tmp.unlink(missing_ok=True)
        raise IOError("файл скачался не полностью")
    with open(tmp, "rb") as f:
        if f.read(2) != b"MZ":
            tmp.unlink(missing_ok=True)
            raise IOError("скачанный файл не похож на программу")
    os.replace(tmp, dst)


# ---------- замена exe ----------
def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def current_exe() -> Path:
    return Path(sys.executable).resolve()


def new_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".new.exe")


def old_path(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".old.exe")


def swap_files(exe: Path, new: Path) -> None:
    """exe → .old.exe, new → exe. При ошибке возвращаем как было."""
    old = old_path(exe)
    if old.exists():
        old.unlink()
    exe.rename(old)
    try:
        new.rename(exe)
    except OSError:
        old.rename(exe)
        raise


def cleanup_old() -> None:
    if not getattr(sys, "frozen", False):
        return
    exe = current_exe()
    for p in (old_path(exe), new_path(exe), new_path(exe).with_name(new_path(exe).name + ".part")):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass  # старый процесс ещё не завершился — удалим в другой раз


def launch(exe: Path) -> None:
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # новый exe — самостоятельный процесс, не «ребёнок» старого
    for k in list(env):
        if k.startswith("_PYI") or k == "_MEIPASS2":
            env.pop(k)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(exe)], env=env, close_fds=True, creationflags=flags, cwd=str(exe.parent))
