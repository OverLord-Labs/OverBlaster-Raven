"""All OverBlaster tunables in one place. Nothing here imports the Raven framework."""

import os

# --- Display -------------------------------------------------------------
# The docs list a 720 x 720 px panel but a 640 x 640 px app container; the app
# reads the real container size at runtime and only falls back to these.
DISPLAY_PX = 640
FOV_DEG = 30.0  # diagonal field of view of the waveguide

# --- Timing --------------------------------------------------------------
# One tick runs the core and repaints the whole scene (a QPainter picture of everything on screen), so the rate is the
# battery dial. Measured on a MacBook Air (tools/bench_tick.py, 640 px): a gameplay frame paints in 2-5 ms, the busiest
# intro frames in about 8 ms, and the core takes well under 1 ms, so even 20 Hz uses under a fifth of its 50 ms budget;
# 20 Hz makes the sky and the bolts visibly smoother than 15. The glasses' board is slower and has not been measured:
# if it cannot keep up, or the battery drain matters more, run with OVERBLASTER_TICK_HZ=15 (or 12).
TICK_HZ = int(os.environ.get("OVERBLASTER_TICK_HZ", 20))
TICK_MS = int(1000 / TICK_HZ)

# --- Dwell buttons ---------------------------------------------------------
DWELL_S = 1.5  # rest the gaze on LAUNCH, RETRY, TITLE or SKIP STORY this long to press it (the framework Button's own default)


# The rules (worlds, rocks, battery, crystals, the BMS chip, wings, levels, scoring) live in overblaster/core/constants.py
# and overblaster/core/levels.py: a port of the web game's core, which is the source of truth for the game's design.

# --- Voice trigger ("Pew") ----------------------------------------------
# Any sound counts; only the volume matters. Levels are 0.0 - 1.0.
# Measured on a MacBook Air mic: a quiet room peaks near 0.005, so these sit about ten times
# above that and low enough that a normal speaking voice fires (no yelling). The debug display
# shows the live level.
VOICE_HI = float(os.environ.get("OVERBLASTER_VOICE_HI", 0.05))
VOICE_LO = float(os.environ.get("OVERBLASTER_VOICE_LO", 0.02))

# --- Eye gaze -------------------------------------------------------------
GAZE_WINDOW = 6  # samples used to judge confidence
GAZE_MIN_SAMPLES = 4  # need this many consecutive non-None samples
GAZE_MAX_SPREAD_PX = 20.0  # jitter above this = low confidence
GAZE_SMOOTHING = 0.5  # 0 = frozen, 1 = no smoothing

# --- Head tracking (IMU) -------------------------------------------------
# The framework's IMU simulator reports {"x", "y", "z"} dicts with gravity (+9.8)
# on z when the head is level and y as "tilt forward / up". The real device's
# axes and units are not documented, so the gyroscope entries below are the
# assumptions to confirm on the glasses (see README, "Calibration").
GYRO_IN_DEGREES = True  # False if the gyroscope reports radians per second
GYRO_YAW_AXIS = 1  # index into the (x, y, z) gyroscope vector
GYRO_YAW_SIGN = 1.0
GYRO_PITCH_AXIS = 0
GYRO_PITCH_SIGN = 1.0
ACCEL_UP_AXIS = 2  # axis that carries gravity when the head is level
ACCEL_FWD_AXIS = 1  # axis that tilts forward / up
ACCEL_PITCH_SIGN = 1.0
# Noise filtering for the head tracker (see sensors.HeadTracker)
GYRO_DEADBAND_DPS = 1.0  # turn rates under this are sensor noise or bias, not a head turn
ACCEL_SMOOTH = 0.25  # weight of each new accelerometer sample in the running average
VIEW_MIN_CUTOFF_HZ = 1.0  # the view is smoothed this hard while the head is still...
VIEW_BETA = 0.04  # ...and the cutoff rises by this many Hz per degree/s of head speed, so turns stay quick
COMPLEMENTARY_ALPHA = 0.95  # weight of the integrated gyro vs. the accelerometer
PITCH_LIMIT = 60.0

# In the simulator the gyroscope is always zero and the arrow keys only move the
# accelerometer (+-2.0 on x for left / right, +-2.0 on y for up / down), so there
# the accelerometer steers like a joystick instead of measuring gravity. This is
# detected automatically (not on a Raven device); OVERBLASTER_SIM=1 forces it.
SIM_FORCE = os.environ.get("OVERBLASTER_SIM", "") == "1"
SIM_STEER_DEG_PER_S = 15.0  # per unit of accelerometer, so 2.0 -> 30 deg/s

# --- Mac IMU (testing without the glasses) ---------------------------------
# overblaster/macimu.py reads this laptop's accelerometer and gyroscope (Apple Silicon).
# Probed on a MacBook Air M3: gravity reads about -1 g on z when flat, so z points DOWN there.
# The pitch is taken from gravity alone (no gyro), and yaw from the gyroscope about that
# vertical axis. Tuned by testing on a MacBook Air M3 (turn left = view left, tilt up = look up).
# If your Mac differs, press Y or P in the app to flip yaw or pitch live; the terminal and the debug
# panel then show the resulting sign to put here. Live flips are not saved between runs.
MAC_IMU_STALE_S = 0.5  # fall back to the arrow keys when no sample has arrived for this long
MAC_GYRO_SCALE = 1.0  # multiply gyro readings by this if a 90 degree turn doesn't read as 90
MAC_YAW_SIGN = -1.0
MAC_PITCH_SIGN = -1.0
MAC_ACCEL_FWD_AXIS = 1  # the axis that moves when you raise the far edge of the lid (0 = x, 1 = y)

# --- Debug display ----------------------------------------------------------
DEBUG_FORCE = os.environ.get("OVERBLASTER_DEBUG", "") == "1"
DEBUG_MIC_FULL_SCALE = 0.25  # level shown as a full bar

# --- Microphone -----------------------------------------------------------
# Off a Raven device the framework's Microphone keeps every recorded sample in
# memory (about 5 MB per minute), so it is restarted this often to cap growth.
MIC_RESTART_S = 30.0

# --- Audio ----------------------------------------------------------------
AUDIO_ENABLED = os.environ.get("OVERBLASTER_MUTE", "") != "1"  # OVERBLASTER_MUTE=1 turns all sound off
AUDIO_MASTER = 0.8
AUDIO_MUSIC = 0.30  # music sits low: it is also what the microphone hears while you say "Pew"
AUDIO_SFX = 0.8
AUDIO_VOICE = 1.0
AUDIO_DUCK = 0.35  # music level while the voice speaks
AUDIO_SHOT_SOUND = False  # the player's own "Pew" is the shot sound; a laser sound would feed back into the mic
