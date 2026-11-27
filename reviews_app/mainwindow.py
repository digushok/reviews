"""Главное окно."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QInputDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .editor import EditorTab
from .imaging import convert_to_jpeg
from .paths import default_data_dir
from . import updater
from .storage import Store, safe_name
from .viewer import ViewerTab
from .widgets import button, label

APP_NAME = "Отзывы"


class Task(QThread):
    """Выполнить функцию в фоне, результат — сигналом."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, fn, pass_self: bool = False):
        super().__init__()
        self.fn = fn
        self.pass_self = pass_self
        self.cancel = False

    def run(self):
        try:
            self.done.emit(self.fn(self) if self.pass_self else self.fn())
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        notice = None
        if data_dir is None:
            data_dir, notice = default_data_dir()
        self.store = Store(data_dir)
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        self.editor = EditorTab(self.store)
        self.viewer = ViewerTab(self.store)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.viewer)

        # --- шапка ---
        header = QFrame()
        header.setObjectName("Header")
        outer = QVBoxLayout(header)
        outer.setContentsMargins(20, 12, 20, 12)
        outer.setSpacing(10)
        hl = QHBoxLayout()
        hl.setSpacing(12)
        outer.addLayout(hl)
        dot = QLabel()
        dot.setObjectName("AppDot")
        dot.setFixedSize(12, 12)
        hl.addWidget(dot)
        hl.addWidget(label(APP_NAME, "AppTitle"))
        hl.addSpacing(18)

        prod_row = QHBoxLayout()
        prod_row.setSpacing(10)
        outer.addLayout(prod_row)
        prod = QFrame()
        prod.setObjectName("ProductBar")
        pl = QHBoxLayout(prod)
        pl.setContentsMargins(10, 4, 4, 4)
        pl.setSpacing(4)
        pl.addWidget(label("Товар:", "Muted"))
        self.product_box = QComboBox()
        self.product_box.setObjectName("ProductBox")
        self.product_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.product_box.setMinimumContentsLength(18)
        self.product_box.setFixedWidth(250)
        self.product_box.setCursor(Qt.PointingHandCursor)
        self.product_box.activated.connect(self._on_product_chosen)
        pl.addWidget(self.product_box)
        for text, tip, slot in (("＋", "Новый товар", self.add_product),
                                ("✎", "Переименовать товар", self.rename_product),
                                ("✕", "Удалить товар вместе с его отзывами", self.delete_product)):
            b = button(text, "icon", tip)
            b.setFixedSize(32, 32)
            b.clicked.connect(slot)
            pl.addWidget(b)
        prod_row.addWidget(prod)
        prod_row.addWidget(label("Отзывы и папки ведутся отдельно для каждого товара", "Muted"))
        prod_row.addStretch(1)
        self.btn_update = button("", "update", "Скачать и установить новую версию")
        self.btn_update.clicked.connect(self.install_update)
        self.btn_update.hide()
        prod_row.addWidget(self.btn_update)
        self.btn_check = button("Проверить обновления", "ghost")
        self.btn_check.clicked.connect(lambda: self.check_updates(silent=False))
        prod_row.addWidget(self.btn_check)

        seg = QFrame()
        seg.setObjectName("Segment")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(4)
        self.tab_buttons = QButtonGroup(self)
        for i, text in enumerate(("✎  Ввод отзывов", "▤  Просмотр")):
            b = button(text)
            b.setCheckable(True)
            sl.addWidget(b)
            self.tab_buttons.addButton(b, i)
        self.tab_buttons.button(0).setChecked(True)
        self.tab_buttons.idClicked.connect(self.switch_tab)
        hl.addWidget(seg)
        hl.addStretch(1)

        btn_folder = button("Открыть папку", "ghost", "Открыть папку с готовыми JPEG этого товара")
        btn_folder.clicked.connect(self.open_data_dir)
        hl.addWidget(btn_folder)
        self.btn_convert = button("Преобразовать в JPEG", "primary", "Перевести все картинки в .jpg и открыть просмотр")
        self.btn_convert.clicked.connect(self.convert_all)
        hl.addWidget(self.btn_convert)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(header)
        cl.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.info = QLabel()
        self.statusBar().addPermanentWidget(self.info)
        self.version_label = label(f"Версия {__version__}", "Version")
        self.statusBar().addPermanentWidget(self.version_label)
        self.statusBar().setSizeGripEnabled(False)

        self.editor.changed.connect(self._update_status)
        self.editor.changed.connect(self._fill_products)
        self.editor.message.connect(lambda m: self.statusBar().showMessage(m, 3000))
        self.viewer.product = self.editor.product
        self._fill_products()
        self._update_status()
        if notice:
            QTimer.singleShot(300, lambda: QMessageBox.information(self, APP_NAME, notice))

        self.latest: updater.Release | None = None
        self._tasks: list[Task] = []
        updater.cleanup_old()
        QTimer.singleShot(5000, updater.cleanup_old)  # старый процесс мог ещё закрываться
        QTimer.singleShot(2000, lambda: self.check_updates(silent=True))

    # ---------- обновления ----------
    def _run(self, fn, done, fail) -> "Task":
        t = Task(fn)
        t.done.connect(done)
        t.failed.connect(fail)
        t.finished.connect(lambda: self._tasks.remove(t) if t in self._tasks else None)
        self._tasks.append(t)
        t.start()
        return t

    def check_updates(self, silent: bool) -> None:
        self.btn_check.setEnabled(False)
        self.btn_check.setText("Проверяю…")

        def done(rel):
            self.btn_check.setEnabled(True)
            self.btn_check.setText("Проверить обновления")
            if updater.is_newer(rel.version, __version__) and rel.url:
                self.latest = rel
                self.btn_update.setText(f"⬆  Обновить до v{rel.version}")
                self.btn_update.show()
                self.version_label.setText(f"Версия {__version__}  ·  доступна v{rel.version}")
                if not silent:
                    self.install_update()
            else:
                self.btn_update.hide()
                self.version_label.setText(f"Версия {__version__}")
                if not silent:
                    self.statusBar().showMessage(f"У вас последняя версия ({__version__}) ✓", 4000)

        def fail(err):
            self.btn_check.setEnabled(True)
            self.btn_check.setText("Проверить обновления")
            if not silent:
                QMessageBox.warning(self, APP_NAME, f"Не удалось проверить обновления.\n\n{err}")

        self._run(updater.fetch_latest, done, fail)

    def install_update(self) -> None:
        rel = self.latest
        if rel is None:
            return
        notes = f"\n\nЧто нового:\n{rel.notes[:1500]}" if rel.notes else ""
        if not updater.can_self_update():
            if QMessageBox.question(self, APP_NAME, f"Доступна версия {rel.version}. Открыть страницу загрузки?{notes}") \
                    == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(rel.page))
            return
        if QMessageBox.question(
            self, "Обновление",
            f"Установить версию {rel.version}? (сейчас {__version__})\n\n"
            f"Программа скачает обновление и перезапустится. Отзывы сохранятся.{notes}",
        ) != QMessageBox.Yes:
            return

        self.editor.commit()
        exe = updater.current_exe()
        new = updater.new_path(exe)
        dlg = QProgressDialog("Скачиваю обновление…", "Отмена", 0, 100, self)
        dlg.setWindowTitle("Обновление")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self.btn_update.setEnabled(False)

        def work(task):
            updater.download(
                rel.url, new,
                progress=lambda d, t: task.progress.emit(d, t or rel.size),
                cancelled=lambda: task.cancel,
            )
            return new

        def on_progress(d, t):
            if t:
                dlg.setValue(min(99, int(d * 100 / t)))
                dlg.setLabelText(f"Скачиваю обновление…  {d / 1048576:.1f} из {t / 1048576:.1f} МБ")

        def done(_):
            task.wait(3000)
            dlg.setValue(100)
            dlg.close()
            try:
                updater.swap_files(exe, new)
                self.editor._leave_current()
                updater.launch(exe)
            except Exception as e:
                self.btn_update.setEnabled(True)
                QMessageBox.warning(
                    self, APP_NAME,
                    f"Не получилось установить обновление автоматически:\n{e}\n\n"
                    f"Скачайте его вручную со страницы релиза.",
                )
                QDesktopServices.openUrl(QUrl(rel.page))
                return
            self._restarting = True
            QApplication.quit()

        def fail(err):
            dlg.close()
            self.btn_update.setEnabled(True)
            new.unlink(missing_ok=True)
            if "отменено" not in err:
                QMessageBox.warning(self, APP_NAME, f"Не удалось скачать обновление.\n\n{err}")

        task = Task(work, pass_self=True)
        task.done.connect(done)
        task.failed.connect(fail)
        task.progress.connect(on_progress)
        dlg.canceled.connect(lambda: setattr(task, "cancel", True))
        task.finished.connect(lambda: self._tasks.remove(task) if task in self._tasks else None)
        self._tasks.append(task)
        task.start()

    # ---------- товары ----------
    def _fill_products(self) -> None:
        self.product_box.blockSignals(True)
        self.product_box.clear()
        for p in self.store.products:
            n = sum(1 for r in self.store.reviews_of(p) if not r.is_empty())
            self.product_box.addItem(f"{p.name}   ({n})", p.id)
        self.product_box.setCurrentIndex(self.store.products.index(self.editor.product))
        self.product_box.blockSignals(False)

    def _select_product(self, p) -> None:
        self.editor.set_product(p)
        self.viewer.product = p
        self._fill_products()
        if self.stack.currentIndex() == 1:
            self.viewer.refresh()
        self._update_status()

    def _on_product_chosen(self, idx: int) -> None:
        p = self.store.product(self.product_box.itemData(idx))
        if p is not None:
            self._select_product(p)

    def _ask_name(self, title: str, text: str = "") -> str | None:
        while True:
            name, ok = QInputDialog.getText(self, title, "Название товара:", text=text)
            if not ok:
                return None
            if name.strip():
                return name
            text = name

    def add_product(self) -> None:
        name = self._ask_name("Новый товар")
        if name is None:
            return
        try:
            p = self.store.add_product(name)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self._select_product(p)
        self.statusBar().showMessage(f"Товар «{p.name}» создан ✓", 3000)

    def rename_product(self) -> None:
        p = self.editor.product
        name = self._ask_name("Переименовать товар", p.name)
        if name is None or name == p.name:
            return
        try:
            self.store.rename_product(p, name)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.editor.refresh_product_name()
        self._fill_products()
        self._update_status()

    def delete_product(self) -> None:
        p = self.editor.product
        n = sum(1 for r in self.store.reviews_of(p) if not r.is_empty())
        msg = f"Удалить товар «{p.name}»?"
        if n:
            msg += f"\n\nВместе с ним удалятся {n} отзыв(ов) и все их картинки."
        if QMessageBox.question(self, "Удалить товар", msg) != QMessageBox.Yes:
            return
        self.editor._leave_current()
        self.store.delete_product(p)
        self._select_product(self.store.ensure_product())

    def switch_tab(self, idx: int) -> None:
        self.tab_buttons.button(idx).setChecked(True)
        if idx == 1:
            self.editor.commit()
            self.convert_all(quiet=True)  # быстро, если всё уже готово
            self._fill_products()
            self.viewer.refresh()
        self.stack.setCurrentIndex(idx)
        self._update_status()

    def _update_status(self) -> None:
        n = sum(1 for r in self.store.reviews if not r.is_empty())
        imgs = sum(len(r.images) for r in self.store.reviews)
        pending = len(self.store.pending_conversions())
        parts = [f"Отзывов: {n}", f"фото: {imgs}"]
        if pending:
            parts.append(f"ждут преобразования: {pending}")
        self.info.setText("   ·   ".join(parts) + "   ")
        self.btn_convert.setText(f"Преобразовать в JPEG  ({pending})" if pending else "Преобразовать в JPEG")

    def convert_all(self, quiet: bool = False) -> None:
        """Обновить папку «Отзывы»: товар / отзыв / «Товар N.jpg»."""
        self.editor.commit()
        dlg = None
        jobs = len(self.store.pending_conversions())

        def progress(i: int, total: int) -> bool:
            nonlocal dlg
            if dlg is None and total:
                dlg = QProgressDialog("Преобразование в JPEG…", "Отмена", 0, total, self)
                dlg.setWindowTitle(APP_NAME)
                dlg.setWindowModality(Qt.WindowModal)
                dlg.setMinimumDuration(300)
            if dlg is not None:
                dlg.setValue(i)
                dlg.setLabelText(f"Преобразование {min(i + 1, total)} из {total}…")
                QApplication.processEvents()
                return not dlg.wasCanceled()
            return True

        errors = self.store.export(convert_to_jpeg, progress=progress)
        if dlg is not None:
            dlg.close()
        self._update_status()
        if errors:
            QMessageBox.warning(self, APP_NAME, "Не удалось преобразовать:\n\n" + "\n".join(errors[:20]))
        elif not quiet:
            self.statusBar().showMessage(
                f"Готово: преобразовано {jobs} ✓  Папка: {self.store.export_root}" if jobs
                else "Все картинки уже в JPEG ✓", 5000
            )
        if not quiet:
            self.switch_tab(1)

    def open_data_dir(self) -> None:
        target = self.store.export_root / safe_name(self.editor.product.name)
        if not target.exists():
            target = self.store.export_root if self.store.export_root.exists() else self.store.root
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def closeEvent(self, e) -> None:
        self.editor._leave_current()
        super().closeEvent(e)


def main() -> int:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("reviews.app")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    theme.apply(app)
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    w = MainWindow(data_dir)
    w.show()
    return app.exec()
