#!/usr/bin/env python3
"""
latency_logger.py  (timing-fixed)
----------------------------------
The bridge stamps each /teleop_echo message with the ROS clock time
at dispatch. The logger records the ROS clock time at receipt.
Both nodes are on the same machine (WSL2), so the same ROS clock is used
and the difference is a true measurement of processing + publish latency.

For WiFi RTT: when the car runs dt_pt_listener --echo-back, the car echoes
the UDP packet back, the bridge receives it and re-publishes on /teleop_echo.
That round-trip gives RTT/2 as the one_way_ms value.

Rejected samples (negative or >5000ms) indicate clock anomalies — logged
but not written to CSV.
"""

import csv
import pathlib
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from ackermann_msgs.msg import AckermannDriveStamped
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

DEFAULT_OUTPUT_DIR = "/tmp/latency"
WINDOW = 200


class LatencyLogger(Node):
    def __init__(self):
        super().__init__("latency_logger")

        self.declare_parameter("output_dir", DEFAULT_OUTPUT_DIR)
        out_dir = pathlib.Path(self.get_parameter("output_dir").value)
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        csv_path = out_dir / f"latency_{ts}.csv"
        self._csv_file = open(csv_path, "w", newline="")
        self._writer   = csv.writer(self._csv_file)
        self._writer.writerow([
            "seq", "send_time_ns", "recv_time_ns",
            "one_way_ms", "steering_angle", "speed"
        ])
        self._csv_file.flush()

        self._seq     = 0
        self._window: deque[float] = deque(maxlen=WINDOW)
        self._rejected = 0

        self._sub_echo = self.create_subscription(
            AckermannDriveStamped, "/teleop_echo",
            self._on_echo, 10,
        )
        self._pub_diag   = self.create_publisher(DiagnosticArray, "/diagnostics", 5)
        self._diag_timer  = self.create_timer(1.0, self._publish_diagnostics)
        self._watch_timer = self.create_timer(5.0, self._watchdog)

        self._echo_count = 0

        self.get_logger().info(f"Logging latency to {csv_path}")
        self.get_logger().info(
            "Waiting for /teleop_echo (frame_id='dt_send') from dt_pt_bridge..."
        )

    # ------------------------------------------------------------------
    def _on_echo(self, msg: AckermannDriveStamped):
        # Record receipt time immediately using ROS clock
        recv_ros_ns = self.get_clock().now().nanoseconds
        self._echo_count += 1

        if msg.header.frame_id != "dt_send":
            return

        send_ros_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )

        one_way_ms = (recv_ros_ns - send_ros_ns) / 1_000_000.0

        if one_way_ms < 0 or one_way_ms > 5000:
            self._rejected += 1
            self.get_logger().warn(
                f"Rejected sample: one_way_ms={one_way_ms:.1f}  "
                f"send_ns={send_ros_ns}  recv_ns={recv_ros_ns}",
                throttle_duration_sec=2.0,
            )
            return

        self._window.append(one_way_ms)

        self._writer.writerow([
            self._seq,
            send_ros_ns,
            recv_ros_ns,
            f"{one_way_ms:.3f}",
            f"{msg.drive.steering_angle:.4f}",
            f"{msg.drive.speed:.4f}",
        ])
        self._csv_file.flush()
        self._seq += 1

        self.get_logger().info(
            f"[seq {self._seq:4d}]  "
            f"one_way={one_way_ms:6.3f} ms  "
            f"avg={self._avg():6.3f} ms  "
            f"p99={self._p99():6.3f} ms",
            throttle_duration_sec=0.5,
        )

    # ------------------------------------------------------------------
    def _watchdog(self):
        if self._echo_count == 0:
            self.get_logger().warn(
                "\n"
                "  ╔═══════════════════════════════════════════════════╗\n"
                "  ║  NO /teleop_echo received yet.                   ║\n"
                "  ║  Check:                                          ║\n"
                "  ║  ros2 topic hz /teleop_echo                      ║\n"
                "  ║  ros2 topic hz /drive                            ║\n"
                "  ║  ros2 node list | grep bridge                    ║\n"
                "  ╚═══════════════════════════════════════════════════╝"
            )
        else:
            self.get_logger().info(
                f"  Status: {self._seq} recorded  "
                f"{self._rejected} rejected  "
                f"avg={self._avg():.3f} ms  "
                f"p99={self._p99():.3f} ms"
            )

    # ------------------------------------------------------------------
    def _avg(self) -> float:
        return sum(self._window) / len(self._window) if self._window else 0.0

    def _p99(self) -> float:
        if not self._window:
            return 0.0
        s = sorted(self._window)
        return s[max(0, int(len(s) * 0.99) - 1)]

    def _publish_diagnostics(self):
        if not self._window:
            return
        avg = self._avg()
        p99 = self._p99()
        arr    = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name        = "dt_pt_latency"
        status.hardware_id = "f1tenth_bridge"
        status.level = (
            DiagnosticStatus.OK   if avg < 20 else
            DiagnosticStatus.WARN if avg < 50 else
            DiagnosticStatus.ERROR
        )
        status.message = f"avg={avg:.3f}ms  p99={p99:.3f}ms  n={len(self._window)}"
        status.values  = [
            KeyValue(key="avg_ms",   value=f"{avg:.3f}"),
            KeyValue(key="p99_ms",   value=f"{p99:.3f}"),
            KeyValue(key="samples",  value=str(len(self._window))),
            KeyValue(key="rejected", value=str(self._rejected)),
        ]
        arr.status.append(status)
        self._pub_diag.publish(arr)

    def destroy_node(self):
        self._csv_file.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LatencyLogger()
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
