// mavlink_rc_servo.ino
// Reads RC toggle channel from MAVLink (Pixhawk) and controls servo

#include <mavlink.h>  // MAVLink library
#include <Servo.h>

Servo gripperServo;  // Servo object
const int servoPin = 9;  // Servo signal pin
const int toggleChannel = 6;  // Assume RC toggle on Channel 6 (change as needed)
uint16_t rcValue = 0;  // Store RC PWM value

void setup() {
  gripperServo.attach(servoPin);
  Serial.begin(57600);  // MAVLink baud rate (match Pixhawk TELEM2)
}

void loop() {
  mavlink_message_t msg;
  mavlink_status_t status;

  // Read incoming serial data from Pixhawk
  while (Serial.available() > 0) {
    uint8_t c = Serial.read();
    if (mavlink_parse_char(MAVLINK_COMM_0, c, &msg, &status)) {
      // Handle RC_CHANNELS_RAW message
      if (msg.msgid == MAVLINK_MSG_ID_RC_CHANNELS_RAW) {
        mavlink_rc_channels_raw_t rc;
        mavlink_msg_rc_channels_raw_decode(&msg, &rc);
        
        // Get the toggle channel value (e.g., chan6_raw for Channel 6)
        switch (toggleChannel) {
          case 5: rcValue = rc.chan5_raw; break;
          case 6: rcValue = rc.chan6_raw; break;
          // Add cases for other channels if needed
          default: rcValue = 0;
        }
        
        // Control servo based on RC value
        if (rcValue > 1500) {  // Toggle ON
          gripperServo.write(180);  // Open
        } else {
          gripperServo.write(0);  // Close
        }
      }
    }
  }
}