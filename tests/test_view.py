import pytest

from overblaster import config as C
from overblaster.view import closest, pixels_per_degree, pointer, project, size_class

W = H = 640


def test_straight_ahead_is_screen_center():
    p = project(100, 0, 100, 0, W, H)
    assert (p.x, p.y) == (320, 320) and p.on_screen and p.side is None


def test_right_and_up_move_the_right_way():
    ppd = pixels_per_degree(W)
    p = project(105, 4, 100, 0, W, H)  # object is right of and above the view
    assert p.x == pytest.approx(320 + 5 * ppd, rel=0.01)  # cos(4 deg) ~ 1
    assert p.y == pytest.approx(320 - 4 * ppd)


def test_projection_wraps_across_north():
    p = project(359, 0, 1, 0, W, H)
    assert p.x < 320 and p.on_screen  # 2 deg to the left, not 358 deg to the right


def test_off_screen_reports_side():
    assert project(140, 0, 100, 0, W, H).side == "right"
    assert project(60, 0, 100, 0, W, H).side == "left"
    assert project(100, 25, 100, -25, W, H).side is None  # far above: off screen, not sideways
    assert not project(100, 25, 100, -25, W, H).on_screen


def test_margin_keeps_partly_visible_sprites():
    edge = project(100 + 15.5, 0, 100, 0, W, H)  # just past the right edge
    assert not edge.on_screen
    assert project(100 + 15.5, 0, 100, 0, W, H, margin=64).on_screen


def test_size_class_picks_one_of_the_prerendered_bands():
    for r in (0.5, 1.0, 1.4, 2.0, 2.6, 3.0, 5.0):
        assert size_class(r) in C.WORLD_BANDS
        assert size_class(r) % 4 == 0  # MediaViewer needs multiples of 4
    assert size_class(C.WORLD_MIN_RADIUS) == min(C.WORLD_BANDS)
    assert size_class(C.WORLD_MAX_RADIUS) == max(C.WORLD_BANDS)
    sizes = [size_class(r / 10) for r in range(5, 40)]
    assert sizes == sorted(sizes)  # growing never shrinks the sprite


def test_a_world_changes_band_only_a_few_times_while_approaching():
    steps = [size_class(C.WORLD_MIN_RADIUS + (C.WORLD_MAX_RADIUS - C.WORLD_MIN_RADIUS) * i / 100) for i in range(101)]
    swaps = sum(a != b for a, b in zip(steps, steps[1:]))
    assert swaps <= len(C.WORLD_BANDS) - 1


def test_every_band_has_its_gifs():
    import os

    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "worlds")
    for kind in (*C.WORLD_KINDS, "chip"):
        for band in C.WORLD_BANDS:
            assert os.path.exists(os.path.join(root, f"world_{kind}_{band}.gif")), (kind, band)


# --- the pointer arrow ---------------------------------------------------------------------
def deg(p):
    return math.degrees(p.angle)


import math  # noqa: E402


def test_the_pointer_points_right_up_left_down_and_everything_between():
    right = pointer(140, 0, 100, 0, W, H)
    left = pointer(60, 0, 100, 0, W, H)
    up = pointer(100, 20, 100, 0, W, H)
    down = pointer(100, -20, 100, 0, W, H)
    assert deg(right) == pytest.approx(0, abs=0.5)
    assert abs(deg(left)) == pytest.approx(180, abs=0.5)
    assert deg(up) == pytest.approx(-90, abs=0.5)  # screen y runs down, so up is negative
    assert deg(down) == pytest.approx(90, abs=0.5)
    assert 0 < deg(pointer(130, -15, 100, 0, W, H)) < 90  # down and to the right
    assert -90 < deg(pointer(130, 15, 100, 0, W, H)) < 0  # up and to the right
    assert -180 < deg(pointer(70, 15, 100, 0, W, H)) < -90  # up and to the left


def test_a_target_behind_you_points_the_shorter_way_round():
    # 170 degrees to the right of the view is just left of straight behind: turn left, not right.
    assert abs(deg(pointer(100 + 170, 0, 100, 0, W, H))) < 5
    assert abs(deg(pointer(100 - 170, 0, 100, 0, W, H))) > 175


def test_the_pointer_wraps_across_north():
    assert deg(pointer(2, 0, 358, 0, W, H)) == pytest.approx(0, abs=0.5)  # 4 degrees to the right
    assert abs(deg(pointer(358, 0, 2, 0, W, H))) == pytest.approx(180, abs=0.5)


def test_the_pointer_sits_on_a_ring_around_the_center_whatever_the_direction():
    for az, el in ((140, 0), (60, 0), (100, 20), (100, -20), (130, 15), (300, -10)):
        p = pointer(az, el, 100, 0, W, H, ring=250)
        assert math.hypot(p.x - W / 2, p.y - H / 2) == pytest.approx(250, abs=0.01)
        assert 0 <= p.x <= W and 0 <= p.y <= H  # always inside the display


def test_the_pointer_turns_as_the_head_turns():
    before = pointer(130, 0, 100, 0, W, H)  # to the right
    after = pointer(130, 0, 130, 15, W, H)  # now the target is below the view
    assert deg(before) == pytest.approx(0, abs=0.5)
    assert deg(after) > 45


def test_on_screen_targets_need_no_arrow_but_big_ones_overhanging_the_edge_count():
    assert pointer(100, 0, 100, 0, W, H).on_screen
    assert pointer(110, 5, 100, 0, W, H).on_screen
    assert not pointer(140, 0, 100, 0, W, H).on_screen
    edge = (100 + 15.5, 0)  # just past the right edge
    assert not pointer(*edge, 100, 0, W, H).on_screen
    assert pointer(*edge, 100, 0, W, H, margin=64).on_screen


def test_closest_picks_the_target_nearest_the_view_not_the_nearest_to_the_ship():
    class T:
        def __init__(self, az, el):
            self.az, self.el = az, el

    near, far = T(110, 5), T(200, 0)
    assert closest([far, near], 100, 0) is near
    assert closest([T(359, 0), T(30, 0)], 5, 0).az == 359  # 6 degrees away across north, not 25
    assert closest([], 0, 0) is None
