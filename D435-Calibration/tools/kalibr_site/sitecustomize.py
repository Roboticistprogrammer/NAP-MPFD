# Auto-imported by Python inside the Kalibr container (via PYTHONPATH, see common.sh).
# On arm64 (ros:noetic), `import cv_bridge` fails with "initialization of
# cv_bridge_boost raised unreported exception" unless cv2 is loaded first.
try:
    import cv2  # noqa: F401
except ImportError:
    pass
