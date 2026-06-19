#!/usr/bin/env python3

import math
import socket

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped
import struct

PACKET_FMT  = "<qffff"
PACKET_SIZE = struct.calcsize(PACKET_FMT)   # 24 bytes
DEFAULT_PORT = 9871


class PtOdomReceiver(Node):
    def __init__(self):
        super().__init__("pt_odom_receiver")
        self.declare_parameter("listen_port", DEFAULT_PORT)
        self.declare_parameter("reset_dt_pose", False)   # off by default
        port           = self.get_parameter("listen_port").value
        self._reset_dt = self.get_parameter("reset_dt_pose").value

        # Publish as full Odometry for trajectory_logger
        self._pub_odom = self.create_publisher(Odometry, "/odom", 10)

        # Optionally publish as initialpose for gym_bridge DT position reset
        # Disabled by default — enabling teleports the DT car to PT odom coords
        self._pub_pose = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", 10
        ) if self._reset_dt else None

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", port))
        self._sock.settimeout(0.1)

        self._count = 0
        self._timer = self.create_timer(0.02, self._recv_and_publish)
        self._watchdog = self.create_timer(5.0, self._watchdog)

        self.get_logger().info(
            f"pt_odom_receiver listening on UDP :{port}\n"
            f"  → /odom          (for trajectory_logger)\n"
            f"  → /initialpose   {'ENABLED' if self._reset_dt else 'DISABLED'}"
        )

    def _recv_and_publish(self):
        try:
            data, _ = self._sock.recvfrom(64)
        except socket.timeout:
            return
        except OSError:
            return

        if len(data) < PACKET_SIZE:
            return

        stamp_ns, x, y, heading, speed = struct.unpack_from(PACKET_FMT, data[:PACKET_SIZE])
        self._count += 1

        sec     = stamp_ns // 1_000_000_000
        nanosec = stamp_ns %  1_000_000_000
        qz = math.sin(heading / 2.0)
        qw = math.cos(heading / 2.0)

        # --- Full Odometry message (trajectory_logger subscribes here) ---
        odom = Odometry()
        odom.header.stamp.sec     = sec
        odom.header.stamp.nanosec = nanosec
        odom.header.frame_id      = "map"
        odom.child_frame_id       = "base_link"
        odom.pose.pose.position.x = float(x)
        odom.pose.pose.position.y = float(y)
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = float(speed)
        self._pub_odom.publish(odom)

        # --- PoseWithCovarianceStamped (gym_bridge DT reset, optional) ---
        pose = PoseWithCovarianceStamped()
        pose.header.stamp.sec     = sec
        pose.header.stamp.nanosec = nanosec
        pose.header.frame_id      = "map"
        pose.pose.pose.position.x = float(x)
        pose.pose.pose.position.y = float(y)
        pose.pose.pose.orientation.z = qz
        pose.pose.pose.orientation.w = qw
        if self._pub_pose is not None:
            self._pub_pose.publish(pose)

    def _watchdog(self):
        if self._count == 0:
            self.get_logger().warn(
                "No UDP packets received yet.\n"
                "  Check car is running: python3 dt_pt_listener.py --send-odom "
                "--dt-host 172.20.10.2 --odom-port 9871\n"
                "  Check car can reach WSL2: ping 172.20.10.2  (from car)"
            )
        else:
            self.get_logger().info(
                f"Receiving PT odom OK — {self._count} packets so far"
            )

    def destroy_node(self):
        self._sock.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PtOdomReceiver()
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
