# OverBlaster

**An OverLord Labs game for the Raven Prism smart glasses.**

You are in a spaceship. Blast the **Rogue Worlds** before they reach you, then harvest the
**energy crystals** they drop. Crystals recharge your battery, and every "Pew" spends some.
Run out of battery, or let a Rogue World hit your ship, and you lose: a world that reaches you
destroys the ship at once. From level 3, a gold world appears. Destroy it to release the
**Overlord BMS** (the Overlord Battery Gauge Chip), a battery management chip that doubles your battery capacity. If it gets past you, it
comes back the next level until you get the chip.

| You do | The game reads |
|---|---|
| Turn your head | IMU: the sky scrolls around you |
| Look at something | Eye gaze: moves the crosshair, only when it is steady (high confidence). Otherwise the crosshair stays centered |
| Say "Pew" (or anything loud) | Microphone level above a threshold pulls the trigger. It stays pulled while the sound goes on, firing 10 shots a second: "pew" is a short burst, "pewwwww" is continuous fire |
| Hold the crosshair on a crystal for 0.3 s | Harvests it |

No 3D: everything is 2D sprites on a black background. Black is transparent on the additive
display, so most of the screen is unlit. Hidden animated sprites are paused so they don't decode
frames.

## Layout

```
main.py                 entry point (simulator / deploy)
overblaster/
  config.py             every tunable number
  game.py               rules: worlds, crystals, battery, chip, levels   (pure Python)
  synth.py              music and sound effects, synthesised with numpy
  audio.py              the mixer, the echo gate, the clip bank           (pure numpy)
  sound.py              what app.py calls: music, sfx, say, gate
  audiosink.py          plays the mix: Qt audio on a Mac, the Speaker on glasses
  voicelines.py         what the voice says; voicefx.py its ship's-computer sound
  bms.py                the Overlord BMS power-up: hold ring, arrow, sparks, callout (pure Python)
  bmslayer.py           the widget that paints it
  sensors.py            HeadTracker, GazeAim, VoiceTrigger filters       (pure Python)
  view.py               sky -> display projection and sprite size bands  (pure Python)
  hud.py                battery meter and level number geometry          (pure Python)
  hudlayer.py           the small widget that paints it
  screens.py            title, between-levels plate and level-start splash geometry (pure Python)
  screenlayers.py       the widgets that paint them
  fx.py                 shot and explosion animation geometry            (pure Python)
  fxlayer.py            the transparent overlay that draws it
  inputs.py             reads the IMU / eye tracker / microphone
  ui.py                 thin wrappers over Raven widgets
  app.py                RavenApp: screens, tick loop, HUD
assets/                 generated art (committed)
tools/prep_assets.py    rebuilds assets/ from the old Planet Zapper frames
tests/                  pytest suite (see Testing)
raven-framework/        the framework, cloned here for development (git-ignored)
```

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install pytest pillow
git clone https://github.com/RavenResonance/raven-framework.git
.venv/bin/pip install -e ./raven-framework
.venv/bin/python -m pytest
```

The framework is proprietary (Raven Resonance, Inc.). It is cloned inside this folder only so the
game can import it, and `.gitignore` keeps it out of this repo.

Run in the simulator:

```sh
.venv/bin/python main.py
```

Off a Raven device the game detects the simulator automatically and fills in for the missing
hardware. There is deliberately **no fire button**: you fire by making noise.

| Glasses | In the simulator |
|---|---|
| IMU (head) | **This Mac's own accelerometer and gyroscope** (Apple Silicon laptops). Raise the far edge of the lid to look up, turn the laptop to look around. If no Mac sensor is found, the arrow keys steer instead. |
| Eye gaze | The mouse. The crosshair goes exactly where the mouse is, inside the game area. |
| Microphone | The Mac's microphone. Say "Pew", clap, anything louder than the threshold. Keep making noise to keep firing. |

The screen is clean: there is no debug text. When you need to tune something, run with
`OVERBLASTER_DEBUG=1` to bring back a **debug panel** at the bottom-left. It shows the live
microphone level against the fire threshold (white mark: re-arms below it, gold mark: fires above
it), which IMU is in use with the head's yaw and pitch, and what the crosshair is following.

While testing the Mac IMU, click the window and press **C** to recenter the view, and **Y** or
**P** to flip the yaw or pitch direction if the view moves the wrong way. The terminal prints
which sign won (the panel shows it too), so you can copy it into `MAC_YAW_SIGN` / `MAC_PITCH_SIGN` in `config.py`.

If "Pew" does nothing, run with `OVERBLASTER_DEBUG=1` and watch the panel. The bar should jump when you speak. If it never gets near
the gold mark, lower `VOICE_HI` (or set `OVERBLASTER_VOICE_HI`, for example `0.03`). A quiet room
reads about 0.005, so the default of 0.05 is about ten times that and a normal speaking voice
fires it. If it fires on background noise, raise it. Check `System Settings >
Privacy & Security > Microphone` allows your terminal.

`python -m overblaster.macimu` prints what the Mac's motion sensors report. `OVERBLASTER_SIM=1`
forces simulator mode.

Deploy to the glasses:

```sh
RAVEN_APP_ID=... RAVEN_APP_KEY=... .venv/bin/python main.py deploy
```

Keep the id and key out of the repo.

## Testing

`.venv/bin/python -m pytest` runs about 85 tests in under 10 seconds:

- **Rules and filters** (`test_game`, `test_sensors`, `test_view`): battery maths, lose condition,
  chip logic, head tracking, gaze confidence, the voice trigger, projection.
- **Balance** (`test_balance`): scripted players keep the energy economy fair. They include bots
  that must turn their head, because instant-aim bots hid a real problem (see Balance).
- **App flow on fake widgets** (`test_app_smoke`, `fake_raven.py`): screens, the tick loop, a fixed
  widget pool, paused hidden sprites, no `resize()` calls.
- **Real framework, offscreen** (`test_real_framework`, `real_framework_game.py`,
  `real_framework_sim.py`): plays four levels with a scripted player on the real `raven_framework`
  widgets, checks the chip doubles capacity, the widget count never changes, and no hidden GIF keeps
  animating. A second script runs the simulator experience: a real mouse event moving the
  crosshair, the real microphone feeding the debug panel, and this Mac's real accelerometer driving
  head tracking (hardware checks only assert when the hardware exists). They run in separate
  processes and are skipped if the framework isn't installed.

## What the framework source taught us

The Raven docs are thin, so these come from reading `raven_framework` 1.0.6 itself. They shaped
the code, and several differ from the docs:

- `MediaViewer` is fixed-size and reloads its image on every resize, so worlds are pre-rendered at
  three size bands and swapped with `load_media()` instead of resized.
- `MediaViewer` paints an opaque black box behind every image, which cuts holes in anything it
  overlaps. The crosshair is therefore built from solid bars, and round art gets a circular
  backing.
- A hidden GIF keeps animating unless you call `pause_video()`.
- `fade_in()` leaves a graphics effect on the game container for good, and the simulator draws its
  picture with `QWidget.render()`, which shifts a child that has an effect by that child's own
  offset. Everything in the game then appeared (40, 50) px away from where the simulator sends
  the mouse, so the crosshair sat off the cursor. The game removes the effect once the fade is done.
  This probably affects any app that calls `fade_in(self.app)` and uses the simulator.
- `Microphone` has **no** `get_level()`. Off-device the level arrives through its `levelChanged`
  signal every 20 ms. On the glasses it is `mic.sensorlib_client.get_microphone_level()`. The game
  ticks every 67 ms, so it holds the peak between ticks (a short "Pew" can't slip between two
  looks). Off-device the framework also keeps all audio in memory (about 5 MB per minute), so
  `inputs.py` restarts the recording every 30 s.
- IMU values are `{"x", "y", "z"}` dicts, and the simulator puts gravity on z with the gyroscope
  always zero.
- The simulator's `EyeControl` returns the mouse position in the 720 px window's coordinates, which
  neither matches the 640 px game area (offset by 40, 50) nor survives the simulator's shrunk view.
  So in the simulator the game takes the mouse from the events the simulator forwards to the app
  and subtracts that offset itself. On the glasses, `Sensorlib.get_gaze_position()` is currently a
  stub that returns `None`.
- The framework's top-right home icon exits the app on dwell, so the HUD keeps clear of that corner.

## Status: what is and isn't verified

Verified here, on a Mac: everything in Testing, `main.py` starting through the real `RunApp`, the
real IMU, eye and microphone classes constructing without errors, this Mac's microphone and motion
sensors reading live, and screenshots of the title,
HUD, worlds, crystals and chip rendered by the real widgets.

**Not verified: anything on the glasses.** Check these first, in this order:

1. **Gyroscope axes and units.** `config.py` assumes degrees per second, with yaw on axis 1 and
   pitch on axis 0. The framework documents neither. See Calibration.
2. **Eye gaze.** In this framework version `EyeControl.get_gaze_position()` returns `None` on the
   device, so the crosshair will stay centered and aiming is head-only. The game handles that, but
   the eye-driven crosshair needs a framework version that delivers gaze. Confidence is a
   heuristic: 4 or more steady, on-screen samples within 20 px.
3. **Microphone on the device.** The path through `Sensorlib.get_microphone_level()` has not run.
   The thresholds were set from a MacBook Air microphone; the glasses will differ.
4. **Frame rate and battery.** The game ticks at 15 Hz and moves a handful of widgets. Offscreen
   timings mean nothing for the glasses.
5. **The Mac IMU's gyroscope scale.** The sensors read fine (about 100 Hz each, gravity near -1 g on
   z, nothing drifting while still) and the directions were tuned on a MacBook Air M3 (`MAC_YAW_SIGN`
   and `MAC_PITCH_SIGN` are both -1 there). Live Y / P flips are not saved between runs: when one
   fixes it, copy the sign the terminal prints into `config.py`. The gyroscope's scale (assumed
   degrees per second) is unconfirmed: turn the laptop 90 degrees and check the debug panel (`OVERBLASTER_DEBUG=1`)
   reads about 90.
6. **A real simulator window.** Everything was run offscreen. The additive-blend preview modes
   haven't been looked at.

## How eye tracking works with this game

Nothing in the game needs a click, a wink or a blink while you play. In the framework, **looking is
hovering**: gaze drives the cursor (the white "gaze marker" ring), and a `Button` fires by *dwell*,
meaning you keep your gaze on it for 1.5 s (or double-blink, per the framework docs). In this game:

- **Aiming:** the crosshair follows where you look, and your head moves the sky. No click.
- **Firing:** your voice. No click.
- **Harvesting a crystal:** hold the crosshair on it for 0.3 s. That is the same dwell idea.
- **The only clicks** are the LAUNCH, Retry and Title buttons, which use the framework's own dwell.

In the simulator, moving the mouse is "looking", and a click is the stand-in for dwell or a blink.
The mouse needing no click to aim is the same as the eyes needing none.

On the glasses the game reads gaze from `EyeControl` first. In this framework version that returns
nothing, so it falls back to the cursor: the framework treats gaze as the cursor, so if the eyes
are moving it, the crosshair follows. **That fallback is untested on the glasses.** A cursor that
has not moved for half a second is ignored there, so a parked cursor never counts as a gaze.

## Head-tracking noise filter

The IMU reading goes through four stages (`config.py`: `GYRO_DEADBAND_DPS`, `ACCEL_SMOOTH`,
`VIEW_MIN_CUTOFF_HZ`, `VIEW_BETA`, `COMPLEMENTARY_ALPHA`):

1. **Mac IMU:** the sensor streams at 100 Hz and the game reads at 15 Hz, so every sample since the
   last read is averaged instead of keeping only the newest.
2. **Gyro dead band:** turn rates under 1 deg/s count as still, so a small bias can't drift the yaw.
3. **Accelerometer:** a running average before it sets the pitch; the pitch blend leans more on the
   gravity direction (alpha 0.95).
4. **View smoothing:** an adaptive (One Euro) filter on the final yaw and pitch. It smooths hard
   while the head is still and eases off as it speeds up, so turns keep their response.

If it feels laggy, raise `VIEW_MIN_CUTOFF_HZ` or `VIEW_BETA`; if it still shimmers, lower them.

## Calibration (on the glasses)

Work through these in order, changing `config.py`:

- **Head moves the wrong way.** Flip `GYRO_YAW_SIGN` or `GYRO_PITCH_SIGN`. If it moves on the wrong
  axis, change `GYRO_YAW_AXIS` or `GYRO_PITCH_AXIS`.
- **Everything is far too fast or slow.** Set `GYRO_IN_DEGREES = False` (radians per second).
- **Pitch snaps or drifts.** Fix `ACCEL_UP_AXIS`, `ACCEL_FWD_AXIS` and `ACCEL_PITCH_SIGN`.
- **Yaw drifts.** Expected, since only the gyroscope drives it. Restart to recenter. A magnetometer
  correction is not implemented.
- **"Pew" misfires or is missed.** Adjust `VOICE_HI` and `VOICE_LO`, or set
  `OVERBLASTER_VOICE_HI` and `OVERBLASTER_VOICE_LO`.
- **Crosshair jumps around.** Adjust `GAZE_MAX_SPREAD_PX` and `GAZE_MIN_SAMPLES`.

## The battery meter and the level

The HUD is a **battery meter** with the **level number** beside it: twenty slanted cells in two rows
of ten at the very top-left of the screen, lit in reading order as the battery drains, then a thin
divider and `LVL 3`. There is no percentage, no label and no level name; the cells are the reading.

- **Colour:** cyan normally, magenta when the battery is under 25%, gold once the Overlord chip has
  doubled it (with a gold `×2` badge under the grid). `LVL n` takes the same colour. A low battery
  beats the chip: a warning is a warning.
- **Motion:** the last lit cell pulses, and every lit cell flickers when the battery is low. It
  repaints only when a cell lights or goes dark, or the level or chip changes, or on that slow
  flicker, so most ticks cost nothing.
- **The level's name appears only when a level starts**, in the level-start splash (below). The
  number stays on the HUD. The names are `LEVEL_NAMES` in `config.py` (placeholders: Outer Rim,
  Asteroid Belt, Nebula Gate, Void Storm, Event Horizon, Deep Space); level 6 and beyond keep the last one.
- The score ends at x=535, just clear of the framework's home button.

## Title, between levels and level start

Three screens share the HUD's look (slanted cells, cyan, gold). Their geometry and timing are pure
Python in `screens.py`; `screenlayers.py` paints them with transparent, mouse-transparent widgets.

- **Title:** two rows of twenty cells pulse in opposite directions around the slanted OVERBLASTER
  wordmark, with the three how-to-play lines and a clipped-corner LAUNCH plate. LAUNCH is the
  framework's own dwell `Button` (look at it for 1.5 s) drawn inside that plate, with its dwell ring
  in the outline.
- **Between levels:** when a level clears, a plate says SECTOR CLEARED while the score counts up
  (1.3 s, ease-out), the NEXT level's number and name rise in, and the battery cells fill in one by
  one to the real charge. It stays up until you acknowledge it: say "Pew" (any loud sound) or press Space,
  once the count-up has finished (1.5 s), so a Pew from the last shot can't skip it. The words keep clear of the crosshair.
- **Level start:** a see-through plate with the level number in a cyan block and the name beside
  it. It is pinned to a spot in the sky 6.3 degrees above where you were looking, so you can turn
  your head and it slides out of the way. It fades in, holds for 6 s, and is gone after 6.8 s. It is made
  before the worlds, so they draw over it.

## The Overlord BMS power-up

The chip is the **Overlord BMS**, a real product of Overlord Labs, so finding it is meant to be
unmistakable (the OD mark is the favicon from overlord-labs.com, `assets/overlord_od.png`).

- **Holding it:** unlike a crystal (0.3 s), the chip needs your aim for `CHIP_HOLD_S` = 2.4 s. A gold
  ring fills around it with HOLD YOUR AIM ON THE CHIP under it. If your aim slips the ring turns pink
  and an arrow next to the crosshair points back at the chip; the hold drains at a fifth of the fill
  speed (`CHIP_HOLD_DRAIN`) and never resets, so a jittery head costs time, not the whole award.
- **Collected:** a ring bursts, ten sparks fly into the battery gauge, and a callout pops out of the
  gauge: OVERLORD BMS FOUND! / BATTERY MANAGEMENT, BUILT FROM THE SILICON UP. / NOW YOU GET 2× THE
  SHOTS. It stays five seconds, then folds into an OD medallion that stays beside the gauge for the run,
  with a gold OD ×2 badge under it. The battery is full and twice as big.
- **With the level clear:** collecting the chip often clears the level too, so the SECTOR CLEARED plate
  waits until the callout has finished.
- The chip sprite is drawn by `tools/make_chip_art.py` from the OD mark. Geometry and timings are in
  `bms.py` (tested); `bmslayer.py` only paints.

## Sound

Music, effects and a female voice, all played from files in `assets/audio/` (10 MB, 44.1 kHz mono 16-bit).

- **Music:** a calm title loop (8 bars) and a driving 16-bar game loop (A minor, 108 BPM, two sections,
  sidechain-pumped pad and bass). It sits low, and ducks while the voice speaks.
- **Effects:** a hit, a world exploding, a crystal chime, rising ticks while you hold the chip, the
  chip fanfare, level start, sector cleared, hull death, battery dead, a confirm, a low-battery
  warning. **There is no laser sound**: you are the laser, and a laser sound would come back through
  the microphone and fire again (`AUDIO_SHOT_SOUND`).
- **Voice:** every popup is spoken: the title, "Level three. Nebula Gate." (joined from three
  clips, so any level works), "Sector cleared.", "Say pew to continue.", "Overlord B M S detected.
  Hold your aim on the chip.", "Overlord B M S found. Two times the shots.", "Hull destroyed.",
  "Battery depleted.", "Battery low." (`voicelines.py`). The bubble's longer text stays on screen only.
- **The microphone hears the game.** Three things stop that from firing shots: the mic is muted
  while the voice speaks (so you cannot fire for the first few seconds of a level announcement);
  the `EchoGate` learns how much of the playback reaches the mic and subtracts it, so music and
  effects do not pull the trigger; and music stays quiet.
- **Quality:** 44.1 kHz; oscillators are band-limited (PolyBLEP, no aliasing fizz); filters are
  linear-phase FIRs; effects are layered (click, body, sub, debris) with a convolution reverb;
  `dsp.py` holds the building blocks. The voice model is the full-precision Kokoro (310 MB, not the
  smaller int8), kept at its native 24 kHz and resampled once.
- **Making the files:** `tools/make_audio.py` renders the music and effects from `synth.py` (numpy
  only). `tools/make_voice.py` renders the voice with Kokoro text-to-speech (female, American,
  `af_heart`; Apache 2.0 model) and `voicefx.py` (pauses inside a clip cut to 70 ms, B M S run together, rumble out, presence lift, compression, a light double and a small room); instructions are in its docstring. The game never
  needs Kokoro. Run with `OVERBLASTER_MUTE=1` for silence; the tests do.
- **On the glasses (not tested):** the framework's `Speaker` plays one WAV at a time, so the mix is
  sent in half-second chunks that overlap by 50 ms. Check on a device that the music has no gaps or
  doubling, that the Speaker accepts 22050 Hz mono, and that the echo gate keeps the mic quiet.
  If not, the chunk size and overlap are `CHUNK_S` and `CHUNK_OVERLAP_S` in `audiosink.py`.

## Finding things: the pointer arrows

The view is only 30° wide, so a blue arrow always points toward the **closest Rogue World** while
it is out of view. It is a full 360° pointer: it turns to face the world however it lies (up, down,
diagonally, or the shorter way round when it is behind you) and keeps turning as you move your head.
It sits on a ring around the middle of the view, clear of the HUD in the corners, and disappears
once the world is on screen. A **gold** arrow does the same for the closest crystal or chip.

## Shooting and getting hit

Each shot is a short animation drawn on one transparent overlay (`fxlayer.py`) with `QPainter`, so
there is no extra widget per effect and nothing repaints between shots:

- a **laser** from the ship's nose to the target (a wide glow, a brighter middle, a white-hot core)
  and a **muzzle flash**
- a **miss** leaves a small cyan ring where the laser landed
- a **hit** flashes the planet white and sends out a gold ring and sparks
- a **kill** is a bigger explosion: a flash, two shockwaves and debris, with the crystals spilling out

When a Rogue World reaches the ship the game is over at once: the view floods red, the planet
explodes where it struck, "HULL DESTROYED" shows for a second, and then the game-over screen says
what happened (a planet, or you ran out of energy). The shapes are pure functions of time
(`fx.py`), so they are unit-tested without Qt.

## Firing, planet toughness and energy

- **Fire rate:** 10 shots a second while the trigger is held (`SHOT_COOLDOWN_S` 0.1). The game ticks
  at 15 Hz (every 67 ms), so a plain cooldown would round up to every other tick (7.5 a second).
  The cooldown carries its leftover fraction from tick to tick, so it averages exactly 10 a second
  at any tick rate, with at most one shot per tick and no stored-up bursts after waiting.
- **The trigger is held, not clicked:** a sound louder than `VOICE_HI` pulls it, and it stays pulled
  while the level is above `VOICE_LO`. Nobody can say "pew" ten times a second, so continuous sound
  is continuous fire.
- **Planets take many hits:** 6 at level 1, one more each level (`WORLD_HP_BASE`,
  `WORLD_HP_PER_LEVEL`), and the chip carrier has 4 more. A hit barely pushes a world back
  (`KNOCKBACK` 0.0015); at 10 hits a second the old value would have flung it away instantly.
- **Energy:** a shot costs 1 unit of 100, a destroyed world drops 3 to 5 crystals worth 3 each. A
  player who lands most of their shots gains energy; one who wastes most of them runs dry.

## Balance

The view is only 30° wide, so a player spends real time turning their head to find targets. Any
world that reaches the ship ends the game, so every world has to be found and killed in time. Worlds
take `APPROACH_SECONDS` 100 to arrive at level 1 and get 12% faster each level (`APPROACH_SPEEDUP`).
Tougher planets take longer to kill, so the approach had to be slowed to match.

Two bugs came out of testing this and are covered by tests: the chip carrier now returns each level
until collected, and when the *last* world hit the ship the game used to call it "level clear"
(the field was empty), so the player seemed to win by being hit.

Simulated outcomes (80 games each, scripted players that must turn their head and hold the trigger):

| Player | Head turn | Hit rate | Loses before | Mostly loses to | Gets the chip | Median level |
|---|---|---|---|---|---|---|
| Casual | 60°/s | 70% | 10% (by level 5) | the hull | 100% | 6 |
| Average | 90°/s | 80% | 15% (by level 6) | the hull | 100% | 7 |
| Skilled | 120°/s | 90% | 100% (by level 12) | the hull | 100% | 8 |
| Poor | 40°/s | 40% | 96% (by level 5) | the battery (89%) | 21% | 3 |
| Spraying | 120°/s | 20% | 100% (by level 5) | the battery | 0% | 2 |

These are scripted players. Real players need a pass on the glasses, and `tests/test_balance.py`
will tell you if a retune breaks the curve.

## Art

The Rogue Worlds are the old Planet Zapper planet animations (`Android/planets`), flattened onto
black and packed into looping GIFs at three sizes by `tools/prep_assets.py` (about 2 MB total, down
from about 10 MB of source frames). The crystal and the chip are drawn by the same script.
