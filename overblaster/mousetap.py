"""Sees every mouse move over the app, whichever widget is under the cursor.

Qt only delivers a plain mouse move (no button held) to a widget that has mouse tracking on, and
throws it away at the first widget under the cursor that doesn't, without trying its parents. Our
sprites and labels don't track the mouse, so a handler on the app widget only ever heard moves
made while a button was held. An application-wide event filter sees the move before it is thrown
away, and maps it back into the app widget's coordinates.

On the glasses the framework treats gaze as the cursor (its Buttons dwell on hover), so this is
also how gaze reaches the game if the eye tracker's own read returns nothing.
"""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget


class MouseTap(QObject):
    def __init__(self, owner: QWidget, on_move, on_press=None) -> None:
        super().__init__(owner)
        self._owner = owner
        self._on_move = on_move
        self._on_press = on_press  # a click (left button) at (x, y) in the owner's coordinates

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress) and isinstance(obj, QWidget):
            if obj is self._owner or self._owner.isAncestorOf(obj):
                p = obj.mapTo(self._owner, event.position().toPoint())
                if kind == QEvent.Type.MouseMove:
                    self._on_move(p.x(), p.y())
                elif self._on_press is not None:
                    self._on_press(p.x(), p.y())
        return False  # only watching: never consume the event
