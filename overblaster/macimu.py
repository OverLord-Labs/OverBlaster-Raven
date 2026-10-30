"""This Mac's own accelerometer and gyroscope, for testing without the glasses.

Apple Silicon laptops expose their motion sensors as AppleSPUHIDDevice entries (vendor
usage page 0xFF00: usage 3 = accelerometer, usage 9 = gyroscope). The interface is
undocumented. It was probed on a MacBook Air (M3) running as an ordinary user, no root: both
sensors report about 100 times per second, 22 bytes each, and gravity reads about -1 g on
z (so on that Mac the z axis points down) with the gyroscope near zero at rest.

The sensors are read from a background thread with their own CFRunLoop, so nothing here
touches Qt. Standard library only (ctypes -> IOKit). Run `python -m overblaster.macimu` to
see what your Mac reports.
"""

import ctypes
import ctypes.util
import struct
import sys
import threading
import time
from typing import Optional, Tuple

from . import config as C

G = 9.80665  # m/s^2 per g, so readings look like the framework's (gravity is about 9.8)
PAGE_VENDOR, USAGE_ACCEL, USAGE_GYRO = 0xFF00, 3, 9
REPORT_INTERVAL_US = 10000  # ask for 100 Hz


def parse_report(data: bytes) -> Optional[Tuple[float, float, float]]:
    """Decode one raw 22-byte report into (x, y, z): g for the accelerometer, deg/s for the gyroscope.

    Three little-endian int32 values at byte offsets 6, 10 and 14, scaled by 1/65536. The
    accelerometer scale is confirmed (gravity came out at 0.998 g); the gyroscope scale is
    assumed to match, so check a known rotation and adjust MAC_GYRO_SCALE if it is off.
    """
    if len(data) < 18:
        return None
    x, y, z = struct.unpack_from("<iii", data, 6)
    return x / 65536.0, y / 65536.0, z / 65536.0


class _Native:
    """ctypes bindings for the few IOKit / CoreFoundation calls we need (loaded lazily)."""

    def __init__(self) -> None:
        iokit_path, cf_path = ctypes.util.find_library("IOKit"), ctypes.util.find_library("CoreFoundation")
        if not iokit_path or not cf_path:
            raise OSError("IOKit / CoreFoundation not found (not macOS?)")
        self.iokit, self.cf = ctypes.CDLL(iokit_path), ctypes.CDLL(cf_path)
        vp, i32, u32 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32
        cf, io = self.cf, self.iokit
        cf.CFStringCreateWithCString.restype = vp
        cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, u32]
        cf.CFNumberGetValue.argtypes = [vp, ctypes.c_int, vp]
        cf.CFNumberGetValue.restype = ctypes.c_ubyte
        cf.CFNumberCreate.restype = vp
        cf.CFNumberCreate.argtypes = [vp, ctypes.c_int, vp]
        cf.CFRelease.argtypes = [vp]
        cf.CFRunLoopGetCurrent.restype = vp
        cf.CFRunLoopRunInMode.argtypes = [vp, ctypes.c_double, ctypes.c_ubyte]
        cf.CFRunLoopRunInMode.restype = i32
        self.mode = vp.in_dll(cf, "kCFRunLoopDefaultMode")
        io.IOServiceMatching.restype = vp
        io.IOServiceMatching.argtypes = [ctypes.c_char_p]
        io.IOServiceGetMatchingServices.argtypes = [u32, vp, ctypes.POINTER(u32)]
        io.IOServiceGetMatchingServices.restype = i32
        io.IOIteratorNext.argtypes = [u32]
        io.IOIteratorNext.restype = u32
        io.IOObjectRelease.argtypes = [u32]
        io.IORegistryEntryCreateCFProperty.argtypes = [u32, vp, vp, u32]
        io.IORegistryEntryCreateCFProperty.restype = vp
        io.IORegistryEntrySetCFProperty.argtypes = [u32, vp, vp]
        io.IORegistryEntrySetCFProperty.restype = i32
        io.IOHIDDeviceCreate.argtypes = [vp, u32]
        io.IOHIDDeviceCreate.restype = vp
        io.IOHIDDeviceOpen.argtypes = [vp, u32]
        io.IOHIDDeviceOpen.restype = i32
        self.callback_type = ctypes.CFUNCTYPE(
            None, vp, i32, vp, i32, u32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_long
        )
        io.IOHIDDeviceRegisterInputReportCallback.argtypes = [vp, vp, ctypes.c_long, self.callback_type, vp]
        io.IOHIDDeviceScheduleWithRunLoop.argtypes = [vp, vp, vp]

    def cfstr(self, text: str):
        return self.cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)  # UTF-8

    def services(self, class_name: str):
        """Yield each registry entry of a class; the caller releases each one."""
        it = ctypes.c_uint32(0)
        matching = self.iokit.IOServiceMatching(class_name.encode())
        if self.iokit.IOServiceGetMatchingServices(0, matching, ctypes.byref(it)) != 0:
            return
        while True:
            svc = self.iokit.IOIteratorNext(it.value)
            if not svc:
                break
            yield svc
        self.iokit.IOObjectRelease(it.value)

    def int_property(self, svc: int, name: str) -> Optional[int]:
        key = self.cfstr(name)
        ref = self.iokit.IORegistryEntryCreateCFProperty(svc, key, None, 0)
        self.cf.CFRelease(key)
        if not ref:
            return None
        out = ctypes.c_int64(0)
        ok = self.cf.CFNumberGetValue(ref, 4, ctypes.byref(out))  # kCFNumberSInt64Type
        self.cf.CFRelease(ref)
        return out.value if ok else None

    def wake_sensors(self) -> None:
        """Best effort: ask the SPU drivers to report at REPORT_INTERVAL_US. Ignored if refused."""
        for svc in self.services("AppleSPUHIDDriver"):
            for name, value in (
                ("SensorPropertyReportingState", 1),
                ("SensorPropertyPowerState", 1),
                ("ReportInterval", REPORT_INTERVAL_US),
            ):
                key = self.cfstr(name)
                num = self.cf.CFNumberCreate(None, 3, ctypes.byref(ctypes.c_int32(value)))  # SInt32
                self.iokit.IORegistryEntrySetCFProperty(svc, key, num)
                self.cf.CFRelease(key)
                self.cf.CFRelease(num)
            self.iokit.IOObjectRelease(svc)


class MacImuSensor:
    """Streams the laptop's accelerometer and gyroscope. start() once; reading() every tick."""

    def __init__(self, clock=time.monotonic, keep_raw: int = 0) -> None:
        self._clock = clock
        self._accel: Optional[Tuple[float, float, float]] = None  # g, the latest sample
        self._gyro: Optional[Tuple[float, float, float]] = None  # deg/s, the latest sample
        # The sensors run at 100 Hz and the game reads at about 15 Hz. Samples are summed here and
        # averaged by reading(), so all of them count instead of one in six.
        self._sum = {USAGE_ACCEL: [0.0, 0.0, 0.0, 0], USAGE_GYRO: [0.0, 0.0, 0.0, 0]}
        self._lock = threading.Lock()
        self._last_at = float("-inf")
        self.counts = {USAGE_ACCEL: 0, USAGE_GYRO: 0}
        self.raw = {USAGE_ACCEL: [], USAGE_GYRO: []}
        self._keep_raw = keep_raw
        self.error: Optional[str] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ----- data ------------------------------------------------------------
    def _on_sample(self, usage: int, data: bytes) -> None:
        """Called from the sensor thread (and by tests) with one raw report."""
        self.counts[usage] += 1
        if len(self.raw[usage]) < self._keep_raw:
            self.raw[usage].append(data)
        parsed = parse_report(data)
        if parsed is None:
            return
        with self._lock:
            if usage == USAGE_ACCEL:
                self._accel = parsed
            else:
                self._gyro = parsed
            acc = self._sum[usage]
            acc[0] += parsed[0]
            acc[1] += parsed[1]
            acc[2] += parsed[2]
            acc[3] += 1
            self._last_at = self._clock()

    def _take_mean(self, usage: int, latest: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """The mean of the samples since the last call, or the latest one if none have arrived."""
        with self._lock:
            x, y, z, n = self._sum[usage]
            self._sum[usage] = [0.0, 0.0, 0.0, 0]
        return (x / n, y / n, z / n) if n else latest

    @property
    def fresh(self) -> bool:
        return self._accel is not None and self._gyro is not None and self._clock() - self._last_at <= C.MAC_IMU_STALE_S

    def reading(self) -> Optional[dict]:
        """The newest reading in the framework's IMU shape (m/s^2 and deg/s), or None if stale."""
        if not self.fresh:
            return None
        ax, ay, az = self._take_mean(USAGE_ACCEL, self._accel)
        gx, gy, gz = (v * C.MAC_GYRO_SCALE for v in self._take_mean(USAGE_GYRO, self._gyro))
        return {
            "accelerometer": {"x": ax * G, "y": ay * G, "z": az * G},
            "gyroscope": {"x": gx, "y": gy, "z": gz},
            "magnetometer": {"x": 0.0, "y": 0.0, "z": 0.0},
        }

    # ----- lifecycle ---------------------------------------------------------
    def start(self, timeout: float = 1.5) -> bool:
        """Open the sensors on a background thread. False (with .error set) if unavailable."""
        if sys.platform != "darwin":
            self.error = "not macOS"
            return False
        self._thread = threading.Thread(target=self._run, name="mac-imu", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.error is None and self._ready.is_set()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            native = _Native()
            native.wake_sensors()
            keep_alive, opened = [], 0
            for svc in native.services("AppleSPUHIDDevice"):
                page = native.int_property(svc, "PrimaryUsagePage")
                usage = native.int_property(svc, "PrimaryUsage")
                if page == PAGE_VENDOR and usage in (USAGE_ACCEL, USAGE_GYRO):
                    dev = native.iokit.IOHIDDeviceCreate(None, svc)
                    rc = native.iokit.IOHIDDeviceOpen(dev, 0) if dev else -1
                    if rc == 0:
                        buf = ctypes.create_string_buffer(4096)
                        callback = native.callback_type(self._make_callback(usage))
                        keep_alive += [buf, callback, dev]
                        native.iokit.IOHIDDeviceRegisterInputReportCallback(
                            dev, ctypes.cast(buf, ctypes.c_void_p), 4096, callback, None
                        )
                        native.iokit.IOHIDDeviceScheduleWithRunLoop(dev, native.cf.CFRunLoopGetCurrent(), native.mode)
                        opened += 1
                    else:
                        self.error = f"could not open sensor (usage {usage}, IOReturn 0x{rc & 0xFFFFFFFF:08x})"
                native.iokit.IOObjectRelease(svc)
            if opened < 2 and self.error is None:
                self.error = "no accelerometer/gyroscope found on this Mac"
            self._ready.set()
            while opened == 2 and not self._stop.is_set():
                native.cf.CFRunLoopRunInMode(native.mode, 0.1, 0)
        except Exception as exc:  # noqa: BLE001 - never let a sensor problem take the game down
            self.error = f"{type(exc).__name__}: {exc}"
            self._ready.set()

    def _make_callback(self, usage: int):
        def on_report(_ctx, _result, _sender, _type, _report_id, report, length):
            self._on_sample(usage, bytes(report[:length]))

        return on_report


if __name__ == "__main__":
    sensor = MacImuSensor(keep_raw=2)
    ok = sensor.start()
    print("started:", ok, "| error:", sensor.error)
    if ok:
        print("sampling for 3 s: tilt and rotate the laptop...")
        t0 = time.time()
        while time.time() - t0 < 3.0:
            time.sleep(0.5)
            r = sensor.reading()
            if r:
                a, g = r["accelerometer"], r["gyroscope"]
                print(f"  accel m/s^2 ({a['x']:+6.2f} {a['y']:+6.2f} {a['z']:+6.2f})   gyro deg/s ({g['x']:+7.2f} {g['y']:+7.2f} {g['z']:+7.2f})")
        print("report counts:", {("accel" if k == USAGE_ACCEL else "gyro"): v for k, v in sensor.counts.items()})
        for usage, name in ((USAGE_ACCEL, "accel"), (USAGE_GYRO, "gyro")):
            for raw in sensor.raw[usage]:
                print(f"  raw {name}:", raw.hex(" "))
    sensor.stop()
