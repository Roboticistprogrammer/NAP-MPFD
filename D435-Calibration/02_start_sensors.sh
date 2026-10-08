#!/usr/bin/env bash
# Starts everything needed for recording, in the background, and stops it all on Ctrl+C:
#   MicroXRCEAgent (PX4 uORB -> ROS2), D435 infra1/infra2 (emitter off), PX4 IMU re-stamper.
# Leave this running in one terminal and use 03_record.sh in another.
set -euo pipefail
source "$(dirname "$0")/common.sh"
source_ros
mkdir -p "${LOG_DIR}"

PIDS=()
cleanup() {
    echo; echo "stopping..."
    for pid in "${PIDS[@]}"; do kill -INT "${pid}" 2>/dev/null || true; done
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start() {  # start <name> <cmd...>
    local name=$1; shift
    "$@" >"${LOG_DIR}/${name}.log" 2>&1 &
    PIDS+=($!)
    echo "started ${name} (pid $!, log: logs/${name}.log)"
}

if pgrep -x MicroXRCEAgent >/dev/null; then
    echo "MicroXRCEAgent already running -- reusing it"
else
    start agent MicroXRCEAgent serial --dev "${FC_SERIAL_DEV}" -b "${FC_BAUD}"
fi

start camera ros2 launch realsense2_camera rs_launch.py \
    camera_name:="${CAMERA_NAME}" camera_namespace:=/ \
    enable_infra1:=true enable_infra2:=true enable_color:=false enable_depth:=false \
    depth_module.infra_profile:="${INFRA_PROFILE}" \
    config_file:="${CALIB_DIR}/config/realsense_calib.yaml"

start restamp python3 "${CALIB_DIR}/tools/px4_imu_restamp.py" --ros-args -p output_topic:="${IMU_TOPIC}"

echo; echo "waiting for streams..."
sleep 8
for t in "${CAM0_TOPIC}" "${CAM1_TOPIC}" /fmu/out/sensor_combined "${IMU_TOPIC}"; do
    rate=$(timeout 6 ros2 topic hz "${t}" --window 50 2>/dev/null | grep -m1 "average rate" | awk '{print $3}' || true)
    [[ -n "${rate}" ]] && rate="${rate} Hz" || rate="NO DATA (check logs/)"
    printf '  %-40s %s\n' "${t}" "${rate}"
done
emitter=$(ros2 param get "/${CAMERA_NAME}" depth_module.emitter_enabled 2>/dev/null | awk '{print $NF}' || true)
echo "  emitter_enabled = ${emitter:-?}  (must be 0)"
grep -m1 "offset frozen" "${LOG_DIR}/restamp.log" | sed 's/^/  /' || echo "  IMU re-stamper still warming up"

echo; echo "Sensors running. Record with ./03_record.sh in another terminal. Ctrl+C here to stop."
wait
