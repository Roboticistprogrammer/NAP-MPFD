Familirization with IsaacLab environment for creating synthetic data and training DRL algorithm for Gripper-UAV project:

https://isaac-sim.github.io/IsaacLab/main/source/setup/walkthrough/training_jetbot_reward_exploration.html
https://isaac-sim.github.io/IsaacLab/main/source/tutorials/03_envs/create_manager_rl_env.html#the-code
https://isaac-sim.github.io/IsaacLab/main/source/tutorials/03_envs/run_rl_training.html


### Hardware Interconnects

FC to RPi: Connected via Telemetry (UART) using the MAVLink protocol. The RPi reads drone vitals (vibration/battery) from the FC while sending movement commands.
RPi to Armbot: Usually connected via USB or UART depending on your servo controller (e.g., a Dynamixel U2D2 or a PCA9685 PWM driver).

#### Edge-Based Sensor Network Configuration

To mimic the "Edge-Based" methodology of Ong et al., the UAV-mounted Armbot utilizes a local sensor suite connected to a Raspberry Pi companion computer. These sensors provide the real-time data required for the State Vector ($S_t$) in the Deep Reinforcement Learning framework.

#### Hardware Architecture Note:
All telemetry is aggregated at the **Raspberry Pi (Edge Node)**. The Flight Controller (FC) communicates via **MAVLink** over a **UART** serial bridge, while the health sensors are daisy-chained on the **I2C bus** to minimize wiring complexity on the UAV frame.

| Sensor | Purpose (State Vector $S_t$) | Connection / Bus | Why for Predictive Maintenance (PdM)? |
| :--- | :--- | :--- | :--- |
| **INA219 / ACS712** | Measures Servo Current | **I2C** (to RPi) | Spikes in current indicate mechanical resistance, friction increase, or "seizing" in gripper joints. |
| **MPU6050 / ADXL345** | Measures Gripper Vibration | **I2C** (to RPi) | High-frequency jitter at the gripper tip suggests loose bolts, gear wear, or structural fatigue. |
| **DHT22 / DS18B20** | Motor/ESC Temperature | **I2C or One-Wire** | Overheating is a primary thermal indicator of impending electronic failure or motor coil degradation. |
| **BNO055** | Absolute Arm Orientation | **I2C** (to RPi) | Detects "sagging" or precision loss where the arm fails to reach commanded coordinates. |
| **FC Internal IMU** | Drone Stability Vitals | **MAVLink (UART)** | Allows the DRL agent to filter out environmental "noise" (wind/turbulence) from actual gripper mechanical issues. |

