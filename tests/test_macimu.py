import pytest

from overblaster import config as C
from overblaster.macimu import G, USAGE_ACCEL, USAGE_GYRO, MacImuSensor, parse_report

# Raw 22-byte reports captured from a MacBook Air (M3), lying flat and still.
ACCEL_FLAT = bytes.fromhex("74 41 00 00 00 00 11 ff ff ff b8 f9 ff ff ed 00 ff ff 00 0b 1d 00")
GYRO_STILL = bytes.fromhex("f9 7a 00 00 00 00 00 00 00 00 40 1f 00 00 00 00 00 00 00 0b 1d 00")


def test_parse_report_reads_real_accelerometer_bytes():
    x, y, z = parse_report(ACCEL_FLAT)
    assert x == pytest.approx(-0.0033, abs=0.001)
    assert y == pytest.approx(-0.0245, abs=0.002)
    assert z == pytest.approx(-0.9964, abs=0.002)  # gravity reads NEGATIVE on this Mac's z


def test_parse_report_reads_real_gyro_bytes_near_zero():
    assert all(abs(v) < 0.2 for v in parse_report(GYRO_STILL))


def test_parse_report_rejects_short_reports():
    assert parse_report(b"\x00" * 10) is None


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def make_sensor():
    clock = Clock()
    return MacImuSensor(clock=clock), clock


def test_reading_needs_both_sensors_and_uses_framework_units():
    sensor, _ = make_sensor()
    assert sensor.reading() is None
    sensor._on_sample(USAGE_ACCEL, ACCEL_FLAT)
    assert sensor.reading() is None  # no gyro yet
    sensor._on_sample(USAGE_GYRO, GYRO_STILL)
    r = sensor.reading()
    assert r["accelerometer"]["z"] == pytest.approx(-0.9964 * G, abs=0.05)  # m/s^2, like the framework
    assert set(r) == {"accelerometer", "gyroscope", "magnetometer"}
    assert sensor.counts == {USAGE_ACCEL: 1, USAGE_GYRO: 1}


def test_reading_goes_stale_so_the_arrow_keys_can_take_over():
    sensor, clock = make_sensor()
    sensor._on_sample(USAGE_ACCEL, ACCEL_FLAT)
    sensor._on_sample(USAGE_GYRO, GYRO_STILL)
    assert sensor.fresh
    clock.t += C.MAC_IMU_STALE_S + 0.1
    assert not sensor.fresh and sensor.reading() is None


def test_gyro_scale_is_applied(monkeypatch):
    sensor, _ = make_sensor()
    spin = bytes(6) + (65536 * 90).to_bytes(4, "little", signed=True) + bytes(12)  # x = 90 deg/s
    sensor._on_sample(USAGE_ACCEL, ACCEL_FLAT)
    sensor._on_sample(USAGE_GYRO, spin)
    assert sensor.reading()["gyroscope"]["x"] == pytest.approx(90.0)
    monkeypatch.setattr(C, "MAC_GYRO_SCALE", 0.5)
    assert sensor.reading()["gyroscope"]["x"] == pytest.approx(45.0)


def test_garbage_reports_are_ignored():
    sensor, _ = make_sensor()
    sensor._on_sample(USAGE_ACCEL, b"\x01\x02")
    assert sensor.reading() is None


def _report(x, y, z):
    import struct

    return b"\x00" * 6 + struct.pack("<iii", int(x * 65536), int(y * 65536), int(z * 65536)) + b"\x00" * 4


def test_a_reading_averages_every_sample_since_the_last_one():
    # The sensor runs at 100 Hz but the game reads at 15 Hz: taking only the newest sample throws
    # most of them away and passes all of their noise through. Averaging them is a free low-pass.
    sensor, _ = make_sensor()
    sensor._on_sample(USAGE_ACCEL, _report(0, 0, -1))
    for v in (4, -4, 6, -6, 1, -1, 5, -5):  # noisy, centred on zero
        sensor._on_sample(USAGE_GYRO, _report(0, v, 0))
    assert abs(sensor.reading()["gyroscope"]["y"]) < 0.1
    for v in (10, 10, 10):
        sensor._on_sample(USAGE_GYRO, _report(0, v, 0))
    assert sensor.reading()["gyroscope"]["y"] == pytest.approx(10, abs=0.01)  # only the new ones count
    assert sensor.reading()["gyroscope"]["y"] == pytest.approx(10, abs=0.01)  # no new samples: the last value holds
