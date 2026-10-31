"""The game screen ported from the web renderer: every debug scene renders, key pixels are lit, and a bot-driven sweep over real
level states (levels 1, 3, 7, 14) renders without errors."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from overblaster.core import (
    CHIP_CAPACITY, HIT_FORGIVENESS, TURN_RATE, Game, azd, bot_target, clamp, empty_input, rock_radius,
)
from overblaster.render.draw import Draw
from overblaster.render.scene import draw_game
from test_render_draw import lit, px, scene

SIZE = 320


@pytest.fixture(autouse=True, scope="module")
def _qt():
    app = QApplication.instance() or QApplication([])
    yield app


SCENES = [
    "splash", "arrow", "rocks", "fight", "laser", "mouse", "wing", "wing:hold", "wing:side", "lvl:7:5", "lvl:12:8", "lvl:28:6", "gauge", "bad",
    "back", "fight7", "close", "arrows", "wave1", "wave1b", "wave2", "chip50", "chipslip", "chipfar", "award", "plate", "over", "win",
]


@pytest.mark.parametrize("name", SCENES)
def test_scene_renders(name):
    img = scene(name)
    assert img.width() == SIZE
    assert lit(img, 0, 0, 640, 640) > 50  # something is drawn


def bright(img, x, y, thresh=60):
    return max(px(img, x, y)) > thresh


def test_hud_in_the_corner_every_level_screen():
    img = scene("lvl:12:8")
    assert lit(img, 20, 4, 150, 64) > 400  # the battery cells
    assert lit(img, 170, 20, 260, 50) > 40  # "LVL 12"
    assert lit(img, 355, 20, 440, 52) > 10  # the two wing outlines
    assert lit(img, 500, 20, 545, 50) > 5  # the score (a 0 at the start of a level is still drawn)


def test_wing_hold_ring_and_label():
    img = scene("wing:hold")
    assert lit(img, 220, 220, 420, 420) > 500  # the wing and its ring
    assert lit(img, 140, 420, 500, 470) > 100  # "HOLD YOUR AIM ON THE WING"


def test_bms_award_card():
    img = scene("award")
    assert lit(img, 20, 108, 480, 244) > 1500  # the gold card under the battery
    assert lit(img, 0, 0, 640, 66) > 600  # the HUD above it


def test_sector_cleared_plate():
    img = scene("plate")
    assert lit(img, 90, 166, 550, 476) > 1500
    assert lit(img, 100, 430, 540, 470) > 100  # "click or space to continue"


def test_bad_gauge_scene_has_both_chips_and_the_callout():
    img = scene("gauge")
    red = blue = 0
    for y in range(0, 640, 4):
        for x in range(0, 640, 4):
            r, g, b = px(img, x, y)
            red += r > 200 and g < 110 and b < 110
            blue += b > 200 and r < 110 and g < 190
    assert red > 20 and blue > 20  # a red chip and a blue one
    assert lit(img, 20, 492, 620, 562) > 300  # the callout box


def test_off_screen_arrows_and_critical_red():
    img = scene("arrows")
    ring = 0
    for ang in range(0, 360, 10):
        import math

        x = 320 + 250 * math.cos(math.radians(ang))
        y = 320 + 250 * math.sin(math.radians(ang))
        ring += lit(img, x - 20, y - 20, x + 20, y + 20)
    assert ring > 300


def test_game_over_screens_still_render():
    assert lit(scene("over"), 100, 100, 540, 300) > 300
    assert lit(scene("win"), 100, 100, 540, 300) > 300


def test_shot_bolt_is_drawn():
    img = scene("laser")
    assert lit(img, 0, 400, 640, 640) > 60  # the bolt streaking in from the lower corner


# ---- the sweep: render real states from a bot's game
def _play_and_render(level: int, seed: int = 3, every: int = 10, max_s: float = 45.0) -> int:
    game = Game(seed=seed)
    game.new_game(False)
    game.phase = "play"
    r = game.run
    r.chip_collected = level > 3
    if r.chip_collected:
        r.capacity = r.charge = CHIP_CAPACITY
    game.start_level(level)
    inp = empty_input()
    inp.pointer.inside = True
    img = QImage(160, 160, QImage.Format.Format_ARGB32)
    d = Draw()
    frames = 0
    max_step = TURN_RATE / 30 * 0.9
    for k in range(int(max_s * 30)):
        if game.phase != "play":
            break
        p = bot_target(game)
        game.view.az = (game.view.az + clamp(azd(p["az"], game.view.az), -max_step, max_step) + 360) % 360
        game.view.el = clamp(game.view.el + clamp(p["el"] - game.view.el, -max_step, max_step), -38, 38)
        inp.fire = game.run.mode == "playing" and any(
            not w.dead and game.run.t >= w.spawn_at and not game.arriving(w) and game.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS
            for w in game.run.worlds
        )
        game.update(1 / 30, inp)
        game.drain()
        if game.run.mode == "intermission" and game.clock - game.run.plate_at > 4:
            break
        if k % every == 0:
            img.fill(0xFF000000)
            pt = QPainter(img)
            d.begin(pt, 160)
            draw_game(d, game)
            pt.end()
            frames += 1
    return frames


@pytest.mark.parametrize("level", [1, 3, 7, 14])
def test_state_sweep_renders_every_tenth_frame(level):
    assert _play_and_render(level) > 10


def test_sweep_through_intermission_and_game_over_phases():
    game = Game(seed=5)
    game.new_game(False)
    game.phase = "play"
    game.run.charge = 0
    inp = empty_input()
    img = QImage(160, 160, QImage.Format.Format_ARGB32)
    d = Draw()
    for _ in range(200):
        game.update(1 / 30, inp)
        game.drain()
        img.fill(0xFF000000)
        pt = QPainter(img)
        d.begin(pt, 160)
        draw_game(d, game)
        pt.end()
        if game.phase == "over":
            break
    assert game.phase == "over"
