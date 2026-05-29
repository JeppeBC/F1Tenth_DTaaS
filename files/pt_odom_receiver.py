#!/usr/bin/env python3
"""
pt_odom_receiver.py  —  runs on WSL2
--------------------------------------
Receives PT odometry UDP packets from the car and republishes them
on /initialpose so gym_bridge resets the DT car's position to match
the physical car's real-world pose.

This closes the PT→DT mirroring loop:
  Car /odom → UDP → WSL2 → /initialpose → gym_bridge → DT moves

Run
---
  ros2 run f1tenth_gym_ros pt_odom_receiver

Packet format (from dt_pt_listener --send-odom):
  struct: <q f f f f  (stamp_ns, x, y, heading, speed)  = 28 bytes
"""

import socket
import struct
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseWithCovarianceStamped

PACKET_FMT  = "<qffff"
PACKET_SIZE = struct.calcsize(PACKET_FMT)   # 28 bytes
DEFAULT_PORT = 9871


class PtOdomReceiver(Node):
    def __init__(self):
        super().__init__("pt_odom_receiver")
        self.declare_parameter("listen_port", DEFAULT_PORT)
        port = self.get_parameter("listen_port").value

        self._pub = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", 10
        )

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", port))
        self._sock.settimeout(0.1)

        self._timer = self.create_timer(0.02, self._recv_and_publish)  # 50 Hz poll
        self.get_logger().info(
            f"pt_odom_receiver listening on UDP port {port} → /initialpose"
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

        stamp_ns, x, y, heading, speed = struct.unpack_from(PACKET_FMT, data)

        msg = PoseWithCovarianceStamped()
        msg.header.stamp.sec     = stamp_ns // 1_000_000_000
        msg.header.stamp.nanosec = stamp_ns %  1_000_000_000
        msg.header.frame_id      = "map"

        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)

        # Convert heading (rad) to quaternion (yaw only)
        msg.pose.pose.orientation.z = math.sin(heading / 2.0)
        msg.pose.pose.orientation.w = math.cos(heading / 2.0)

        self._pub.publish(msg)

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
