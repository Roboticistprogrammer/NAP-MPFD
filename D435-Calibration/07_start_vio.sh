#!/usr/bin/env bash
# Starts the full VIO -> PX4 pipeline in a tmux session, one window per process, in dependency order:
#
#   agent       MicroXRCEAgent          PX4 uORB <-> ROS 2 over ${FC_SERIAL_DEV}  (own session: ${VIO_SESSION}-agent)
#   2 camera    realsense2_camera       /d435i/infra{1,2}/image_rect_raw (config/realsense_vio.yaml)
#   3 imu       px4_imu_restamp.py      /fmu/out/sensor_combined -> /calib/imu on the host clock
#   4 openvins  ov_msckf                /calib/imu + infra1/2 -> /ov_msckf/odomimu
#   5 bridge    vio_px4_bridge          /ov_msckf/odomimu -> /fmu/in/vehicle_visual_odometry
#   6 status    topic rates every 5 s (tools/vio_rates.py: counts only, no cameras)
#
#   ./07_start_vio.sh          start (or re-attach to) the session
#   ./07_start_vio.sh stop     Ctrl+C every window, then close the session -- the agent keeps running
#   ./07_start_vio.sh stop all also stop the agent
#   ./07_start_vio.sh status   print topic rates once, cameras included -- costs ~a core for ~25 s, not while flying
#
# tmux: Ctrl+b n / p = next / previous window, Ctrl+b <number> = jump, Ctrl+b d = detach (keeps running).
# Window output is also logged to logs/vio_<window>.log.
#
# Why the agent lives in its own session: once an agent goes away, PX4's uxrce_dds_client often never
# connects to the next one (agent sits at "running..." with no "session established") until you run
# `uxrce_dds_client stop` / `start` on the FC or reboot it. So restarting the pipeline keeps the agent.
set -euo pipefail
source "$(dirname "$0")/common.sh"

# Sourced inside every tmux window. Not source_ros: that leaves `set -u` on in the interactive shell.
ROS_ENV="source ${ROS_SETUP} && source ${VIO_WS}/install/setup.bash"

# topic  qos  field -- `ros2 topic echo --field` keeps image messages from flooding the terminal
CHECKS=(
    "/fmu/out/sensor_combined         best_effort timestamp"
    "/calib/imu                       reliable    header.stamp"
    "${CAM0_TOPIC}  reliable    header.stamp"
    "${CAM1_TOPIC}  reliable    header.stamp"
    "/ov_msckf/odomimu                reliable    header.stamp"
    "/fmu/in/vehicle_visual_odometry  best_effort timestamp"
)

wait_topic() {  # wait_topic <topic> <qos> <field> <timeout_s>
    local deadline=$((SECONDS + $4))
    printf '  waiting for %-40s' "$1"
    while ((SECONDS < deadline)); do
        if timeout 3 ros2 topic echo --once --qos-reliability "$2" --field "$3" "$1" >/dev/null 2>&1; then
            echo "ok"; return 0
        fi
    done
    echo "TIMEOUT"; return 1
}

AGENT_SESSION="${VIO_SESSION}-agent"
# tmux -t matches session names by prefix ("vio" finds "vio-agent"), so every -t below uses "=name" (exact).
# Every process the vio session starts (not the agent), for leftover detection.
PIPELINE_RE='realsense2_camera|px4_imu_restamp|ov_msckf|vio_px4_bridge'

window() {  # window <name> <command>
    tmux new-window -t "=${VIO_SESSION}:" -n "$1" -c "${CALIB_DIR}"
    tmux pipe-pane -t "=${VIO_SESSION}:$1" -o "cat >> '${LOG_DIR}/vio_$1.log'"
    tmux send-keys -t "=${VIO_SESSION}:$1" "${ROS_ENV} && $2" C-m
    echo "started window '$1'"
}

attach() {
    if [[ -n "${TMUX:-}" ]]; then tmux switch-client -t "=${VIO_SESSION}"; else tmux attach -t "=${VIO_SESSION}"; fi
}

status() {  # status [light] -- light skips the camera topics
    source_ros
    echo "VIO pipeline rates ($(date +%T)):"
    for c in "${CHECKS[@]}"; do
        read -r t _ <<<"${c}"
        # `ros2 topic hz` on a 640x480 image topic took 85 % of a core on the Pi 5; looped, that starved
        # OpenVINS (tracking 20 -> 190 ms, IMU gaps) until it lost every feature and diverged.
        if [[ "${1:-}" == light && "${t}" == *image* ]]; then printf '  %-40s %s\n' "${t}" "(skipped)"; continue; fi
        rate=$(timeout 4 ros2 topic hz --window 30 "${t}" 2>/dev/null \
               | grep -m1 "average rate" | awk '{printf "%.1f Hz", $3}' || true)
        printf '  %-40s %s\n' "${t}" "${rate:-NO DATA}"
    done
    echo "Expected: sensor_combined/calib/imu ~100 Hz, cameras 30 Hz, odomimu/visual_odometry ~30 Hz."
    echo "On the FC (QGC MAVLink console): listener vehicle_visual_odometry, then listener estimator_status_flags (cs_ev_pos)."
}

stop() {  # stop [all]
    if tmux has-session -t "=${VIO_SESSION}" 2>/dev/null; then
        # Reverse start order so the bridge stops before its inputs disappear.
        for w in status bridge openvins imu camera; do
            tmux send-keys -t "=${VIO_SESSION}:${w}" C-c 2>/dev/null || true
            sleep 1
        done
        sleep 2
        tmux kill-session -t "=${VIO_SESSION}"
        echo "stopped '${VIO_SESSION}'"
    else
        echo "no '${VIO_SESSION}' session running"
    fi
    # Pipeline processes can outlive their window (seen: two orphaned vio_px4_bridge, parent = init),
    # and duplicates would double-publish to PX4 -- stop whatever survived.
    if pgrep -f "${PIPELINE_RE}" >/dev/null; then
        pkill -INT -f "${PIPELINE_RE}" || true
        sleep 3
        pkill -KILL -f "${PIPELINE_RE}" || true
        echo "stopped leftover pipeline processes"
    fi
    if [[ "${1:-}" == all ]] && tmux has-session -t "=${AGENT_SESSION}" 2>/dev/null; then
        tmux send-keys -t "=${AGENT_SESSION}:agent" C-c
        sleep 1
        tmux kill-session -t "=${AGENT_SESSION}"
        echo "stopped '${AGENT_SESSION}' -- the FC's uxrce_dds_client may need a restart before the next agent connects"
    elif tmux has-session -t "=${AGENT_SESSION}" 2>/dev/null; then
        echo "agent left running in '${AGENT_SESSION}' (./07_start_vio.sh stop all to stop it too)"
    fi
}

case "${1:-start}" in
    stop)   stop "${2:-}"; exit 0 ;;
    status) status "${2:-}"; exit 0 ;;
    start)  ;;
    *)      echo "usage: $0 [start|stop|status]" >&2; exit 1 ;;
esac

# --- preflight ---------------------------------------------------------------
command -v tmux >/dev/null || { echo "tmux is not installed: sudo apt install tmux" >&2; exit 1; }
if tmux has-session -t "=${VIO_SESSION}" 2>/dev/null; then
    # A window closes when its process exits and the shell is then closed (e.g. OpenVINS crashed or was
    # Ctrl+C'd, then Ctrl+D) -- re-attaching to such a session looks like a start but leaves PX4 with no VIO.
    missing=()
    for w in camera imu openvins bridge; do
        tmux list-windows -t "=${VIO_SESSION}" -F '#W' | grep -qx "${w}" || missing+=("${w}")
    done
    if ((${#missing[@]})); then
        echo "session '${VIO_SESSION}' is incomplete (no window: ${missing[*]}) -- run ./07_start_vio.sh stop, then start again" >&2
        exit 1
    fi
    echo "session '${VIO_SESSION}' already running -- attaching (./07_start_vio.sh stop to restart)"
    attach; exit 0
fi
for f in estimator_config.yaml kalibr_imucam_chain.yaml kalibr_imu_chain.yaml; do
    [[ -f "${OV_CONFIG_DIR}/${f}" ]] || { echo "missing ${OV_CONFIG_DIR}/${f} -- run ./08_install_openvins_config.sh" >&2; exit 1; }
done
[[ -e "${FC_SERIAL_DEV}" ]] || { echo "${FC_SERIAL_DEV} not found (FC TELEM2 link)" >&2; exit 1; }
if pgrep -f "${PIPELINE_RE}" >/dev/null; then
    echo "pipeline processes already running outside the '${VIO_SESSION}' session:" >&2
    pgrep -af "${PIPELINE_RE}" | cut -c1-120 | sed 's/^/  /' >&2
    echo "run ./07_start_vio.sh stop (or stop 02_start_sensors.sh -- the D435 can only be opened once)" >&2
    exit 1
fi
mkdir -p "${LOG_DIR}"
source_ros
echo "OpenVINS config: ${OV_CONFIG_DIR} (calibration: $(cat "${OV_CONFIG_DIR}/CALIBRATION_SOURCE" 2>/dev/null || echo unknown))"

# Window 0 is a plain shell; each process gets its own window after it.
tmux new-session -d -s "${VIO_SESSION}" -n shell -c "${CALIB_DIR}"
tmux send-keys -t "=${VIO_SESSION}:shell" "${ROS_ENV}" C-m

# --- 1. uXRCE-DDS agent ----------------------------------------------------------
if pgrep -x MicroXRCEAgent >/dev/null; then
    echo "MicroXRCEAgent already running -- reusing it (tmux attach -t ${AGENT_SESSION} to see it)"
else
    tmux new-session -d -s "${AGENT_SESSION}" -n agent -c "${CALIB_DIR}"
    tmux pipe-pane -t "=${AGENT_SESSION}:agent" -o "cat >> '${LOG_DIR}/vio_agent.log'"
    tmux send-keys -t "=${AGENT_SESSION}:agent" "${ROS_ENV} && MicroXRCEAgent serial --dev ${FC_SERIAL_DEV} -b ${FC_BAUD}" C-m
    echo "started agent in session '${AGENT_SESSION}'"
fi
wait_topic /fmu/out/sensor_combined best_effort timestamp 30 || {
    echo "  -> no PX4 data. If the agent only shows 'running...' (no 'session established'), run on the FC:"
    echo "       uxrce_dds_client stop && uxrce_dds_client start -t serial -d /dev/ttyS3 -b ${FC_BAUD}"
    echo "     (or reboot the FC). Continuing anyway -- the rest picks the data up once it flows."
}

# --- 2. D435 (emitter off like the calibration, but auto exposure -- see config/realsense_vio.yaml) ---
window camera "ros2 launch realsense2_camera rs_launch.py \
camera_name:=${CAMERA_NAME} camera_namespace:=/ \
enable_infra1:=true enable_infra2:=true enable_color:=false enable_depth:=false \
depth_module.infra_profile:=${INFRA_PROFILE} \
config_file:=${CALIB_DIR}/config/realsense_vio.yaml"
wait_topic "${CAM0_TOPIC}" reliable header.stamp 30 || true
wait_topic "${CAM1_TOPIC}" reliable header.stamp 10 || true

# --- 3. IMU on the host clock (the topic the calibration and OpenVINS use) ------------------
window imu "python3 ${CALIB_DIR}/tools/px4_imu_restamp.py --ros-args -p output_topic:=${IMU_TOPIC}"
wait_topic "${IMU_TOPIC}" reliable header.stamp 20 || true   # ~5 s warm-up before the first message

# --- 4. OpenVINS ---------------------------------------------------------------------
window openvins "ros2 launch ov_msckf subscribe.launch.py \
config_path:=${OV_CONFIG_DIR}/estimator_config.yaml max_cameras:=2 use_stereo:=true verbosity:=INFO"
echo "  OpenVINS initialises after ~2 s with the drone still on the ground (ZUPT holds it there until it first moves)"

# --- 5. VIO -> PX4 bridge -----------------------------------------------------------
window bridge "ros2 run nap_px4_bridge vio_px4_bridge"

# --- 6. status ---------------------------------------------------------------------
window status "nice -n 10 python3 ${CALIB_DIR}/tools/vio_rates.py"

tmux select-window -t "=${VIO_SESSION}:openvins"
echo; echo "All started. Attaching to tmux session '${VIO_SESSION}' (Ctrl+b d to detach, ./07_start_vio.sh stop to stop)."
sleep 1
attach
