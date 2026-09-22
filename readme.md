# BAP — UAV Gripper Predictive Maintenance

**Final repo** for the MPFD thesis project: developing and validating a
deep-learning-based predictive-maintenance / fault-detection system for a
UAV-mounted robotic gripper, fusing UAV motor telemetry with gripper
sensor data. See [`ml/README.md`](ml/README.md) for the current state of
that work (data sources, open questions — the model itself hasn't been
built yet).

This repo consolidates what were previously two separate working repos:

- **`dronex_ws_dev`** — the real-hardware ROS2/PX4/VIO workspace (`src/`,
  `scripts/`, `utility/`, `Docs/`). Its full bring-up narrative is kept
  below as **Appendix A** — **written when the compute board was a Jetson
  Orin Nano; the project has since moved to a Raspberry Pi 5** (see the
  ⚠️ warning in [`Docs/setup.md`](Docs/setup.md)'s uXRCE-DDS section for
  what's still unreconciled between the two).
- **`NAP-MPFD`** — thesis notes and the [`gripper/`](gripper/) subsystem
  (ArmBot data logger + new web GUI, moved here from that repo's
  `armbot_gripper_logger/` folder).

## Hardware

Raspberry Pi 5, SSH'd into from a laptop, talking to:

- **Pixhawk 6C** (PX4 flight controller) — MAVLink over USB for GCS/param
  access, uXRCE-DDS over TELEM2 for VIO odometry (Appendix A §4 below,
  and [`Docs/setup.md`](Docs/setup.md)).
- **Arduino Nano** (JSumo ArmBot Control Board) — USB serial, drives the
  5-DOF gripper arm. See [`gripper/README.md`](gripper/README.md).

## Repo map

| Path | What |
|---|---|
| `src/` | ROS2 (Jazzy) colcon workspace — OpenVINS, `px4_msgs`, the PX4↔VIO bridge, camera bring-up |
| `gripper/` | ArmBot firmware, data logger, and the web-based manual jog GUI |
| `ml/` | Predictive-maintenance model work (scaffold only so far) |
| `Docs/` | `setup.md` (command cheat sheet), plus this file's Appendix A |
| `scripts/`, `utility/` | Bring-up/debug scripts, PX4's `mavlink_shell.py`, camera/IMU calibration ([`utility/calibration/README.md`](utility/calibration/README.md)) |

## Setup

Quick-reference commands: [`Docs/setup.md`](Docs/setup.md). Gripper setup
(firmware, logger, GUI): [`gripper/README.md`](gripper/README.md).

---

## Appendix A — Real-Hardware VIO/PX4 Bring-Up Log (historical, Jetson-era)

*Kept as-is from `dronex_ws_dev` — valuable bring-up detail and
methodology, but written for a Jetson Orin Nano; current hardware is a
Raspberry Pi 5 (see the hardware note above).*

Last updated: 2026-08-11, from a live shell on the target Jetson.

### Goal

Run the customized OpenVINS fork (`Roboticistprogrammer/dronex_ws`, `openvins` branch, plus
its `open_vins_ws` submodule) as VIO on a physical Intel RealSense D435, on this Jetson Orin
Nano, feeding pose into PX4 (Pixhawk 6C) for eventual position-mode flight. This workspace
(`drone_ws_dev`) is the **real-hardware** ROS2 workspace — separate from `dronex_ws`, which is
a **simulation-first** dev repo (Docker + Gazebo Harmonic + PX4 SITL) and stays that way.

### 1. Jetson snapshot

| | |
|---|---|
| Board | NVIDIA Jetson Orin Nano (Developer Kit Super), P-Number p3767-0005 |
| L4T / JetPack | R36.4.7 (JetPack 6.2-class) |
| OS | Ubuntu 22.04.5 LTS, kernel 5.15.148-tegra |
| CPU | 6 cores, power mode `MAXN_SUPER` (already active) |
| RAM | 7.4 GiB total, 3 GiB swap. Two sequential `-j1`/`-j2` colcon builds (OpenVINS, px4_msgs) both completed with no OOM. |
| Disk | 937 GB NVMe, 608 GB free |
| ROS2 | Humble, `/opt/ros/humble` |
| librealsense2 | 2.56.5 (apt) + `ros-humble-realsense2-camera` 4.58.2 |
| **Two OpenCV installs coexist** | JetPack's system OpenCV **4.8.0** (what `find_package(OpenCV)` picks up) *and* Ubuntu universe's OpenCV **4.5.4** contrib libs (pulled in transitively by ROS's `cv_bridge`). Root cause of the ArUco build issue in §2 — worth remembering for any future OpenCV-touching error on this box. |
| Pre-existing tools found mid-session | `MicroXRCEAgent` v2.4.3 was already built/installed (`/usr/local/bin`, plus source at `~/Apps/Micro-XRCE-DDS-Agent` and a separate `~/px4_ros_uxrce_dds_ws`) — missed in the initial bring-up survey, worth remembering to search more broadly (`find /home -iname ...`) before assuming a tool is missing. |
| Pre-existing services | `mavlink-router.service` + `mavlink-anywhere-dashboard.service`, installed/enabled — see §4.2 |

### 2. OpenVINS build: all 5 packages compile clean

`colcon build --executor sequential --parallel-workers 1` (MAKEFLAGS=-j1, sequential — 8GB
board, colcon+ceres compiles are memory-hungry) — **`Summary: 5 packages finished [37min
25s]`**, zero errors. `ov_core`, `ov_data`, `ov_eval`, `ov_init`, `ov_msckf` all registered,
`run_subscribe_msckf` (the real-sensor entry point) present.

- **Fixed:** `opencv2/aruco.hpp: No such file or directory` — JetPack's OpenCV 4.8.0 moved
  ArUco into the new `objdetect` module; OpenVINS's `TrackAruco.cpp` uses the old contrib API.
  Built with `-DENABLE_ARUCO_TAGS=OFF` (a toggle the fork already ships for exactly this) —
  we don't need fiducial-marker tracking for drone VIO anyway.
- **Watch item, unconfirmed:** `ov_msckf`'s link step warned about `cv_bridge` (built against
  Ubuntu's 4.5.4 OpenCV) coexisting with OpenVINS (linked against JetPack's 4.8.0). Build
  succeeded; first thing to suspect if `run_subscribe_msckf` crashes/garbles images specifically
  at the ROS↔OpenVINS image handoff once R4 actually runs it against live camera data.

### 3. RealSense D435 — now on USB3, confirmed clean

Started the session on USB2 (`480M`) — tested anyway rather than treating it as a blocker,
and got a clean 30Hz on both infra1/infra2 simultaneously with only a driver "reduced
performance expected" warning. Since then the camera was moved to the board's USB3 port
(`lsusb -t` now shows `5000M`, `rs-enumerate-devices` confirms `Usb Type Descriptor: 3.2`),
retested with the identical profile (640x480@30, both infrared streams): same clean
**30.0 Hz on both streams**, and the "reduced performance" warning is gone. USB3 headroom is
now available for future needs (depth, higher resolution) but wasn't actually required to hit
this profile.

### 4. Flight controller link (Pixhawk 6C)

#### 4.1 Two protocols, two links

| Job | Protocol | Status |
|---|---|---|
| Ground-station visual awareness (QGC) | MAVLink | ✅ Live, solid all session |
| VIO odometry injection (OpenVINS ↔ PX4 EKF2) | uXRCE-DDS | ⚠️ Proven working at least once; physically intermittent — see §4.3 |

PX4 needs a separate serial port instance per protocol, so this always meant two physical
links: **USB-C → MAVLink** (GCS), **TELEM2/3 → Jetson header UART → uXRCE-DDS** (VIO).

#### 4.2 MAVLink / laptop visual awareness — solid

Pixhawk 6C on USB (`/dev/ttyACM0`, `/dev/serial/by-id/usb-Auterion_PX4_FMU_v6C.x_0-if00`,
921600 baud). `mavlink-router` picked it up cleanly. Reach it from QGroundControl via UDP
`<jetson-ip>:14550` or TCP `<jetson-ip>:5760` (get current IP with `hostname -I` — it's
DHCP-assigned and can change). This link stayed solid through every reboot/power-cycle done
today and was also used throughout as a diagnostic channel — `pymavlink` scripts read/wrote
PX4 parameters and even opened a live NuttX shell over it (MAVLink's `SERIAL_CONTROL`
message, `SERIAL_CONTROL_DEV_SHELL`) for direct `dmesg`/module-status access without needing
QGroundControl.

#### 4.3 uXRCE-DDS / OpenVINS↔PX4 link — working, confirmed with real data

**Long troubleshooting arc, condensed.** TELEM2 initially produced zero bytes despite every
config check passing. Systematically ruled out, in order: PX4 param encoding (a real bug hit
twice — MAVLink's `PARAM_SET`/`PARAM_VALUE` carry INT32 params as float32-bit-reinterpreted,
not a plain float cast), FC-side connector pin order (was backwards, fixed), baud rate (swept
57600–921600, plus 3M per one reference), the Jetson's `nvgetty` serial-console service (found
and disabled), GND wiring, and a full loopback test (jumper across Jetson header pins 8/10)
that proved the Jetson's UART1 hardware was 100% good. Also tried TELEM3 as a fully separate
port/cable/config — same symptom.

**Two real, distinct root causes, found in sequence:**

1. **Wrong port mentally mapped.** What was assumed to be "TELEM2" during much of the
   debugging didn't actually correspond to the physical TELEM2 connector — confirmed via
   PX4's own `dmesg` (`Starting UXRCE-DDS Client on /dev/ttyS3`) and PX4's
   `Tools/serial/generate_config.py` source (TELEM1=101, TELEM2=102, TELEM3=103 — fixed,
   global across all boards, not guessed). Once the physical cable and `UXRCE_DDS_CFG`
   value actually agreed on the same port, real sessions started forming.
2. **CPU contention on the FC itself.** Even with the right port, the session would connect
   then drop after tens of seconds. Root cause: PX4's default USB MAVLink stream (high-rate,
   auto-started via `SYS_USB_AUTO`) was competing for FC-side CPU/scheduling time against the
   timing-sensitive uXRCE-DDS timesync handshake. Setting **`SYS_USB_AUTO=0`** + FC reboot
   fixed it — sessions now establish and stay up.

**Trade-off:** `SYS_USB_AUTO=0` also disables MAVLink over USB, so QGroundControl can no
longer reach the FC that way (§4.2's UDP/TCP method is dead until this is revisited). Not
urgent, but needs a follow-up — likely a lower-rate MAVLink instance on a different port, or
toggling `SYS_USB_AUTO` back only when the DDS agent isn't running.

**Confirmed working, with real data**, not just a session handshake:
- `uxrce_dds_client status` on PX4's shell: `time sync converge[d]` (first time all session),
  `rt/fmu/out/...` data writers created cleanly.
- `ros2 topic hz /fmu/out/sensor_combined`: **~100 Hz sustained**.
- The bridge node (§5) republishing it as `/d435i/imu` at the same ~100 Hz, with physically
  correct values at rest: `linear_acceleration.z ≈ -9.84 m/s²` (gravity, correct sign for
  PX4's FRD/Z-down convention), angular velocity near-zero on all axes.

Current PX4 config (confirmed, TELEM2 active): `UXRCE_DDS_CFG=102`, `SER_TEL2_BAUD=921600`,
`SYS_USB_AUTO=0`, `MAV_1_CONFIG=0`, `MAV_2_CONFIG=0`.

`utility/mavlink_shell.py` — PX4's own official Tools/mavlink_shell.py (v1.16.0, unmodified,
downloaded not hand-written) — gives an interactive NuttX shell over any MAVLink-carrying
serial link: `./utility/mavlink_shell.py /dev/ttyTHS1 --baudrate 57600`. Same interface used
programmatically throughout this debugging arc via MAVLink's `SERIAL_CONTROL` message.

### 5. px4_msgs + the VIO↔PX4 bridge node — both built and working

Cloned `PX4/px4_msgs` at `release/1.16` (matches this FC's firmware exactly — confirmed via
`AUTOPILOT_VERSION` over MAVLink: PX4 v1.16.0) into `src/px4_msgs`, `colcon build
--packages-select px4_msgs`: **13m26s, success**, 227 message types registered.

`src/dronex_px4_bridge` (`vio_px4_bridge` node, Python/`ament_python`) bridges both
directions:

- **`/fmu/out/sensor_combined` → `/d435i/imu`** (`sensor_msgs/Imu`) — confirmed live at ~100Hz
  with physically correct values (§4.3). PX4's raw FRD body-frame gyro/accel passed through
  *unconverted* — R2's Kalibr calibration will be run against this exact native frame rather
  than introduce an extra unverified manual conversion.
- **`/ov_msckf/odomimu` → `/fmu/in/vehicle_visual_odometry`** (`px4_msgs/VehicleOdometry`) —
  code complete, not yet live-testable (needs OpenVINS actually running, that's R4). Handles:
  - **QoS**: PX4's `/fmu/*` topics are `BEST_EFFORT` — a subscriber left on ROS2's default
    `RELIABLE` QoS fails to match and silently receives nothing. Explicit `BEST_EFFORT` QoS
    used on both the sensor_combined subscription and the outgoing odometry publisher.
  - **Frame conversion**: world frame only (OpenVINS's gravity-aligned, arbitrary-heading
    world → PX4's NED), via the standard MAVROS/PX4-ecosystem static rotation quaternion. No
    body-frame (FLU→FRD) conversion needed — since the IMU feed above is left in native FRD,
    OpenVINS's own body-frame outputs come out already FRD-native.
  - **Quaternion field order**: PX4 arrays are scalar-first (`q[0]=w`), verified against PX4
    v1.16.0 source (`matrix/Quaternion.hpp`), not ROS's scalar-last convention.
  - Flagged with a `TODO(R4)` in the code: the orientation conversion is the one piece of
    this bridge that's easy to get subtly wrong and hard to verify without real motion —
    check it against known bench-rig movement once OpenVINS is live.

### 6. Key architecture fact carried over from the sim design

**The real D435 (non-`i`) has no onboard IMU at all.** `dronex_ws`'s own `bridge.yaml` already
made this choice deliberately in sim, sourcing IMU from PX4 rather than the camera. On real
hardware this is now concretely how it has to work: **OpenVINS's IMU input comes from PX4**
(via uXRCE-DDS, `/fmu/out/vehicle_imu`), time-synchronized with the D435's infra1/infra2
frames. Camera↔FC-IMU extrinsics are part of R2's calibration deliverable.

Topic naming worth mirroring from the sim bridge for config/tooling continuity:
`/d435i/infra1/image_raw`, `/d435i/infra2/image_raw` (+ `camera_info`) — real launch comes
from `realsense2_camera` directly (topics currently land at
`/camera/camera/infra{1,2}/image_rect_raw` by default — remap in R1's launch file).

### 7. Workspace layout

*As of this section being written (still `dronex_ws_dev`, pre-consolidation).
For where these pieces actually live now, see the repo map at the top of
this file — this workspace's `src/`/`scripts/`/`utility/`/`Docs/` moved
into `BAP/` as-is, `dronex_wms_bridge` was dropped (WMS integration is out
of scope for BAP), and `gripper/` + `ml/` were added alongside it.*

```
drone_ws_dev/                     # git repo: Dronex-Delivery-Solutions/dronex_ws_dev, branch main
├── readme.md                     # this file
├── utility/mavlink_shell.py       # PX4's official Tools/mavlink_shell.py, unmodified (§4.3)
├── build/ install/ log/           # colcon artifacts (gitignored)
├── src/
│   ├── open_vins/                 # builds clean (§2); ov_data/ (~380MB benchmark data) gitignored
│   ├── px4_msgs/                  # release/1.16, builds clean (§5)
│   ├── dronex_vio_bringup/        # our own launch files; d435_infra.launch.py is R1's deliverable
│   └── dronex_px4_bridge/         # vio_px4_bridge node, builds + runs clean (§5)
└── dronex_ws_sim_reference/       # dronex_ws (openvins branch), COLCON_IGNORE'd, gitignored —
    └── ...                        #   reference only, sim-first dev repo, not part of this build
```

### 8. Practical plan

✅ = confirmed, ⚠️ = open item, ⬜ = untouched:

| Phase | Goal | Status |
|---|---|---|
| **R0 — Jetson bring-up** | Toolchain builds; RealSense enumerates | ✅ Done |
| **R1 — Camera streaming** | D435 infra1/infra2 as ROS2 topics, usable rate | ✅ Done. `dronex_vio_bringup/launch/d435_infra.launch.py` — 30Hz confirmed on both streams via the actual launch file, topics land at `/d435i/infra{1,2}/image_rect_raw` (§6 naming). |
| **R2 — Calibration** | Real intrinsics + D435↔FC-IMU extrinsics + Allan-variance IMU noise from PX4's IMU | ⬜ Not started, but unblocked — reliable IMU data now flowing (§4.3). Tooling ready: [`utility/calibration/README.md`](utility/calibration/README.md) (screen-displayed AprilGrid + Kalibr workflow) — still need the IMU noise params (Allan variance) as a separate input. |
| **R3 — PX4 link** | Micro-XRCE-DDS-Agent + `px4_msgs`, bidirectional | ✅ Done. Two real root causes found and fixed (wrong port, then FC-side CPU contention — §4.3), sustained ~100Hz IMU data confirmed with physically correct values, bridge node built and verified for the IMU direction. Odometry-out direction is code-complete, live-verification is R4's job. ⚠️ QGC/USB MAVLink is now unavailable as a side effect (§4.1) — needs a follow-up decision. |
| **R4 — Bench VIO validation** | `config/jetson_d435` + recorded bag, `/ov_msckf/odomimu` plausible | ⬜ Depends on R2–R3 |
| **R5 — Ground rig test** | Full stack live on airframe, props off | ⬜ |
| **R6 — Supervised first hover** | Tethered/supervised, safety pilot fallback | ⬜ |
| **R7 — Field validation** | Untethered, VIO-aided vs GPS-only, occlusion failsafe test | ⬜ |

### 9. Immediate next actions

1. ~~Make TELEM2/3↔Jetson connection reliable~~ — done. Real root causes were a port
   mental-mapping mismatch and FC-side CPU contention (`SYS_USB_AUTO`), not the wiring itself.
2. ~~Write the R1 launch file~~ — done, `dronex_vio_bringup/launch/d435_infra.launch.py`.
3. ~~Write the VIO↔PX4 bridge node~~ — done, `dronex_px4_bridge`, IMU direction verified live.
4. **Decide on QGC/ground-station access** now that `SYS_USB_AUTO=0` killed the USB MAVLink
   path (§4.1) — options: a lower-rate MAVLink instance on a spare port, or only flipping
   `SYS_USB_AUTO` back on when the DDS agent isn't running.
5. Start R2 calibration (Kalibr against D435 + PX4 IMU) — no longer blocked,
   tooling in [`utility/calibration/`](utility/calibration/README.md). Its
   README's §0 has a to-do: confirm the D435's IR cameras can actually see
   a screen-displayed target before trusting that method over printing.
6. Hold off on `EKF2_EV_CTRL` / `EKF2_HGT_REF` (vision-fusion estimator params) until R4 — these
   affect real flight behavior and shouldn't be set before the VIO pipeline itself is validated.
7. Keep an eye on the dual-OpenCV linker warning (§2) the first time `run_subscribe_msckf` runs
   against live camera data.
8. R4 (bench VIO validation): actually run OpenVINS against live D435 + `/d435i/imu`, confirm
   `/ov_msckf/odomimu` is plausible, then live-verify the bridge's odometry-out direction
   (watch that `TODO(R4)` orientation-conversion note in `vio_px4_bridge_node.py`).

### 10. Repo separation — done

> **Superseded by the BAP consolidation.** This section documents
> `dronex_ws_dev`'s own git history, which is *not* carried into BAP — BAP
> started with a fresh git history pointed at
> `https://github.com/Roboticistprogrammer/NAP-MPFD.git` instead (not yet
> pushed). Kept below for the record of how `dronex_ws_dev` itself was
> originally split off.

`drone_ws_dev` is its own git repo, decoupled from `dronex_ws` (sim-heavy):

- Remote: `https://github.com/Dronex-Delivery-Solutions/dronex_ws_dev.git`, branch `main`.
- Commits: `ed9b416` (initial: OpenVINS vendored, ArUco disabled, workspace bring-up),
  `89290fa` (readme: Pixhawk connection + link-split documentation). `px4_msgs` (§5) and this
  update not yet committed — do that next.
- `src/open_vins`'s own `.git` was removed and vendored flat (not a submodule, per your call).
  Upstream history stays intact at `Roboticistprogrammer/open_vins_ws` for reference.
- `src/open_vins/ov_data/` (~380MB benchmark datasets, irrelevant to real-hardware flight) and
  `dronex_ws_sim_reference/` are both `.gitignore`'d — kept locally, not pushed.
- Two GitHub PATs used today (cloning `dronex_ws`, pushing here) were both used transiently via
  auth header, never written to disk — worth rotating both since they were pasted in chat.

### 11. Notes on today's session

- This board has a history of frequent reboots going back months (checked `last -x` /
  `/var/log/syslog` while investigating one mid-session) — none from today's session
  correlated with anything done here (clean compiler exits, no OOM-kill/panic messages).
  Worth watching if it recurs, not treated as session-caused.
- `dronex_ws`'s sim stack (Docker/Gazebo/PX4 SITL) is a separate effort on a different host —
  M0–M2 done there, M3 stalled on that host's Docker OOM-crash. Orthogonal to this track.
