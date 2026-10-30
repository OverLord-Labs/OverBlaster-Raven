import pytest

from overblaster import config as C
from overblaster import hud


def model(p=0.78, chip=False, level=3):
    return hud.build(p, chip, level)


# ---- the meter ----
def test_the_meter_is_twenty_cells_in_two_rows_of_ten():
    m = model()
    assert len(m.cells) == 20
    ys = sorted({round(min(y for _, y in c.points), 1) for c in m.cells})
    assert len(ys) == 2 and ys[1] - ys[0] > 24  # two rows with a gap between them
    xs_top = sorted(min(x for x, _ in c.points) for c in m.cells[:10])
    assert xs_top == sorted(xs_top) and len(set(xs_top)) == 10


def test_cells_are_slanted_parallelograms():
    for c in model().cells:
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = c.points
        assert y1 == y2 and y3 == y4 and y3 > y1  # flat top and bottom
        assert x1 > x4 and x2 > x3 and (x2 - x1) == pytest.approx(x3 - x4)  # leaning


def test_cells_light_in_reading_order_and_the_last_lit_one_is_marked():
    for p, expected in ((1.0, 20), (0.78, 16), (0.5, 10), (0.51, 11), (0.04, 1), (0.0, 0)):
        m = model(p)
        assert [c.lit for c in m.cells].count(True) == expected, p
        assert [c.lit for c in m.cells] == [True] * expected + [False] * (20 - expected)
        assert [c.last for c in m.cells].count(True) == (1 if expected else 0)
        if expected:
            assert m.cells[expected - 1].last


def test_any_charge_at_all_lights_at_least_one_cell():
    assert hud.lit_cells(0.001) == 1 and hud.lit_cells(0.0) == 0 and hud.lit_cells(1.0) == 20 and hud.lit_cells(1.5) == 20


def test_the_meter_is_at_the_very_top_left_of_the_screen():
    top = min(y for c in model().cells for _, y in c.points)
    left = min(x for c in model().cells for x, _ in c.points)
    assert 0 <= top <= 10 and 0 <= left <= 40


def test_the_meter_and_the_level_fit_in_a_small_corner():
    m = model(chip=True, level=128)  # even a three-digit level
    assert max(x for c in m.cells for x, _ in c.points) < 170
    assert m.caption.x + 6 * (m.caption.size * 0.7 + m.caption.spacing) < 400  # nothing reaches toward the score


# ---- colour ----
def test_colour_is_cyan_normally_magenta_when_low_and_gold_with_the_chip():
    assert model(0.78).tone == hud.CYAN
    assert model(0.24).tone == hud.PINK and model(0.24).low
    assert model(0.0).tone == hud.PINK
    assert model(0.78, chip=True).tone == hud.GOLD and not model(0.78, chip=True).low
    assert model(0.10, chip=True).tone == hud.PINK  # low beats the chip: a warning is a warning
    assert not model(0.25).low and model(0.25).tone == hud.CYAN


# ---- the level number: "LVL 1", and never the level's name ----
def test_the_level_is_shown_as_lvl_and_the_number_not_zero_padded():
    for level in (1, 3, 10, 42):
        assert model(level=level).caption.text == f"LVL {level}"


def test_there_is_no_level_name_percentage_or_energy_label_in_the_hud():
    for p, chip, level in ((0.78, False, 1), (1.0, True, 5), (0.1, False, 3), (0.0, False, 6)):
        m = model(p, chip, level)
        words = " ".join(t.text for t in m.texts)
        assert words == f"LVL {level}", words  # nothing else is written
        assert not hasattr(m, "name")
        assert not any(n in words for n in C.LEVEL_NAMES)


def test_the_level_sits_to_the_right_of_the_meter_vertically_centred_on_it():
    m = model()
    meter_right = max(x for c in m.cells for x, _ in c.points)
    meter_top = min(y for c in m.cells for _, y in c.points)
    meter_bottom = max(y for c in m.cells for _, y in c.points)
    assert m.caption.x > meter_right and m.divider[0] > meter_right and m.divider[0] < m.caption.x
    middle = (meter_top + meter_bottom) / 2
    glyph_middle = m.caption.y - m.caption.size * 0.35  # about the middle of the capitals above the baseline
    assert glyph_middle == pytest.approx(middle, abs=5)


def test_the_level_takes_the_batterys_colour():
    for p, chip in ((0.78, False), (0.1, False), (0.78, True)):
        m = model(p, chip)
        assert m.caption.color == m.tone


def test_the_level_number_is_big_enough_to_read_on_the_glasses():
    assert model().caption.size >= 22  # it is the only text beside the meter, so it can be large


# ---- the chip badge ----
def test_the_chip_badge_is_under_the_meter_and_only_with_the_chip():
    assert model(0.78).pill is None
    pill = model(0.78, chip=True).pill
    assert pill is not None
    x, y, w, h = pill
    assert y > max(y for c in model().cells for _, y in c.points)  # below the grid
    assert x >= 0 and x + w < 170
    assert w >= 24 + 40, "room for the OD mark and a x2"


def test_the_badge_pops_in_overshooting_a_little_then_settles():
    scales = [hud.badge_scale(i / 20) for i in range(21)]
    assert scales[0] == pytest.approx(0.4) and scales[-1] == pytest.approx(1.0)
    assert max(scales) > 1.0 and scales[-1] == 1.0


# ---- the level names (shown only when a level starts) ----
def test_level_names_exist_and_the_last_one_repeats():
    assert C.level_name(1) == C.LEVEL_NAMES[0] and C.level_name(len(C.LEVEL_NAMES)) == C.LEVEL_NAMES[-1]
    assert C.level_name(99) == C.LEVEL_NAMES[-1] and C.level_name(0) == C.LEVEL_NAMES[0]
