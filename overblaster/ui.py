"""The one framework-facing helper the app needs.

The game's own widgets are gone: the whole screen is painted by scenelayer.SceneLayer. What is left is reading the
size of the game area, which the framework reports at runtime (the docs list 640 x 640 px for the app container).
"""

from . import config as C


def display_size(app) -> tuple:
    try:
        return app.width(), app.height()
    except Exception:  # noqa: BLE001
        return C.DISPLAY_PX, C.DISPLAY_PX
