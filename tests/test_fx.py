import math

import pytest

from overblaster import fx

MUZZLE = (320.0, 600.0)
TARGET = (320.0, 200.0)


def shapes(kind, age, size=60.0):
    return fx.shot_shapes(kind, age, MUZZLE, TARGET, size)


def lines(items):
    return [s for s in items if isinstance(s, fx.Line)]


def circles(items):
    return [s for s in items if isinstance(s, fx.Circle)]


def test_every_shape_is_well_formed_at_every_moment():
    for kind in ("miss", "hit", "kill"):
        for step in range(0, 80):
            for s in shapes(kind, step * 0.01):
                assert 0.0 <= s.alpha <= 1.0, (kind, step, s)
                assert all(math.isfinite(v) for v in vars(s).values() if isinstance(v, float))
                assert s.color == tuple(max(0, min(255, c)) for c in s.color)


def test_a_shot_fires_a_beam_from_the_ship_to_the_target():
    beams = lines(shapes("hit", 0.0))
    assert beams, "no beam at the moment of firing"
    longest = max(beams, key=lambda l: abs(l.y2 - l.y1))
    assert (longest.x1, longest.y1) == MUZZLE and (longest.x2, longest.y2) == TARGET
    # three layers: a wide faint glow, a brighter middle, a white-hot core
    widths = sorted({round(l.width) for l in beams if (l.x1, l.y1) == MUZZLE}, reverse=True)
    assert len(widths) >= 3 and any(l.color == fx.WHITE for l in beams)


def test_the_beam_fades_and_is_gone_after_its_length():
    bright = max(l.alpha for l in lines(shapes("miss", 0.0)))
    dim = max(l.alpha for l in lines(shapes("miss", fx.BEAM_S * 0.8)) if l.color == fx.WHITE)
    assert dim < bright
    assert not [l for l in lines(shapes("miss", fx.BEAM_S + 0.01)) if (l.x1, l.y1) == MUZZLE]


def test_there_is_a_muzzle_flash_at_the_ship_then_it_ends():
    assert [c for c in circles(shapes("miss", 0.0)) if (c.x, c.y) == MUZZLE]
    assert not [c for c in circles(shapes("miss", fx.MUZZLE_S + 0.01)) if (c.x, c.y) == MUZZLE]


def test_each_shot_ends_with_nothing_left_to_draw():
    # A shot lasts as long as its longest part: the beam and muzzle flash, or the impact.
    for kind, impact in (("miss", fx.MISS_S), ("hit", fx.HIT_S), ("kill", fx.KILL_S)):
        length = max(impact, fx.BEAM_S, fx.MUZZLE_S)
        assert shapes(kind, 0.0)
        assert shapes(kind, length + 0.01) == [], f"{kind} still drawing after {length} s"


def test_the_game_keeps_a_shot_long_enough_for_its_longest_animation():
    from overblaster import config as C

    assert C.SHOT_FX_S >= max(fx.BEAM_S, fx.MUZZLE_S, fx.MISS_S, fx.HIT_S, fx.KILL_S)


def test_a_kill_is_bigger_and_busier_than_a_hit_which_is_bigger_than_a_miss():
    def reach(kind, age):
        return max((c.radius for c in circles(shapes(kind, age)) if (c.x, c.y) == TARGET), default=0)

    age = 0.1
    assert reach("kill", age) > reach("hit", age) > reach("miss", age)
    assert len(shapes("kill", 0.05)) > len(shapes("hit", 0.05)) > len(shapes("miss", 0.05))


def test_impacts_scale_with_the_size_of_the_world():
    small = max(c.radius for c in circles(shapes("kill", 0.2, size=30)) if (c.x, c.y) == TARGET)
    big = max(c.radius for c in circles(shapes("kill", 0.2, size=90)) if (c.x, c.y) == TARGET)
    assert big > small * 2


def test_impacts_are_centered_on_the_target():
    for kind in ("hit", "kill"):
        impact = [c for c in circles(shapes(kind, 0.1)) if (c.x, c.y) == TARGET]
        assert impact


def test_death_explosion_frames_the_whole_view_in_red_then_ends():
    first = fx.death_shapes(0.0, (500, 200), 64, 640, 640)
    rects = [s for s in first if isinstance(s, fx.Rect)]
    assert len(rects) == 4 and all(r.color == fx.RED for r in rects)
    covered = sum(r.w * r.h for r in rects)
    assert covered > 0.15 * 640 * 640  # a vignette you can't miss
    assert fx.death_shapes(fx.DEATH_S + 0.01, (500, 200), 64, 640, 640) == []
    late = [s for s in fx.death_shapes(fx.DEATH_S * 0.9, (500, 200), 64, 640, 640) if isinstance(s, fx.Rect)]
    assert max(r.alpha for r in late) < max(r.alpha for r in rects)  # it fades


def test_death_blast_stays_on_screen_even_if_the_world_was_off_to_the_side():
    for center in ((-300, 100), (2000, 100), (320, -50), (320, 5000)):
        blast = [s for s in fx.death_shapes(0.2, center, 64, 640, 640) if isinstance(s, fx.Circle)]
        assert blast
        assert all(0 <= c.x <= 640 and 0 <= c.y <= 640 for c in blast)
