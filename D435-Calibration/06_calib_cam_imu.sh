#!/usr/bin/env bash
# Kalibr camera <-> IMU calibration (T_cam_imu + time offset), using the camchain from step 05.
#   ./06_calib_cam_imu.sh <imu_bag_name> <cam_bag_name>
# Output: results/<imu_bag>/<imu_bag>-camchain-imucam.yaml, -imu.yaml, results txt, report PDF.
# Then run ./08_install_openvins_config.sh <imu_bag> to push them into the OpenVINS config.
set -euo pipefail
source "$(dirname "$0")/common.sh"

IMU_BAG=$(basename "${1:?usage: $0 <imu bag> <cam bag>}" .bag)
CAM_BAG=$(basename "${2:?usage: $0 <imu bag> <cam bag>}" .bag)
CAMCHAIN="results/${CAM_BAG}/${CAM_BAG}-camchain.yaml"
[[ -f "${CALIB_DIR}/${CAMCHAIN}" ]] || { echo "missing ${CAMCHAIN} -- run 05_calib_cameras.sh ${CAM_BAG}" >&2; exit 1; }
[[ -f "${BAG_DIR}/${IMU_BAG}.bag" ]] || "${CALIB_DIR}/04_convert.sh" "${IMU_BAG}"

# --timeoffset-padding: search range for the camera-IMU time offset [s]. The re-stamper
#   already aligns clocks to a few ms; 0.1 s leaves room for PX4 filter delay.
# --imu-models calibrated: PX4 already applies its own accel/gyro calibration.
# --bag-from-to could trim the still segments at start/end if the fit struggles.
run_kalibr kalibr_calibrate_imu_camera \
    --target /data/config/aprilgrid.yaml \
    --cam "/data/${CAMCHAIN}" \
    --imu /data/config/imu_px4.yaml \
    --imu-models calibrated \
    --bag "${IMU_BAG}.bag" \
    --timeoffset-padding 0.1 \
    --dont-show-report \
    || echo "WARNING: kalibr exited with an error (often only the PDF report step)"
[[ -f "${BAG_DIR}/${IMU_BAG}-camchain-imucam.yaml" ]] || { echo "no calibration output -- see errors above" >&2; exit 1; }

# Kalibr writes next to the bag (its working dir); keep bags/ for bags only.
mkdir -p "${RESULTS_DIR}/${IMU_BAG}"
for f in camchain-imucam.yaml imu.yaml results-imucam.txt report-imucam.pdf; do
    if [[ -f "${BAG_DIR}/${IMU_BAG}-${f}" ]]; then mv -f "${BAG_DIR}/${IMU_BAG}-${f}" "${RESULTS_DIR}/${IMU_BAG}/"; fi
done
cp "${CALIB_DIR}/config/imu_px4.yaml" "${RESULTS_DIR}/${IMU_BAG}/imu_input.yaml"

echo; echo "Results in results/${IMU_BAG}/. Sanity checks:"
echo "  - timeshift_cam_imu should be a few ms to a few tens of ms, not ~0.1 (padding limit)"
echo "  - translation in T_cam_imu should match the physical mount within ~1 cm"
echo "  - gyro/accel error plots in the report should look like white noise"
echo "Next: ./08_install_openvins_config.sh ${IMU_BAG}"
