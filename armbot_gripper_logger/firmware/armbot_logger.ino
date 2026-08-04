/*
  ArmBot Gripper Data Logger — Firmware
  =======================================
  Reads potentiometer positions (manual jog control) for 5 axes on the
  JSumo ArmBot Control Board, drives the corresponding servos, and streams
  timestamped commanded-angle and derived grip-state data over USB serial
  for logging by log_session.py on the host PC.

  This is a Tier-1 (open-loop) logger: it records the COMMANDED angle sent
  to each servo, not a measured/actual joint angle, since the stock 9g
  servos on this kit are not feedback-capable. See README.md for details.

  Modes
  -----
  MANUAL (default): servos follow the potentiometers, exactly like a plain
  jog controller. This is how a "teach" demonstration is performed.

  PLAYBACK: servos ignore the pots and instead follow angle setpoints sent
  by the host over serial ("a1,a2,a3,a4,a5\n"), one line per desired pose.
  Used by log_session.py to replay a previously taught trajectory against a
  new object. Host switches modes with a single-character command line:
  "M" -> manual, "P" -> playback.

  Buttons (see Armbot_control_board.jpeg silkscreen)
  ----------------------------------------------------
  RECORD_BUTTON_PIN (D13) and START_BUTTON_PIN (A1) are read every loop and
  their debounced state is streamed with every telemetry line so the host
  can detect press edges itself (no on-device event queue needed). As a
  safety measure, pressing RECORD while in PLAYBACK mode immediately aborts
  back to MANUAL — a physical kill switch during autonomous replay.

  AXIS MAPPING (confirmed via firmware/tools/identify_axes.ino):
  Slot1=base, Slot2=shoulder, Slot3=elbow, Slot4=gripper, Slot5=unused
  (5th servo slot is wired on the board but not physically populated on
  this arm — its column will still stream but has no physical meaning).

  GRIPPER KINEMATICS (confirmed by hand-jogging + Serial Monitor):
  this gripper is NOT a simple one-directional jaw servo. It's OPEN at
  BOTH travel extremes (~0 deg and ~180 deg) and fully CLOSED at the
  midpoint (~96 deg) — consistent with a linkage-driven mechanism rather
  than a direct jaw actuator. grip_state is therefore derived from
  distance-from-center, not a simple low/high threshold. The exact
  GRIPPER_CLOSE_TOL_DEG / GRIPPER_OPEN_MARGIN_DEG band below are estimates
  — refine after watching grip_state track a real grasp.
*/

#include <Servo.h>

// ---------------------- Configuration ----------------------

const uint8_t NUM_AXES = 5;

const char* AXIS_NAMES[NUM_AXES] = {"base", "shoulder", "elbow", "gripper", "unused"};

// Confirmed against the board silkscreen (D12..D8 -> Servo1..5,
// A2/A3/A4/A7/A6 -> Pot Servo1..5) and against Setup-ArduinoNano.ino.
const uint8_t POT_PINS[NUM_AXES]   = {A2, A3, A4, A7, A6};
const uint8_t SERVO_PINS[NUM_AXES] = {12, 11, 10, 9, 8};

const uint8_t RECORD_BUTTON_PIN = 13; // Button 1 (Record), active LOW
const uint8_t START_BUTTON_PIN  = A1; // Button 2 (Start), active LOW
const unsigned long DEBOUNCE_MS = 25;

// Per-axis servo travel limits (degrees). Adjust to your arm's safe range
// to avoid commanding the servo into a mechanical hard stop.
const int SERVO_MIN_DEG[NUM_AXES] = {0, 0, 0, 0, 0};
const int SERVO_MAX_DEG[NUM_AXES] = {180, 180, 180, 180, 180};

const uint8_t GRIPPER_AXIS = 3; // Slot4 (0-based index)
// Gripper is open at both travel extremes and closed at the midpoint (see
// note above) — grip_state is derived from |angle - CENTER|, not a simple
// low/high split.
const int GRIPPER_CLOSE_CENTER_DEG = 96;  // angle at which jaws are fully closed
const int GRIPPER_CLOSE_TOL_DEG    = 12;  // within this of center = "closed"
const int GRIPPER_OPEN_MARGIN_DEG  = 25;  // within this of either extreme (0/180) = "open"
const int GRIP_HYSTERESIS_DEG      = 2;   // ignore jitter smaller than this

const unsigned long SAMPLE_INTERVAL_MS = 20; // 50 Hz
const long BAUD_RATE = 115200;
// -------------------------------------------------------------

enum Mode { MODE_MANUAL, MODE_PLAYBACK };

Servo servos[NUM_AXES];
int angles[NUM_AXES];
int lastGripperAngle = 90;
Mode mode = MODE_MANUAL;
unsigned long lastSampleMs = 0;

// Debounce state per button.
bool debouncedRecordState = false, lastRawRecordState = false;
bool debouncedStartState  = false, lastRawStartState  = false;
unsigned long lastRecordChangeMs = 0, lastStartChangeMs = 0;

// Incoming serial command buffer.
char cmdBuf[32];
uint8_t cmdLen = 0;

bool updateDebounced(bool rawState, bool &lastRawState, bool &debouncedState,
                      unsigned long &lastChangeMs) {
  unsigned long now = millis();
  if (rawState != lastRawState) {
    lastChangeMs = now;
    lastRawState = rawState;
  }
  if ((now - lastChangeMs) > DEBOUNCE_MS) {
    debouncedState = rawState;
  }
  return debouncedState;
}

const char* gripStateFromAngle(int angle, int prevAngle) {
  int dist = abs(angle - GRIPPER_CLOSE_CENTER_DEG);
  int prevDist = abs(prevAngle - GRIPPER_CLOSE_CENTER_DEG);

  if (dist <= GRIPPER_CLOSE_TOL_DEG) return "closed";
  if (angle <= GRIPPER_OPEN_MARGIN_DEG || angle >= 180 - GRIPPER_OPEN_MARGIN_DEG) return "open";
  if (dist < prevDist - GRIP_HYSTERESIS_DEG) return "closing";
  if (dist > prevDist + GRIP_HYSTERESIS_DEG) return "opening";
  return "holding";
}

void applySetpointLine(char* line) {
  int values[NUM_AXES];
  uint8_t count = 0;
  char* tok = strtok(line, ",");
  while (tok != NULL && count < NUM_AXES) {
    values[count++] = atoi(tok);
    tok = strtok(NULL, ",");
  }
  if (count != NUM_AXES) return; // malformed, ignore

  for (uint8_t i = 0; i < NUM_AXES; i++) {
    int deg = constrain(values[i], SERVO_MIN_DEG[i], SERVO_MAX_DEG[i]);
    angles[i] = deg;
    servos[i].write(deg);
  }
}

void handleCommandLine(char* line) {
  if (line[0] == 'M' && line[1] == '\0') {
    mode = MODE_MANUAL;
  } else if (line[0] == 'P' && line[1] == '\0') {
    mode = MODE_PLAYBACK;
  } else if (mode == MODE_PLAYBACK) {
    applySetpointLine(line);
  }
}

void pollSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) {
        cmdBuf[cmdLen] = '\0';
        handleCommandLine(cmdBuf);
        cmdLen = 0;
      }
    } else if (cmdLen < sizeof(cmdBuf) - 1) {
      cmdBuf[cmdLen++] = c;
    }
  }
}

void setup() {
  Serial.begin(BAUD_RATE);

  pinMode(RECORD_BUTTON_PIN, INPUT_PULLUP);
  pinMode(START_BUTTON_PIN, INPUT_PULLUP);

  // Read initial knob positions before attaching the servos, so the arm
  // doesn't jump on power-up.
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    int raw = analogRead(POT_PINS[i]);
    angles[i] = map(raw, 0, 1023, SERVO_MIN_DEG[i], SERVO_MAX_DEG[i]);
  }

  for (uint8_t i = 0; i < NUM_AXES; i++) {
    servos[i].attach(SERVO_PINS[i]);
    servos[i].write(angles[i]);
  }

  // Lines starting with '#' are treated as comments/headers by
  // log_session.py and are not written into the CSV data.
  Serial.println("# ArmBot Gripper Logger firmware v2.0");
  Serial.print("# columns: device_t_us");
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    Serial.print(',');
    Serial.print(AXIS_NAMES[i]);
    Serial.print("_deg");
  }
  Serial.println(",grip_state,mode,record_btn,start_btn");
}

void loop() {
  // Buttons and host commands are serviced every loop iteration so a
  // playback abort or setpoint isn't delayed by the 20ms sample gate below.
  bool recordPressed = updateDebounced(digitalRead(RECORD_BUTTON_PIN) == LOW,
                                        lastRawRecordState, debouncedRecordState,
                                        lastRecordChangeMs);
  updateDebounced(digitalRead(START_BUTTON_PIN) == LOW,
                   lastRawStartState, debouncedStartState, lastStartChangeMs);

  if (mode == MODE_PLAYBACK && recordPressed) {
    mode = MODE_MANUAL; // physical kill switch during autonomous replay
  }

  pollSerialCommands();

  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;

  if (mode == MODE_MANUAL) {
    for (uint8_t i = 0; i < NUM_AXES; i++) {
      int raw = analogRead(POT_PINS[i]); // 0-1023
      int deg = map(raw, 0, 1023, SERVO_MIN_DEG[i], SERVO_MAX_DEG[i]);
      servos[i].write(deg);
      angles[i] = deg;
    }
  }
  // In PLAYBACK mode, angles[] was already updated (and servos written) by
  // applySetpointLine() as setpoints arrived; just report the current state.

  const char* gripState = gripStateFromAngle(angles[GRIPPER_AXIS], lastGripperAngle);
  lastGripperAngle = angles[GRIPPER_AXIS];

  // device_t_us wraps around ~every 70 minutes (unsigned long overflow of
  // micros()); keep individual trials well under that window.
  Serial.print(micros());
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    Serial.print(',');
    Serial.print(angles[i]);
  }
  Serial.print(',');
  Serial.print(gripState);
  Serial.print(',');
  Serial.print(mode == MODE_MANUAL ? 'M' : 'P');
  Serial.print(',');
  Serial.print(debouncedRecordState ? 1 : 0);
  Serial.print(',');
  Serial.println(debouncedStartState ? 1 : 0);
}
