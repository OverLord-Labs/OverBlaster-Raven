import pytest

from overblaster import config as C
from overblaster.sensors import GazeAim, HeadTracker, ImuProfile, PeakHold, VoiceTrigger, as_vec3, pixels_to_degrees

DT = 1 / 15


def reading(accel=(0, 0, 9.8), gyro=(0, 0, 0)):  # the framework simulator puts gravity on z
    return {"accelerometer": accel, "gyroscope": gyro, "magnetometer": (0, 0, 0)}


# --- as_vec3 ---------------------------------------------------------------
def test_as_vec3_accepts_dicts_sequences_and_junk():
    assert as_vec3({"x": 1, "y": 2, "z": 3}) == (1.0, 2.0, 3.0)
    assert as_vec3([1, 2, 3]) == (1.0, 2.0, 3.0)
    assert as_vec3(None) is None
    assert as_vec3({"x": 1}) is None
    assert as_vec3("abc") is None


# --- HeadTracker -----------------------------------------------------------
def test_yaw_integrates_gyro_and_wraps():
    h = HeadTracker(sim=False)
    for _ in range(15):  # one second at 90 deg/s about the yaw axis
        h.update(reading(gyro=_gyro(yaw=90)), DT)
    assert h.yaw == pytest.approx(90, abs=0.5)
    for _ in range(45):  # 3 more seconds: 270 deg more, 360 total
        h.update(reading(gyro=_gyro(yaw=90)), DT)
    assert 0 <= h.yaw < 360
    assert min(h.yaw, 360 - h.yaw) < 1.0  # back near the start, wrapped rather than 360


def test_recenter_zeroes_yaw_only():
    h = HeadTracker(sim=False)
    for _ in range(15):
        h.update(reading(gyro=_gyro(yaw=45)), DT)
    h.recenter()
    assert h.yaw == 0


def test_pitch_snaps_to_gravity_then_tracks_gyro():
    h = HeadTracker(sim=False)
    level = h.update(reading(accel=(0, 0, 9.8)), DT)
    assert level[1] == pytest.approx(0, abs=0.1)

    h2 = HeadTracker(sim=False)
    tilted = h2.update(reading(accel=(0, 9.8, 9.8)), DT)  # gravity split between up (z) and forward (y)
    assert tilted[1] == pytest.approx(45 * C.ACCEL_PITCH_SIGN, abs=0.1)


def test_gyro_pitch_is_corrected_back_by_gravity():
    h = HeadTracker(sim=False)
    h.update(reading(), DT)
    for _ in range(3):  # a gyro spike that gravity says didn't really happen
        h.update(reading(gyro=_gyro(pitch=50)), DT)
    spiked = h.pitch
    for _ in range(200):
        h.update(reading(), DT)
    assert abs(h.pitch) < abs(spiked)
    assert h.pitch == pytest.approx(0, abs=0.5)


def test_missing_reading_keeps_last_angles():
    h = HeadTracker(sim=False)
    h.update(reading(gyro=_gyro(yaw=90)), DT)
    before = (h.yaw, h.pitch)
    assert h.update(None, DT) == before
    assert h.update(reading(), 0) == before


def test_sim_mode_arrow_keys_steer_like_a_joystick():
    left = HeadTracker(sim=True)
    for _ in range(15):  # left arrow = +x in the framework simulator: the view turns left
        left.update(reading(accel=(2.0, 0, 9.8)), DT)
    assert left.yaw == pytest.approx(360 - 2.0 * C.SIM_STEER_DEG_PER_S, abs=1.0)

    up = HeadTracker(sim=True)
    for _ in range(15):  # up arrow = +y: the view looks up
        up.update(reading(accel=(0, 2.0, 9.8)), DT)
    assert up.pitch == pytest.approx(2.0 * C.SIM_STEER_DEG_PER_S, abs=1.0)

    idle = HeadTracker(sim=True)
    for _ in range(15):
        idle.update(reading(), DT)
    assert (idle.yaw, idle.pitch) == (0, 0)  # gravity alone must not move the view


def _gyro(yaw=0.0, pitch=0.0):
    v = [0.0, 0.0, 0.0]
    v[C.GYRO_YAW_AXIS] = yaw * C.GYRO_YAW_SIGN
    v[C.GYRO_PITCH_AXIS] = pitch * C.GYRO_PITCH_SIGN
    return tuple(v)


# --- GazeAim ---------------------------------------------------------------
def test_gaze_needs_several_steady_samples_before_it_is_trusted():
    g = GazeAim(640, 640)
    assert g.update((100, 100)) == (320, 320) and not g.confident
    for _ in range(C.GAZE_MIN_SAMPLES):
        pos = g.update((100, 100))
    assert g.confident and pos == pytest.approx((100, 100))


def test_jittery_gaze_falls_back_to_center():
    g = GazeAim(640, 640)
    for i in range(10):
        pos = g.update((100 + (i % 2) * 80, 100))
    assert not g.confident and pos == (320, 320)


def test_none_or_offscreen_gaze_resets_confidence():
    g = GazeAim(640, 640)
    for _ in range(8):
        g.update((200, 200))
    assert g.confident
    assert g.update(None) == (320, 320) and not g.confident
    for _ in range(8):
        g.update((200, 200))
    assert g.confident
    assert g.update((900, 200)) == (320, 320) and not g.confident


def test_gaze_smoothing_follows_a_moved_target():
    g = GazeAim(640, 640)
    for _ in range(8):
        g.update((100, 100))
    for _ in range(C.GAZE_WINDOW + 4):
        pos = g.update((300, 100))
    assert pos[0] == pytest.approx(300, abs=15)


def test_pixels_to_degrees_directions():
    assert pixels_to_degrees(320, 320, 640, 640) == (0, 0)
    right, up = pixels_to_degrees(640, 0, 640, 640)
    assert right == pytest.approx(C.FOV_DEG / 2) and up == pytest.approx(C.FOV_DEG / 2)


# --- VoiceTrigger ----------------------------------------------------------
def test_voice_starts_firing_when_loud_and_keeps_firing_while_the_sound_continues():
    v = VoiceTrigger(hi=0.4, lo=0.1)
    assert not v.update(0.2)  # too quiet to start
    assert v.update(0.8)  # a loud sound starts it
    assert v.update(0.9)  # and it keeps firing...
    assert v.update(0.3)  # ...even after the level drops, as long as the sound goes on...
    assert v.update(0.12)
    assert not v.update(0.05)  # ...and it stops when the sound does


def test_a_sound_must_pass_the_high_threshold_to_start_but_only_the_low_one_to_continue():
    v = VoiceTrigger(hi=0.4, lo=0.1)
    assert not v.update(0.3)  # between the two: not enough to start
    assert v.update(0.5)
    assert v.update(0.3)  # the same level now continues it


def test_after_stopping_a_new_loud_sound_is_needed_to_start_again():
    v = VoiceTrigger(hi=0.4, lo=0.1)
    assert v.update(0.8)
    assert not v.update(0.05)
    assert not v.update(0.3)  # quiet-ish noise afterwards doesn't restart it
    assert v.update(0.6)  # a fresh pew does


def test_a_missing_microphone_never_fires_and_releases_the_trigger():
    v = VoiceTrigger(hi=0.4, lo=0.1)
    assert v.update(0.8)
    assert not v.update(None)
    assert not v.update(0.3)  # it was released, so 0.3 can't continue it


# --- Mac IMU profile ---------------------------------------------------------
def mac_reading(accel=(0.0, 0.0, -9.8), gyro=(0.0, 0.0, 0.0)):
    return {"accelerometer": dict(zip("xyz", accel)), "gyroscope": dict(zip("xyz", gyro)), "magnetometer": {}}


def test_mac_laptop_flat_reads_level_even_though_gravity_is_negative_z():
    h = HeadTracker(sim=False, profile=ImuProfile.mac())
    assert h.update(mac_reading(), DT)[1] == pytest.approx(0, abs=0.1)


def test_mac_forward_tilt_comes_from_gravity_alone():
    h = HeadTracker(sim=False, profile=ImuProfile.mac())
    # Far edge raised 30 degrees: gravity splits between the forward axis and -z.
    import math

    g = 9.8
    h.update(mac_reading(accel=(0, g * math.sin(math.radians(30)), -g * math.cos(math.radians(30)))), DT)
    assert h.pitch == pytest.approx(30 * C.MAC_PITCH_SIGN, abs=0.5)
    # A gyro spin about x must NOT move the pitch: the profile takes pitch from gravity only.
    before = h.pitch
    h.update(mac_reading(accel=(0, g * math.sin(math.radians(30)), -g * math.cos(math.radians(30))), gyro=(90, 0, 0)), DT)
    assert h.pitch == pytest.approx(before, abs=0.01)


def test_mac_yaw_integrates_rotation_about_the_vertical_axis_and_can_be_flipped():
    for flip in (1.0, -1.0):
        h = HeadTracker(sim=False, profile=ImuProfile.mac(yaw_flip=flip))
        for _ in range(15):  # one second at 90 deg/s about z
            h.update(mac_reading(gyro=(0, 0, 90)), DT)
        expected = (90 * C.MAC_YAW_SIGN * flip) % 360
        assert h.yaw == pytest.approx(expected, abs=1.0)


# --- PeakHold ---------------------------------------------------------------
def test_peak_hold_keeps_a_brief_spike_between_looks():
    p = PeakHold()
    for level in (0.01, 0.40, 0.02, 0.01):  # a 20 ms spike inside one 67 ms tick
        p.update(level)
    assert p.take() == pytest.approx(0.40)
    assert p.take() == pytest.approx(0.01)  # the next tick starts from the latest level, not 0.4


# --- GazeAim trust_all (the simulator's mouse) -------------------------------
def test_a_moving_mouse_is_followed_immediately_not_treated_as_jitter():
    g = GazeAim(640, 640, trust_all=True)
    for x in range(100, 400, 60):  # sweeping fast: 60 px per tick would be "jitter" to the eye filter
        pos = g.update((x, 200))
    assert g.confident and pos == (340, 200)  # exactly where the mouse is, with no lag
    assert g.update((10, 10)) != (320, 320)  # no waiting for steady samples
    assert g.update(None) == (320, 320) and not g.confident
    assert g.update((900, 900)) == (320, 320)  # still ignores positions outside the display


def test_the_eye_filter_still_rejects_a_sweep():
    g = GazeAim(640, 640)
    for x in range(100, 400, 60):
        pos = g.update((x, 200))
    assert not g.confident and pos == (320, 320)


# --- noise filtering ---------------------------------------------------------
import random  # noqa: E402


def noisy_still(h, seconds=20, gyro_noise=0.6, accel_noise=0.25, seed=1):
    rnd = random.Random(seed)
    out = []
    for _ in range(int(seconds / DT)):
        accel = (rnd.gauss(0, accel_noise), rnd.gauss(0, accel_noise), 9.8 + rnd.gauss(0, accel_noise))
        gyro = _gyro(yaw=rnd.gauss(0, gyro_noise), pitch=rnd.gauss(0, gyro_noise))
        out.append(h.update(reading(accel=accel, gyro=gyro), DT))
    return out


def spread(values):
    m = sum(values) / len(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5


def test_a_still_head_with_a_noisy_sensor_barely_moves_the_view():
    h = HeadTracker(sim=False)
    out = noisy_still(h)[30:]  # after settling
    steps = [abs(b[1] - a[1]) for a, b in zip(out, out[1:])] + [abs((b[0] - a[0] + 180) % 360 - 180) for a, b in zip(out, out[1:])]
    assert max(steps) < 0.35, f"the view jumps {max(steps):.2f} degrees between ticks while the head is still"
    assert spread([p for _, p in out]) < 0.35


def test_the_filter_costs_little_lag_when_the_head_turns():
    h = HeadTracker(sim=False)
    for _ in range(5):
        h.update(reading(), DT)
    seen = []
    for _ in range(15):  # a brisk one second turn at 60 deg/s
        seen.append(h.update(reading(gyro=_gyro(yaw=60)), DT)[0])
    assert seen[-1] > 52, f"after a 60 degree turn the view only reached {seen[-1]:.1f}"
    assert seen[0] > 1  # and it starts moving at once
    assert seen == sorted(seen)  # never steps backwards


def test_small_gyro_bias_does_not_drift_the_yaw():
    h = HeadTracker(sim=False)
    for _ in range(int(60 / DT)):  # a minute with a 0.4 deg/s offset
        out = h.update(reading(gyro=_gyro(yaw=0.4)), DT)
    assert min(out[0], 360 - out[0]) < 1.0


def test_pitch_settles_on_the_true_tilt_through_noise():
    h = HeadTracker(sim=False, profile=ImuProfile.mac())
    out = []
    rnd = random.Random(2)
    import math

    rad = math.radians(20)
    for _ in range(int(10 / DT)):
        a = [rnd.gauss(0, 0.25), 0.0, 0.0]
        a[C.MAC_ACCEL_FWD_AXIS] = 9.8 * math.sin(rad) + rnd.gauss(0, 0.25)
        a[2] = -9.8 * math.cos(rad) + rnd.gauss(0, 0.25)
        out.append(h.update(reading(accel=tuple(a)), DT)[1])
    assert abs(abs(out[-1]) - 20) < 2.0
    assert spread(out[-60:]) < 0.5
