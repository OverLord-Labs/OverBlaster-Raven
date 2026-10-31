"""Draw a whole Game: dispatch on its phase, as the web Renderer.render does for a square screen (port of web src/render/renderer.ts).

The intro and the playfield live in story.py and playfield.py (later stages); until they exist they draw nothing but black.
"""

from typing import Callable, Optional

from ..core.constants import CYAN, W
from .draw import Draw
from .screens import draw_over, draw_title


def _lazy(module: str, name: str) -> Optional[Callable]:
    try:
        mod = __import__(f"{__package__}.{module}", fromlist=[name])
    except ModuleNotFoundError as e:
        if e.name and e.name.endswith(f".{module}"):
            return None
        raise
    return getattr(mod, name, None)


def draw_playfield(d: Draw, game) -> None:
    fn = _lazy("playfield", "draw_playfield")
    if fn:
        fn(d, game)


def draw_game(d: Draw, game) -> None:
    """Paint `game` onto d's painter (the painter's device is cleared to black first)."""
    d.ctx.clear("#000000")
    d.ctx.reset_transform()
    phase = game.phase
    if phase == "title":
        draw_title(d, game)
    elif phase == "intro":
        fn = _lazy("story", "draw_intro")
        if fn:
            fn(d, game, draw_playfield)
    elif phase == "play":
        draw_playfield(d, game)
    elif phase == "over":
        draw_over(d, game)
    if game.launching and phase == "title":
        c = d.ctx
        c.fill_style = "rgba(0,0,0,.6)"
        c.fill_rect(0, 0, W, W)
        d.text("LOADING SOUND…", 320, 330, 22, CYAN, 700, 5, "center")
