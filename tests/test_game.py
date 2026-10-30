import random

import pytest

from overblaster import config as C
from overblaster.game import Crystal, Game, State, World, angular_distance, az_delta, crosshair_bearing


def make_game(seed: int = 1) -> Game:
    g = Game(rng=random.Random(seed))
    g.update(1.0, 0, 0)  # leave the opening intermission, start level 1
    return g


def stationary_world(az=0.0, el=0.0, hp=1, progress=0.5, chip=False) -> World:
    return World(az=az, el=el, az_v=0, el_v=0, progress=progress, speed=0, hp=hp, kind="a", chip_carrier=chip)


def test_az_delta_wraps():
    assert az_delta(359, 1) == -2
    assert az_delta(1, 359) == 2
    assert angular_distance(359, 0, 1, 0) == pytest.approx(2.0)


def test_level_one_starts_with_five_worlds():
    g = make_game()
    assert g.level == 1 and g.state is State.PLAYING
    assert len(g.worlds) == C.WORLDS_BASE


def test_shot_costs_battery_even_on_a_miss():
    g = make_game()
    g.worlds.clear()
    g.worlds.append(stationary_world(az=100))
    before = g.charge
    assert g.shoot(0, 0)
    assert g.charge == before - C.SHOT_COST
    assert len(g.worlds) == 1


def test_cooldown_blocks_rapid_fire():
    g = make_game()
    assert g.shoot(0, 0)
    assert not g.shoot(0, 0)
    g.update(C.SHOT_COOLDOWN_S + 0.01, 0, 0)
    assert g.shoot(0, 0)


def test_hit_destroys_world_and_drops_crystals():
    g = make_game()
    g.worlds[:] = [stationary_world(hp=1)]
    assert g.shoot(0, 0)
    assert not g.worlds
    assert C.CRYSTALS_MIN <= len(g.crystals) <= C.CRYSTALS_MAX
    assert "destroyed" in g.events


def test_multi_hp_world_survives_and_is_knocked_back():
    g = make_game()
    g.worlds[:] = [stationary_world(hp=2, progress=0.5)]
    g.shoot(0, 0)
    assert g.worlds[0].hp == 1
    assert g.worlds[0].progress == pytest.approx(0.5 - C.KNOCKBACK)


def test_harvest_needs_dwell_then_recharges_clamped_to_capacity():
    g = make_game()
    g.worlds[:] = [stationary_world(az=120)]
    g.charge = 50
    g.crystals[:] = [Crystal(az=0, el=0)]
    g.update(C.HARVEST_DWELL_S / 2, 0, 0)
    assert g.crystals and g.charge == 50
    g.update(C.HARVEST_DWELL_S, 0, 0)
    assert not g.crystals
    assert g.charge == 50 + C.CRYSTAL_VALUE

    g.charge = g.capacity - 1
    g.crystals[:] = [Crystal(az=0, el=0)]
    g.update(C.HARVEST_DWELL_S + 0.01, 0, 0)
    assert g.charge == g.capacity


def test_dwell_drains_when_aim_leaves():
    g = make_game()
    g.worlds[:] = [stationary_world(az=120)]
    g.crystals[:] = [Crystal(az=0, el=0)]
    g.update(0.2, 0, 0)
    g.update(0.2, 90, 0)
    assert g.crystals[0].dwell == 0.0


def test_uncollected_crystal_expires():
    g = make_game()
    g.worlds[:] = [stationary_world(az=120)]
    g.crystals[:] = [Crystal(az=0, el=0)]
    g.update(C.CRYSTAL_LIFETIME_S + 0.1, 90, 0)
    assert not g.crystals
    assert "crystal_lost" in g.events


def test_a_world_reaching_the_ship_ends_the_game():
    g = make_game()
    g.worlds[:] = [
        World(az=0, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a"),
        stationary_world(az=120, progress=0.2),  # another world is still far away
    ]
    before = g.charge
    g.update(0.1, 90, 0)
    assert g.state is State.LOST and g.lost_cause == "hull"
    assert g.charge == before  # battery was fine: the hull is what failed
    assert "hull_destroyed" in g.events
    assert g.impact is not None and g.impact[2] > 0  # where and how big, for the explosion
    assert not g.shoot(0, 0)


def test_the_last_world_hitting_the_ship_is_a_loss_not_a_level_clear():
    """The field is empty after the world is removed, which must not read as 'level clear'."""
    g = make_game()
    g.worlds[:] = [World(az=0, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a")]
    g.crystals.clear()
    g.update(0.1, 90, 0)
    assert g.state is State.LOST and g.lost_cause == "hull"
    assert "level_clear" not in g.events
    g.update(5.0, 90, 0)  # and it stays lost
    assert g.state is State.LOST and g.level == 1


def test_losing_to_the_hull_and_to_the_battery_are_told_apart():
    g = make_game()
    g.charge = C.SHOT_COST - 1
    g.update(0.1, 90, 0)
    assert g.state is State.LOST and g.lost_cause == "battery" and g.impact is None


def test_lose_when_out_of_battery_and_no_crystals():
    g = make_game()
    g.charge = C.SHOT_COST - 1
    g.update(0.1, 90, 0)
    assert g.state is State.LOST
    assert "lost" in g.take_events()
    assert not g.shoot(0, 0)


def test_not_lost_while_a_crystal_can_still_be_harvested():
    g = make_game()
    g.charge = 0
    g.crystals[:] = [Crystal(az=0, el=0)]
    g.update(0.1, 90, 0)
    assert g.state is State.PLAYING
    g.update(C.HARVEST_DWELL_S + 0.1, 0, 0)  # harvest it: +6 is enough for a shot
    assert g.state is State.PLAYING and g.charge >= C.SHOT_COST


def test_level_clears_then_advances():
    g = make_game()
    g.worlds.clear()
    g.update(0.1, 0, 0)
    assert g.state is State.INTERMISSION
    g.update(C.INTERMISSION_S + 0.1, 0, 0)
    assert g.level == 2 and g.state is State.PLAYING
    assert len(g.worlds) == C.WORLDS_BASE + C.WORLDS_PER_LEVEL


def test_worlds_spawn_near_where_the_player_is_looking():
    g = Game(rng=random.Random(3))
    g.set_view(200, 0)
    g.update(1.0, 0, 0)
    assert all(abs(az_delta(w.az, 200)) <= C.SPAWN_SPREAD for w in g.worlds)


def _advance_to_level(g: Game, level: int) -> None:
    for _ in range(100):
        if g.level >= level:
            return
        assert g.state is not State.LOST, f"the game ended at level {g.level} ({g.lost_cause})"
        g.worlds.clear()
        g.crystals.clear()
        g.update(0.1, 0, 0)  # level clear
        g.update(C.INTERMISSION_S + 0.1, 0, 0)  # next level
    raise AssertionError(f"never reached level {level}")


def test_chip_carrier_first_appears_at_the_chip_level_and_returns_until_collected():
    g = make_game()
    _advance_to_level(g, C.CHIP_LEVEL - 1)
    assert not any(w.chip_carrier for w in g.worlds)
    _advance_to_level(g, C.CHIP_LEVEL)
    assert sum(w.chip_carrier for w in g.worlds) == 1
    # The player let it through: no chip. It must be offered again, not lost for good.
    _advance_to_level(g, C.CHIP_LEVEL + 1)
    assert sum(w.chip_carrier for w in g.worlds) == 1
    _advance_to_level(g, C.CHIP_LEVEL + 2)
    assert sum(w.chip_carrier for w in g.worlds) == 1


def test_a_carrier_that_is_killed_but_whose_chip_is_missed_comes_back():
    """With a world hitting the ship now fatal, the chip is lost another way: the carrier is
    destroyed, but the chip expires uncollected. It must be offered again, not lost for the run."""
    g = make_game()
    _advance_to_level(g, C.CHIP_LEVEL)
    carrier = next(w for w in g.worlds if w.chip_carrier)
    g.worlds[:] = [carrier, stationary_world(az=200, progress=0.1)]
    carrier.hp, carrier.az, carrier.el, carrier.speed, carrier.az_v, carrier.el_v = 1, 0, 0, 0, 0, 0
    g.shoot(0, 0)
    assert [c.is_chip for c in g.crystals] == [True]
    g.update(C.CHIP_LIFETIME_S + 0.5, 90, 0)  # the player never aimed at it
    assert not g.crystals and not g.chip_collected
    _advance_to_level(g, C.CHIP_LEVEL + 1)
    assert any(w.chip_carrier for w in g.worlds)


def test_chip_doubles_capacity_exactly_once():
    g = make_game()
    _advance_to_level(g, C.CHIP_LEVEL)
    carrier = next(w for w in g.worlds if w.chip_carrier)
    g.worlds[:] = [carrier]
    carrier.hp = 1
    carrier.az, carrier.el, carrier.speed, carrier.az_v, carrier.el_v = 0, 0, 0, 0, 0
    g.charge = 30
    g.shoot(0, 0)
    chips = [c for c in g.crystals if c.is_chip]
    assert len(chips) == 1 and len(g.crystals) == 1

    g.update(C.CHIP_HOLD_S + 0.05, chips[0].az, chips[0].el)
    assert g.chip_collected
    assert g.capacity == C.BATTERY_START * C.CHIP_CAPACITY_FACTOR
    assert g.charge == g.capacity

    # Once collected, later levels never spawn another carrier (CHIP_REPEAT is off).
    for level in range(C.CHIP_LEVEL + 1, C.CHIP_LEVEL * 3):
        _advance_to_level(g, level)
        assert not any(w.chip_carrier for w in g.worlds)


def test_crosshair_bearing_adds_offset_and_wraps():
    az, el = crosshair_bearing(359, 10, 3, -4)
    assert az == pytest.approx(2) and el == pytest.approx(6)


# --- shot records (they drive the animation) -----------------------------------------------
def test_a_shot_is_recorded_as_a_miss_a_hit_or_a_kill():
    g = make_game()
    g.worlds[:] = [stationary_world(az=100, hp=2)]
    g.shoot(0, 0)  # nothing there
    assert [s.kind for s in g.shots] == ["miss"]
    g.update(C.SHOT_COOLDOWN_S + 0.01, 0, 0)
    g.shoot(100, 0)  # hits, the world has 2 hit points
    assert g.shots[-1].kind == "hit" and g.shots[-1].radius_deg > 0
    g.update(C.SHOT_COOLDOWN_S + 0.01, 0, 0)
    g.shoot(100, 0)  # destroys it
    assert g.shots[-1].kind == "kill" and g.shots[-1].radius_deg > 0
    assert (g.shots[-1].az, g.shots[-1].el) == (100, 0)  # where the world was, so the blast lands there


def test_shots_age_out_even_after_the_game_is_lost():
    g = make_game()
    g.worlds[:] = [stationary_world(az=100, hp=5)]
    g.shoot(100, 0)
    assert g.shots
    g.worlds[:] = [World(az=0, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a")]
    g.update(0.1, 90, 0)
    assert g.state is State.LOST and g.shots  # the animation is still playing
    g.update(C.SHOT_FX_S + 0.1, 90, 0)
    assert not g.shots  # and it is not frozen on screen forever


# --- fire rate and tougher planets -----------------------------------------------------------
def shots_fired_holding_the_trigger(seconds: float, tick_hz: float = C.TICK_HZ) -> int:
    g = make_game()
    g.worlds[:] = [stationary_world(az=100, hp=10_000)]  # a target that never dies
    g.charge = g.capacity = 1e9  # never runs out of battery
    fired, dt = 0, 1.0 / tick_hz
    for _ in range(int(seconds * tick_hz)):
        fired += g.shoot(0, 0)  # the trigger is held: try to fire on every tick
        g.update(dt, 0, 0)
    return fired


def test_holding_the_trigger_fires_ten_shots_a_second():
    assert C.SHOT_COOLDOWN_S == pytest.approx(0.1)
    assert shots_fired_holding_the_trigger(6.0) == pytest.approx(60, abs=3)


def test_the_fire_rate_holds_at_other_tick_rates_too():
    for hz in (10, 15, 20, 30, 60):
        rate = shots_fired_holding_the_trigger(5.0, hz) / 5.0
        assert rate == pytest.approx(10, abs=1.0), (hz, rate)


def test_waiting_does_not_bank_a_burst_of_shots():
    g = make_game()
    g.worlds[:] = [stationary_world(az=100, hp=10_000)]
    g.charge = g.capacity = 1e9
    for _ in range(100):  # idle for ~6 seconds
        g.update(1 / C.TICK_HZ, 0, 0)
    burst = 0
    for _ in range(3):  # then pull the trigger for a fifth of a second
        burst += g.shoot(0, 0)
        g.update(1 / C.TICK_HZ, 0, 0)
    assert burst <= 3  # at most one per tick, never a stored-up volley


def test_planets_take_many_hits_and_get_tougher_each_level():
    g = make_game()
    assert all(w.hp >= 5 for w in g.worlds), [w.hp for w in g.worlds]
    level1 = min(w.hp for w in g.worlds)
    _advance_to_level(g, 6)
    assert min(w.hp for w in g.worlds if not w.chip_carrier) > level1


def test_a_planet_really_takes_that_many_hits_to_destroy():
    g = make_game()
    world = stationary_world(az=100, hp=g._base_hp())
    g.worlds[:] = [world]
    g.charge = g.capacity = 1e9
    hits = 0
    while world in g.worlds and hits < 100:
        assert g.shoot(100, 0)
        hits += 1
        g.update(C.SHOT_COOLDOWN_S + 0.01, 100, 0)
    assert hits == g._base_hp() >= 5


def test_a_shot_barely_pushes_a_world_back_now_that_there_are_ten_a_second():
    assert C.KNOCKBACK * 10 < 0.05  # holding the beam on a world for a second must not undo its whole approach


# --- holding the between-levels plate until the player acknowledges it -----------------
def make_holding_game():
    g = make_game()
    g.hold_between_levels = True
    return g


def test_a_held_level_clear_waits_as_long_as_it_takes():
    g = make_holding_game()
    g.worlds.clear()
    g.update(0.1, 0, 0)
    assert g.state is State.INTERMISSION and g.awaiting_ack is False  # still inside the minimum pause
    for _ in range(600):  # a minute
        g.update(0.1, 0, 0)
    assert g.state is State.INTERMISSION and g.level == 1 and g.awaiting_ack


def test_acknowledging_starts_the_next_level():
    g = make_holding_game()
    g.worlds.clear()
    g.update(0.1, 0, 0)  # clears the level
    g.update(C.INTERMISSION_S + 0.1, 0, 0)
    assert g.awaiting_ack
    g.acknowledge()
    g.update(0.1, 0, 0)
    assert g.level == 2 and g.state is State.PLAYING and not g.awaiting_ack


def test_an_early_acknowledgement_does_not_skip_the_minimum_pause():
    g = make_holding_game()
    g.worlds.clear()
    g.update(0.1, 0, 0)
    g.acknowledge()
    g.update(0.1, 0, 0)
    assert g.state is State.INTERMISSION  # the plate was barely up
    g.update(C.INTERMISSION_S, 0, 0)
    assert g.level == 2


def test_the_next_clear_needs_its_own_acknowledgement():
    g = make_holding_game()
    g.worlds.clear()
    g.update(0.1, 0, 0)
    g.update(C.INTERMISSION_S + 0.1, 0, 0)
    g.acknowledge()
    g.update(0.1, 0, 0)
    assert g.level == 2
    g.worlds.clear()
    g.crystals.clear()
    g.update(0.1, 0, 0)  # level 2 is clear
    g.update(C.INTERMISSION_S + 0.2, 0, 0)
    assert g.state is State.INTERMISSION and g.level == 2 and g.awaiting_ack


def test_the_opening_pause_never_waits():
    g = make_holding_game()
    g.update(1.0, 0, 0)  # level 0's half second, before level 1
    assert g.level == 1 and g.state is State.PLAYING


def test_without_the_hold_levels_advance_by_themselves():
    g = make_game()
    assert g.hold_between_levels is False  # the bots and the balance tests rely on this


# --- holding your aim on the Overlord BMS chip ---------------------------------------------
def chip_game():
    g = make_game()
    g.worlds.clear()
    g.state = State.PLAYING
    g.crystals[:] = [Crystal(az=0.0, el=0.0, is_chip=True)]
    return g, g.crystals[0]


def test_the_chip_needs_a_long_hold_not_a_glance():
    g, chip = chip_game()
    g.update(C.HARVEST_DWELL_S + 0.1, 0, 0)  # long enough for any crystal
    assert not g.chip_collected and 0 < chip.progress < 0.3
    g.update(C.CHIP_HOLD_S, 0, 0)
    assert g.chip_collected and not g.crystals


def test_progress_runs_from_zero_to_one_and_reports_whether_you_are_on_it():
    g, chip = chip_game()
    assert chip.progress == 0 and chip.on_target is False
    g.update(C.CHIP_HOLD_S / 2, 0, 0)
    assert chip.progress == pytest.approx(0.5, abs=0.02) and chip.on_target
    g.update(0.1, 90, 0)  # aim has slipped away
    assert chip.on_target is False


def test_a_slip_drains_the_hold_slowly_and_never_resets_it():
    g, chip = chip_game()
    g.update(C.CHIP_HOLD_S * 0.6, 0, 0)
    before = chip.progress
    g.update(1.0, 90, 0)  # a second off target
    assert before - chip.progress == pytest.approx(C.CHIP_HOLD_DRAIN, abs=0.02)
    assert chip.progress > 0.2  # the old rule would have zeroed it


def test_the_drain_stops_at_zero():
    g, chip = chip_game()
    g.update(0.5, 0, 0)
    g.update(10.0, 90, 0)  # a long time away (the chip is still alive)
    assert chip.progress == 0.0 and chip.dwell == 0.0


def test_an_ordinary_crystal_is_unchanged():
    g = make_game()
    g.worlds.clear()
    g.state = State.PLAYING
    g.crystals[:] = [Crystal(az=0.0, el=0.0)]
    c = g.crystals[0]
    g.update(C.HARVEST_DWELL_S / 2, 0, 0)
    assert c.progress == pytest.approx(0.5, abs=0.05)
    g.update(C.HARVEST_DWELL_S, 0, 0)
    assert not g.crystals


def test_collecting_the_chip_remembers_where_it_was_for_the_effects():
    g, chip = chip_game()
    chip.az, chip.el = 5.0, 2.0
    g.update(C.CHIP_HOLD_S + 0.1, 5.0, 2.0)
    assert g.chip_at == (5.0, 2.0) and "chip" in g.events
