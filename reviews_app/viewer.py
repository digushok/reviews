"""Вкладка «Просмотр»: листание отзывов и перетаскивание JPEG наружу."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .editor import card, make_review_list, review_title
from .imaging import convert_to_jpeg, load_qimage
from .storage import Product, Review, Store
from .widgets import PATH_ROLE, DragOutImageList, button, hrow, label


class ViewerTab(QWidget):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.items: list[Review] = []
        self.index = 0
        self.product: Product | None = None

        # --- слева: список ---
        left, ll = card()
        ll.setContentsMargins(12, 14, 12, 12)
        self.count_badge = label("", "Badge")
        ll.addLayout(hrow(label("Готовые отзывы", "Section"), self.count_badge, stretch_at=2))
        self.list = make_review_list()
        self.list.currentRowChanged.connect(self.show_index)
        ll.addWidget(self.list, 1)

        # --- справа: отзыв ---
        right, rl = card()
        self.btn_prev = button("←", "round", "Предыдущий (PgUp)")
        self.btn_next = button("→", "round", "Следующий (PgDown)")
        self.btn_prev.clicked.connect(lambda: self.show_index(self.index - 1))
        self.btn_next.clicked.connect(lambda: self.show_index(self.index + 1))
        self.title = label("", "Title")
        self.title.setAlignment(Qt.AlignCenter)
        self.subtitle = label("", "Muted")
        self.subtitle.setAlignment(Qt.AlignCenter)
        mid = QVBoxLayout()
        mid.setSpacing(0)
        mid.addWidget(self.title)
        mid.addWidget(self.subtitle)
        nav = hrow(self.btn_prev)
        nav.addLayout(mid, 1)
        nav.addWidget(self.btn_next)
        rl.addLayout(nav)

        self.btn_copy = button("Копировать текст", "ghost")
        self.btn_copy.clicked.connect(self.copy_text)
        rl.addLayout(hrow(label("Текст отзыва", "Section"), self.btn_copy, stretch_at=1))
        self.text = QPlainTextEdit(readOnly=True)
        rl.addWidget(self.text, 2)

        rl.addSpacing(4)
        rl.addLayout(hrow(label("Фотографии", "Section"),
                          label("тащите мышкой куда нужно — уйдёт файл .jpg  ·  правый клик — копировать", "Muted"),
                          stretch_at=2))
        self.images = DragOutImageList(190)
        self.images.setFocusPolicy(Qt.NoFocus)
        self.images.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(PATH_ROLE)))
        )
        self.images.setContextMenuPolicy(Qt.CustomContextMenu)
        self.images.customContextMenuRequested.connect(self._image_menu)
        rl.addWidget(self.images, 3)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 820])

        # пустое состояние
        empty, el = card()
        el.addStretch(1)
        t = label("Пока нет отзывов", "Title")
        t.setAlignment(Qt.AlignCenter)
        s = label("У этого товара ещё нет отзывов. Добавьте их на вкладке «Ввод отзывов».", "Muted")
        s.setAlignment(Qt.AlignCenter)
        el.addWidget(t)
        el.addWidget(s)
        el.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.addWidget(split)
        self.stack.addWidget(empty)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.stack)

        for key, step in (("PgUp", -1), ("PgDown", 1), ("Alt+Left", -1), ("Alt+Right", 1),
                          ("Ctrl+Left", -1), ("Ctrl+Right", 1)):
            QShortcut(QKeySequence(key), self, lambda s=step: self.show_index(self.index + s),
                      context=Qt.WidgetWithChildrenShortcut)

    def refresh(self) -> None:
        current_id = self.items[self.index].id if 0 <= self.index < len(self.items) else None
        reviews = self.store.reviews_of(self.product) if self.product else []
        self.items = [r for r in reviews if not r.is_empty()]
        self.count_badge.setText(str(len(self.items)))
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.items:
            self.list.addItem(QListWidgetItem(review_title(self.store, r)))
        self.list.blockSignals(False)
        self.stack.setCurrentIndex(0 if self.items else 1)
        idx = next((i for i, r in enumerate(self.items) if r.id == current_id), 0)
        self.show_index(idx)

    def show_index(self, idx: int) -> None:
        self.images.clear()
        if not self.items:
            self.index = 0
            return
        idx = max(0, min(idx, len(self.items) - 1))
        self.index = idx
        r = self.items[idx]
        self.list.blockSignals(True)
        self.list.setCurrentRow(idx)
        self.list.blockSignals(False)
        self.title.setText(f"Отзыв {idx + 1} из {len(self.items)}")
        photos = f"{len(r.images)} фото" if r.images else "без фото"
        self.subtitle.setText(f"{self.product.name}  ·  {photos}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(self.items) - 1)
        self.text.setPlainText(r.text)
        self.btn_copy.setText("Копировать текст")
        if self.store.pending_conversions([r]):
            self.store.export(convert_to_jpeg, reviews=[r])  # подстраховка
        for name in r.images:
            dst = self.store.jpeg_path(r, name)
            if dst.exists():
                self.images.add_image(dst, dst.name)

    def copy_text(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())
        self.btn_copy.setText("Скопировано ✓")
        QTimer.singleShot(1500, lambda: self.btn_copy.setText("Копировать текст"))

    def _image_menu(self, pos) -> None:
        item = self.images.itemAt(pos)
        if item is None:
            return
        path = item.data(PATH_ROLE)
        menu = QMenu(self)
        menu.addAction("Копировать картинку", lambda: QApplication.clipboard().setImage(load_qimage(path, 20000)))
        menu.addAction("Копировать путь к файлу", lambda: QApplication.clipboard().setText(path))
        menu.addAction("Открыть", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.exec(self.images.mapToGlobal(pos))
