# Правила работы с этим репозиторием

- Общаться с владельцем по-русски.
- Когда изменения согласованы и сделаны: прогнать `pytest -q`, закоммитить, запушить в `main`
  и сразу выпустить релиз — не спрашивая отдельного подтверждения.
- Релиз: поднять `__version__` в `reviews_app/__init__.py`, затем
  `gh api repos/digushok/reviews/actions/workflows/build.yml/dispatches -X POST -f ref=main -f 'inputs[version]=vX.Y.Z' -f 'inputs[notes]=<что нового, по-русски>'`
  (текст «что нового» пользователь видит в окне обновления внутри программы)
  (пуш тегов и создание релизов напрямую из облачной сессии запрещены — релиз создаёт сам workflow).
- Программа для Windows на PySide6 + Pillow, exe собирает GitHub Actions (PyInstaller).
