"""The Python core against the TypeScript core.

tests/golden/core_parity.json is written by the web game (npx tsx scripts/golden.ts in OverBlaster-web) and holds what
the TypeScript core does for fixed seeds and scripts. This port must reproduce it: the same random numbers, the same
level plans, the same scripted runs, the same intro events and the same bot results.
"""

import json
import math
import os

import pytest

from overblaster.core import (
    COUNT_AT, EV, GAME_AT, INTRO_CUES, INTRO_END, INTRO_LINES, JUMP_AT, PARTS, RISER_AT, SH, SKIP_STORY_TO, Game, Rng, bot_target, empty_input,
    level_plan, simulate_level,
)

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "core_parity.json")
G = json.load(open(GOLDEN))
DT = 1 / 30
TOL = 1e-6


def same(a, b, path="") -> None:
    """Deep equality, with floats compared to TOL."""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str):
        assert a == b, f"{path}: {a!r} != {b!r}"
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        assert math.isclose(a, b, rel_tol=TOL, abs_tol=TOL), f"{path}: {a!r} != {b!r}"
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{path}[{i}]")
    elif isinstance(a, dict):
        assert set(a) == set(b), f"{path}: keys {sorted(a)} != {sorted(b)}"
        for k in a:
            same(a[k], b[k], f"{path}.{k}")
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def r9(x):
    return round(x * 1e9) / 1e9


def counts(evs, into):
    for e in evs:
        into[e["type"]] = into.get(e["type"], 0) + 1


def snap(g):
    r = g.run
    return {"t": round(g.clock * 1e6) / 1e6, "charge": r9(r.charge), "score": r.score, "az": r9(g.view.az), "el": r9(g.view.el),
            "worlds": len([w for w in r.worlds if not w.dead]), "crystals": len(r.crystals), "gauges": len(r.gauges), "wings": r.wings,
            "mode": r.mode, "level": r.level}


def test_rng_matches():
    r = Rng(42)
    same([r.next() for _ in range(20)], G["rng42"], "rng42")


@pytest.mark.parametrize("n", [4, 7, 8, 14, 20, 28, 33, 42])
def test_level_plans_match(n):
    plan = [{"t": r9(p.t), "az": r9(p.az), "el": r9(p.el), "hp": p.hp, "appr": r9(p.appr), "eject": p.eject} for p in level_plan(n, Rng(n))]
    same(plan, G["plans"][str(n)], f"plan{n}")


def test_scripted_run_one_matches():
    from overblaster.core import Turn

    g = Game(seed=9)
    g.begin_game()
    g.drain()
    ev, trace = {}, []
    for i in range(180):
        f = empty_input()
        f.fire = True
        f.turn = Turn(1, 0)
        g.update(DT, f)
        counts(g.drain(), ev)
        if i % 30 == 29:
            trace.append(snap(g))
    same({"final": snap(g), "trace": trace, "events": ev}, G["run1"], "run1")


def test_scripted_run_two_with_bad_gauges_matches():
    g = Game(seed=5)
    g.begin_game()
    g.drain()
    g.run.chip_collected = True
    g.run.capacity = 200
    g.run.charge = 200
    g.start_level(7)
    g.drain()
    ev, trace = {}, []
    inp = empty_input()
    inp.fire = True

    def extra(s):
        return {**s, "bad": g.run.bad.color if g.run.bad else None, "capacity": g.run.capacity}

    for i in range(750):
        if g.phase != "play":
            break
        p = bot_target(g)
        g.view.az, g.view.el = p["az"], p["el"]
        g.update(DT, inp)
        counts(g.drain(), ev)
        if i % 30 == 29:
            trace.append(extra(snap(g)))
    assert G["run2"]["events"].get("zap", 0) > 0, "the golden run should include bad gauges"
    same({"final": extra(snap(g)), "trace": trace, "events": ev}, G["run2"], "run2")


def test_the_whole_intro_matches():
    g = Game(seed=2)
    g.launch()
    first = g.drain()
    g.begin_intro()
    evs = [{"f": -1, **e} for e in first]
    for f in range(round((INTRO_END + 0.5) / DT)):
        g.update(DT, empty_input())
        for e in g.drain():
            evs.append({"f": f, **e})
    worlds = [{"az": r9(x.az), "el": r9(x.el), "spawnAt": r9(x.spawn_at), "hp": x.hp} for x in g.run.worlds]
    same({"events": evs, "phase": g.phase, "level": g.run.level, "worlds": worlds, "clock": round(g.clock * 1e6) / 1e6}, G["introRun"], "introRun")


@pytest.mark.parametrize("cmd,at,key", [("skipStory", 3, "skipStory"), ("skipIntro", 2, "skipIntro")])
def test_skip_commands_match(cmd, at, key):
    g = Game(seed=2)
    g.begin_intro()
    g.drain()
    for _ in range(round(at / DT)):
        g.update(DT, empty_input())
        g.drain()
    f = empty_input()
    f.commands = [cmd]
    g.update(DT, f)
    evs = list(g.drain())
    for fr in range(round(12 / DT)):
        g.update(DT, empty_input())
        for e in g.drain():
            evs.append({"f": fr, **e})
    same({"t": round(g.intro.t * 1e6) / 1e6, "phase": g.phase, "events": evs}, G[key], key)


def test_bot_simulations_match():
    for row in G["sims"]:
        r = simulate_level(row["level"], seed=row["seed"], noise=row["noise"])
        got = {"seed": row["seed"], "noise": row["noise"], "level": r.level, "lost": r.lost, "cause": r.cause, "seconds": r.seconds,
               "wings": r.wings, "minCharge": r.min_charge, "rocks": r.rocks, "badTaken": r.bad_taken, "gaugesSeen": r.gauges_seen}
        want = dict(row)
        want["cause"] = want.get("cause")  # a missing cause (JSON drops undefined/null differently) is None
        same(got, want, f"sim L{row['level']} s{row['seed']}")


def test_intro_tables_match():
    I = G["intro"]
    same([{"key": p.key, "text": p.text, "t0": r9(p.t0), "D": r9(p.D), "v0": r9(p.v0), "v1": r9(p.v1)} for p in PARTS], I["parts"], "parts")
    same([[r9(a), r9(b), t] for a, b, t in INTRO_LINES], I["lines"], "lines")
    same([{"at": r9(c.at), "events": c.events} for c in INTRO_CUES], I["cues"], "cues")
    same({k: r9(v) for k, v in EV.items()}, I["ev"], "ev")
    same({"SH": SH, "COUNT_AT": r9(COUNT_AT), "JUMP_AT": r9(JUMP_AT), "GAME_AT": GAME_AT, "INTRO_END": INTRO_END, "RISER_AT": r9(RISER_AT),
          "SKIP_STORY_TO": r9(SKIP_STORY_TO)}, I["times"], "times")
