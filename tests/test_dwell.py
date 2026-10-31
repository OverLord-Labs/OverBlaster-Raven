"""Gaze-dwell plates: no widgets, just time on a box."""

from overblaster.core.layout import LAUNCH, RETRY, TOTITLE
from overblaster.dwell import Dwell

DT = 0.05
ON = (LAUNCH.x + 10, LAUNCH.y + 10)


def run(d, seconds, gaze, boxes):
    pressed = None
    for _ in range(int(seconds / DT + 0.5)):
        pressed = d.update(DT, gaze, boxes) or pressed
    return pressed


def test_presses_after_the_dwell_time_and_not_before():
    d = Dwell(1.5)
    assert run(d, 1.4, ON, {"launch": LAUNCH}) is None
    assert 0.9 < d.progress["launch"] < 1.0
    assert run(d, 0.2, ON, {"launch": LAUNCH}) == "launch"
    assert d.progress.get("launch", 0.0) < 0.2  # and starts again from (nearly) nothing


def test_the_fill_drains_faster_than_it_fills_when_the_gaze_leaves():
    d = Dwell(1.5)
    run(d, 1.0, ON, {"launch": LAUNCH})
    full = d.progress["launch"]
    run(d, 0.5, (0.0, 0.0), {"launch": LAUNCH})
    assert d.progress["launch"] < full - 0.5
    run(d, 1.0, None, {"launch": LAUNCH})  # no gaze at all
    assert "launch" not in d.progress


def test_only_the_box_under_the_gaze_fills():
    d = Dwell(1.5)
    run(d, 1.0, (RETRY.x + 5, RETRY.y + 5), {"retry": RETRY, "title": TOTITLE})
    assert "retry" in d.progress and "title" not in d.progress
    assert run(d, 1.0, (TOTITLE.x + 5, TOTITLE.y + 5), {"retry": RETRY, "title": TOTITLE}) is None
    assert d.progress.get("title", 0) > d.progress.get("retry", 0)


def test_boxes_that_go_away_are_forgotten():
    d = Dwell(1.5)
    run(d, 0.5, ON, {"launch": LAUNCH})
    d.update(DT, ON, {})
    assert d.progress == {}
