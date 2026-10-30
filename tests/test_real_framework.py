"""Runs the whole game on the real Raven Framework widgets (offscreen), if it is installed."""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def test_a_perfect_player_clears_four_levels_and_collects_the_chip_on_real_widgets():
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "real_framework_game.py")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 77:
        pytest.skip("raven_framework (or PySide6) is not installed")
    assert result.returncode == 0, result.stdout + result.stderr[-2000:]


def test_simulator_mode_on_real_widgets_and_this_machines_hardware():
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "real_framework_sim.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 77:
        pytest.skip("raven_framework (or PySide6) is not installed")
    assert result.returncode == 0, result.stdout + result.stderr[-2000:]


def test_the_simulators_picture_lines_up_with_its_mouse_mapping():
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "real_framework_composite.py")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode == 77:
        pytest.skip("raven_framework (or PySide6) is not installed")
    assert result.returncode == 0, result.stdout + result.stderr[-2000:]


def test_sound_reaches_the_real_qt_audio_output_and_the_voice_unmutes_the_mic_afterwards():
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "real_framework_audio.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 77:
        pytest.skip("no audio output device here")
    assert result.returncode == 0, result.stdout + result.stderr[-2000:]
