import math

import pytest

from overblaster import config as C
from overblaster import hud, screens


def width(text, size, weight="medium", spacing=0.0):
    """A stand-in for Inter: about 0.66 em per capital letter plus tracking (black is a little wider)."""
    return len(text) * (size * (0.72 if weight == "black" else 0.66) + spacing)


CROSSHAIR = (284, 284, 356, 356)  # the crosshair box at the centre of the screen


def box(t):
    w = width(t.text, t.size, t.weight, t.spacing)
    x = t.x - w / 2 if t.anchor == "middle" else t.x
    return (x, t.y - t.size, x + w, t.y)


def hits_crosshair(t):
    x1, y1, x2, y2 = box(t)
    return not (x2 < CROSSHAIR[0] or x1 > CROSSHAIR[2] or y2 < CROSSHAIR[1] or y1 > CROSSHAIR[3])


# ================= title =================
def test_the_title_has_two_rows_of_twenty_cells_above_and_below_the_wordmark():
    m = screens.title_model(0.0, width)
    top = [c for c in m.cells if c.row == "top"]
    bottom = [c for c in m.cells if c.row == "bottom"]
    assert len(top) == len(bottom) == 20
    word_y = m.wordmark.y
    assert max(y for c in top for _, y in c.points) < word_y - m.wordmark.size * 0.6  # clear above the capitals
    assert min(y for c in bottom for _, y in c.points) > word_y  # below the baseline


def test_the_two_rows_run_in_opposite_directions():
    def lit_order(row, t):
        return [c.alpha for c in sorted([c for c in screens.title_model(t, width).cells if c.row == row], key=lambda c: c.points[0][0])]

    t = 0.3  # early in the cycle: the cells that start first are bright
    top, bottom = lit_order("top", t), lit_order("bottom", t)
    assert top[0] > top[-1], "the top row should start at the left"
    assert bottom[-1] > bottom[0], "the bottom row should start at the right"


def test_a_cell_pulses_on_and_off_and_loops():
    a = [screens.boot_alpha(t / 100, 0.0) for t in range(0, 600)]
    assert min(a) == pytest.approx(0.06, abs=0.01) and max(a) == pytest.approx(0.95, abs=0.01)
    assert screens.boot_alpha(0.0, 0.0) == pytest.approx(0.06, abs=0.001)
    assert screens.boot_alpha(0.3, 0.0) == pytest.approx(screens.boot_alpha(0.3 + screens.BOOT_PERIOD, 0.0), abs=1e-6)  # loops
    assert screens.boot_alpha(1.0, 0.0) == pytest.approx(0.95)  # held lit in the middle of the cycle


def test_the_wordmark_fits_the_screen_whatever_the_font_width():
    for w in (lambda t, s, wt="bold", sp=0.0: len(t) * (s * 0.6 + sp), width, lambda t, s, wt="black", sp=0.0: len(t) * (s * 0.8 + sp)):
        m = screens.title_model(0.0, w)
        assert w(m.wordmark.text, m.wordmark.size, m.wordmark.weight, m.wordmark.spacing) <= 560 + 1e-6
        assert m.wordmark.size >= 40


def test_the_title_says_what_the_game_is_and_how_to_play_and_nothing_else():
    words = [t.text for t in screens.title_model(0.0, width).texts]
    assert "OVERBLASTER" in words and "AN OVERLORD LABS GAME" in words
    assert "TURN YOUR HEAD TO AIM" in words and "SAY “PEW” TO FIRE" in words and "HOLD YOUR AIM ON CRYSTALS TO HARVEST THEM" in words
    assert "LOOK AT IT FOR 1.5 SECONDS" in words


def test_the_launch_button_has_room_below_the_hints():
    m = screens.title_model(0.0, width)
    hint_bottom = max(t.y for t in m.texts if t.text.startswith(("TURN", "SAY", "HOLD")))
    x, y, w, h = screens.LAUNCH
    assert y > hint_bottom + 10 and x + w / 2 == 320 and y + h < screens.SIZE


# ================= between levels (count-up) =================
def test_the_score_counts_up_with_an_ease_out_and_ends_exactly_on_the_score():
    assert screens.count_up(0.0, 12480) == 0
    assert screens.count_up(screens.COUNT_S, 12480) == 12480 and screens.count_up(99, 12480) == 12480
    mid = screens.count_up(screens.COUNT_S / 2, 12480)
    assert 0.8 * 12480 < mid < 12480  # fast at first: most of it in the first half
    values = [screens.count_up(t / 50, 12480) for t in range(0, 80)]
    assert values == sorted(values)  # never goes backwards


def test_a_zero_score_stays_zero():
    assert screens.count_up(0.7, 0) == 0
    assert screens.pause_model(2, 0, 20, hud.CYAN, 0.9, width).score.text == "0"


def test_the_pause_plate_says_the_level_is_cleared_and_what_comes_next():
    m = screens.pause_model(3, 12480, 16, hud.CYAN, 5.0, width)
    words = [t.text for t in m.texts]
    assert "LVL 3" in words and "SECTOR CLEARED" in words and "SCORE" in words and "NEXT" in words
    assert "LVL 4" in words and C.level_name(4) in words
    assert m.score.text == "12,480"
    assert m.next_name_text == C.level_name(4)


def test_next_slides_in_after_the_score_starts_counting():
    early, late = screens.pause_model(3, 12480, 16, hud.CYAN, 0.2, width), screens.pause_model(3, 12480, 16, hud.CYAN, 1.5, width)
    assert early.next_alpha == 0.0 and late.next_alpha == pytest.approx(1.0)
    assert early.next_dy > 5 and late.next_dy == pytest.approx(0.0)


def test_the_cells_fill_in_one_after_another_to_the_batterys_real_level():
    final = screens.pause_model(3, 12480, 13, hud.CYAN, 2.0, width)
    assert [c.lit for c in final.cells] == [True] * 13 + [False] * 7
    assert all(c.alpha == pytest.approx(0.95) for c in final.cells if c.lit)
    mid = screens.pause_model(3, 12480, 13, hud.CYAN, 0.45, width)
    alphas = [c.alpha for c in mid.cells if c.lit]
    assert alphas == sorted(alphas, reverse=True) and alphas[0] > alphas[-1]  # earlier cells are further along
    assert screens.pause_model(3, 12480, 0, hud.CYAN, 2.0, width).cells[0].lit is False


def test_the_pause_plate_uses_the_batterys_colour_for_its_cells():
    assert screens.pause_model(3, 100, 4, hud.PINK, 2.0, width).tone == hud.PINK


def test_the_words_on_the_pause_plate_stay_clear_of_the_crosshair():
    m = screens.pause_model(3, 12480, 16, hud.CYAN, 5.0, width)
    for t in m.texts:
        assert not hits_crosshair(t), (t.text, box(t))
    assert min(y for c in m.cells for _, y in c.points) > CROSSHAIR[3]  # and so do the cells


def test_the_pause_plate_is_in_the_middle_of_the_screen():
    xs = [x for x, _ in screens.pause_model(3, 100, 10, hud.CYAN, 5.0, width).plate]
    ys = [y for _, y in screens.pause_model(3, 100, 10, hud.CYAN, 5.0, width).plate]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(320) and 120 < (min(ys) + max(ys)) / 2 < 400


# ================= level start (number block) =================
def test_the_splash_fades_in_holds_and_fades_out_behind_everything():
    assert screens.splash_alpha(0.0) == 0.0
    assert screens.splash_alpha(screens.SPLASH_FADE_IN) == pytest.approx(screens.SPLASH_MAX)
    assert screens.splash_alpha(1.5) == pytest.approx(screens.SPLASH_MAX)
    assert 0 < screens.splash_alpha(screens.SPLASH_END - 0.2) < screens.SPLASH_MAX
    assert screens.splash_alpha(screens.SPLASH_END) == 0.0 and screens.splash_alpha(10) == 0.0
    assert screens.SPLASH_MAX <= 0.6, "it is a background layer: it must stay see-through"
    assert 5.0 <= screens.SPLASH_END <= 10.0, "several seconds, long enough to read and look around"


def test_the_splash_has_the_level_number_in_a_block_and_the_name_beside_it():
    m = screens.splash_model(3, C.level_name(3), width)
    assert m.number.text == "3" and m.caption.text == "LVL" and m.name.text == C.level_name(3)
    bx = [x for x, _ in m.block]
    assert m.name.x > max(bx)  # the name sits to the right of the block
    assert m.number.color == (0, 0, 0) and m.caption.color == (0, 0, 0)  # dark on the solid block


def test_the_splash_is_centred_on_its_anchor_point():
    m = screens.splash_model(3, C.level_name(3), width)
    xs = [x for x, _ in m.plate]; ys = [y for _, y in m.plate]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(0) and (min(ys) + max(ys)) / 2 == pytest.approx(0)


def test_every_level_name_fits_inside_the_splash_plate():
    for level in range(1, 12):
        m = screens.splash_model(level, C.level_name(level), width)
        plate_right = max(x for x, _ in m.plate)
        assert m.name.x + width(m.name.text, m.name.size, m.name.weight, m.name.spacing) <= plate_right - 16, (level, m.name.size)
        assert m.name.size >= 30


def test_a_long_name_shrinks_to_fit():
    short = screens.splash_model(3, "VOID STORM", width).name.size
    longest = screens.splash_model(3, "KUIPER BELT OUTPOST", width).name.size
    assert longest < short


def test_the_splash_sits_just_above_the_crosshair_so_the_crosshair_never_strikes_through_it():
    cx, cy = screens.SPLASH_ANCHOR  # where its centre is on screen when the level starts
    m = screens.splash_model(5, C.level_name(5), width)
    bottom = cy + max(y for _, y in m.plate)
    assert bottom < CROSSHAIR[1], f"the plate reaches y={bottom}, into the crosshair"
    assert cx == 320


def test_the_anchor_is_a_small_angle_above_where_the_player_is_looking():
    assert 4 < screens.SPLASH_EL_OFFSET < 9  # degrees up, so it sits above the crosshair
    assert screens.SPLASH_EL_OFFSET * (C.DISPLAY_PX / C.FOV_DEG) == pytest.approx(320 - screens.SPLASH_ANCHOR[1], abs=1.0)


def test_the_plate_asks_for_a_pew_to_continue_once_the_numbers_have_settled():
    early = screens.pause_model(3, 12480, 16, hud.CYAN, 0.3, width)
    late = screens.pause_model(3, 12480, 16, hud.CYAN, 3.0, width)
    prompt = lambda m: next(t for t in m.texts if "CONTINUE" in t.text)
    assert prompt(early).alpha == 0.0 and prompt(late).alpha == pytest.approx(1.0)
    assert "PEW" in prompt(late).text
    assert not hits_crosshair(prompt(late))
    plate_bottom = max(y for _, y in late.plate)
    assert prompt(late).y < plate_bottom - 8  # inside the plate


def test_the_plate_can_be_dismissed_only_after_the_count_up():
    assert screens.ACK_MIN_S >= screens.COUNT_S
