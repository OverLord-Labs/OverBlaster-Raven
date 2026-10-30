"""All OverBlaster tunables in one place. Nothing here imports the Raven framework."""

import os

# --- Display -------------------------------------------------------------
# The docs list a 720 x 720 px panel but a 640 x 640 px app container; the app
# reads the real container size at runtime and only falls back to these.
DISPLAY_PX = 640
FOV_DEG = 30.0  # diagonal field of view of the waveguide

# --- Timing --------------------------------------------------------------
TICK_HZ = 15  # game update rate; kept low to save battery
TICK_MS = int(1000 / TICK_HZ)

# --- World space (degrees) ----------------------------------------------
EL_LIMIT = 20.0  # worlds stay within +/- this elevation (the vertical field of view is only +/- 15)
SPAWN_SPREAD = 45.0  # worlds spawn within +/- this azimuth of where the player looks (the view is only 30 wide)
SPAWN_APPROACH = 0.0  # approach progress at spawn (0 = far away, 1 = hits the ship)

# --- HUD ------------------------------------------------------------------
# Announced by the banner when a level starts, and shown nowhere else. Level 6 and beyond keep the last one.
LEVEL_NAMES = ("OUTER RIM", "ASTEROID BELT", "NEBULA GATE", "VOID STORM", "EVENT HORIZON", "DEEP SPACE")


def level_name(level: int) -> str:
    return LEVEL_NAMES[max(0, min(level, len(LEVEL_NAMES)) - 1)]


# --- Rogue Worlds --------------------------------------------------------
WORLD_KINDS = ("a", "b", "c")
# At about 21 px per degree, 3.0 degrees of radius is the 128 px sprite size, so the
# artwork is never upscaled. Worlds are drawn at one of WORLD_BANDS (px); MediaViewer
# is fixed-size and reloads on resize, so the sprite is swapped at the band edges
# (see view.size_class). These must match the GIFs made by tools/prep_assets.py.
WORLD_BANDS = (64, 96, 128)
WORLD_MIN_RADIUS = 1.0  # angular radius at spawn (far away)
WORLD_MAX_RADIUS = 3.0  # angular radius when about to hit the ship
HIT_FORGIVENESS = 1.5  # hit radius = visual radius * this (sprites are drawn in size bands, so a bit generous)
APPROACH_SECONDS = 100.0  # seconds to reach the ship at level 1. A world that arrives ends the game, so
#                          head-turning players need real time to find and kill every one
APPROACH_SPEEDUP = 0.12  # +12 % speed per level
DRIFT_DEG_PER_S = 2.5  # max sideways drift speed at level 1
KNOCKBACK = 0.0015  # each hit pushes a world back this far; at 10 hits a second it must stay small
WORLDS_BASE = 5
WORLD_HP_BASE = 6  # hits to destroy a world at level 1
WORLD_HP_PER_LEVEL = 1  # and one more each level
CARRIER_EXTRA_HP = 4  # the chip carrier is tougher still
WORLDS_PER_LEVEL = 2
MAX_WORLDS_ON_SCREEN = 8  # also the size of the widget pool

# --- Battery -------------------------------------------------------------
BATTERY_START = 100.0
SHOT_COST = 1.0
CRYSTAL_VALUE = 3.0
SHOT_FX_S = 0.5  # how long a shot's animation is kept (the longest effect, a kill's explosion)
SHOT_COOLDOWN_S = 0.10  # 10 shots a second

# --- Crystals ------------------------------------------------------------
CRYSTALS_MIN, CRYSTALS_MAX = 3, 5  # crystals dropped when a world is destroyed
MAX_CRYSTALS_ON_SCREEN = 6
CRYSTAL_LIFETIME_S = 9.0  # seconds before an uncollected crystal drifts away
CRYSTAL_RADIUS = 3.0  # harvest radius in degrees
HARVEST_DWELL_S = 0.30  # crosshair must stay on a crystal this long
HARVEST_DECAY = 2.0  # dwell drains this much faster than it fills when aim leaves

# --- Overlord Battery Gauge Chip ----------------------------------------
CHIP_LEVEL = 3  # first level with a chip carrier world (after 2 clear levels); it returns each level until the chip is collected
CHIP_REPEAT = False  # True = another chip every CHIP_LEVEL levels
CHIP_CAPACITY_FACTOR = 2.0
CHIP_LIFETIME_S = 18.0
CHIP_HOLD_S = 2.4  # the Overlord BMS has to be held in your aim this long, not just glanced at
CHIP_HOLD_DRAIN = 0.2  # a slip drains this fraction of the hold per second (a fifth of the fill speed), and never resets it

# --- Scoring -------------------------------------------------------------
SCORE_HIT = 20
SCORE_DESTROY = 500
SCORE_CRYSTAL = 50
SCORE_CHIP = 1000
INTERMISSION_S = 2.0

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
