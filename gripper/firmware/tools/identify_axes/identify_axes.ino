/*
  identify_axes.ino — one-time hardware test, not part of the logger.

  Purpose: find out which physical joint each of the 5 wired servo/pot
  slots actually drives, before trusting AXIS_NAMES / GRIPPER_AXIS in
  firmware/armbot_logger.ino. This board wires 5 slots but this arm only
  has 4 servos physically populated, so one slot is expected to move
  nothing.

  How to use:
    1. Upload this sketch (Arduino IDE, board = Nano).
    2. Open Serial Monitor at 115200 baud.
    3. Turn ONE knob at a time, slowly, and watch which joint on the arm
       moves. Note it down, e.g. "Slot1 = base".
    4. Repeat for slots 2-5. One slot should visibly do nothing (the
       unpopulated servo) — note that too.
    5. Transfer the resulting order into AXIS_NAMES / GRIPPER_AXIS in
       firmware/armbot_logger.ino, then re-upload the real logger sketch.

  Behavior mirrors normal operation (each pot drives its matching servo
  1:1) so it's safe to leave the arm assembled while testing.
*/

#include <Servo.h>

const uint8_t NUM_SLOTS = 5;
const uint8_t POT_PINS[NUM_SLOTS]   = {A2, A3, A4, A7, A6};
const uint8_t SERVO_PINS[NUM_SLOTS] = {12, 11, 10, 9, 8};

Servo servos[NUM_SLOTS];
const unsigned long PRINT_INTERVAL_MS = 500;
unsigned long lastPrintMs = 0;

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < NUM_SLOTS; i++) {
    servos[i].attach(SERVO_PINS[i]);
  }
  Serial.println("# identify_axes: turn one knob at a time, note which joint moves");
}

void loop() {
  int angle[NUM_SLOTS];
  for (uint8_t i = 0; i < NUM_SLOTS; i++) {
    int raw = analogRead(POT_PINS[i]);
    angle[i] = map(raw, 0, 1023, 0, 180);
    servos[i].write(angle[i]);
  }

  unsigned long now = millis();
  if (now - lastPrintMs < PRINT_INTERVAL_MS) {
    return;
  }
  lastPrintMs = now;

  for (uint8_t i = 0; i < NUM_SLOTS; i++) {
    Serial.print("Slot");
    Serial.print(i + 1);
    Serial.print('=');
    if (angle[i] < 100) Serial.print('0');
    if (angle[i] < 10) Serial.print('0');
    Serial.print(angle[i]);
    Serial.print("  ");
  }
  Serial.println();
}
