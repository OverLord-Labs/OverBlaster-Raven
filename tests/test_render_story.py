"""The story intro drawn with QPainter (port of web story.ts): rendered offscreen at a quarter size, checked by pixel."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from overblaster.core import COUNT_AT, EV, JUMP_AT, PARTS, Game, Rng
from overblaster.debug_scenes import apply_scene
from overblaster.render import story
from overblaster.render.draw import Draw
from overblaster.render.scene import draw_game

SIZE = 160  # a quarter of 640: fast, and still enough to see what is where


@pytest.fixture(autouse=True, scope="module")
def _qt():
    app = QApplication.instance() or QApplication([])
    yield app


def render(t: float, seed: int = 1) -> QImage:
    game = Game(seed=seed)
    apply_scene(game, "intro", str(t), None)
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    img.fill(0xFF000000)
    p = QPainter(img)
    draw_game(Draw(p, SIZE), game)
    p.end()
    return img


def px(img, x, y):
    k = img.width() / 640
    c = QColor(img.pixel(int(x * k), int(y * k)))
    return c.red(), c.green(), c.blue()


def lit(img, x0, y0, x1, y1, thresh=60):
    k = img.width() / 640
    n = 0
    for y in range(int(y0 * k), int(y1 * k)):
        for x in range(int(x0 * k), int(x1 * k)):
            c = QColor(img.pixel(x, y))
            if max(c.red(), c.green(), c.blue()) > thresh:
                n += 1
    return n


def test_tables_are_the_webs():
    r = Rng(7)
    a, sp, ph, w = r.next() * 6.283, 0.5 + r.next() * 1.1, r.next(), 1.5 + r.next() * 2
    assert story.RAYS[0] == (a, sp, ph, w, True)
    assert len(story.RAYS) == 100 and sum(1 for x in story.RAYS if x[4]) == 20
    assert len(story.DEBRIS) == 30 and all(0 < d[1] < 1 and 0.4 <= d[2] <= 0.7 for d in story.DEBRIS)


def test_every_frame_of_the_intro_draws():
    """t = 0 .. 45 s in half-second steps: no exceptions, and the picture is never a blank, apart from the very first instant."""
    for i in range(0, 91):
        t = i * 0.5
        img = render(t)
        if t >= 1:
            assert lit(img, 0, 0, 640, 640, 25) > 40, f"t={t} drew almost nothing"


def test_the_bridge_has_its_console_and_crew():
    img = render(5)
    assert lit(img, 150, 556, 490, 592) > 100  # the POWER cells, lit
    assert lit(img, 60, 440, 200, 520, 20) > 50  # a crew silhouette's rim light and the console lights
    assert lit(img, 140, 100, 500, 372, 40) > 500  # the tunnel in the window


def test_power_falls_and_the_banners_show():
    full, half, none = render(PARTS[2].v0), render(EV["w1"] + 1.4), render(EV["w2"] + 1.6)
    assert lit(full, 150, 556, 490, 592, 150) > lit(half, 150, 556, 490, 592, 150) > lit(none, 150, 556, 490, 592, 150)
    banner = render(EV["w1"] + 0.6)  # WING 1 LOST
    assert lit(banner, 170, 182, 470, 236, 120) > 10


def test_the_map_is_there_for_the_last_two_lines_and_gone_for_the_count():
    during = render(PARTS[5].t0 + 4.5)
    assert lit(during, 296, 424, 344, 456, 100) > 5  # the Meridian's dot, cyan
    assert lit(during, 0, 100, 640, 400, 40) > 300  # the route and the rocks
    count = render(COUNT_AT + 0.4)
    assert lit(count, 0, 100, 640, 400, 40) < lit(during, 0, 100, 640, 400, 40) * 0.5  # no map behind the numbers
    assert lit(count, 250, 270, 390, 380, 150) > 40  # the white 3


def test_go_and_the_jump_rays():
    img = render(JUMP_AT + 0.1)
    assert lit(img, 200, 250, 440, 380, 200) > 40  # GO
    assert lit(img, 0, 0, 640, 640, 100) > 400  # rays streaming out


def test_a_frame_is_a_pure_function_of_its_time():
    a, b = render(8.3, seed=1), render(8.3, seed=99)
    assert a == b  # the story uses no game randomness


def test_skip_button_shows_only_during_the_story():
    game = Game(seed=1)
    apply_scene(game, "intro", "5", None)
    assert game.story_btn_visible()
    apply_scene(game, "intro", str(COUNT_AT + 1), None)
    assert not game.story_btn_visible()
