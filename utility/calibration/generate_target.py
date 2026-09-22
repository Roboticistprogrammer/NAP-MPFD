#!/usr/bin/env python3
"""
generate_target.py — AprilGrid calibration target generator, for display on a
screen (or printing) at a *physically known* scale.

Why this exists: Kalibr's own `kalibr_create_target_pdf` assumes you're
printing on paper. This instead renders the grid as a pixel-exact PNG for
displaying on a screen at true physical scale — which needs the screen's
*actual* pixels-per-inch, not what the OS reports (frequently wrong) and not
CSS's assumed 96dpi (not tied to real physical size at all). The `ruler`
command measures that; `grid` uses it.

Two-step workflow:
    1. ruler  — generate a reference line, display it fullscreen at 100% zoom
                (no scaling), measure its physical width with an actual ruler.
    2. grid   — generate the AprilGrid PNG + matching Kalibr target.yaml,
                sized correctly from that measurement.

Same tool doubles as a print-target generator: pass your printer's DPI as
--ppi and a canvas the size of your paper at that DPI (e.g. A4 @ 300dpi =
2481x3508px) instead of your screen's resolution.

See README.md before using this for real calibration data — in particular
the mandatory IR-visibility check if you're calibrating the D435's infra1/
infra2 cameras (an LCD screen is not guaranteed visible to a near-IR sensor;
this is unverified for this project's hardware).

Requires: opencv-contrib-python, numpy
"""
import argparse
import sys

import cv2
import numpy as np

MM_PER_INCH = 25.4
TAG_FAMILY_MAX_ID = 586  # tag36h11 has 587 unique tags, ids 0-586


def require_apriltag_dict():
    if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "DICT_APRILTAG_36h11"):
        sys.exit(
            "cv2.aruco.DICT_APRILTAG_36h11 not available in this OpenCV build.\n"
            "Install: pip install opencv-contrib-python"
        )
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


def draw_tag(canvas, tag_dict, tag_id, x0, y0, side_px):
    if hasattr(cv2.aruco, "generateImageMarker"):
        tag_img = cv2.aruco.generateImageMarker(tag_dict, tag_id, side_px)
    else:  # older OpenCV API
        tag_img = cv2.aruco.drawMarker(tag_dict, tag_id, side_px)
    canvas[y0:y0 + side_px, x0:x0 + side_px] = tag_img


def blank_canvas(width_px, height_px):
    return np.full((height_px, width_px), 255, dtype=np.uint8)


def put_caption(img, lines, origin):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,), 1, cv2.LINE_AA)
        y += 24


def cmd_ruler(args):
    img = blank_canvas(args.screen_width_px, args.screen_height_px)
    cy = args.screen_height_px // 2
    x0 = (args.screen_width_px - args.length_px) // 2
    x1 = x0 + args.length_px
    cv2.line(img, (x0, cy), (x1, cy), (0,), 3)
    for x in (x0, x1):
        cv2.line(img, (x, cy - 20), (x, cy + 20), (0,), 3)
    put_caption(img, [
        f"Reference line is exactly {args.length_px}px wide.",
        "Display this FULLSCREEN at 100% zoom / no scaling (see README).",
        "Measure the line's physical width with a ruler, in mm.",
        f"Then: generate_target.py grid --measured-mm <value> --reference-px {args.length_px} ...",
    ], origin=(x0, cy + 60))
    cv2.imwrite(args.out, img)
    print(f"Wrote {args.out} ({args.screen_width_px}x{args.screen_height_px}px)")


def resolve_ppi(args):
    if args.ppi:
        return args.ppi
    if args.measured_mm:
        return args.reference_px / args.measured_mm * MM_PER_INCH
    sys.exit("Provide either --ppi directly, or --measured-mm (+ --reference-px, from the ruler step).")


def cmd_grid(args):
    tag_dict = require_apriltag_dict()

    max_id = args.rows * args.cols - 1
    if max_id > TAG_FAMILY_MAX_ID:
        sys.exit(f"tag36h11 only has {TAG_FAMILY_MAX_ID + 1} unique tags (ids 0-{TAG_FAMILY_MAX_ID}); "
                  f"{args.cols}x{args.rows} needs id {max_id}.")

    ppi = resolve_ppi(args)
    px_per_mm = ppi / MM_PER_INCH

    tag_px = round(args.tag_size_mm * px_per_mm)
    spacing_px = round(args.tag_size_mm * args.tag_spacing_ratio * px_per_mm)
    pitch_px = tag_px + spacing_px

    grid_w = args.cols * tag_px + (args.cols - 1) * spacing_px
    grid_h = args.rows * tag_px + (args.rows - 1) * spacing_px

    if grid_w > args.screen_width_px or grid_h > args.screen_height_px:
        sys.exit(
            f"Grid ({grid_w}x{grid_h}px) doesn't fit the given canvas "
            f"({args.screen_width_px}x{args.screen_height_px}px) at this ppi/tag size — "
            "shrink --tag-size-mm, reduce --cols/--rows, or grow the canvas."
        )

    canvas = blank_canvas(args.screen_width_px, args.screen_height_px)
    x_off = (args.screen_width_px - grid_w) // 2
    y_off = (args.screen_height_px - grid_h) // 2

    for row in range(args.rows):
        for col in range(args.cols):
            tag_id = row * args.cols + col  # row-major, top-left = id 0 — verify against Kalibr's detector (README)
            draw_tag(canvas, tag_dict, tag_id, x_off + col * pitch_px, y_off + row * pitch_px, tag_px)

    put_caption(canvas, [
        f"{args.cols}x{args.rows} AprilGrid (tag36h11) — tagSize={args.tag_size_mm}mm, "
        f"spacing ratio={args.tag_spacing_ratio}, ppi={ppi:.2f}",
        "Display FULLSCREEN at 100% zoom / no scaling. See README before recording data.",
    ], origin=(20, 30))

    cv2.imwrite(args.out, canvas)
    with open(args.out_yaml, "w") as f:
        f.write(
            "target_type: 'aprilgrid'\n"
            f"tagCols: {args.cols}\n"
            f"tagRows: {args.rows}\n"
            f"tagSize: {args.tag_size_mm / 1000.0}\n"
            f"tagSpacing: {args.tag_spacing_ratio}\n"
        )

    print(f"Wrote {args.out} ({grid_w}x{grid_h}px grid on a "
          f"{args.screen_width_px}x{args.screen_height_px}px canvas, ppi={ppi:.2f})")
    print(f"Wrote {args.out_yaml}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ruler = sub.add_parser("ruler", help="Generate a reference line to measure your screen's true PPI")
    p_ruler.add_argument("--screen-width-px", type=int, required=True)
    p_ruler.add_argument("--screen-height-px", type=int, required=True)
    p_ruler.add_argument("--length-px", type=int, default=1000)
    p_ruler.add_argument("--out", default="ruler.png")
    p_ruler.set_defaults(func=cmd_ruler)

    p_grid = sub.add_parser("grid", help="Generate the AprilGrid target image + Kalibr target.yaml")
    p_grid.add_argument("--screen-width-px", type=int, required=True)
    p_grid.add_argument("--screen-height-px", type=int, required=True)
    p_grid.add_argument("--rows", type=int, default=6)
    p_grid.add_argument("--cols", type=int, default=6)
    p_grid.add_argument("--tag-size-mm", type=float, default=30.0)
    p_grid.add_argument("--tag-spacing-ratio", type=float, default=0.3)
    p_grid.add_argument("--ppi", type=float, default=None, help="Use directly if already known (e.g. printer DPI)")
    p_grid.add_argument("--measured-mm", type=float, default=None,
                         help="Physical width you measured for the ruler line, in mm")
    p_grid.add_argument("--reference-px", type=int, default=1000,
                         help="Must match --length-px used for the ruler step")
    p_grid.add_argument("--out", default="target.png")
    p_grid.add_argument("--out-yaml", default="target.yaml")
    p_grid.set_defaults(func=cmd_grid)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
