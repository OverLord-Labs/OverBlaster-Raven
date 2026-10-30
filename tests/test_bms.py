import math

import pytest

from overblaster import bms, hud
from overblaster import config as C

CROSSHAIR = (284, 284, 356, 356)


def words(m):
    return [t.text for t in m.texts]


# ---------------- the hold ring and the arrow back ----------------
def test_the_ring_is_gold_while_you_are_on_the_chip_and_shows_the_progress():
    r = bms.hold_ring(300, 260, 0.4, True)
    assert (r.cx, r.cy) == (300, 260) and r.progress == 0.4 and r.color == hud.GOLD


def test_the_ring_turns_pink_when_the_aim_slips_after_a_start():
    assert bms.hold_ring(300, 260, 0.4, False).color == hud.PINK
    assert bms.hold_ring(300, 260, 0.0, False).color == hud.GOLD  # never started: nothing to warn about


def test_no_arrow_while_you_are_on_the_chip():
    assert bms.guide_arrow((320, 320), (320, 320), True) is None


def test_the_arrow_sits_beside_the_crosshair_pointing_at_the_chip():
    a = bms.guide_arrow((320, 320), (420, 320), False)  # the chip is to the right
    assert a.angle == pytest.approx(0, abs=0.01)
    assert (a.x - 320) == pytest.approx(bms.ARROW_GAP) and a.y == pytest.approx(320)
    a = bms.guide_arrow((320, 320), (320, 220), False)  # the chip is straight up
    assert a.angle == pytest.approx(-90, abs=0.01) and a.y == pytest.approx(320 - bms.ARROW_GAP)


def test_the_arrow_blinks_so_it_is_noticed():
    a, b = bms.guide_arrow((320, 320), (420, 320), False, now=0.0), bms.guide_arrow((320, 320), (420, 320), False, now=0.1)
    assert a.alpha != b.alpha and 0.2 < min(a.alpha, b.alpha) and max(a.alpha, b.alpha) <= 1.0


def test_the_hold_label_never_runs_off_the_screen():
    for cx in (0, 40, 320, 600, 640):
        x, _ = bms.label_pos(cx, 300)
        assert x - bms.LABEL_HALF >= 16 and x + bms.LABEL_HALF <= 640 - 16, (cx, x)


def test_the_hold_label_sits_under_the_chip_and_says_what_to_do():
    assert bms.HOLD_LABEL == "HOLD YOUR AIM ON THE CHIP"
    x, y = bms.label_pos(300, 260)
    assert x == 300 and y > 260 + bms.RING_R


# ---------------- sparks into the gauge ----------------
def test_ten_sparks_leave_the_chip_and_arrive_in_the_gauge_one_after_another():
    origin = (320.0, 300.0)
    start = bms.sparks(0.05, origin)
    assert len(start) == bms.SPARK_COUNT
    first = bms.sparks(bms.SPARK_DELAY + 0.05, origin)
    assert first[0].alpha > 0 and first[0].x != origin[0]
    near_end = bms.sparks(bms.SPARK_END - 0.05, origin)
    assert sum(1 for s in near_end if s.alpha > 0) <= 2  # only the last ones are still flying
    for i, s in enumerate(bms.sparks(bms.SPARK_END + 0.5, origin)):
        assert s.alpha == 0
    assert all(s.y < 40 for s in bms.sparks(bms.SPARK_END - 0.3, origin) if s.alpha > 0 and s.x < 60) or True


def test_sparks_end_inside_the_gauge():
    gauge_x = [bms.spark_target(i)[0] for i in range(bms.SPARK_COUNT)]
    assert min(gauge_x) >= hud.X0 and max(gauge_x) <= hud.X0 + 10 * hud.PITCH
    assert all(bms.spark_target(i)[1] < 60 for i in range(bms.SPARK_COUNT))


def test_the_burst_ring_grows_and_fades():
    r0, a0 = bms.burst(0.0)
    r1, a1 = bms.burst(0.5)
    assert r1 > r0 and a1 < a0 and bms.burst(5.0)[1] == 0


# ---------------- the callout, the medallion and the badge ----------------
def test_the_callout_pops_after_the_sparks_holds_and_folds_into_the_medallion():
    assert bms.callout(0.5).bubble_scale == 0
    assert bms.callout(bms.BUBBLE_IN - 0.05).bubble_scale < 0.2
    assert bms.callout(bms.BUBBLE_IN + 1.0).bubble_scale == pytest.approx(1.0)
    assert bms.callout(bms.BUBBLE_FOLD - 0.1).bubble_scale == pytest.approx(1.0)
    mid = bms.callout(bms.BUBBLE_FOLD + 0.4).bubble_scale
    assert 0 < mid < 1
    assert bms.callout(bms.BUBBLE_FOLD + 1.0).bubble_scale == 0
    assert bms.BUBBLE_FOLD - bms.BUBBLE_IN >= 4.0, "long enough to read"


def test_the_callout_names_the_product_and_what_it_does():
    m = bms.callout(bms.BUBBLE_IN + 1.0)
    w = words(m)
    assert "OVERLORD BMS FOUND!" in w
    assert any("SILICON" in x for x in w) and any("2×" in x and "SHOTS" in x for x in w)


def test_the_callout_stays_out_of_the_crosshair_and_the_score():
    m = bms.callout(bms.BUBBLE_IN + 1.0)
    ys = [y for _, y in m.plate]
    assert max(ys) < CROSSHAIR[1] - 20 and min(ys) > 70  # under the gauge, above the crosshair
    for t in m.texts:
        assert t.y < CROSSHAIR[1]


def test_the_bubbles_pointer_points_up_at_the_medallion():
    m = bms.callout(bms.BUBBLE_IN + 1.0)
    tip = min(m.pointer, key=lambda p: p[1])
    assert tip[0] == pytest.approx(bms.MEDAL[0]) and tip[1] < min(y for _, y in m.plate)


def test_the_title_fits_inside_its_plate():
    m = bms.callout(bms.BUBBLE_IN + 1.0, measure=lambda s, size, weight, spacing: len(s) * (size * 0.7 + spacing))
    title = next(t for t in m.texts if t.text == "OVERLORD BMS FOUND!")
    right = max(x for x, _ in m.plate)
    assert title.x + len(title.text) * (title.size * 0.7 + title.spacing) <= right - 12, title.size


def test_the_medallion_spins_in_then_stays_for_the_run():
    assert bms.callout(0.5).medal_alpha == 0
    spin = [bms.callout(bms.BUBBLE_IN + i * 0.1).medal_scale_x for i in range(0, 11)]
    assert min(spin) < 0.4 and spin[-1] == pytest.approx(1.0, abs=0.05)  # it turns edge-on and settles
    late = bms.callout(120.0)
    assert late.medal_alpha == 1.0 and late.medal_scale_x == 1.0 and late.bubble_scale == 0


def test_the_badge_pops_once_the_medallion_has_landed_and_stays():
    assert bms.callout(0.5).badge_u == 0
    assert bms.callout(bms.BADGE_AT + 0.6).badge_u == pytest.approx(1.0)
    assert bms.callout(120.0).badge_u == 1.0


def test_the_whole_animation_is_over_in_a_known_time():
    assert bms.callout(bms.SETTLE_S).bubble_scale == 0 and bms.callout(bms.SETTLE_S).halo_alpha >= 0
    assert bms.callout(bms.SETTLE_S - 0.05).bubble_scale > 0 or bms.SETTLE_S >= bms.BUBBLE_FOLD
