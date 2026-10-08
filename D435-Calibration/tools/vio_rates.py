#!/usr/bin/env python3
"""Print VIO pipeline topic rates every few seconds (window 6 of 07_start_vio.sh).

One long-lived node that only counts messages (raw subscriptions, nothing is deserialized). It replaces a
loop of `ros2 topic hz` calls: each call took ~85 % of a core on the Pi 5 for several seconds, enough to
push OpenVINS frame times from ~6 to ~36 ms. Camera topics are left out on purpose -- just receiving a
640x480 image stream costs 50-85 % of a core here.

  python3 vio_rates.py [--ros-args -p period_s:=5.0]
"""
import time

import rclpy
from nav_msgs.msg import Odometry
from px4_msgs.msg import SensorCombined, VehicleOdometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu

# topic, type, best_effort, expected rate
TOPICS = [
    ('/fmu/out/sensor_combined', SensorCombined, True, '~100 Hz'),
    ('/calib/imu', Imu, False, '~100 Hz'),
    ('/ov_msckf/odomimu', Odometry, False, '30-100 Hz once initialised'),
    ('/fmu/in/vehicle_visual_odometry', VehicleOdometry, True, 'same as odomimu; 0 = bridge dropping a diverged estimate'),
]


class VioRates(Node):
    def __init__(self):
        super().__init__('vio_rates')
        self.declare_parameter('period_s', 5.0)
        self.counts = {t: 0 for t, *_ in TOPICS}
        for topic, msg_type, best_effort, _ in TOPICS:
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT if best_effort
                             else ReliabilityPolicy.RELIABLE)
            self.create_subscription(msg_type, topic, lambda _, t=topic: self._count(t), qos, raw=True)
        self.t0 = time.monotonic()
        self.create_timer(float(self.get_parameter('period_s').value), self._print)

    def _count(self, topic):
        self.counts[topic] += 1

    def _print(self):
        now = time.monotonic()
        dt, self.t0 = now - self.t0, now
        print(f"\nVIO pipeline rates ({time.strftime('%T')}, cameras not checked -- see tools/vio_rates.py):")
        for topic, _, _, expected in TOPICS:
            n, self.counts[topic] = self.counts[topic], 0
            print(f"  {topic:34s} {n / dt:6.1f} Hz   (expected {expected})" if n else
                  f"  {topic:34s}  NO DATA   (expected {expected})")
        print('On the FC (QGC MAVLink console): listener estimator_status_flags (cs_ev_pos)', flush=True)


def main():
    rclpy.init()
    node = VioRates()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
