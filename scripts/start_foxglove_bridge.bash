#!/usr/bin/env bash
# Launches foxglove_bridge on this RPi (source of the RealSense camera
# topics), listening on all interfaces at the default port 8765.
#
# On your laptop, open Foxglove Studio and connect to:
#   ws://192.168.1.125:8765
# No ROS2 install or DDS discovery needed on the laptop side.
#
# Requires: sudo apt-get install -y ros-jazzy-foxglove-bridge
set -eo pipefail

WS_DIR="/home/skywarriors/workspaces/BAP"

# ROS's setup.bash references unset variables internally, so -u can't be
# active while sourcing it.
set +u
source /opt/ros/jazzy/setup.bash
[ -f "${WS_DIR}/install/setup.bash" ] && source "${WS_DIR}/install/setup.bash"
set -u

ros2 pkg prefix foxglove_bridge >/dev/null 2>&1 || {
  echo "foxglove_bridge is not installed. Run:" >&2
  echo "  sudo apt-get install -y ros-jazzy-foxglove-bridge" >&2
  exit 1
}

exec ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=0.0.0.0 port:=8765
