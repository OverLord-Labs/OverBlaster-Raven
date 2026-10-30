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
    def __init__(self, owner: QWidget, on_move) -> None:
        super().__init__(owner)
        self._owner = owner
        self._on_move = on_move

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseMove and isinstance(obj, QWidget):
            if obj is self._owner or self._owner.isAncestorOf(obj):
                p = obj.mapTo(self._owner, event.position().toPoint())
                self._on_move(p.x(), p.y())
        return False  # only watching: never consume the event
