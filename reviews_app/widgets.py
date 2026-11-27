"""Общие виджеты: зона для картинок, галерея с перетаскиванием наружу, поле текста."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton

from . import theme
from .imaging import load_qimage
from .importer import DropData, snapshot

PATH_ROLE = Qt.UserRole
NAME_ROLE = Qt.UserRole + 1

_thumb_cache: dict[tuple[str, float, int], QPixmap] = {}


def thumbnail(path: Path, size: int) -> QPixmap:
    try:
        key = (str(path), path.stat().st_mtime, size)
    except OSError:
        return QPixmap()
    if key not in _thumb_cache:
        try:
            _thumb_cache[key] = QPixmap.fromImage(load_qimage(path, size))
        except Exception:
            _thumb_cache[key] = QPixmap()
    return _thumb_cache[key]


def button(text: str, kind: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def label(text: str = "", name: str = "") -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    return lb


def hrow(*widgets, stretch_at: int | None = None, spacing: int = 8) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if i == stretch_at:
            lay.addStretch(1)
        if w is not None:
            lay.addWidget(w)
    if stretch_at is not None and stretch_at >= len(widgets):
        lay.addStretch(1)
    return lay


class ImageList(QListWidget):
    """Сетка миниатюр."""

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(parent)
        self.thumb_size = thumb_size
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setIconSize(QSize(thumb_size, thumb_size))
        self.setGridSize(QSize(thumb_size + 22, thumb_size + 36))
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def add_image(self, path: Path, text: str, name: str = "") -> QListWidgetItem:
        item = QListWidgetItem(QIcon(thumbnail(path, self.thumb_size)), text)
        item.setData(PATH_ROLE, str(path))
        item.setData(NAME_ROLE, name)
        item.setToolTip(str(path))
        self.addItem(item)
        return item


class DropImageList(ImageList):
    """Зона, куда бросают картинки: из проводника, из браузера, Ctrl+V."""

    dropped = Signal(object)  # DropData

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(thumb_size, parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setProperty("dragOver", False)

    def _set_over(self, on: bool) -> None:
        if self.property("dragOver") != on:
            self.setProperty("dragOver", on)
            theme.repolish(self)

    def dragEnterEvent(self, e):
        if snapshot(e.mimeData(), read_payload=False).has_anything():
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self._set_over(True)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        e.setDropAction(Qt.CopyAction)
        e.accept()

    def dragLeaveEvent(self, e):
        self._set_over(False)

    def dropEvent(self, e):
        self._set_over(False)
        data = snapshot(e.mimeData())
        if data.has_anything():
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self.dropped.emit(data)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count():
            return
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        r = self.viewport().rect()
        cx, cy = r.center().x(), r.center().y() - 26
        accent = QColor(theme.ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT_SOFT))
        p.drawEllipse(QRectF(cx - 26, cy - 26, 52, 52))
        pen = QPen(accent, 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(int(cx - 10), int(cy), int(cx + 10), int(cy))
        p.drawLine(int(cx), int(cy - 10), int(cx), int(cy + 10))
        f = QFont(self.font())
        f.setPointSizeF(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(r.left(), cy + 34, r.width(), 24), Qt.AlignCenter, "Перетащите картинки сюда")
        f.setBold(False)
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        p.drawText(
            QRectF(r.left(), cy + 58, r.width(), 22), Qt.AlignCenter,
            "из папки или прямо из браузера  ·  или Ctrl+V  ·  или кнопка «Добавить»",
        )
        p.end()


class DragOutImageList(ImageList):
    """Галерея: картинки можно перетащить наружу как файлы .jpg."""

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(thumb_size, parent)
        self.setObjectName("Gallery")
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragOnly)
        self.setCursor(Qt.OpenHandCursor)

    def startDrag(self, actions):
        items = self.selectedItems()
        if not items:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(it.data(PATH_ROLE)) for it in items])
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = items[0].icon().pixmap(self.thumb_size)
        if not pm.isNull():
            pm = pm.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(pm)
            drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.CopyAction, Qt.CopyAction)


class ReviewTextEdit(QPlainTextEdit):
    """Поле текста: брошенные/вставленные картинки уходят в отзыв, а не превращаются в текст."""

    dropped = Signal(object)  # DropData

    def _images_only(self, mime, paste: bool = False) -> DropData | None:
        d = snapshot(mime, read_payload=False)
        if paste and mime.hasText() and not d.local_files:
            return None  # вставляют текст (пусть даже с картинками внутри) — это текст
        if d.local_files or d.file_contents or d.image is not None or d.img_srcs:
            return d
        return None

    def dragEnterEvent(self, e):
        if self._images_only(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._images_only(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if self._images_only(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self.dropped.emit(snapshot(e.mimeData()))
        else:
            super().dropEvent(e)

    def canInsertFromMimeData(self, mime):
        return bool(self._images_only(mime, paste=True)) or super().canInsertFromMimeData(mime)

    def insertFromMimeData(self, mime):
        if self._images_only(mime, paste=True):
            self.dropped.emit(snapshot(mime))
        else:
            super().insertFromMimeData(mime)
