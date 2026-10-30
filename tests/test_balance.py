"""Scripted-player simulations that guard the energy economy.

Good aim and harvesting must be sustainable for several levels; wasting shots
and ignoring crystals must lose. If you retune config.py, these tell you whether
the game is still fair.
"""

import random

from overblaster import config as C
from overblaster.game import Game, State, az_delta, wrap_az

DT = 1 / C.TICK_HZ


def run(strategy, seed: int, seconds: float = 600.0, accuracy: float = 1.0, max_level: int = 6) -> Game:
    """Play one game. `accuracy` is the fraction of shots that are aimed correctly."""
    g = Game(rng=random.Random(seed))
    miss = random.Random(seed + 1000)
    t = 0.0
    while t < seconds and g.state is not State.LOST and g.level <= max_level:
        aim = strategy(g)
        g.update(DT, *aim)
        if strategy.shoots(g):
            g.shoot(*(aim if miss.random() < accuracy else (aim[0] + 40.0, aim[1])))
        g.take_events()
        t += DT
    return g


def good_player(g: Game):
    """Harvests crystals first, otherwise shoots the nearest world with perfect aim."""
    if g.crystals:
        c = g.crystals[0]
        return c.az, c.el
    if g.worlds:
        w = max(g.worlds, key=lambda w: w.progress)
        return w.az, w.el
    return g.view_az, g.view_el


good_player.shoots = lambda g: bool(g.worlds) and not g.crystals


def spray_player(g: Game):
    """Fires constantly at a fixed spot, never harvests."""
    return 180.0, 0.0


spray_player.shoots = lambda g: True


def test_perfect_aim_and_harvesting_reaches_level_six_every_time():
    for seed in range(10):
        g = run(good_player, seed)
        assert g.state is not State.LOST, f"seed {seed} lost at level {g.level}"
        assert g.level >= 6, f"seed {seed} stalled at level {g.level}"


def test_a_casual_player_hitting_half_their_shots_usually_reaches_the_chip_level():
    reached = sum(run(good_player, seed, accuracy=0.5, max_level=C.CHIP_LEVEL).level >= C.CHIP_LEVEL for seed in range(30))
    assert reached >= 24, f"only {reached}/30 reached level {C.CHIP_LEVEL}"


def test_a_player_hitting_under_a_third_of_their_shots_loses():
    for seed in range(10):
        assert run(good_player, seed, accuracy=0.2, max_level=8).state is State.LOST


def test_chip_is_collected_by_a_good_player():
    g = run(good_player, 4)
    assert g.chip_collected and g.capacity == C.BATTERY_START * C.CHIP_CAPACITY_FACTOR


def test_wasting_shots_loses_early():
    for seed in range(5):
        g = run(spray_player, seed, seconds=120.0)
        assert g.state is State.LOST
        assert g.level <= 2


# --- Players who have to turn their head -----------------------------------
# The instant-aim bots above hid a real problem: a player must slew their head to find
# each world (the view is only 30 degrees wide), which costs time. These bots do that.

def run_lagged(seed: int, rate: float, accuracy: float, max_level: int, tol: float = 1.0) -> Game:
    """A player who turns their head at most `rate` deg/s, fires only once aligned within
    `tol` degrees, and lands `accuracy` of their shots. Harvests crystals before shooting."""
    g = Game(rng=random.Random(seed))
    miss = random.Random(seed + 1000)
    yaw = pitch = t = 0.0
    n = 0
    while t < 900.0 and g.state is not State.LOST and g.level <= max_level:
        if g.crystals:
            target, fire = (g.crystals[0].az, g.crystals[0].el), False
        elif g.worlds:
            w = max(g.worlds, key=lambda w: w.progress)
            target, fire = (w.az, w.el), True
        else:
            target, fire = (yaw, pitch), False
        d_az, d_el = az_delta(target[0], yaw), target[1] - pitch
        yaw = wrap_az(yaw + max(-rate, min(rate, d_az * 5)) * DT)
        pitch = max(-60.0, min(60.0, pitch + max(-rate, min(rate, d_el * 5)) * DT))
        g.set_view(yaw, pitch)
        aim = (yaw, pitch)
        shoot = fire and abs(d_az) < tol and abs(d_el) < tol  # held trigger: the game paces the shots
        if shoot and miss.random() >= accuracy:
            aim = (yaw + 40.0, pitch)
        g.update(DT, *aim)
        if shoot:
            g.shoot(*aim)
        g.take_events()
        t += DT
        n += 1
    return g


def _outcomes(n: int, **kw):
    games = [run_lagged(seed, **kw) for seed in range(n)]
    return (
        sum(g.state is State.LOST for g in games) / n,
        sum(g.chip_collected for g in games) / n,
        sorted(g.level for g in games)[n // 2],
    )


def test_a_casual_player_who_turns_slowly_survives_and_gets_the_chip():
    lost, chip, _ = _outcomes(40, rate=60, accuracy=0.7, max_level=5)
    assert lost <= 0.15 and chip >= 0.95, (lost, chip)


def test_a_skilled_player_goes_deep_but_the_game_is_not_endless():
    lost, chip, median_level = _outcomes(40, rate=120, accuracy=0.9, max_level=12)
    assert chip >= 0.95
    assert lost >= 0.9, "difficulty should eventually beat a skilled player"
    assert 7 <= median_level <= 10, median_level


def test_a_slow_inaccurate_player_usually_loses_early():
    lost, _, median_level = _outcomes(40, rate=40, accuracy=0.4, max_level=5)
    assert lost >= 0.7 and median_level <= 5, (lost, median_level)


def test_spraying_shots_loses_by_level_three_even_with_fast_head_turns():
    games = [run_lagged(seed, rate=120, accuracy=0.2, max_level=5) for seed in range(20)]
    assert all(g.state is State.LOST and g.level <= 3 for g in games)
