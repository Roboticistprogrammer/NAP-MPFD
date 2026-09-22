# ArmBot Gripper — Logging & Control

Bench-top data logging and manual-control toolchain for the CODLAI ArmBot
(Arduino-based, 5-DOF) mounted as BAP's UAV gripper, as a first step toward
the predictive-maintenance / fault-diagnosis pipeline (see [`../ml/README.md`](../ml/README.md)
for where this data eventually feeds).

This is a **Tier-1 (open-loop) logger**: it records the *commanded* servo
angle at each axis — derived from the control board's potentiometers —
together with a derived grip state, timestamped and streamed over USB
serial. It does not assume closed-loop position feedback, since the stock
9 g servos on this kit are standard RC servos without a feedback line.

---

## Repository Structure

```
gripper/
├── firmware/
│   ├── armbot_logger.ino          # Arduino sketch (upload via Arduino IDE / USB)
│   └── tools/
│       └── identify_axes/
│           └── identify_axes.ino # One-time hardware test, see §1 (already run)
├── logger/
│   └── log_session.py        # Python host-side logger — dataset capture (pyserial)
├── gui/
│   └── app.py                # Local web GUI — manual angle jogging (Flask + pyserial)
├── data/                      # Logged trial CSVs (Tier-1 dataset)
├── programs/                   # Taught/replayable motion programs
└── README.md
```

---

## 1. Hardware Assumptions — Verify Before Use

`POT_PINS` / `SERVO_PINS` / button pins in `firmware/armbot_logger.ino` are
confirmed against this specific JSumo ArmBot Control Board (see
`Armbot_control_board.jpeg`) — no need to re-derive those. Axis identity is
also confirmed, via `firmware/tools/identify_axes.ino`:

| Slot | `AXIS_NAMES` | Notes |
|---|---|---|
| 1 | `base` | |
| 2 | `shoulder` | |
| 3 | `elbow` | |
| 4 | `gripper` | `GRIPPER_AXIS = 3` |
| 5 | `unused` | Wired on the board, no servo physically attached on this arm — streams a value with no physical meaning |

**Gripper kinematics** — also confirmed by hand-jogging: this gripper is
*not* a simple one-directional jaw servo. It's **open at both travel
extremes** (~0° and ~180°) and **fully closed at the midpoint** (~96°),
consistent with a linkage-driven mechanism. `grip_state` in the firmware
is derived from distance-from-center (`GRIPPER_CLOSE_CENTER_DEG = 96`),
not a low/high split. `GRIPPER_CLOSE_TOL_DEG` / `GRIPPER_OPEN_MARGIN_DEG`
are reasonable starting estimates — refine them if `grip_state` doesn't
track a real grasp cleanly once you're running trials.

**Tier 1 vs. Tier 2:** the values logged here are *commanded* angles, not
measured joint positions — the Nano only knows what angle it told the
servo to reach, not what angle the joint actually achieved. This is
sufficient for an initial normal-operation baseline. If you later add
feedback-capable servos or an inline current sensor (e.g. ACS712) on the
servo power rail, extend the schema below with the additional Tier 2
columns rather than replacing it.

---

## 2. Setup

### Arduino firmware

1. Open `firmware/armbot_logger.ino` in the Arduino IDE.
2. Select the correct board (Arduino Nano) and port.
3. Verify pin/threshold constants as described above.
4. Upload via USB.
5. Optional sanity check: open the Serial Monitor at 115200 baud — you
   should see a `#`-prefixed header line, followed by continuous CSV
   lines updating as you turn the potentiometers.

### Python environment

One shared venv for everything under `gripper/` (the logger and the GUI
have near-identical, lightweight dependencies and are never run at the
same time — see `requirements.txt`). `ml/` has its own separate venv +
`requirements.txt`, since its dependencies are a different, heavier
stack unrelated to serial/Flask.

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 logger/log_session.py --port /dev/ttyUSB0 --out data --programs programs
```

---

## 3. Web GUI — Manual Angle Jogging

A local web app for jogging each axis by hand from a browser — useful for
positioning the arm, sanity-checking a range of motion, or driving the
gripper without needing to physically turn the board's potentiometers.
Talks to the *same* `armbot_logger.ino` firmware and protocol as the
logger above (no firmware changes needed), so don't run the GUI and
`log_session.py` against the same serial port at the same time.

```bash
source venv/bin/activate      # the same venv from §2 — nothing extra to install
python3 gui/app.py --port /dev/ttyUSB0
```

Then, from your laptop's browser (SSH'd into the RPi5, so no X11
forwarding needed): `http://<rpi-ip>:5000`.

The page mirrors the control board: one slider per axis (base, shoulder,
elbow, gripper; the unused 5th slot is shown disabled, matching §1), live
grip-state/mode readouts, and Record/Start button indicators. Sliders
start out **disabled and mirroring the live potentiometer positions** —
click **Enable Playback Control** to take over (this seeds the sliders
from whatever the arm's current pose is, so control never jumps the arm),
and **Release to Manual** to hand it back to the pots. Physically pressing
**Record** on the board aborts playback immediately either way (same
firmware-level kill switch used by Replay, §4).

---

## 4. Usage

With the Arduino connected and the firmware uploaded:

```bash
python logger/log_session.py --port /dev/ttyUSB0 --out data --programs programs
```

(Use the appropriate `COMx` port on Windows.)

On start, you'll get a menu:

```
1) Manual trial (Enter to start/stop)
2) Teach a new procedure (Start/Record buttons)
3) Replay a saved procedure
4) Quit
```

**1) Manual trial** — the original flow: pick an object/scenario/condition
label, press Enter to start capturing, jog the arm by hand, press Enter
again to stop. Written straight to a per-trial CSV.

**2) Teach / 3) Replay** — see §5 below.

Trial output files are named automatically:

```
{condition_label}_{scenario_id}_{object_id}_trial{NN}.csv
```

e.g. `normal_SC02_OBJ-C_trial07.csv`

---

## 5. Teach & Replay

For a repeatable scenario (e.g. grip a paper cup, move it a bit, return it
to its starting position), teach the motion once and replay it against
each object rather than re-jogging it by hand every trial:

1. **Teach** (menu option 2): position the arm at the motion's starting
   pose, press the board's **Start** button (`D13`/`A1` — see
   `Armbot_control_board.jpeg`) — this marks the start pose and begins
   sampling. Perform the maneuver by hand via the pots. Press **Record**
   to stop; you'll be prompted for a program name and it's saved to
   `programs/<name>.csv` (a sequence of relative timestamps + joint
   angles, not a trial CSV).
2. **Replay** (menu option 3): pick a saved program, then the usual
   object/scenario/condition prompts. The firmware switches into playback
   mode and drives the servos through the recorded angles itself — the
   pots are ignored for the duration. The run is logged as a normal trial
   CSV, so you get one dataset row set per replay, per object.
3. **Safety**: pressing **Record** on the board at any point during replay
   immediately aborts playback and returns the arm to manual (pot) control
   — a physical kill switch if the arm is about to do something unwanted.
   The partial run up to that point is still saved.

---

## 6. CSV Schema

Each row is one timestamped sample across all five axes (wide format —
convenient for direct use as a multivariate time-series input later,
without needing to pivot a long-format log):

| Column | Description |
|---|---|
| `host_timestamp` | PC-side wall-clock time (ISO 8601, ms resolution) at receipt |
| `device_t_us` | Arduino `micros()` value at the time of sampling (monotonic, wraps ~every 70 min — keep trials well under that) |
| `trial_id` | Auto-incrementing ID, unique per trial |
| `object_id` | See object reference table below |
| `scenario_id` | See scenario reference table below |
| `condition_label` | `normal` by default; fault-condition sessions get a `fault_*` label |
| `base_deg`, `shoulder_deg`, `elbow_deg`, `gripper_deg`, `unused_deg` | Commanded angle per axis (degrees). `unused_deg` has no physical meaning — see §1 |
| `grip_state` | `open` / `closing` / `closed` / `opening` / `holding`, derived from the gripper axis |
| `notes` | Empty by default; fill in manually post-hoc (e.g. "object slipped at ~2.1s") |

`programs/<name>.csv` (from Teach, §5) uses a different, simpler schema:
`t_ms` (time relative to the taught start pose) + the same axis columns +
`grip_state` — it's a motion template, not a labeled dataset trial.

---

## 7. Object Reference

| ID | Object | Approx. weight | Property tested |
|---|---|---|---|
| OBJ-A | Small rigid cube | ~20–30 g | Low-load rigid baseline |
| OBJ-B | Medium rigid cylinder | ~80–100 g | Mid-load rigid |
| OBJ-C | Near-limit rigid block | ~180–200 g | Upper-load boundary (near the 200 g rated max) |
| OBJ-D | Compliant object (foam/sponge) | ~30–50 g | Deformable grasp |
| OBJ-E | Smooth/slippery item (plastic bottle) | ~50–80 g | Low-friction surface, slip risk |
| OBJ-F | Fragile/light item (paper cup) | ~5–10 g | Over-grip sensitivity |

## 8. Scenario Reference

| ID | Scenario | Description |
|---|---|---|
| SC-01 | Repeated-cycle endurance | Same object, N consecutive grasp cycles |


All scenarios above are intended as **normal-condition** baselines for
this first data-collection pass. Fault-condition variants (mechanical /
electrical / software / environmental, per the thesis fault taxonomy)
are layered on as a second labeling pass using the same objects and
scenarios, distinguished by `condition_label`.

---

## 9. Known Limitations & Next Steps

- **No closed-loop feedback**: `*_deg` columns are commanded, not
  measured, positions. A failed grasp despite a "correct" command is
  itself a candidate fault signature, not a logging error.
- **Manual (Teach) trials still depend on the operator**: replayed trials
  reproduce the taught motion exactly, but the original teach demo's
  timing/repeatability is only as good as how it was performed; note
  significant deviations in the `notes` column.
- **USB-tethered**: appropriate for bench-top data collection. Once
  testing moves to an untethered/in-flight context, this logger's
  serial-reading logic can be re-wrapped as a ROS 2 (`rclpy`) node with
  minimal changes, or the firmware extended to log to an onboard SD card.
- **Trial-based file naming** (one CSV per trial) is deliberate — it
  supports trial-based dataset splitting later, avoiding the temporal
  leakage that random point-wise splitting would introduce.
