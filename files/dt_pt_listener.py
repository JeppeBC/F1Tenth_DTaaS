#!/usr/bin/env python3
"""
dt_pt_listener.py  —  runs ON the physical F1Tenth car
-------------------------------------------------------
Receives packed UDP drive commands from dt_pt_bridge (WSL2 side),
re-publishes them on the local /teleop topic so the car's existing
VESC / motor driver stack picks them up unchanged.

Also sends a minimal UDP echo back to the sender so dt_pt_bridge can
close the RTT loop for latency measurement (optional but recommended).

Install / run on the car
------------------------
  # Copy this file to the car, then:
  python3 dt_pt_listener.py --host 0.0.0.0 --port 9870 \
      --ros-domain-id 0 --echo-back

  # Or wrap in a systemd service / launch file.

Requires: rclpy, ackermann_msgs   (standard F1Tenth ROS 2 setup)
"""

import argparse
import socket
import struct
import threading

import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped
from ackermann_msgs.msg import AckermannDrive


PACKET_FMT = "<qff"  # int64 stamp_ns, float32 steer, float32 speed
PACKET_SIZE = struct.calcsize(PACKET_FMT)  # 16 bytes


class DtPtListener(Node):
    def __init__(self, host: str, port: int, echo_back: bool):
        super().__init__("dt_pt_listener")

        self._echo_back = echo_back
        self._pub = self.create_publisher(
            AckermannDriveStamped, "/teleop", 10
        )

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self.get_logger().info(f"Listening for DT commands on {host}:{port}")

        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def _recv_loop(self):
        while rclpy.ok():
            try:
                data, addr = self._sock.recvfrom(64)
            except OSError:
                continue

            if len(data) < PACKET_SIZE:
                continue

            stamp_ns, steer, speed = struct.unpack_from(PACKET_FMT, data)

            msg = AckermannDriveStamped()
            msg.header.stamp.sec = stamp_ns // 1_000_000_000
            msg.header.stamp.nanosec = stamp_ns % 1_000_000_000
            msg.header.frame_id = "dt_recv"
            msg.drive = AckermannDrive(
                steering_angle=steer,
                speed=speed,
            )
            self._pub.publish(msg)

            if self._echo_back:
                # Echo the raw packet straight back — zero copy, minimal overhead
                try:
                    self._sock.sendto(data, addr)
                except OSError:
                    pass

    def destroy_node(self):
        self._sock.close()
        super().destroy_node()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.20.10.8")
    parser.add_argument("--port", type=int, default=9870)
    parser.add_argument("--echo-back", action="store_true",
                        help="Echo packets back to sender for RTT measurement")
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = DtPtListener(args.host, args.port, args.echo_back)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
