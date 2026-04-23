#!/usr/bin/env python3
"""
dt_pt_bridge.py
---------------
Bridges the Digital Twin (RViz2 / keyboard) to the Physical Twin (F1Tenth car).

Subscribe to /teleop (AckermannDriveStamped) published by the keyboard node,
forward commands to the PT via UDP (WiFi) or optionally serial/ROS bridge,
and publish a /teleop_stamped_ack echo for round-trip latency benchmarking.

Usage
-----
1.  Set PT_HOST / PT_PORT to match whatever listener you run on the car.
2.  ros2 run <your_pkg> dt_pt_bridge

Topics
------
  Sub : /teleop                (ackermann_msgs/AckermannDriveStamped)
  Pub : /teleop_echo           (ackermann_msgs/AckermannDriveStamped)
        Mirrors inbound msg + original send timestamp in the header stamp,
        so latency_logger.py can measure one-way and round-trip delay.

Transport
---------
  Default: UDP unicast to PT_HOST:PT_PORT.
  The car must run a matching UDP listener (see dt_pt_listener.py).
  Change _send_to_pt() to use serial or a ROS topic bridge if preferred.
"""

import json
import socket
import struct
import time
import threading

import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped
from std_msgs.msg import Header
from builtin_interfaces.msg import Time as RosTime

# ---------------------------------------------------------------------------
# Configuration — edit these or override via ROS params
# ---------------------------------------------------------------------------
DEFAULT_PT_HOST = "192.168.1.100"   # IP of the physical car on WiFi
DEFAULT_PT_PORT = 9870              # UDP port the car listens on
DEFAULT_SEND_HZ = 50                # Max forward rate (Hz) — throttle protection
# ---------------------------------------------------------------------------


class DtPtBridge(Node):
    def __init__(self):
        super().__init__("dt_pt_bridge")

        # Declare parameters so they can be overridden at launch
        self.declare_parameter("pt_host", DEFAULT_PT_HOST)
        self.declare_parameter("pt_port", DEFAULT_PT_PORT)
        self.declare_parameter("max_send_hz", DEFAULT_SEND_HZ)

        self._pt_host = self.get_parameter("pt_host").value
        self._pt_port = self.get_parameter("pt_port").value
        self._min_interval = 1.0 / self.get_parameter("max_send_hz").value

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

        self._last_send_time = 0.0
        self._lock = threading.Lock()

        self._sub = self.create_subscription(
            AckermannDriveStamped,
            "/teleop",
            self._teleop_callback,
            10,
        )

        # Echo publisher — replays the message back so the logger can
        # measure the time from send to when the PT acknowledged receipt.
        # For one-way latency the PT sends its own echo; for loopback
        # benchmarking (no PT) we echo immediately here.
        self._pub_echo = self.create_publisher(
            AckermannDriveStamped, "/teleop_echo", 10
        )

        self.get_logger().info(
            f"dt_pt_bridge ready — forwarding /teleop → {self._pt_host}:{self._pt_port}"
        )

    # ------------------------------------------------------------------
    def _teleop_callback(self, msg: AckermannDriveStamped):
        now = time.monotonic()
        with self._lock:
            if now - self._last_send_time < self._min_interval:
                return  # rate-limit
            self._last_send_time = now

        send_stamp = self.get_clock().now()

        # Inject send timestamp into the header so the echo/logger can
        # compute one-way latency even without a synchronised clock on the PT.
        msg.header.stamp = send_stamp.to_msg()
        msg.header.frame_id = "dt_send"

        self._send_to_pt(msg)

        # Publish echo for loopback latency benchmarking (no PT required)
        echo = AckermannDriveStamped()
        echo.header = msg.header
        echo.drive = msg.drive
        self._pub_echo.publish(echo)

    # ------------------------------------------------------------------
    def _send_to_pt(self, msg: AckermannDriveStamped):
        """
        Serialise and transmit a drive command to the physical car.
        Format: 4-byte float32 little-endian × 2  (steering_angle, speed)
        preceded by an 8-byte int64 Unix nanosecond timestamp.
        Total: 16 bytes per packet — minimal overhead.
        """
        stamp_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )
        payload = struct.pack(
            "<qff",
            stamp_ns,
            msg.drive.steering_angle,
            msg.drive.speed,
        )
        try:
            self._sock.sendto(payload, (self._pt_host, self._pt_port))
        except OSError as exc:
            self.get_logger().warn(f"UDP send failed: {exc}", throttle_duration_sec=2.0)


def main(args=None):
    rclpy.init(args=args)
    node = DtPtBridge()
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
