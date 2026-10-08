#!/usr/bin/env bash
# Launches foxglove_bridge on this RPi, listening on all interfaces at port 8765, set up so watching
# the VIO pipeline from the laptop cannot starve OpenVINS or command the drone.
#
# On your laptop, open Foxglove Studio and connect to:
#   ws://<pi-ip>:8765   (hostname -I)
# No ROS2 install or DDS discovery needed on the laptop side.
#
# Camera view: /ov_msckf/trackhist_preview -- OpenVINS's feature-track image, half size, JPEG, <= 5 Hz,
# drawn only while a panel shows it (local OpenVINS patch in ROS2Visualizer.cpp). Not the raw images:
# on this Pi any extra subscriber to a raw 640x480 image costs 50-85 % of a core (even in C++, it is the
# DDS transport), which made OpenVINS diverge.
#
# Precautions:
#   - only light topics are visible (TOPICS below); raw images and /ov_msckf/trackhist (~55 MB/s) are not
#   - read-only: the laptop cannot publish (e.g. /fmu/in/*), call services or change parameters
#   - the bridge runs at nice 10, so OpenVINS wins any CPU contention
#
# Requires: sudo apt-get install -y ros-jazzy-foxglove-bridge
set -eo pipefail

source "$(dirname "$0")/../common.sh"

# Regexes, matched against full topic names.
TOPICS=(
    '/ov_msckf/(odomimu|poseimu|pathimu|points_slam|points_msckf|trackhist_preview)'
    '/fmu/out/(vehicle_local_position|vehicle_odometry|vehicle_attitude|estimator_status_flags)'
    '/fmu/out/(vehicle_status(_v[0-9]+)?|failsafe_flags|vehicle_land_detected|vehicle_control_mode|battery_status)'
    '/fmu/in/vehicle_visual_odometry'
    '/tf(_static)?'
)

# ROS's setup.bash references unset variables internally, so -u can't be
# active while sourcing it.
set +u
source "${ROS_SETUP}"
[ -f "${VIO_WS}/install/setup.bash" ] && source "${VIO_WS}/install/setup.bash"
set -u

ros2 pkg prefix foxglove_bridge >/dev/null 2>&1 || {
  echo "foxglove_bridge is not installed. Run:" >&2
  echo "  sudo apt-get install -y ros-jazzy-foxglove-bridge" >&2
  exit 1
}

whitelist="[$(printf "'^%s\$'," "${TOPICS[@]}" | sed 's/,$//')]"

exec nice -n 10 ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  address:=0.0.0.0 port:=8765 \
  topic_whitelist:="${whitelist}" \
  capabilities:="[connectionGraph]" \
  client_topic_whitelist:="['^$']" service_whitelist:="['^$']" param_whitelist:="['^$']" \
  max_qos_depth:=5 send_buffer_limit:=2000000
