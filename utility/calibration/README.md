# Camera/IMU Calibration — Screen-Displayed AprilGrid

Generates an AprilGrid calibration target (tag36h11, Kalibr's format) sized
to a *physically verified* scale, for display on a screen instead of
printing — then walks through recording a calibration bag and running Kalibr
against it. This is R2 from `readme.md` Appendix A — still not done, and
what's most likely behind the feature-tracking problems mentioned when
running the msckf smoke test (it was using `config/rs_d455/` — calibration
for a *different physical camera*, in mono — as a stand-in; see that
conversation for the full diagnosis).

---

## 0. Before anything else: verify IR visibility on the D435

`d435i`'s infra1/infra2 cameras are near-IR (~850nm), not RGB. Whether an
LCD screen's "black" vs "white" pixels produce enough near-IR contrast for
that sensor to actually see the tag is **not something I could confirm one
way or the other** — LCD panels aren't designed or specified for IR
contrast, only visible. Check this before relying on the method:

```bash
# Disable the D435's IR projector -- it would otherwise wash out a flat
# target with its own dot pattern (meant for textured 3D surfaces, not this).
ros2 param set /d435i depth_module.emitter_enabled 0
```

Then look at the live infra1 feed while pointing the camera at your screen
showing full-white, then full-black. Easiest given this project's existing
tooling: `../../scripts/start_foxglove_bridge.bash` on the RPi5, then in
Foxglove Studio on your laptop subscribe to `/d435i/infra1/image_rect_raw`.
(Alternative if you'd rather not use Foxglove: `ros2 run rqt_image_view
rqt_image_view` over `ssh -X`, picking that same topic.)

**If there's no usable contrast**, don't force it — print instead. The same
`generate_target.py grid` command below works for printing too: pass your
printer's DPI as `--ppi` and a canvas sized to your paper at that DPI (e.g.
A4 @ 300dpi = `--screen-width-px 2481 --screen-height-px 3508`) instead of
your screen's resolution.

---

## 1. Setup

```bash
cd utility/calibration
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Own venv, separate from `gripper/`'s and `ml/`'s — different, unrelated
dependencies (OpenCV/numpy for target generation, nothing to do with
serial or Flask).

## 2. Measure your screen's true PPI

Don't trust the OS's reported DPI or a printer/browser's assumed 96px/inch
— both are frequently wrong and would silently give you the wrong metric
scale for the *entire* calibration. Measure it directly instead.

Find your screen's actual pixel resolution first (`xrandr | grep '*'` on
Linux, or your OS's display settings), then:

```bash
python3 generate_target.py ruler --screen-width-px 1920 --screen-height-px 1080 --out ruler.png
```

Open `ruler.png` and display it **fullscreen at 100% zoom — no "fit to
screen" or "scale to window"**, or the measurement (and everything
downstream) is wrong. Measure the printed line's physical width with an
actual ruler, in mm.

## 3. Generate the target

```bash
python3 generate_target.py grid \
  --screen-width-px 1920 --screen-height-px 1080 \
  --measured-mm <your ruler measurement> --reference-px 1000 \
  --tag-size-mm 30 --rows 6 --cols 6 \
  --out target.png --out-yaml target.yaml
```

Adjust `--tag-size-mm`/`--rows`/`--cols` if it errors that the grid doesn't
fit your screen. Outputs:

- `target.png` — display fullscreen at 100% zoom (same caveat as the ruler).
- `target.yaml` — Kalibr's AprilGrid target config; keep it, you'll pass it
  to Kalibr directly.

**Sanity-check before recording a full session**: point the actual camera
at the displayed grid and confirm the corners look sharp, evenly lit, and
glare-free (angle the screen/lights if there's reflection). Tag IDs are
assigned row-major from the top-left (id 0) — this matched Kalibr's own
detector in local testing (`detectMarkers` recovered all 36 ids from a
generated 6x6 grid) but worth a quick look before trusting it on new
hardware.

## 4. Record a calibration bag (on the RPi5)

Wave/rotate the target through the full field of view, varying distance,
with enough rotation to excite the IMU (Kalibr's IMU-camera step needs
that, not just translation):

```bash
ros2 bag record /d435i/infra1/image_rect_raw /d435i/infra2/image_rect_raw /d435i/imu -o calib_bag
```

## 5. Run Kalibr — on your laptop (x86_64), not the RPi5

Kalibr is a ROS1 tool; installing it natively on ROS2 Jazzy/arm64 is more
trouble than it's worth. Use the official
[`ethz-asl/kalibr` Docker image](https://github.com/ethz-asl/kalibr) on
your laptop instead, against a copy of `calib_bag`.

**Bag format**: `ros2 bag record` writes a ROS2 bag; Kalibr expects ROS1
`.bag`. Convert it first:

```bash
pip install rosbags
rosbags-convert --src calib_bag --dst calib_bag.bag
```

Then, inside the Kalibr container:

```bash
kalibr_calibrate_cameras --target target.yaml --bag calib_bag.bag \
  --models pinhole-radtan pinhole-radtan \
  --topics /d435i/infra1/image_rect_raw /d435i/infra2/image_rect_raw

kalibr_calibrate_imu_camera --target target.yaml --bag calib_bag.bag \
  --cam camchain-*.yaml --imu imu.yaml
```

`imu.yaml` is IMU noise-density/random-walk parameters — Kalibr needs real
ones (Allan-variance derived, ideally from PX4's IMU on this rig; this is
also still-open R2 scope per `readme.md` Appendix A §1) rather than a
guess, or the IMU-camera calibration output won't mean much.

## 6. Wire the result into OpenVINS

Drop the resulting `camchain-imucam-*.yaml` into
`src/open_vins/config/<name>/kalibr_imucam_chain.yaml`, and write a matching
`estimator_config.yaml` (copy `config/rs_d455/estimator_config.yaml` as a
starting point, but set **`max_cameras: 2`** — the rs_d455 stand-in was
mono, which is part of why tracking looked broken against this stereo
rig). Then rerun R4 (bench validation): launch OpenVINS live against
`/d435i/infra{1,2}` + `/d435i/imu`, confirm `/ov_msckf/odomimu` looks
plausible before touching a flight.
