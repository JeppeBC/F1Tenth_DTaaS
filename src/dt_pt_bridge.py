#!/usr/bin/env python3
"""
dt_pt_bridge.py
---------------
Forwards keyboard drive commands from the DT to the Physical Twin over UDP.

Only forwards messages with frame_id == 'dt_send' — i.e. commands stamped
by ackermann_keyboard_teleop. This prevents the Bluetooth controller's
commands (which bleed back from the car via DDS on domain 0) from being
re-forwarded to the car, breaking the feedback loop.

Subscribes : /drive        (ackermann_msgs/AckermannDriveStamped)
Publishes  : /teleop_echo  (ackermann_msgs/AckermannDriveStamped)
UDP out    : pt_host:pt_port
"""

import socket
import struct
import time
import threading

import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped

DEFAULT_PT_HOST  = "172.20.10.8"
DEFAULT_PT_PORT  = 9870
DEFAULT_SEND_HZ  = 50


class DtPtBridge(Node):
    def __init__(self):
        super().__init__("dt_pt_bridge")

        self.declare_parameter("pt_host",     DEFAULT_PT_HOST)
        self.declare_parameter("pt_port",     DEFAULT_PT_PORT)
        self.declare_parameter("max_send_hz", DEFAULT_SEND_HZ)

        self._pt_host      = self.get_parameter("pt_host").value
        self._pt_port      = self.get_parameter("pt_port").value
        self._min_interval = 1.0 / self.get_parameter("max_send_hz").value

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

        self._last_send_time  = 0.0
        self._last_drive_time = 0.0
        self._lock = threading.Lock()
        self._msgs_forwarded  = 0

        self._sub = self.create_subscription(
            AckermannDriveStamped, "/drive",
            self._drive_callback, 10,
        )
        self._pub_echo = self.create_publisher(
            AckermannDriveStamped, "/teleop_echo", 10
        )

        self._watchdog_timer = self.create_timer(5.0, self._watchdog)

        self.get_logger().info(
            f"dt_pt_bridge ready\n"
            f"  Sub : /drive  (only forwarding frame_id='dt_send')\n"
            f"  UDP → {self._pt_host}:{self._pt_port}\n"
            f"  Pub : /teleop_echo  (for latency_logger)\n"
            f"  Rate: {int(1.0/self._min_interval)} Hz max"
        )

    def _drive_callback(self, msg: AckermannDriveStamped):
        now = time.monotonic()
        with self._lock:
            self._last_drive_time = now
            if now - self._last_send_time < self._min_interval:
                return
            self._last_send_time = now

        # Re-stamp with exact dispatch time for latency measurement
        # Preserve original frame_id so logger can identify keyboard vs controller
        original_frame_id   = msg.header.frame_id
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.header.frame_id = "dt_send"

        self._send_udp(msg)
        self._pub_echo.publish(msg)

        with self._lock:
            self._msgs_forwarded += 1
        self.get_logger().debug(
            f"Forwarded frame_id='{original_frame_id}' "
            f"speed={msg.drive.speed:.2f}",
        )

    def _send_udp(self, msg: AckermannDriveStamped):
        stamp_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )
        payload = struct.pack(
            "<qff", stamp_ns,
            msg.drive.steering_angle,
            msg.drive.speed,
        )
        try:
            self._sock.sendto(payload, (self._pt_host, self._pt_port))
        except OSError as exc:
            self.get_logger().warn(
                f"UDP send failed: {exc}",
                throttle_duration_sec=5.0,
            )

    def _watchdog(self):
        with self._lock:
            drive_age = time.monotonic() - self._last_drive_time
            fwd       = self._msgs_forwarded

        if self._last_drive_time == 0.0:
            self.get_logger().warn(
                "No /drive messages received yet. "
                "Is the relay or keyboard teleop running?"
            )
        elif drive_age > 3.0:
            self.get_logger().warn(
                f"/drive silent for {drive_age:.1f}s  (forwarded={fwd})"
            )
        else:
            self.get_logger().info(
                f"Forwarding OK — sent={fwd}"
            )


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
