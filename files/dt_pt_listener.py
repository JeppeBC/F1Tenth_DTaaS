#!/usr/bin/env python3
"""
dt_pt_listener.py  —  runs ON the physical F1Tenth car
-------------------------------------------------------
Clean separation of concerns — does NOT touch the existing control chain:
  joy_teleop → /teleop → ackermann_mux → /ackermann_cmd → VESC

This script only:
  1. Receives keyboard commands from WSL2 via UDP → publishes to /drive
     (ackermann_mux navigation slot, priority 10 — joystick always wins)
  2. Subscribes to /ackermann_cmd (mux output) → sends back to WSL2 via UDP
     so the DT mirrors whatever the mux decides (keyboard or controller)
  3. Sends /odom back to WSL2 for position mirroring
  4. Echoes drive packets back to WSL2 for latency measurement

Usage
-----
  export ROS_DOMAIN_ID=0
  python3 dt_pt_listener.py --port 9870 --echo-back \\
      --send-odom --dt-host 172.20.10.2 --odom-port 9871

The joystick always has priority 90 vs keyboard priority 10 in the mux.
No interference with existing teleop chain whatsoever.
"""

import argparse
import socket
import struct
import threading
import time
import math

import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped, AckermannDrive
from nav_msgs.msg import Odometry

DRIVE_FMT  = "<qff"
DRIVE_SIZE = struct.calcsize(DRIVE_FMT)   # 16 bytes  (stamp_ns, steer, speed)
ODOM_FMT   = "<qffff"                     # stamp_ns, x, y, heading, speed


class DtPtListener(Node):
    def __init__(self, host, port, echo_back, output_topic,
                 send_odom, dt_host, odom_port):
        super().__init__("dt_pt_listener")

        self._echo_back   = echo_back
        self._send_odom   = send_odom
        self._dt_host     = dt_host
        self._odom_port   = odom_port

        # Publish keyboard commands to navigation slot (/drive, priority 10)
        self._pub_drive = self.create_publisher(
            AckermannDriveStamped, output_topic, 10
        )

        # Subscribe to mux output — relay back to DT for mirroring
        self._sub_cmd = self.create_subscription(
            AckermannDriveStamped, "/ackermann_cmd",
            self._ackermann_cmd_callback, 10,
        )

        # Subscribe to odom — relay back to DT for position sync
        if send_odom and dt_host:
            self._sub_odom = self.create_subscription(
                Odometry, "/odom", self._odom_callback, 10
            )
            self.get_logger().info(
                f"Sending /odom back to DT at {dt_host}:{odom_port}"
            )

        # Single UDP socket for all outgoing traffic
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))

        self.get_logger().info(
            f"Listening for DT keyboard commands on {host}:{port}\n"
            f"  → publishing to '{output_topic}' (mux navigation slot)\n"
            f"  → joystick still controls via /teleop at higher priority\n"
            f"  → mirroring /ackermann_cmd back to DT"
        )

        self._udp_thread = threading.Thread(
            target=self._udp_recv_loop, daemon=True
        )
        self._udp_thread.start()

    # ------------------------------------------------------------------
    # Receive keyboard commands from WSL2 over UDP
    # ------------------------------------------------------------------
    def _udp_recv_loop(self):
        while rclpy.ok():
            try:
                data, addr = self._sock.recvfrom(64)
            except OSError:
                continue

            if len(data) < DRIVE_SIZE:
                continue

            stamp_ns, steer, speed = struct.unpack_from(DRIVE_FMT, data)

            msg = AckermannDriveStamped()
            msg.header.stamp.sec     = stamp_ns // 1_000_000_000
            msg.header.stamp.nanosec = stamp_ns %  1_000_000_000
            msg.header.frame_id      = "dt_recv"
            msg.drive = AckermannDrive(
                steering_angle=float(steer),
                speed=float(speed),
            )

            # Publish to /drive (navigation slot, mux priority 10)
            # Joystick at priority 90 always overrides when active
            self._pub_drive.publish(msg)

            # Echo packet back for RTT latency measurement
            if self._echo_back:
                try:
                    self._sock.sendto(data, addr)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Mirror mux output back to DT over UDP
    # ------------------------------------------------------------------
    def _ackermann_cmd_callback(self, msg: AckermannDriveStamped):
        """
        /ackermann_cmd is the authoritative output of the car's mux.
        Send it back to WSL2 so gym_bridge can mirror the real car's
        motion in RViz2 — whether driven by joystick or keyboard.
        """
        if not self._dt_host:
            return
        stamp_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )
        payload = struct.pack(
            DRIVE_FMT, stamp_ns,
            msg.drive.steering_angle,
            msg.drive.speed,
        )
        try:
            self._sock.sendto(payload, (self._dt_host, 9872))  # separate port
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Send odometry back to WSL2 for position sync
    # ------------------------------------------------------------------
    def _odom_callback(self, msg: Odometry):
        if not self._send_odom or not self._dt_host:
            return
        x       = msg.pose.pose.position.x
        y       = msg.pose.pose.position.y
        qz      = msg.pose.pose.orientation.z
        qw      = msg.pose.pose.orientation.w
        heading = 2.0 * math.atan2(qz, qw)
        speed   = msg.twist.twist.linear.x
        stamp_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )
        payload = struct.pack(ODOM_FMT, stamp_ns, x, y, heading, speed)
        try:
            self._sock.sendto(payload, (self._dt_host, self._odom_port))
        except OSError:
            pass

    def destroy_node(self):
        self._sock.close()
        super().destroy_node()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",         default="0.0.0.0")
    parser.add_argument("--port",         type=int, default=9870)
    parser.add_argument("--echo-back",    action="store_true")
    parser.add_argument("--output-topic", default="/drive",
                        help="Mux navigation topic (default: /drive)")
    parser.add_argument("--send-odom",    action="store_true")
    parser.add_argument("--dt-host",      default="")
    parser.add_argument("--odom-port",    type=int, default=9871)
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = DtPtListener(
        args.host, args.port, args.echo_back, args.output_topic,
        args.send_odom, args.dt_host, args.odom_port,
    )
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
