#!/usr/bin/env bash
# Opens a Herdr tab with 5 panes and launches everything needed for the
# OpenVINS smoke test: MicroXRCEAgent, D435 camera bringup, the PX4 bridge,
# run_subscribe_msckf (mono, rs_d455 stand-in config), and a monitor of
# /ov_msckf/odomimu. Re-launches everything from scratch, including the
# pieces whose terminals got closed earlier.
#
# Run this yourself from an ordinary shell (not from inside Claude) — it
# was drafted, not executed, since the agent that wrote it isn't running
# inside a Herdr-managed pane and can't drive Herdr from outside one.
set -euo pipefail

command -v herdr >/dev/null || { echo "herdr not found in PATH" >&2; exit 1; }
command -v jq    >/dev/null || { echo "jq not found in PATH (needed to parse herdr's JSON output)" >&2; exit 1; }

WS_DIR="/home/skywarriors/workspaces/BAP"
ROS_SRC="source /opt/ros/jazzy/setup.bash && source ${WS_DIR}/install/setup.bash"

AGENT_CMD="sudo MicroXRCEAgent serial --dev /dev/ttyAMA0 -b 921600"
CAMERA_CMD="${ROS_SRC} && ros2 launch dronex_vio_bringup d435_infra.launch.py"
BRIDGE_CMD="${ROS_SRC} && ros2 run dronex_px4_bridge vio_px4_bridge"
MSCKF_CMD="${ROS_SRC} && ros2 run ov_msckf run_subscribe_msckf --ros-args -p config_path:=${WS_DIR}/src/open_vins/config/rs_d455/estimator_config.yaml -p topic_imu:=/d435i/imu -p topic_camera0:=/d435i/infra1/image_rect_raw"
MONITOR_CMD="${ROS_SRC} && ros2 topic echo /ov_msckf/odomimu"

echo "Creating tab..."
TAB_JSON=$(herdr tab create --label "VIO Smoke Test" --cwd "$WS_DIR" --focus)
TAB_ID=$(jq -r '.result.tab.tab_id' <<<"$TAB_JSON")
P_AGENT=$(jq -r '.result.root_pane.pane_id' <<<"$TAB_JSON")

echo "Building layout..."
# +--------+--------+
# | AGENT  | CAMERA |
# +--------+--------+
# | BRIDGE | MSCKF  |
# +--------+--------+
# |      MONITOR     |
# +-------------------+
P_MONITOR=$(jq -r '.result.pane.pane_id' <<<"$(herdr pane split "$P_AGENT" --direction down --ratio 0.75 --cwd "$WS_DIR" --no-focus)")
P_CAMERA=$(jq -r '.result.pane.pane_id' <<<"$(herdr pane split "$P_AGENT" --direction right --ratio 0.5 --cwd "$WS_DIR" --no-focus)")
P_BRIDGE=$(jq -r '.result.pane.pane_id' <<<"$(herdr pane split "$P_AGENT" --direction down --ratio 0.5 --cwd "$WS_DIR" --no-focus)")
P_MSCKF=$(jq -r '.result.pane.pane_id' <<<"$(herdr pane split "$P_CAMERA" --direction down --ratio 0.5 --cwd "$WS_DIR" --no-focus)")

herdr pane rename "$P_AGENT"   "agent"   >/dev/null
herdr pane rename "$P_CAMERA"  "camera"  >/dev/null
herdr pane rename "$P_BRIDGE"  "bridge"  >/dev/null
herdr pane rename "$P_MSCKF"   "msckf"   >/dev/null
herdr pane rename "$P_MONITOR" "monitor" >/dev/null

echo "Launching commands..."
herdr pane run "$P_AGENT"   "$AGENT_CMD"
herdr pane run "$P_CAMERA"  "$CAMERA_CMD"
herdr pane run "$P_BRIDGE"  "$BRIDGE_CMD"
herdr pane run "$P_MSCKF"   "$MSCKF_CMD"
herdr pane run "$P_MONITOR" "$MONITOR_CMD"

cat <<EOF

Launched in tab $TAB_ID:
  agent   ($P_AGENT)  - MicroXRCEAgent on /dev/ttyAMA0 @ 921600
                        needs your sudo password typed directly in that pane
  camera  ($P_CAMERA) - D435 infra1/infra2 bringup
  bridge  ($P_BRIDGE) - vio_px4_bridge (PX4 <-> ROS2 IMU/odometry bridge)
  msckf   ($P_MSCKF)  - run_subscribe_msckf smoke test (mono, rs_d455 stand-in config)
  monitor ($P_MONITOR) - ros2 topic echo /ov_msckf/odomimu

Once all panes are up, leave the platform still on a flat surface for a
few seconds and watch the msckf pane for:
  q_GtoI = ... | p_IinG = ...
That line means it initialized. Only then move it, smoothly, to see the
monitor pane respond.
EOF
