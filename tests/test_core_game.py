"""The rules of the game core: a port of the web game's tests/core.test.ts."""

import math

from overblaster.core import (
    CHIP_CAPACITY, CHIP_HOLD, COUNT_AT, GAME_AT, INTRO_END, LEVELS, MAX_LEVEL, WING_HOLD, Game, Head, InputFrame, Press, Rng, Turn, azd,
    empty_input, level_plan, level_say, simulate_level, Look,
)

DT = 1 / 30


def play(seed: int = 1) -> Game:
    g = Game(seed=seed)
    g.begin_game()
    g.drain()
    return g


def step(g: Game, secs: float, **kw):
    """Advance by secs seconds, one frame at a time. Keyword args fill the InputFrame. Returns the events."""
    out = []
    for _ in range(round(secs / DT)):
        f = empty_input()
        for k, v in kw.items():
            setattr(f, k, v)
        g.update(DT, f)
        out.extend(g.drain())
    return out


def look(g: Game, p) -> None:
    """Put the crosshair on a point of the sky by turning the head there."""
    g.view.az = p.az
    g.view.el = p.el


def types(events, t):
    return [e for e in events if e["type"] == t]


def test_rng_is_reproducible_from_a_seed():
    a, b = Rng(42), Rng(42)
    assert [a.next(), a.next(), a.next()] == [b.next(), b.next(), b.next()]


def test_rng_stays_in_range():
    r = Rng(3)
    for _ in range(1000):
        v = r.next()
        assert 0 <= v < 1


def test_azd_takes_the_short_way_round():
    assert azd(350, 10) == -20
    assert azd(10, 350) == 20


def test_every_level_has_a_name_and_a_plan():
    assert MAX_LEVEL == len(LEVELS)
    for n in range(4, MAX_LEVEL + 1):
        plan = level_plan(n, Rng(n))
        assert len(plan) > 0
        assert all(r.hp >= 1 and r.appr > 0 for r in plan)


def test_same_seed_same_plan():
    assert level_plan(20, Rng(5)) == level_plan(20, Rng(5))


def test_levels_say_numbers_above_19_as_tens_then_units():
    assert level_say(3) == ["level_word", "num_03", "name_2"]
    assert level_say(28) == ["level_word", "num_20", "num_08"]
    assert level_say(30) == ["level_word", "num_30"]


def test_a_shot_costs_one_unit_and_the_cooldown_limits_the_rate():
    g = play()
    c0 = g.run.charge
    step(g, 1.05, fire=True)
    assert 9 <= c0 - g.run.charge <= 11


def test_a_rock_that_reaches_you_ends_the_run_by_hull():
    g = play()
    g.run.t = 5
    w = g.run.worlds[0]
    w.spawn_at = 0
    w.p = 0.99
    w.speed = 1
    ev = step(g, 3)
    assert g.run.lost_cause == "hull"
    assert types(ev, "gameOver")
    assert g.phase == "over"


def test_out_of_battery_with_rocks_left_is_a_battery_loss():
    g = play()
    g.run.charge = 0
    g.run.crystals = []
    step(g, 3)
    assert g.run.lost_cause == "battery"


def test_destroying_a_rock_drops_crystals_and_aim_on_one_recharges_the_battery():
    g = play(7)
    g1 = g.run
    step(g, 1.2)  # the first rock spawns
    for _ in range(900):
        if g1.crystals:
            break
        live = g.live_rocks()
        if live:
            look(g, live[0])
        step(g, DT, fire=True)
    assert len(g1.crystals) > 0
    g1.charge = 50
    c = g1.crystals[0]
    look(g, c)
    step(g, 0.5)
    assert g1.charge > 50


def test_the_chip_doubles_capacity_and_refills_when_held_2_4_s():
    g = play()
    r = g.run
    r.level = 3
    g.eject_chip(100, 0)
    look(g, r.chip)
    step(g, CHIP_HOLD + 0.3)
    assert r.chip_collected is True
    assert r.capacity == CHIP_CAPACITY
    assert r.charge == CHIP_CAPACITY


def test_level_14_will_not_end_until_its_wing_is_collected():
    g = play()
    g.run.chip_collected = True
    g.start_level(14)
    g.run.worlds = []
    step(g, 6)
    assert g.run.wing is not None
    assert g.run.mode == "playing"
    step(g, 5)
    assert g.run.mode == "playing"  # nothing to shoot, still waiting on the wing
    look(g, g.run.wing)
    step(g, WING_HOLD + 0.3)
    assert g.run.wings == 1
    assert g.run.mode == "intermission"


def test_level_28_can_be_reached_directly_and_still_ends_once_its_wing_is_taken():
    r = simulate_level(28, seed=1, noise=1, max_seconds=120)
    assert r.wings == 1
    assert r.seconds < 120


def test_aim_that_slips_drains_the_hold_instead_of_resetting_it():
    g = play()
    g.start_level(14)
    g.run.worlds = []
    step(g, 6)
    w = g.run.wing
    look(g, w)
    step(g, 1.0)
    d1 = w.dwell
    g.view.az = (w.az + 40) % 360
    step(g, 0.5)
    assert 0 < w.dwell < d1


def test_the_intro_runs_story_countdown_and_jump_then_hands_over_to_level_1_and_play():
    g = Game(seed=2)
    g.launch()
    assert types(g.drain(), "launch")
    g.begin_intro()
    ev = step(g, INTRO_END + 0.5)
    assert g.phase == "play"
    assert len(types(ev, "say")) >= 11  # 7 story lines + 3, 2, 1, go... and the level voice
    assert any(e["on"] for e in types(ev, "alarm"))
    assert any(e["name"] == "game" for e in types(ev, "music"))
    assert g.run.level == 1


def test_skip_story_lands_before_the_countdown_cuts_the_voice_and_keeps_the_later_cues():
    g = Game(seed=2)
    g.begin_intro()
    step(g, 3)
    f = empty_input()
    f.commands = ["skipStory"]
    g.update(DT, f)
    ev = g.drain()
    assert any(e["keys"] == [] for e in types(ev, "say"))
    assert COUNT_AT - 1.5 < g.intro.t < COUNT_AT
    rest = step(g, 6)
    assert any(e["keys"][:1] == ["m_three"] for e in types(rest, "say"))
    assert any(e["keys"][:1] == ["m_go"] for e in types(rest, "say"))


def test_skip_intro_goes_straight_to_the_game():
    g = Game(seed=2)
    g.begin_intro()
    step(g, 2)
    f = empty_input()
    f.commands = ["skipIntro"]
    g.update(DT, f)
    assert g.intro.t >= GAME_AT


def test_absolute_head_orientation_sets_the_view_directly_and_ignores_keys_and_drag():
    g = play()
    step(g, 0.5, head=Head(350, 5), turn=Turn(1, 1), look=Look(50, 50))
    assert math.isclose(g.view.az, 350, abs_tol=1e-9)
    assert math.isclose(g.view.el, 5, abs_tol=1e-9)
    assert g.view.sensor_live is False
    step(g, DT, head=Head(-10, 99))
    assert math.isclose(g.view.az, 350, abs_tol=1e-9)
    assert g.view.el == 38


def test_two_games_with_one_seed_and_one_input_script_end_the_same():
    def run():
        g = play(9)
        step(g, 6, fire=True, turn=Turn(1, 0))
        return [g.run.charge, g.run.score, g.view.az, len(g.run.worlds)]

    assert run() == run()


def test_the_bot_clears_the_early_levels():
    for level in [1, 2, 4, 5, 6]:
        r = simulate_level(level, seed=1, noise=1)
        assert not r.lost, f"level {level}: {r.cause}"


def test_the_bot_collects_the_wing_on_level_14():
    r = simulate_level(14, seed=1, noise=1)
    assert not r.lost
    assert r.wings == 1


def test_a_press_on_the_title_launches_and_the_retry_button_restarts():
    g = Game(seed=1)
    f = empty_input()
    f.presses = [Press(320, 520)]
    g.update(DT, f)
    assert types(g.drain(), "launch")
    assert g.launching
    g.begin_game()
    g.drain()
    g.run.charge = 0
    g.run.crystals = []
    step(g, 3)
    assert g.phase == "over"
    f = empty_input()
    f.presses = [Press(320, 360)]  # inside RETRY
    g.update(DT, f)
    assert g.phase == "play"
    assert g.run.level == 1 and g.run.score == 0
