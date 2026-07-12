#include <Servo.h>

const uint8_t SERVO_PINS[5] = {12, 11, 10, 9, 8};
const uint8_t POT_PINS[5]   = {A2, A3, A4, A7, A6};

const uint8_t RECORD_BUTTON_PIN = 13;
const uint8_t START_BUTTON_PIN = A1;

Servo servos[5];

const unsigned long CONTROL_INTERVAL_MS = 20;
unsigned long previousControlTime = 0;

int filteredPot[5] = {512, 512, 512, 512, 512};

void setup() {
  Serial.begin(115200);

  pinMode(RECORD_BUTTON_PIN, INPUT_PULLUP);
  pinMode(START_BUTTON_PIN, INPUT_PULLUP);

  // Read initial knob positions before attaching the servos.
  for (uint8_t i = 0; i < 5; i++) {
    filteredPot[i] = analogRead(POT_PINS[i]);
  }

  for (uint8_t i = 0; i < 5; i++) {
    servos[i].attach(SERVO_PINS[i]);

    int initialAngle = map(filteredPot[i], 0, 1023, 10, 170);
    servos[i].write(initialAngle);
  }

  delay(1000);

  Serial.println(
    "time_ms,joint1_cmd,joint2_cmd,joint3_cmd,joint4_cmd,joint5_cmd,"
    "pot1_raw,pot2_raw,pot3_raw,pot4_raw,pot5_raw,"
    "record_button,start_button"
  );
}

void loop() {
  unsigned long now = millis();

  if (now - previousControlTime < CONTROL_INTERVAL_MS) {
    return;
  }

  previousControlTime = now;

  int commandAngle[5];

  for (uint8_t i = 0; i < 5; i++) {
    int newReading = analogRead(POT_PINS[i]);

    // Simple low-pass filter to reduce potentiometer noise.
    filteredPot[i] = (filteredPot[i] * 7 + newReading) / 8;

    commandAngle[i] = map(filteredPot[i], 0, 1023, 10, 170);
    commandAngle[i] = constrain(commandAngle[i], 10, 170);

    servos[i].write(commandAngle[i]);
  }

  Serial.print(now);

  for (uint8_t i = 0; i < 5; i++) {
    Serial.print(',');
    Serial.print(commandAngle[i]);
  }

  for (uint8_t i = 0; i < 5; i++) {
    Serial.print(',');
    Serial.print(filteredPot[i]);
  }

  Serial.print(',');
  Serial.print(digitalRead(RECORD_BUTTON_PIN));

  Serial.print(',');
  Serial.println(digitalRead(START_BUTTON_PIN));
}
