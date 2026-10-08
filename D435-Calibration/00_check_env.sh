#!/usr/bin/env bash
# Checks that everything the calibration pipeline needs is present. Read-only.
set -uo pipefail
source "$(dirname "$0")/common.sh"

ok()   { printf '  \e[32m[ok]\e[0m   %s\n' "$*"; }
bad()  { printf '  \e[31m[FAIL]\e[0m %s\n' "$*"; FAILED=1; }
warn() { printf '  \e[33m[warn]\e[0m %s\n' "$*"; }
FAILED=0

echo "== Host / ROS 2"
[[ -f "${ROS_SETUP}" ]] && ok "ROS 2 at ${ROS_SETUP}" || bad "missing ${ROS_SETUP}"
[[ -f "${VIO_WS}/install/setup.bash" ]] && ok "vio_ws built" || bad "colcon build in ${VIO_WS} (px4_msgs, OpenVINS, nap_px4_bridge)"
source_ros 2>/dev/null
python3 -c "import px4_msgs.msg" 2>/dev/null && ok "px4_msgs importable" || bad "px4_msgs not importable"
ros2 pkg prefix realsense2_camera >/dev/null 2>&1 && ok "realsense2_camera" || bad "apt install ros-jazzy-realsense2-camera"
python3 -c "import rosbag2_py" 2>/dev/null && ok "rosbag2" || bad "rosbag2 missing"

echo "== Camera"
RS_INFO=$(rs-enumerate-devices 2>/dev/null)   # captured once: `producer | grep -q` + pipefail = false failures
if grep -q "Intel RealSense D4" <<<"${RS_INFO}"; then
    ok "$(rs-enumerate-devices -s 2>/dev/null | sed -n 2p | tr -s ' ')"
    grep -q "Usb Type Descriptor.*3\." <<<"${RS_INFO}" && ok "USB3" || warn "not on USB3 -- two infra streams may drop frames"
    grep -qiE "\bAccel\b|\bGyro\b" <<<"${RS_INFO}" \
        && warn "camera HAS an IMU (D435i?) -- you could calibrate against it instead of PX4" \
        || ok "no camera IMU (plain D435) -> PX4 IMU will be used"
else
    bad "no RealSense camera detected"
fi

echo "== Flight controller IMU"
command -v MicroXRCEAgent >/dev/null && ok "MicroXRCEAgent at $(command -v MicroXRCEAgent)" || bad "MicroXRCEAgent not installed"
if [[ -e "${FC_SERIAL_DEV}" ]]; then
    [[ -r "${FC_SERIAL_DEV}" && -w "${FC_SERIAL_DEV}" ]] && ok "${FC_SERIAL_DEV} accessible" || bad "no rw on ${FC_SERIAL_DEV} (add user to dialout)"
else
    bad "${FC_SERIAL_DEV} not present"
fi
pgrep -f "mavlink-routerd.*${FC_SERIAL_DEV}" >/dev/null && warn "mavlink-router holds ${FC_SERIAL_DEV} -- stop it first"

echo "== Kalibr toolchain"
if docker info >/dev/null 2>&1; then
    ok "docker usable"
    docker image inspect "${KALIBR_IMAGE}" >/dev/null 2>&1 && ok "image ${KALIBR_IMAGE} built" \
        || warn "image ${KALIBR_IMAGE} not built yet -> ./01_build_kalibr.sh"
else
    bad "docker not usable by $(whoami)"
fi
[[ -x "${VENV_DIR}/bin/rosbags-convert" ]] && ok "rosbags-convert in .venv" || warn "rosbags not installed yet -> ./01_build_kalibr.sh"

echo "== Disk"
avail=$(df -BG --output=avail "${CALIB_DIR}" | tail -1 | tr -dc 0-9)
(( avail > 10 )) && ok "${avail} GB free" || warn "only ${avail} GB free (two 640x480 streams ~ 18 MB/s)"

echo
(( FAILED )) && { echo "Some checks FAILED."; exit 1; } || echo "Environment OK."
