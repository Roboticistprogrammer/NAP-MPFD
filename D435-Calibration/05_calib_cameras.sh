#!/usr/bin/env bash
# Kalibr stereo camera calibration (infra1 + infra2 intrinsics and baseline).
#   ./05_calib_cameras.sh <cam_bag_name>
# Output: results/<name>/<name>-camchain.yaml (+ results txt / report PDF)
set -euo pipefail
source "$(dirname "$0")/common.sh"

NAME=$(basename "${1:?usage: $0 <cam bag name>}" .bag)
[[ -f "${BAG_DIR}/${NAME}.bag" ]] || "${CALIB_DIR}/04_convert.sh" "${NAME}"

# --bag-freq 4: subsample to 4 Hz -- plenty of views, keeps the Pi 5 run time sane.
# pinhole-radtan: D435 infra streams (Y8) are already rectified by the ASIC, so
# distortion should come out near zero; large values mean a bad recording.
run_kalibr kalibr_calibrate_cameras \
    --target /data/config/aprilgrid.yaml \
    --bag "${NAME}.bag" --bag-freq 4.0 \
    --models pinhole-radtan pinhole-radtan \
    --topics "${CAM0_TOPIC}" "${CAM1_TOPIC}" \
    --dont-show-report \
    || echo "WARNING: kalibr exited with an error (often only the PDF report step)"
[[ -f "${BAG_DIR}/${NAME}-camchain.yaml" ]] || { echo "no calibration output -- see errors above" >&2; exit 1; }

# Kalibr writes next to the bag (its working dir); keep bags/ for bags only.
mkdir -p "${RESULTS_DIR}/${NAME}"
for f in camchain.yaml results-cam.txt report-cam.pdf; do
    if [[ -f "${BAG_DIR}/${NAME}-${f}" ]]; then mv -f "${BAG_DIR}/${NAME}-${f}" "${RESULTS_DIR}/${NAME}/"; fi
done
echo; echo "Check reprojection error in results/${NAME}/${NAME}-results-cam.txt (aim < 0.3 px)."
echo "Next: ./06_calib_cam_imu.sh <imu_bag_name> ${NAME}"
