#!/usr/bin/env python3
"""
app.py — Local web GUI for jogging the ArmBot's servo angles over the
same USB-serial link used by ../logger/log_session.py, against the
unmodified ../firmware/armbot_logger.ino protocol.

Run on the RPi5 (wherever the Arduino Nano is actually plugged in), then
open the page from your laptop's browser over the LAN:

    python3 app.py --port /dev/ttyUSB0
    # -> http://<rpi-ip>:5000

Protocol recap (see ../firmware/armbot_logger.ino):
  - Firmware streams one CSV telemetry line per sample (~50 Hz):
    device_t_us,base_deg,shoulder_deg,elbow_deg,gripper_deg,unused_deg,
    grip_state,mode,record_btn,start_btn
  - "M\n" / "P\n" switch the firmware between MANUAL (servos follow the
    board's potentiometers) and PLAYBACK (servos follow setpoints sent
    over serial).
  - In PLAYBACK mode, "a1,a2,a3,a4,a5\n" (degrees, one line per pose)
    drives the five servos directly. The physical RECORD button aborts
    back to MANUAL at any time (firmware-side kill switch).

This GUI only ever writes setpoints while the operator has explicitly
enabled playback control, and it seeds the sliders from the last-known
telemetry angles first, so enabling control never jumps the arm.

Requires: flask, pyserial (pip install flask pyserial)
"""

import argparse
import sys
import threading
import time

import serial
from flask import Flask, jsonify, render_template, request

AXIS_NAMES = ["base", "shoulder", "elbow", "gripper", "unused"]
GRIPPER_AXIS = 3
EXPECTED_FIELDS = 1 + len(AXIS_NAMES) + 1 + 1 + 1 + 1  # t_us + axes + grip_state + mode + record + start

app = Flask(__name__)

state_lock = threading.Lock()
state = {
    "connected": False,
    "angles": [90, 90, 90, 90, 90],
    "grip_state": "unknown",
    "mode": "M",
    "record_btn": False,
    "start_btn": False,
    "last_update": 0.0,
}

ser: serial.Serial = None
ser_lock = threading.Lock()


def parse_telemetry_line(line: str):
    parts = line.split(",")
    if len(parts) != EXPECTED_FIELDS:
        return None
    try:
        angles = [int(p) for p in parts[1:1 + len(AXIS_NAMES)]]
    except ValueError:
        return None
    return {
        "angles": angles,
        "grip_state": parts[1 + len(AXIS_NAMES)],
        "mode": parts[2 + len(AXIS_NAMES)],
        "record_btn": parts[3 + len(AXIS_NAMES)] == "1",
        "start_btn": parts[4 + len(AXIS_NAMES)] == "1",
    }


def serial_reader_loop(port: str, baud: int):
    global ser
    while True:
        try:
            with ser_lock:
                ser = serial.Serial(port, baud, timeout=1)
            with state_lock:
                state["connected"] = True
            print(f"Connected to {port} @ {baud} baud.")
            while True:
                raw = ser.readline().decode("utf-8", errors="replace").strip()
                if not raw or raw.startswith("#"):
                    continue
                parsed = parse_telemetry_line(raw)
                if parsed is None:
                    continue
                with state_lock:
                    state.update(parsed)
                    state["last_update"] = time.time()
        except serial.SerialException as exc:
            with state_lock:
                state["connected"] = False
            print(f"Serial error ({exc}); retrying in 2s...", file=sys.stderr)
            time.sleep(2)


@app.route("/")
def index():
    return render_template("index.html", axis_names=AXIS_NAMES, gripper_axis=GRIPPER_AXIS)


@app.route("/api/state")
def api_state():
    with state_lock:
        return jsonify(dict(state))


@app.route("/api/mode", methods=["POST"])
def api_mode():
    mode = request.json.get("mode")
    if mode not in ("M", "P"):
        return jsonify({"error": "mode must be 'M' or 'P'"}), 400
    with ser_lock:
        if ser is None or not ser.is_open:
            return jsonify({"error": "not connected"}), 503
        ser.write(f"{mode}\n".encode())
    return jsonify({"ok": True})


@app.route("/api/setpoint", methods=["POST"])
def api_setpoint():
    angles = request.json.get("angles")
    if not isinstance(angles, list) or len(angles) != len(AXIS_NAMES):
        return jsonify({"error": f"angles must be a list of {len(AXIS_NAMES)} integers"}), 400
    try:
        clamped = [max(0, min(180, int(a))) for a in angles]
    except (TypeError, ValueError):
        return jsonify({"error": "angles must be integers"}), 400
    with ser_lock:
        if ser is None or not ser.is_open:
            return jsonify({"error": "not connected"}), 503
        ser.write((",".join(str(a) for a in clamped) + "\n").encode())
    return jsonify({"ok": True})


def main():
    parser = argparse.ArgumentParser(description="ArmBot gripper GUI (local web app)")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address for the web server")
    parser.add_argument("--http-port", type=int, default=5000)
    args = parser.parse_args()

    reader = threading.Thread(
        target=serial_reader_loop, args=(args.port, args.baud), daemon=True
    )
    reader.start()

    app.run(host=args.host, port=args.http_port)


if __name__ == "__main__":
    main()
