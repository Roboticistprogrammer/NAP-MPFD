import rclpy
import rclpy.time
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from nav_msgs.msg import Odometry
from px4_msgs.msg import SensorCombined, VehicleOdometry
from sensor_msgs.msg import Imu

# Standard MAVROS/PX4-ecosystem static rotation quaternion for the ENU(world)->NED(world)
# axis change (roll=pi, pitch=0, yaw=pi/2), in ROS xyzw order. No body-frame (FLU->FRD)
# term is needed here -- see the module docstring on why.
_Q_NED_ENU_XYZW = (0.70710678, 0.70710678, 0.0, 0.0)

# PX4's /fmu/out/* publishers and /fmu/in/* subscribers (via the uXRCE-DDS agent) use
# BEST_EFFORT reliability. A subscriber left on ROS2's default RELIABLE QoS will fail
# to match and silently receive nothing -- no error, just dead silence.
PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


def _quat_mult_xyzw(q1, q2):
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _enu_to_ned(x, y, z):
    return y, x, -z


def _enu_orientation_to_ned(qx, qy, qz, qw):
    """World-frame-only ENU->NED conversion. Returns PX4's scalar-first (w,x,y,z)
    order -- verified against PX4 v1.16.0 source (matrix/Quaternion.hpp), which
    differs from ROS's scalar-last geometry_msgs/Quaternion.

    TODO(R4): this is the one piece of this bridge that's easy to get subtly wrong
    and hard to verify without real motion. Once the bench rig is up, move it a
    known distance/heading and confirm PX4's fused NED position/heading tracks in
    the expected direction before trusting this for anything beyond bench testing.
    """
    x, y, z, w = _quat_mult_xyzw(_Q_NED_ENU_XYZW, (qx, qy, qz, qw))
    return w, x, y, z


class VioPx4Bridge(Node):
    """Bridges PX4 <-> OpenVINS over px4_msgs (uXRCE-DDS), in both directions:

    /fmu/out/sensor_combined -> /d435i/imu (sensor_msgs/Imu)
        The D435 has no onboard IMU (see readme.md sec 6) -- OpenVINS's IMU input
        has to come from the flight controller. Passed through in PX4's native FRD
        body frame, intentionally unconverted: R2's Kalibr camera<->IMU calibration
        will be run against this exact frame, so a manual FLU conversion here would
        just add an unverified transform between us and the real calibration.

    /ov_msckf/odomimu -> /fmu/in/vehicle_visual_odometry (px4_msgs/VehicleOdometry)
        Because the IMU feed above is left in FRD, OpenVINS's own body-frame outputs
        (angular_velocity, and the body component of orientation) come out already
        FRD-native -- so only the *world* frame needs converting (OpenVINS's
        gravity-aligned, arbitrary-heading world frame -> PX4's NED), not the body
        frame. See _enu_orientation_to_ned's docstring for the one part of this that
        still needs real-motion verification.
    """

    def __init__(self):
        super().__init__('vio_px4_bridge')

        self.imu_pub = self.create_publisher(Imu, '/d435i/imu', 10)
        self.create_subscription(
            SensorCombined, '/fmu/out/sensor_combined', self._on_sensor_combined, PX4_QOS
        )

        self.odom_pub = self.create_publisher(
            VehicleOdometry, '/fmu/in/vehicle_visual_odometry', PX4_QOS
        )
        self.create_subscription(Odometry, '/ov_msckf/odomimu', self._on_vio_odom, 10)

        self.get_logger().info(
            'vio_px4_bridge up: /fmu/out/sensor_combined -> /d435i/imu, '
            '/ov_msckf/odomimu -> /fmu/in/vehicle_visual_odometry'
        )

    def _on_sensor_combined(self, msg: SensorCombined):
        imu = Imu()
        # msg.timestamp is PX4's since-boot microseconds; only meaningful in the
        # companion computer's time domain once uXRCE-DDS timesync has converged
        # (see readme.md sec 4.3 -- check `uxrce_dds_client status` if this looks off).
        imu.header.stamp = rclpy.time.Time(nanoseconds=int(msg.timestamp) * 1000).to_msg()
        imu.header.frame_id = 'px4_imu'

        imu.angular_velocity.x = float(msg.gyro_rad[0])
        imu.angular_velocity.y = float(msg.gyro_rad[1])
        imu.angular_velocity.z = float(msg.gyro_rad[2])
        imu.linear_acceleration.x = float(msg.accelerometer_m_s2[0])
        imu.linear_acceleration.y = float(msg.accelerometer_m_s2[1])
        imu.linear_acceleration.z = float(msg.accelerometer_m_s2[2])

        # sensor_combined carries no orientation estimate -- mark it explicitly
        # unknown (REP 145 / sensor_msgs/Imu convention) rather than leaving a
        # misleading identity quaternion.
        imu.orientation_covariance[0] = -1.0

        self.imu_pub.publish(imu)

    def _on_vio_odom(self, msg: Odometry):
        out = VehicleOdometry()
        out.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        out.timestamp_sample = int(rclpy.time.Time.from_msg(msg.header.stamp).nanoseconds / 1000)

        out.pose_frame = VehicleOdometry.POSE_FRAME_NED
        p = msg.pose.pose.position
        out.position[0], out.position[1], out.position[2] = _enu_to_ned(p.x, p.y, p.z)

        q = msg.pose.pose.orientation
        out.q[0], out.q[1], out.q[2], out.q[3] = _enu_orientation_to_ned(q.x, q.y, q.z, q.w)

        out.velocity_frame = VehicleOdometry.VELOCITY_FRAME_NED
        v = msg.twist.twist.linear
        out.velocity[0], out.velocity[1], out.velocity[2] = _enu_to_ned(v.x, v.y, v.z)

        # Already FRD-native (unconverted IMU input, see class docstring).
        av = msg.twist.twist.angular
        out.angular_velocity[0] = float(av.x)
        out.angular_velocity[1] = float(av.y)
        out.angular_velocity[2] = float(av.z)

        pcov = msg.pose.covariance
        out.position_variance[0] = float(pcov[0])
        out.position_variance[1] = float(pcov[7])
        out.position_variance[2] = float(pcov[14])
        out.orientation_variance[0] = float(pcov[21])
        out.orientation_variance[1] = float(pcov[28])
        out.orientation_variance[2] = float(pcov[35])

        tcov = msg.twist.covariance
        out.velocity_variance[0] = float(tcov[0])
        out.velocity_variance[1] = float(tcov[7])
        out.velocity_variance[2] = float(tcov[14])

        out.reset_counter = 0
        out.quality = 0  # OpenVINS reports no normalized quality metric; PX4 treats 0 as "unknown"

        self.odom_pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = VioPx4Bridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
