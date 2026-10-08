#!/usr/bin/env bash
# One-time setup:
#   1. rosbags (ROS2 -> ROS1 bag converter) in a local venv
#   2. Kalibr docker image (ROS1 Noetic). On a Pi 5 the catkin build takes ~1-2 h.
#      Alternative: build/run the same Dockerfile on a faster x86 PC and copy bags there.
#   3. Aprilgrid PDF matching config/aprilgrid.yaml, for printing
set -euo pipefail
source "$(dirname "$0")/common.sh"

echo "== rosbags venv"
if [[ ! -x "${VENV_DIR}/bin/rosbags-convert" ]]; then
    python3 -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install "rosbags>=0.10"
fi
"${VENV_DIR}/bin/rosbags-convert" --help >/dev/null && echo "rosbags-convert ready"

echo "== Kalibr image (${KALIBR_IMAGE})"
if docker image inspect "${KALIBR_IMAGE}" >/dev/null 2>&1 && [[ "${1:-}" != "--rebuild" ]]; then
    echo "already built (pass --rebuild to rebuild)"
else
    # -j2: catkin + Eigen-heavy Kalibr sources can exhaust 8 GB RAM at higher parallelism
    docker build --build-arg BUILD_JOBS=2 -t "${KALIBR_IMAGE}" "${CALIB_DIR}/docker" 2>&1 \
        | tee "${CALIB_DIR}/docker/build.log"
fi

echo "== Aprilgrid target PDF"
mkdir -p "${BAG_DIR}"
read -r cols rows tsize tspace < <(python3 - "${CALIB_DIR}/config/aprilgrid.yaml" <<'EOF'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
print(c['tagCols'], c['tagRows'], c['tagSize'], c['tagSpacing'])
EOF
)
run_kalibr "kalibr_create_target_pdf --type apriltag --nx ${cols} --ny ${rows} --tsize ${tsize} --tspace ${tspace} /data/config/aprilgrid.pdf"
echo "Print config/aprilgrid.pdf at 100 % scale (no 'fit to page'), glue it flat on a rigid board,"
echo "measure one tag edge with calipers and correct tagSize in config/aprilgrid.yaml."
