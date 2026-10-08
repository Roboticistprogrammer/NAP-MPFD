#!/usr/bin/env bash
# Converts a ROS2 bag in bags/ to a ROS1 .bag for Kalibr.
#   ./04_convert.sh <bag_name>      e.g. ./04_convert.sh imu_20260928_140000
set -euo pipefail
source "$(dirname "$0")/common.sh"

NAME=${1:?usage: $0 <bag_name in bags/>}
NAME=$(basename "${NAME%.bag}")
SRC="${BAG_DIR}/${NAME}"
DST="${BAG_DIR}/${NAME}.bag"

[[ -d "${SRC}" ]] || { echo "no ROS2 bag at ${SRC}" >&2; exit 1; }
[[ -x "${VENV_DIR}/bin/rosbags-convert" ]] || { echo "run ./01_build_kalibr.sh first" >&2; exit 1; }
[[ -e "${DST}" ]] && { echo "${DST} exists -- delete it to re-convert" >&2; exit 1; }

"${VENV_DIR}/bin/rosbags-convert" --src "${SRC}" --dst "${DST}"
ls -lh "${DST}"
