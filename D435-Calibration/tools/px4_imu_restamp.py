#!/usr/bin/env python3
"""Republish PX4's /fmu/out/sensor_combined as sensor_msgs/Imu stamped on the HOST clock.

Why this exists (instead of reusing nap_px4_bridge's /d435i/imu):
    PX4's `timestamp` is microseconds since FC boot, while realsense2_camera stamps
    images with host (system) time. Kalibr needs both streams on one clock -- it only
    refines a *small* residual time offset, it cannot bridge a ~1.7e9 s gap.

How:
    offset = min(host_receive_time - px4_timestamp) over a warm-up window.
    The minimum is the sample with the least transport latency, so
    `px4_timestamp + offset` keeps PX4's exact sample spacing (no jitter from
    DDS/serial delivery) and lands within a few ms of true host time. Kalibr's
    time-offset estimate then absorbs what is left (latency floor + PX4 filter delay).

    The offset is frozen after warm-up so there are no jumps inside a recording;
    clock drift is monitored and reported instead.

Frame: PX4 FRD body frame, passed through unchanged (same as nap_px4_bridge), so
the resulting T_cam_imu is directly valid for the /d435i/imu feed OpenVINS uses.
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time

from px4_msgs.msg import SensorCombined
from sensor_msgs.msg import Imu

# PX4 /fmu/out/* publishers are BEST_EFFORT; a RELIABLE subscriber silently receives nothing.
PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=50,
)


class Px4ImuRestamp(Node):
    def __init__(self):
        super().__init__('px4_imu_restamp')
        self.declare_parameter('output_topic', '/calib/imu')
        self.declare_parameter('frame_id', 'px4_imu')
        self.declare_parameter('warmup_samples', 500)       # ~5 s at 100 Hz
        self.declare_parameter('drift_warn_ms', 2.0)

        self.frame_id = self.get_parameter('frame_id').value
        self.warmup_samples = int(self.get_parameter('warmup_samples').value)
        self.drift_warn_ns = int(self.get_parameter('drift_warn_ms').value * 1e6)

        self.pub = self.create_publisher(Imu, self.get_parameter('output_topic').value, 1000)
        self.create_subscription(SensorCombined, '/fmu/out/sensor_combined', self._on_msg, PX4_QOS)

        self.n_warmup = 0
        self.offset_ns = None          # frozen host - px4 offset
        self.warmup_min_ns = None
        self.window_min_ns = None      # min latency in the current monitoring window
        self.window_count = 0
        self.last_px4_us = None
        self.n_pub = 0
        self.n_dropped = 0

        self.get_logger().info(
            f'waiting for /fmu/out/sensor_combined (warm-up {self.warmup_samples} samples)...')

    def _on_msg(self, msg: SensorCombined):
        host_ns = self.get_clock().now().nanoseconds
        px4_ns = int(msg.timestamp) * 1000
        delta = host_ns - px4_ns

        # Non-monotonic / duplicate samples break Kalibr's spline fit -- drop them.
        if self.last_px4_us is not None and msg.timestamp <= self.last_px4_us:
            self.n_dropped += 1
            return
        self.last_px4_us = msg.timestamp

        if self.offset_ns is None:
            self.warmup_min_ns = delta if self.warmup_min_ns is None else min(self.warmup_min_ns, delta)
            self.n_warmup += 1
            if self.n_warmup >= self.warmup_samples:
                self.offset_ns = self.warmup_min_ns
                self.get_logger().info(
                    f'offset frozen: host - px4 = {self.offset_ns / 1e9:.6f} s '
                    f'({"PX4 already on host epoch" if abs(self.offset_ns) < 1e9 else "PX4 boot clock"}). '
                    f'Publishing IMU now.')
            return

        # Drift monitor: residual latency of the best sample per ~10 s window should stay ~0.
        residual = delta - self.offset_ns
        self.window_min_ns = residual if self.window_min_ns is None else min(self.window_min_ns, residual)
        self.window_count += 1
        if self.window_count >= 1000:
            report = (f'published {self.n_pub}, dropped {self.n_dropped}, '
                      f'min residual latency {self.window_min_ns / 1e6:+.2f} ms')
            # separate call sites: rclpy forbids changing severity at one call site
            if abs(self.window_min_ns) > self.drift_warn_ns:
                self.get_logger().warn(report + ' -- clock drift, restart before recording')
            else:
                self.get_logger().info(report)
            self.window_min_ns = None
            self.window_count = 0

        imu = Imu()
        imu.header.stamp = Time(nanoseconds=px4_ns + self.offset_ns).to_msg()
        imu.header.frame_id = self.frame_id
        imu.angular_velocity.x = float(msg.gyro_rad[0])
        imu.angular_velocity.y = float(msg.gyro_rad[1])
        imu.angular_velocity.z = float(msg.gyro_rad[2])
        imu.linear_acceleration.x = float(msg.accelerometer_m_s2[0])
        imu.linear_acceleration.y = float(msg.accelerometer_m_s2[1])
        imu.linear_acceleration.z = float(msg.accelerometer_m_s2[2])
        imu.orientation_covariance[0] = -1.0   # no orientation estimate (REP 145)
        if msg.accelerometer_clipping or msg.gyro_clipping:
            self.get_logger().warn('IMU clipping -- move less violently', throttle_duration_sec=1.0)
        self.pub.publish(imu)
        self.n_pub += 1


def main():
    rclpy.init()
    node = Px4ImuRestamp()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
