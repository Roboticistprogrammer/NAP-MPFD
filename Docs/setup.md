# Quick Reference — BAP

Commands for debugging/checking up on this workspace, day to day. For the full narrative
(what's done, what's pending, why decisions were made) see [`readme.md`](../readme.md) at the
workspace root — this file is just the copy-pasteable cheat sheet.

## Workspace sourcing

Needed before any `ros2`/`colcon` command in a fresh shell:

```bash
source /opt/ros/jazzy/setup.bash
source ~/workspaces/BAP/install/setup.bash
```

## RealSense D435 (infra1/infra2, R1)

```bash
ros2 launch dronex_vio_bringup d435_infra.launch.py
# override resolution/rate if needed, default is 640x480x30:
ros2 launch dronex_vio_bringup d435_infra.launch.py d435_infra_profile:=640x480x15
```

Check it's actually streaming:

```bash
ros2 topic list | grep d435i
ros2 topic hz /d435i/infra1/image_rect_raw
ros2 topic hz /d435i/infra2/image_rect_raw
```

Expect a clean **30 Hz** on both, std dev well under 1ms. Topics land flat under
`/d435i/...` (not the driver's default `/camera/camera/...` nesting) to match
`dronex_ws`'s sim bridge naming.

## MAVLink (Pixhawk 6C, GCS/laptop link — via USB)

Already running as a systemd service, nothing to start manually:

```bash
systemctl status mavlink-router.service
sudo systemctl restart mavlink-router.service   # if it ever needs a kick
```

From your laptop's QGroundControl: **UDP** to `<jetson-ip>:14550`, or **TCP** to
`<jetson-ip>:5760`. Get the Jetson's current IP (it's DHCP, can change):

```bash
hostname -I
```

## uXRCE-DDS Agent (Pixhawk 6C, VIO link — via TELEM2)

> ⚠️ **Unreconciled since the Jetson → RPi5 move**: this section's device path
> (`/dev/ttyTHS1`) and the `nvgetty` gotcha below are both Jetson-specific.
> `scripts/smoke-test.bash` uses `/dev/ttyAMA0` for the current RPi5 setup —
> confirm the right device/gotchas for TELEM2 on the RPi5 and update this
> section accordingly.

Start (Jetson-era, needs RPi5 confirmation — see warning above):

```bash
sudo MicroXRCEAgent serial --dev /dev/ttyTHS1 -b 921600
```

Stop:

```bash
sudo pkill -f MicroXRCEAgent
```

Once a session is up, check for PX4 topics on the ROS2 side:

```bash
ros2 topic list | grep fmu
ros2 topic hz /fmu/out/vehicle_imu
```

A healthy startup log looks like this — `create_client` → `establish_session` →
`create_participant` → repeated `create_topic`/`create_subscriber`/`create_datareader`:

```
info | Root.cpp           | create_client      | create              | client_key: 0x00000001, session_id: 0x81
info | SessionManager.hpp | establish_session   | session established | client_key: 0x00000001, address: 1
info | ProxyClient.cpp    | create_participant  | participant created | client_key: 0x00000001, participant_id: 0x001(1)
info | ProxyClient.cpp    | create_topic        | topic created       | ...
```

If it just sits at `logger setup | verbose_level: 4` with nothing after — PX4 either isn't
configured to talk on that port yet, or the connection just isn't up right now. Wait ~15s
(PX4's client retries on its own cycle) before assuming something's wrong.

**Current known-good PX4 config** (query/set via the param scripts below if these ever look
different):

| Param | Value | Meaning |
|---|---|---|
| `UXRCE_DDS_CFG` | `102` | TELEM2 |
| `SER_TEL2_BAUD` | `921600` | matches the Agent's `-b` above |
| `MAV_1_CONFIG` | `0` | disabled (no radio on TELEM1) |
| `MAV_2_CONFIG` | `0` | disabled (TELEM2 is DDS, not MAVLink) |

## PX4 param read/set over MAVLink (no QGroundControl needed)

Useful for checking/fixing config from the Jetson directly. **Gotcha:** MAVLink's
`PARAM_SET`/`PARAM_VALUE` carry INT32 params bit-reinterpreted as float32, not as a plain
float cast — the helpers below handle that correctly; don't skip it if writing your own.

```python
from pymavlink import mavutil
import time, struct

m = mavutil.mavlink_connection('tcp:127.0.0.1:5760')
m.wait_heartbeat(timeout=10)

def read_int(name):
    m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
    deadline = time.time() + 8
    while time.time() < deadline:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and msg.param_id.rstrip('\x00') == name:
            return struct.unpack('<i', struct.pack('<f', msg.param_value))[0]
    return None

def set_int(name, value):
    fbits = struct.unpack('<f', struct.pack('<i', value))[0]
    m.mav.param_set_send(m.target_system, m.target_component, name.encode(), fbits,
                          mavutil.mavlink.MAV_PARAM_TYPE_INT32)
    deadline = time.time() + 8
    while time.time() < deadline:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and msg.param_id.rstrip('\x00') == name:
            return struct.unpack('<i', struct.pack('<f', msg.param_value))[0]
    return None

print(read_int("UXRCE_DDS_CFG"))
```

## PX4 MAVLink shell (NuttX console, no serial cable needed)

Runs PX4's own shell over the existing MAVLink link — same thing QGroundControl's "MAVLink
Console" widget uses. Good for `dmesg`, `uxrce_dds_client status`, restarting modules, etc.
without needing a second physical connection.

```python
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('tcp:127.0.0.1:5760')
m.wait_heartbeat(timeout=10)

def shell_cmd(cmd, read_time=3):
    data = (cmd + "\n").encode()
    padded = list(data) + [0] * (70 - len(data))
    m.mav.serial_control_send(
        mavutil.mavlink.SERIAL_CONTROL_DEV_SHELL,
        mavutil.mavlink.SERIAL_CONTROL_FLAG_EXCLUSIVE | mavutil.mavlink.SERIAL_CONTROL_FLAG_RESPOND,
        0, 0, len(data), padded)
    out = b""
    deadline = time.time() + read_time
    while time.time() < deadline:
        msg = m.recv_match(type='SERIAL_CONTROL', blocking=True, timeout=0.5)
        if msg:
            out += bytes(msg.data[:msg.count])
    return out.decode(errors='replace')

print(shell_cmd("uxrce_dds_client status"))
print(shell_cmd("dmesg"))                          # PX4's own boot log
print(shell_cmd("echo TEST > /dev/ttyS3"))          # raw write, bypasses the DDS client entirely
```

`dmesg` is the fastest way to confirm which physical port maps to which NuttX device on
**this specific board** — don't assume, grep for it:

```python
full = shell_cmd("dmesg", read_time=6)
for line in full.splitlines():
    if "uxrce" in line.lower():
        print(line)
# Confirmed on this board: TELEM2 -> /dev/ttyS3, TELEM3 -> /dev/ttyS1
```

## Known gotchas (things that cost real time to figure out)

- **TELEM port ≠ obvious `ttyS` number.** Don't assume — confirm via `dmesg` (above) every
  time you're unsure which physical connector maps to which NuttX device on this board.
- **`nvgetty`** (Jetson's serial-console service) can claim a header UART by default. Check:
  `systemctl is-active nvgetty.service` — should be `inactive`.
- **A momentary successful `MicroXRCEAgent` session doesn't mean the physical connection is
  reliable.** Loose jumper wires can connect just long enough to establish a session and then
  drop. If it worked once and now doesn't, physically re-check the connector before assuming
  a config regression.
- **PX4 needs a reboot** for `UXRCE_DDS_CFG`/`SER_TEL2_BAUD`-style params to take effect —
  these bind at module startup, not live.
