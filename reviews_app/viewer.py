"""Вкладка «Просмотр»: листание отзывов и перетаскивание JPEG наружу."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .editor import review_title
from .imaging import convert_to_jpeg
from .storage import Review, Store
from .widgets import PATH_ROLE, DragOutImageList


class ViewerTab(QWidget):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.items: list[Review] = []
        self.index = 0

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_index)

        self.btn_prev = QPushButton("◀  Предыдущий")
        self.btn_prev.setToolTip("PgUp")
        self.btn_next = QPushButton("Следующий  ▶")
        self.btn_next.setToolTip("PgDown")
        self.btn_prev.clicked.connect(lambda: self.show_index(self.index - 1))
        self.btn_next.clicked.connect(lambda: self.show_index(self.index + 1))
        self.counter = QLabel()
        self.counter.setAlignment(Qt.AlignCenter)
        self.counter.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.text = QPlainTextEdit(readOnly=True)
        btn_copy = QPushButton("Копировать текст")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))

        self.images = DragOutImageList(200)
        self.images.setFocusPolicy(Qt.NoFocus)
        self.images.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(PATH_ROLE)))
        )
        self.images.setContextMenuPolicy(Qt.CustomContextMenu)
        self.images.customContextMenuRequested.connect(self._image_menu)
        hint = QLabel(
            "Перетащите картинку мышкой куда нужно — уйдёт файл .jpg. "
            "Двойной клик — открыть, правый клик — копировать."
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)

        nav = QHBoxLayout()
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.counter, 1)
        nav.addWidget(self.btn_next)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(nav)
        rl.addWidget(self.text, 2)
        tb = QHBoxLayout()
        tb.addStretch(1)
        tb.addWidget(btn_copy)
        rl.addLayout(tb)
        rl.addWidget(hint)
        rl.addWidget(self.images, 3)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Отзывы"))
        ll.addWidget(self.list)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 800])
        QVBoxLayout(self).addWidget(split)

        for key, step in (("PgUp", -1), ("PgDown", 1), ("Alt+Left", -1), ("Alt+Right", 1), ("Ctrl+Left", -1), ("Ctrl+Right", 1)):
            QShortcut(QKeySequence(key), self, lambda s=step: self.show_index(self.index + s),
                      context=Qt.WidgetWithChildrenShortcut)

    def refresh(self) -> None:
        current_id = self.items[self.index].id if 0 <= self.index < len(self.items) else None
        self.items = [r for r in self.store.reviews if not r.is_empty()]
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.items:
            self.list.addItem(QListWidgetItem(review_title(self.store, r)))
        self.list.blockSignals(False)
        idx = next((i for i, r in enumerate(self.items) if r.id == current_id), 0)
        self.show_index(idx)

    def show_index(self, idx: int) -> None:
        self.images.clear()
        if not self.items:
            self.index = 0
            self.counter.setText("Отзывов пока нет")
            self.text.setPlainText("")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        idx = max(0, min(idx, len(self.items) - 1))
        self.index = idx
        r = self.items[idx]
        self.list.blockSignals(True)
        self.list.setCurrentRow(idx)
        self.list.blockSignals(False)
        self.counter.setText(f"Отзыв {idx + 1} из {len(self.items)}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(self.items) - 1)
        self.text.setPlainText(r.text)
        for i, name in enumerate(r.images, 1):
            src, dst = self.store.source_path(r, name), self.store.jpeg_path(r, name)
            if src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
                try:
                    convert_to_jpeg(src, dst)  # подстраховка, если забыли нажать «Преобразовать»
                except Exception:
                    continue
            if dst.exists():
                self.images.add_image(dst, f"{i}. {dst.name}")

    def _image_menu(self, pos) -> None:
        item = self.images.itemAt(pos)
        if item is None:
            return
        path = item.data(PATH_ROLE)
        menu = QMenu(self)
        menu.addAction("Копировать картинку", lambda: QApplication.clipboard().setImage(QImage(path)))
        menu.addAction("Копировать путь к файлу", lambda: QApplication.clipboard().setText(path))
        menu.addAction("Открыть", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.exec(self.images.mapToGlobal(pos))
