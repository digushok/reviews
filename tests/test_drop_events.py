"""Настоящие события перетаскивания: dragEnter → dragMove → drop, как их шлёт Windows."""
import io
import warnings
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from reviews_app.mainwindow import MainWindow

ACTIONS = Qt.CopyAction | Qt.MoveAction | Qt.LinkAction


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, ms=300):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def drag_and_drop(app, widget, mime) -> bool:
    """Как Windows: события идут в виджет под курсором, у которого включён приём перетаскивания."""
    target = widget
    while target is not None and not target.acceptDrops():
        target = target.parentWidget()
    assert target is not None, "никто не принимает перетаскивание — курсор будет «запрещено»"
    pos = widget.mapTo(target, widget.rect().center())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        enter = QDragEnterEvent(pos, ACTIONS, mime, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(target, enter)
        if not enter.isAccepted():
            return False
        move = QDragMoveEvent(pos, ACTIONS, mime, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(target, move)
    drop = QDropEvent(QPointF(pos), ACTIONS, mime, Qt.LeftButton, Qt.NoModifier)
    app.sendEvent(target, drop)
    return drop.isAccepted()


def webp_file(path: Path) -> Path:
    Image.new("RGB", (120, 80), (200, 30, 30)).save(path, "WEBP")
    return path


def test_drop_file_on_photo_zone_and_elsewhere(app, tmp_path):
    w = MainWindow(tmp_path / "data")
    w.show()
    e = w.editor
    f = webp_file(tmp_path / "a.webp")

    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(f))])
    assert drag_and_drop(app, e.images.viewport(), m)
    wait(app)
    assert len(e.current.images) == 1

    # в заголовок/пустое место вкладки — тоже работает
    m2 = QMimeData()
    m2.setUrls([QUrl.fromLocalFile(str(f))])
    assert drag_and_drop(app, e.title, m2)
    wait(app)
    assert len(e.current.images) == 2

    # в поле текста — картинка уходит в отзыв, текст не портится
    m3 = QMimeData()
    m3.setUrls([QUrl.fromLocalFile(str(f))])
    assert drag_and_drop(app, e.text.viewport(), m3)
    wait(app)
    assert len(e.current.images) == 3 and e.text.toPlainText() == ""
    w.close()


def test_drop_browser_image_data_url(app, tmp_path):
    import base64

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), (0, 0, 200)).save(buf, "WEBP")
    src = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    w = MainWindow(tmp_path / "data")
    w.show()
    m = QMimeData()
    m.setHtml(f'<a href="https://shop.example/product/1"><img src="{src}"></a>')
    m.setText("https://shop.example/product/1")
    assert drag_and_drop(app, w.editor.images.viewport(), m)
    wait(app)
    assert len(w.editor.current.images) == 1
    w.close()
