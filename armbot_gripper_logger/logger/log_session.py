#!/usr/bin/env python3
"""
log_session.py — Host-side data logger for the ArmBot Gripper Data Logger.

Reads the CSV stream produced by firmware/armbot_logger.ino over USB
serial and offers three workflows:

  1. Manual trial   — Enter to start/stop capture while jogging by hand,
                       written straight to a per-trial CSV.
  2. Teach           — press the board's START button to mark a pose and
                       begin capture, press RECORD to stop; the motion is
                       saved as a reusable "program" (programs/<name>.csv).
  3. Replay          — drive the arm through a saved program's recorded
                       setpoints (firmware ignores the pots while doing
                       so), logging the run as a normal per-trial CSV so
                       it can be repeated against different objects.

Trial files follow the project's naming convention:

    {condition_label}_{scenario_id}_{object_id}_trial{NN}.csv

Usage:
    python log_session.py --port COM5           # Windows
    python log_session.py --port /dev/ttyUSB0   # Linux/Mac

Requires: pyserial   (pip install pyserial)
"""

import argparse
import csv
import datetime as dt
import sys
import threading
import time
from pathlib import Path

import serial

# Reference IDs — see README.md for full object/scenario descriptions.
OBJECT_IDS = ["OBJ-A", "OBJ-B", "OBJ-C", "OBJ-D", "OBJ-E", "OBJ-F"]
SCENARIO_IDS = ["SC-01", "SC-02", "SC-03", "SC-04", "SC-05"]
DEFAULT_CONDITION = "normal"

# Confirmed via firmware/tools/identify_axes.ino: Slot5 is wired on the
# board but not physically populated on this arm, so unused_deg streams
# but has no physical meaning.
AXIS_COLUMNS = ["base_deg", "shoulder_deg", "elbow_deg", "gripper_deg", "unused_deg"]
HEADER = (
    ["host_timestamp", "device_t_us", "trial_id", "object_id", "scenario_id",
     "condition_label"] + AXIS_COLUMNS + ["grip_state", "notes"]
)
# device_t_us + axes + grip_state + mode + record_btn + start_btn
EXPECTED_FIELDS = 1 + len(AXIS_COLUMNS) + 1 + 1 + 1 + 1


def prompt_choice(label: str, options: list) -> str:
    print(f"\n{label}:")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        raw = input(f"Select {label} [1-{len(options)}] or type a custom value: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw:
            return raw
        print("Please enter a value.")


def prompt_trial_meta() -> dict:
    object_id = prompt_choice("Object", OBJECT_IDS)
    scenario_id = prompt_choice("Scenario", SCENARIO_IDS)
    condition_label = input(
        f"Condition label [default: {DEFAULT_CONDITION}]: "
    ).strip() or DEFAULT_CONDITION
    return {"object_id": object_id, "scenario_id": scenario_id, "condition_label": condition_label}


def next_trial_id(out_dir: Path) -> int:
    """Simple incrementing trial counter based on files already in out_dir."""
    return len(list(out_dir.glob("*.csv"))) + 1


def trial_filename(trial_num: int, meta: dict) -> str:
    return f"{meta['condition_label']}_{meta['scenario_id']}_{meta['object_id']}_trial{trial_num:02d}.csv"


def read_serial_line(ser: serial.Serial):
    try:
        raw = ser.readline().decode("utf-8", errors="replace").strip()
    except serial.SerialException as exc:
        print(f"Serial read error: {exc}", file=sys.stderr)
        return None
    if not raw or raw.startswith("#"):
        return None
    return raw


def parse_row(line: str):
    """Parse one telemetry line from the firmware into a dict, or None if malformed."""
    parts = line.split(",")
    if len(parts) != EXPECTED_FIELDS:
        return None  # malformed/partial line, skip rather than corrupt the row
    n = len(AXIS_COLUMNS)
    return {
        "device_t_us": parts[0],
        "axis_vals": parts[1:1 + n],
        "grip_state": parts[1 + n],
        "mode": parts[1 + n + 1],
        "record_btn": parts[1 + n + 2] == "1",
        "start_btn": parts[1 + n + 3] == "1",
    }


def read_row(ser: serial.Serial):
    line = read_serial_line(ser)
    if line is None:
        return None
    return parse_row(line)


def build_trial_row(meta: dict, trial_id: str, row: dict) -> list:
    host_ts = dt.datetime.now().isoformat(timespec="milliseconds")
    return (
        [host_ts, row["device_t_us"], trial_id, meta["object_id"], meta["scenario_id"],
         meta["condition_label"]] + row["axis_vals"] + [row["grip_state"], ""]
    )


def write_trial_csv(rows: list, out_path: Path):
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"Saved {len(rows)} samples -> {out_path}")


def start_new_trial(out_dir: Path):
    """Prompt for trial metadata and return (trial_id, out_path)."""
    meta = prompt_trial_meta()
    trial_num = next_trial_id(out_dir)
    trial_id = f"T{trial_num:04d}"
    out_path = out_dir / trial_filename(trial_num, meta)
    return meta, trial_id, out_path


def run_manual_trial(ser: serial.Serial, out_dir: Path):
    meta, trial_id, out_path = start_new_trial(out_dir)

    print("Press ENTER to START capturing this trial...")
    input()
    print("Capturing... move the arm through the scenario now.")
    print("Press ENTER again to STOP.")

    rows = []
    ser.reset_input_buffer()
    stop_flag = {"stop": False}

    def wait_for_stop():
        input()
        stop_flag["stop"] = True

    t = threading.Thread(target=wait_for_stop, daemon=True)
    t.start()

    while not stop_flag["stop"]:
        row = read_row(ser)
        if row is None:
            continue
        rows.append(build_trial_row(meta, trial_id, row))

    write_trial_csv(rows, out_path)


def run_teach(ser: serial.Serial, programs_dir: Path):
    print("\nTeach a new procedure.")
    print("Position the arm at the desired START pose, then press the")
    print("START button on the control board.")

    ser.reset_input_buffer()

    # Wait for a start_btn rising edge; the row that carries it becomes the
    # trajectory's t=0 pose.
    prev_start = False
    first_row = None
    while first_row is None:
        row = read_row(ser)
        if row is None:
            continue
        if row["start_btn"] and not prev_start:
            first_row = row
        prev_start = row["start_btn"]

    print("Recording... perform the maneuver now.")
    print("Press RECORD on the control board to finish.")

    t0_us = int(first_row["device_t_us"])
    traj_rows = [first_row]
    prev_record = first_row["record_btn"]

    while True:
        row = read_row(ser)
        if row is None:
            continue
        traj_rows.append(row)
        if row["record_btn"] and not prev_record:
            break
        prev_record = row["record_btn"]

    name = input("Program name [default: program]: ").strip() or "program"
    programs_dir.mkdir(parents=True, exist_ok=True)
    out_path = programs_dir / f"{name}.csv"

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t_ms"] + AXIS_COLUMNS + ["grip_state"])
        for row in traj_rows:
            t_ms = (int(row["device_t_us"]) - t0_us) / 1000.0
            writer.writerow([f"{t_ms:.1f}"] + row["axis_vals"] + [row["grip_state"]])

    print(f"Saved {len(traj_rows)} samples -> {out_path}")


def load_program(path: Path) -> list:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        return list(reader)


def run_replay(ser: serial.Serial, programs_dir: Path, out_dir: Path):
    programs = sorted(programs_dir.glob("*.csv"))
    if not programs:
        print(f"No saved programs found in {programs_dir}. Teach one first (menu option 2).")
        return

    chosen_name = prompt_choice("Program to replay", [p.name for p in programs])
    chosen_path = programs_dir / chosen_name
    if not chosen_path.is_file():
        print(f"No such program: {chosen_path}")
        return

    traj = load_program(chosen_path)
    if not traj:
        print("Selected program is empty, nothing to replay.")
        return

    meta, trial_id, out_path = start_new_trial(out_dir)

    input("Position/attach the object, then press ENTER to start replay...")
    ser.reset_input_buffer()
    ser.write(b"P\n")

    rows = []
    aborted = False
    start_time = time.monotonic()

    for traj_row in traj:
        t_ms = float(traj_row[0])
        axis_vals = traj_row[1:1 + len(AXIS_COLUMNS)]

        target_time = start_time + t_ms / 1000.0
        now = time.monotonic()
        if target_time > now:
            time.sleep(target_time - now)

        ser.write((",".join(axis_vals) + "\n").encode())

        while ser.in_waiting:
            row = read_row(ser)
            if row is None:
                continue
            rows.append(build_trial_row(meta, trial_id, row))
            if row["mode"] != "P":
                aborted = True
                break
        if aborted:
            break

    if aborted:
        print("Playback aborted (RECORD pressed on the board). Saving partial trial.")
    else:
        # Drain any telemetry still in flight for the final setpoint, then
        # hand control back to the pots.
        time.sleep(0.1)
        while ser.in_waiting:
            row = read_row(ser)
            if row is not None:
                rows.append(build_trial_row(meta, trial_id, row))
        ser.write(b"M\n")
        print("Replay complete, arm handed back to manual control.")

    write_trial_csv(rows, out_path)


def main():
    parser = argparse.ArgumentParser(description="ArmBot gripper data logger")
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--out", default="data", help="Output directory for trial CSV files")
    parser.add_argument("--programs", default="programs", help="Output directory for taught programs")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    programs_dir = Path(args.programs)
    programs_dir.mkdir(parents=True, exist_ok=True)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print(f"Could not open serial port {args.port}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Connected to {args.port} @ {args.baud} baud. Trials -> {out_dir.resolve()}, Programs -> {programs_dir.resolve()}")

    try:
        while True:
            print("\n1) Manual trial (Enter to start/stop)")
            print("2) Teach a new procedure (Start/Record buttons)")
            print("3) Replay a saved procedure")
            print("4) Quit")
            choice = input("Choose [1-4]: ").strip()

            if choice == "1":
                run_manual_trial(ser, out_dir)
            elif choice == "2":
                run_teach(ser, programs_dir)
            elif choice == "3":
                run_replay(ser, programs_dir, out_dir)
            elif choice in ("4", "q", "Q"):
                break
            else:
                print("Please enter 1, 2, 3, or 4.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        ser.close()
        print("Serial port closed.")


if __name__ == "__main__":
    main()
