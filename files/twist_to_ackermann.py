#!/usr/bin/env python3
"""
twist_to_ackermann.py
---------------------
Converts geometry_msgs/Twist (from teleop_twist_keyboard) to
ackermann_msgs/AckermannDriveStamped (expected by gym_bridge on /teleop).

Subscribes : /cmd_vel   (geometry_msgs/Twist)
Publishes  : /teleop    (ackermann_msgs/AckermannDriveStamped)

Conversion
----------
  speed          = twist.linear.x          (m/s forward)
  steering_angle = twist.angular.z * gain  (rad)

The steering_gain parameter maps angular.z (rad/s yaw rate) to a physical
steering angle. A value of 0.3 works well for F1Tenth at low speed — tune
it for your track and car geometry.

Run
---
  ros2 run f1tenth_gym_ros twist_to_ackermann
  # or with custom gain:
  ros2 run f1tenth_gym_ros twist_to_ackermann --ros-args -p steering_gain:=0.4
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from ackermann_msgs.msg import AckermannDriveStamped, AckermannDrive


class TwistToAckermann(Node):
    def __init__(self):
        super().__init__("twist_to_ackermann")

        self.declare_parameter("steering_gain", 0.3)
        self._gain = self.get_parameter("steering_gain").value

        self._sub = self.create_subscription(
            Twist, "/cmd_vel", self._callback, 10
        )
        self._pub = self.create_publisher(
            AckermannDriveStamped, "/teleop", 10
        )

        self.get_logger().info(
            f"twist_to_ackermann ready  "
            f"(steering_gain={self._gain})  "
            f"/cmd_vel → /teleop"
        )

    def _callback(self, msg: Twist):
        out = AckermannDriveStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = "base_link"
        out.drive = AckermannDrive(
            speed=float(msg.linear.x),
            steering_angle=float(msg.angular.z) * self._gain,
        )
        self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = TwistToAckermann()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
