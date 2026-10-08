#!/usr/bin/env bash
# Records a calibration bag (needs 02_start_sensors.sh running).
#
#   ./03_record.sh cam    [seconds=90]    stereo intrinsics/extrinsics recording
#   ./03_record.sh imu    [seconds=90]    camera <-> IMU recording
#   ./03_record.sh static [seconds=10800] IMU only, FC perfectly still, for Allan variance (optional)
set -euo pipefail
source "$(dirname "$0")/common.sh"
source_ros

MODE=${1:-}
case "${MODE}" in
    cam)    DUR=${2:-90};    TOPICS=("${CAM0_TOPIC}" "${CAM1_TOPIC}")
            HINT="Keep the Aprilgrid fully in view of BOTH cameras. Move SLOWLY:
  tilt the board/camera through every direction, cover image corners and edges,
  vary the distance (~0.4-1.5 m). Avoid motion blur." ;;
    imu)    DUR=${2:-90};    TOPICS=("${CAM0_TOPIC}" "${CAM1_TOPIC}" "${IMU_TOPIC}")
            HINT="Board FIXED, move the drone/rig (camera + FC rigidly mounted!) in front of it.
  Start still for ~3 s. Then excite every axis: roll, pitch, yaw, and translate
  up/down, left/right, forward/back -- smooth but brisk. Keep the grid in view.
  End still for ~3 s." ;;
    static) DUR=${2:-10800}; TOPICS=("${IMU_TOPIC}")
            HINT="Do NOT touch the rig. Motors off, on a vibration-free surface, for the whole duration." ;;
    *) sed -n 2,7p "$0"; exit 1 ;;
esac

# Sanity check the streams before wasting a recording
for t in "${TOPICS[@]}"; do
    timeout 5 ros2 topic echo --once "${t}" --field header.stamp >/dev/null 2>&1 \
        || { echo "no data on ${t} -- is 02_start_sensors.sh running?" >&2; exit 1; }
done

mkdir -p "${BAG_DIR}"
NAME="${MODE}_$(date +%Y%m%d_%H%M%S)"
echo "${HINT}"
echo
for i in 5 4 3 2 1; do printf '\rstarting in %d ' "$i"; sleep 1; done; echo

ros2 bag record -o "${BAG_DIR}/${NAME}" --max-cache-size 200000000 --topics "${TOPICS[@]}" \
    >"${LOG_DIR}/record_${NAME}.log" 2>&1 &
REC=$!
# SIGTERM, not SIGINT: bash makes background jobs of a script ignore SIGINT, so
# `kill -INT` would never reach the recorder. rosbag2 finalizes the bag on SIGTERM too.
stop_rec() { kill -TERM ${REC} 2>/dev/null; wait ${REC} 2>/dev/null || true; }
trap 'echo; echo "stopped early"; stop_rec; exit 130' INT TERM
for ((s = DUR; s > 0; s--)); do printf '\rrecording %s: %4d s left ' "${NAME}" "$s"; sleep 1; done
echo
stop_rec
trap - INT TERM

ros2 bag info "${BAG_DIR}/${NAME}" | grep -E "Duration|Topic:|Messages"
echo
echo "saved: bags/${NAME}   -> next: ./04_convert.sh ${NAME}"
