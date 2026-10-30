import pytest

from overblaster.inputs import RavenInputs


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, value):
        for fn in self.slots:
            fn(value)


class FakeQtMic:
    """Like the framework's Qt microphone: pushes a level every 20 ms through levelChanged."""

    sensorlib_client = None

    def __init__(self):
        self.levelChanged = Signal()
        self.recording = False
        self.starts = self.stops = 0

    def start_recording(self):
        self.recording, self.starts = True, self.starts + 1

    def stop_recording(self):
        self.recording, self.stops = False, self.stops + 1
        return b""


class FakeDeviceClient:
    def __init__(self):
        self.level = 0.0

    def get_microphone_level(self):
        return self.level


class FakeDeviceMic(FakeQtMic):
    def __init__(self):
        super().__init__()
        self.sensorlib_client = FakeDeviceClient()
        self.levelChanged = None  # the real device Microphone never updates .level


def inputs_with(mic):
    return RavenInputs(imu=object(), eye=object(), mic=mic)


def test_a_brief_spike_between_ticks_is_not_missed():
    mic = FakeQtMic()
    inputs = inputs_with(mic)
    assert inputs.mic_level() == 0.0 and mic.recording  # first call starts the microphone
    for level in (0.01, 0.35, 0.02):  # three 20 ms reports inside one game tick
        mic.levelChanged.emit(level)
    assert inputs.mic_level() == pytest.approx(0.35)
    assert inputs.mic_status == "listening"


def test_device_microphone_is_polled_from_the_sensorlib_client():
    mic = FakeDeviceMic()
    inputs = inputs_with(mic)
    mic.sensorlib_client.level = 0.42
    assert inputs.mic_level() == pytest.approx(0.42)


def test_missing_microphone_reports_a_status_instead_of_crashing():
    inputs = RavenInputs(imu=object(), eye=object(), mic=None)
    inputs._mic = None
    assert inputs.mic_level() is None and inputs.mic_status == "no microphone"


def test_off_device_recording_restarts_to_cap_memory(monkeypatch):
    import overblaster.inputs as mod
    from overblaster import config as C

    clock = {"t": 0.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock["t"])
    mic = FakeQtMic()
    inputs = inputs_with(mic)
    inputs.mic_level()
    clock["t"] += C.MIC_RESTART_S + 1
    inputs.mic_level()
    assert mic.stops == 1 and mic.starts == 2
