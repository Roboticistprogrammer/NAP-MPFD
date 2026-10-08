# Shared settings for the D435 <-> PX4 IMU calibration scripts.
# Sourced by every NN_*.sh script -- edit values here, not in the scripts.

CALIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BAG_DIR="${CALIB_DIR}/bags"
LOG_DIR="${CALIB_DIR}/logs"
RESULTS_DIR="${CALIB_DIR}/results"
VENV_DIR="${CALIB_DIR}/.venv"

# ROS 2 environment: px4_msgs, OpenVINS and nap_px4_bridge are built in ../vio_ws (colcon build there)
ROS_SETUP="/opt/ros/jazzy/setup.bash"
VIO_WS="$(dirname "${CALIB_DIR}")/vio_ws"

# Flight controller link (Pixhawk 6C TELEM2 -> Pi 5 UART), PX4 params in README.md
FC_SERIAL_DEV="/dev/ttyAMA0"
FC_BAUD="921600"

# Topics
CAMERA_NAME="d435i"                                # keeps topic names identical to the VIO setup
CAM0_TOPIC="/${CAMERA_NAME}/infra1/image_rect_raw"
CAM1_TOPIC="/${CAMERA_NAME}/infra2/image_rect_raw"
IMU_TOPIC="/calib/imu"                             # host-clock re-stamped PX4 IMU (tools/px4_imu_restamp.py)
INFRA_PROFILE="640x480x30"

# Kalibr docker image
KALIBR_IMAGE="kalibr:noetic"

# VIO (07_start_vio.sh / 08_install_openvins_config.sh)
# OpenVINS reads its config straight from src/ via config_path, so no rebuild is needed after a recalibration.
OV_CONFIG_DIR="${VIO_WS}/src/open_vins/config/d435_px4"
VIO_SESSION="vio"                                  # tmux session name
# 08 multiplies the Kalibr IMU noise densities / random walks by this for OpenVINS only (Kalibr input untouched).
# The values in config/imu_px4.yaml are near-datasheet; on the airframe, with sensor_combined decimated to an
# uneven 5/10/15 ms spacing, they made OpenVINS overconfident and it diverged to km-scale. 1 = no inflation.
OV_IMU_NOISE_SCALE="5"

source_ros() {
    # ROS setup scripts reference unset variables, so relax `set -u` while sourcing
    set +u
    source "${ROS_SETUP}"
    source "${VIO_WS}/install/setup.bash"
    set -u
}

run_kalibr() {
    # Runs a command inside the Kalibr container with this folder mounted at /data.
    docker run --rm -i $([[ -t 0 ]] && echo -t) \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp -e MPLBACKEND=Agg \
        -v "${CALIB_DIR}:/data" -w /data/bags \
        "${KALIBR_IMAGE}" \
        bash -c "source /catkin_ws/devel/setup.bash && export PATH=/catkin_ws/devel/lib/kalibr:\$PATH PYTHONPATH=/data/tools/kalibr_site:\$PYTHONPATH && $*"
}
