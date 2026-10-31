"""The QPainter Draw layer and the screens ported from the web renderer: rendered offscreen, checked by pixel."""

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from overblaster.core import GOLD, PINK, Game
from overblaster.debug_scenes import apply_scene
from overblaster.render.draw import Draw, Gradient, advance_scale, css, mixc, parse_color
from overblaster.render.scene import draw_game
from overblaster.render.sprites import draw_cells, wing_icon

SIZE = 320


@pytest.fixture(autouse=True, scope="module")
def _qt():
    """A Qt application for the module (made here, not at import, so collecting this file does not change how other tests start)."""
    app = QApplication.instance() or QApplication([])
    yield app


def paint(fn, size=SIZE):
    """Run fn(draw) on a black size x size image and return it."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0xFF000000)
    p = QPainter(img)
    d = Draw(p, size)
    fn(d)
    p.end()
    return img


def px(img, x, y):
    """The colour at logical (x, y) of a 640-space picture."""
    k = img.width() / 640
    c = QColor(img.pixel(int(x * k), int(y * k)))
    return c.red(), c.green(), c.blue()


def lit(img, x0, y0, x1, y1, thresh=40):
    """How many pixels in the logical box are brighter than thresh in any channel."""
    k = img.width() / 640
    n = 0
    for y in range(int(y0 * k), int(y1 * k)):
        for x in range(int(x0 * k), int(x1 * k)):
            c = QColor(img.pixel(x, y))
            if max(c.red(), c.green(), c.blue()) > thresh:
                n += 1
    return n


def scene(name, size=SIZE):
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from render_scene import render

    return render(name, size)


# ---- colour helpers
def test_css_and_mixc():
    assert css((1, 2, 3)) == "rgba(1,2,3,1)" and css((1, 2, 3), 0.5) == "rgba(1,2,3,0.5)"
    assert mixc((0, 0, 0), (255, 255, 255), 0.5) == (128, 128, 128)  # halves round up, like Math.round


def test_parse_color_forms():
    assert parse_color("rgba(0,229,255,.5)").getRgb() == (0, 229, 255, 128)
    assert parse_color("rgb(10,20,30)").getRgb() == (10, 20, 30, 255)
    assert parse_color("#7dff7d").getRgb() == (125, 255, 125, 255)
    assert parse_color("transparent").alpha() == 0
    assert parse_color((1, 2, 3)).getRgb() == (1, 2, 3, 255)


# ---- text
def test_text_width_grows_with_size_and_letter_spacing():
    d = Draw(None)
    w20, w40 = d.text_w("OVERBLASTER", 20, 700), d.text_w("OVERBLASTER", 40, 700)
    assert 1.9 < w40 / w20 < 2.3
    assert d.text_w("ABC", 20, 700, 5) == pytest.approx(d.text_w("ABC", 20, 700, 0.0001) + 10, abs=0.1)  # two gaps of 5
    assert d.text_w("", 20) == 0 or d.text_w("", 20, 700, 3) == -3


def test_advance_scale_is_one_to_two_and_a_half_percent_wider_at_most():
    assert advance_scale(8) == 1.0 and advance_scale(100) == pytest.approx(1.025) and 1.0 < advance_scale(20) < 1.025


def test_text_aligns():
    def draw(align):
        return paint(lambda d: d.text("HELLO", 320, 330, 40, "#fff", 700, None, align))

    def span(img):
        k = img.width() / 640
        cols = [x for x in range(img.width()) for y in range(img.height()) if QColor(img.pixel(x, y)).red() > 128]
        return min(cols) / k, max(cols) / k

    left, center, right = span(draw("left")), span(draw("center")), span(draw("right"))
    assert left[0] == pytest.approx(320, abs=8) and right[1] == pytest.approx(320, abs=10)  # ink starts and ends inside the glyph bearings
    assert (center[0] + center[1]) / 2 == pytest.approx(320, abs=8)


# ---- the canvas facade
def test_fill_rect_and_global_alpha_and_save_restore():
    def go(d):
        c = d.ctx
        c.fill_style = "#ff0000"
        c.save()
        c.global_alpha = 0.5
        c.fill_rect(0, 0, 100, 100)
        c.restore()
        assert c.global_alpha == 1
        c.fill_style = "#00ff00"
        c.fill_rect(200, 0, 100, 100)

    img = paint(go)
    r, g, b = px(img, 50, 50)
    assert 110 < r < 145 and g == 0  # half-strength red on black
    assert px(img, 250, 50) == (0, 255, 0)


def test_translate_rotate_scale_compose_like_the_canvas():
    def go(d):
        c = d.ctx
        c.translate(320, 320)
        c.rotate(math.pi / 2)  # x now points down
        c.scale(2, 1)
        c.fill_style = "#fff"
        c.fill_rect(10, -5, 20, 10)  # in user space: becomes x in [-10, 10], y in [20, 60]

    img = paint(go)
    assert px(img, 320, 320 + 40) == (255, 255, 255) and px(img, 320 + 30, 320 + 40) == (0, 0, 0)


def test_arc_runs_clockwise_from_the_start_angle_like_the_canvas():
    def go(d):
        c = d.ctx
        c.stroke_style = "#fff"
        c.line_width = 12
        c.begin_path()
        c.arc(320, 320, 100, -math.pi / 2, 0)  # top to right: the top-right quarter
        c.stroke()

    img = paint(go)
    assert px(img, 320 + 71, 320 - 71)[0] > 200  # up and to the right
    assert px(img, 320 - 71, 320 - 71) == (0, 0, 0) and px(img, 320 + 71, 320 + 71) == (0, 0, 0)


def test_full_circle_arc_and_ellipse():
    def go(d):
        c = d.ctx
        c.fill_style = "#fff"
        c.begin_path()
        c.arc(160, 320, 50, 0, 7)
        c.fill()
        c.begin_path()
        c.ellipse(480, 320, 80, 30, 0, 0, 7)
        c.fill()

    img = paint(go)
    assert px(img, 160, 320) == (255, 255, 255) and px(img, 160, 380) == (0, 0, 0)
    assert px(img, 480 + 70, 320)[0] > 200 and px(img, 480, 320 + 45) == (0, 0, 0)


def test_clip_confines_painting_and_restore_lifts_it():
    def go(d):
        c = d.ctx
        c.save()
        c.begin_path()
        c.rect(100, 100, 100, 100)
        c.clip()
        c.fill_style = "#fff"
        c.fill_rect(0, 0, 640, 640)
        c.restore()
        c.fill_style = "#0f0"
        c.fill_rect(400, 400, 50, 50)

    img = paint(go)
    assert px(img, 150, 150) == (255, 255, 255) and px(img, 300, 300) == (0, 0, 0) and px(img, 420, 420) == (0, 255, 0)


def test_gradients_and_fill_rule():
    def go(d):
        c = d.ctx
        g = c.create_linear_gradient(0, 0, 640, 0)
        g.add_color_stop(0, "#000")
        g.add_color_stop(1, "#fff")
        assert isinstance(g, Gradient)
        c.fill_style = g
        c.fill_rect(0, 0, 640, 100)
        r = c.create_radial_gradient(320, 400, 0, 320, 400, 100)
        r.add_color_stop(0, "rgba(255,0,0,1)")
        r.add_color_stop(1, "rgba(255,0,0,0)")
        c.fill_style = r
        c.fill_rect(200, 300, 240, 200)
        # a ring: a square with a hole (even-odd)
        c.fill_style = "#0ff"
        c.begin_path()
        c.rect(20, 200, 100, 100)
        c.rect(50, 230, 40, 40)
        c.fill("evenodd")

    img = paint(go)
    assert px(img, 40, 50)[0] < 70 and px(img, 600, 50)[0] > 190  # dark to light
    assert px(img, 320, 400)[0] > 200 and px(img, 320 + 90, 400)[0] < 40  # red centre fading out
    assert px(img, 30, 210) == (0, 255, 255) and px(img, 70, 250) == (0, 0, 0)  # the hole


def test_line_dash_makes_gaps():
    def go(d):
        c = d.ctx
        c.stroke_style = "#fff"
        c.line_width = 8
        c.set_line_dash([20, 20])
        c.begin_path()
        c.move_to(0, 320)
        c.line_to(640, 320)
        c.stroke()

    img = paint(go)
    row = [QColor(img.pixel(x, int(320 * SIZE / 640))).red() > 128 for x in range(SIZE)]
    changes = sum(1 for a, b in zip(row, row[1:]) if a != b)
    assert 28 <= changes <= 34  # 16 dashes of 20 px over 640 px: 32 edges


def test_lighter_composite_adds():
    def go(d):
        c = d.ctx
        c.fill_style = "rgb(100,0,0)"
        c.fill_rect(0, 0, 640, 640)
        c.global_composite_operation = "lighter"
        c.fill_style = "rgb(100,50,0)"
        c.fill_rect(0, 0, 640, 640)

    assert px(paint(go), 300, 300) == (200, 50, 0)


def test_glow_spreads_light_past_the_edge_and_no_glow_turns_it_off():
    def go(d):
        d.glow("rgba(255,255,255,.9)", 20)
        d.ctx.fill_style = "#f00"
        d.ctx.fill_rect(300, 300, 40, 40)
        d.no_glow()
        d.ctx.fill_rect(500, 300, 40, 40)

    img = paint(go)
    assert px(img, 320, 320)[0] == 255
    assert max(px(img, 295, 320)) > 40  # a halo just outside the glowing square
    assert max(px(img, 495, 320)) == 0  # none beside the plain one
    assert max(px(img, 300 - 40, 320)) < max(px(img, 295, 320))  # and it fades with distance


def test_logo_draws_when_the_asset_exists():
    img = paint(lambda d: d.logo(320, 320, 120))
    assert lit(img, 260, 260, 380, 380) > 100


def test_polygons_plates_and_the_crosshair():
    img = paint(lambda d: (d.fill_poly(d.slanted(100, 100, 100, 50, 20), "#fff", None), d.crosshair(400, 400)))
    assert px(img, 150, 125) == (255, 255, 255) and px(img, 300, 125) == (0, 0, 0)
    assert px(img, 400 + 18, 400)[1] > 150  # the green arm
    plate = Draw.cut_plate(0, 0, 100, 50, 10)
    assert plate[0] == (10, 0) and plate[-1] == (0, 10) and len(plate) == 6


def test_stars_are_the_same_every_time():
    a = paint(lambda d: d.draw_stars(3.0, 3, 0, 0.7))
    b = paint(lambda d: d.draw_stars(3.0, 3, 0, 0.7))
    assert a == b and lit(a, 0, 0, 640, 640, 12) > 40


def test_rocks_are_drawn_in_pink_gold_and_grey():
    def go(d):
        d.draw_rock(120, 320, 60, 0.3, PINK, True, False, False)
        d.draw_rock(320, 320, 60, 0.3, GOLD, True, False, False)
        d.draw_rock(520, 320, 60, 0.3, (141, 162, 180), False, False, True)

    img = paint(go)
    for x in (120, 320, 520):
        assert lit(img, x - 60, 260, x + 60, 380) > 300
    rim = [px(img, x, y) for y in range(260, 380, 2) for x in range(256, 384, 2)]
    assert any(r > 200 and g > 150 and b < 90 for r, g, b in rim)  # a yellow rim


# ---- sprites
def test_wing_icon_fills_gold_and_the_ghost_is_pink_and_dashed():
    img = paint(lambda d: (wing_icon(d, 160, 320, 1.0, 0.9, False), wing_icon(d, 480, 320, 1.0, 0, True)))
    gold = [px(img, x, y) for x in range(120, 200, 4) for y in range(305, 335, 3)]
    assert any(r > 200 and g > 150 and b < 60 for r, g, b in gold)  # the gold fill between the cell lines
    assert lit(img, 400, 270, 560, 370) > 50
    assert px(img, 480, 320)[0] < 40  # an outline only: no gold fill


def test_battery_cells_light_in_order():
    for frac, n in ((1.0, 20), (0.5, 10), (0.04, 1), (0.0, 0)):
        img = paint(lambda d: draw_cells(d, 0.0, frac, (0, 229, 255), False, 1.0), 640)
        count = 0
        for i in range(20):
            x, y = 26 + (i % 10) * 12.5 + 7, 8 + (i // 10) * 30 + 12
            c = QColor(img.pixel(int(x), int(y)))
            count += c.green() > 150
        assert count == n


# ---- screens
def test_title_screen_has_the_wordmark_the_launch_plate_and_stars():
    img = scene("title")
    assert lit(img, 60, 180, 580, 250, 200) > 2000  # the white wordmark
    assert lit(img, 130, 318, 510, 340) > 200 and px(img, 320, 489)[2] > 100  # the gold line; the plate's top edge is cyan
    assert lit(img, 190, 500, 450, 550, 150) > 200  # LAUNCH
    assert lit(img, 0, 0, 640, 100, 12) > 20  # stars


def test_game_over_variants_use_their_colours():
    hull = scene("over")
    assert lit(hull, 150, 100, 500, 150, 100) > 500
    pink = [px(hull, x, 130) for x in range(150, 500)]
    assert any(r > 200 and b > 150 and g < 120 for r, g, b in pink)  # HULL DESTROYED in pink
    won = scene("win")
    gold = [px(won, x, 130) for x in range(150, 500)]
    assert any(r > 200 and g > 150 and b < 80 for r, g, b in gold)  # BELT CLEARED in gold
    assert lit(won, 290, 266, 350, 326, 60) > 100  # the logo shows only on the win screen


def test_the_buttons_are_where_the_hit_boxes_are():
    img = scene("over")
    for y in (330, 420):  # the top edges of RETRY and TITLE
        assert max(px(img, 320, y + dy)[2] for dy in (-1, 0, 1)) > 100


def test_loading_overlay_dims_the_title():
    def go(name):
        g = Game(seed=1)
        apply_scene(g, name)
        g.launching = True

        def draw(d):
            draw_game(d, g)

        return paint(draw)

    img = go("title")
    assert lit(img, 100, 300, 540, 360, 150) > 100 and px(img, 320, 200) != px(scene("title"), 320, 200)


def test_every_phase_draws_without_error():
    for name in ("title", "intro:6", "intro:36", "intro:40", "lvl:3:2", "over", "win"):
        img = scene(name)
        assert img.width() == SIZE


def test_scenes_render_at_any_size_and_agree():
    a, b = scene("title", 320), scene("title", 640)
    assert b.width() == 640 and lit(a, 0, 0, 640, 640, 100) > 0
    from PySide6.QtCore import Qt

    sa = a.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    sb = b.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    total = sum(abs(QColor(sa.pixel(x, y)).green() - QColor(sb.pixel(x, y)).green()) for y in range(64) for x in range(64))
    assert total / 4096 < 3  # the same picture at two resolutions (mean difference of 3 levels of 255 after shrinking both)
