#!/usr/bin/env python3
"""
latency_logger.py  (fixed)
--------------------------
Key fix: only correlate messages whose header.frame_id == "dt_send".
This prevents the Bluetooth controller (or any other publisher on /teleop)
from polluting the pending dict with stamps that will never be echoed back,
which was causing the CSV to stay empty.

Also fixes the harmless rcl_shutdown traceback on Ctrl-C.
"""

import csv
import pathlib
import time
from collections import deque

import rclpy
from rclpy.node import Node
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
        self._writer = csv.writer(self._csv_file)
        self._writer.writerow(
            ["seq", "send_time_ns", "recv_time_ns", "one_way_ms",
             "steering_angle", "speed"]
        )
        self._csv_file.flush()
        self.get_logger().info(f"Logging latency to {csv_path}")

        self._seq = 0
        self._window: deque[float] = deque(maxlen=WINDOW)
        self._pending: dict[int, float] = {}

        self._sub_out = self.create_subscription(
            AckermannDriveStamped, "/teleop",
            self._on_send, 10,
        )
        self._sub_echo = self.create_subscription(
            AckermannDriveStamped, "/teleop_echo",
            self._on_echo, 10,
        )

        self._pub_diag = self.create_publisher(DiagnosticArray, "/diagnostics", 5)
        self._diag_timer = self.create_timer(1.0, self._publish_diagnostics)

        self.get_logger().info(
            "Waiting for /teleop messages with frame_id='dt_send'..."
        )

    # ------------------------------------------------------------------
    def _stamp_to_ns(self, stamp) -> int:
        return stamp.sec * 1_000_000_000 + stamp.nanosec

    def _on_send(self, msg: AckermannDriveStamped):
        # CRITICAL FIX: only track messages stamped by dt_pt_bridge
        # ignore the Bluetooth controller and any other publisher on /teleop
        if msg.header.frame_id != "dt_send":
            return

        key = self._stamp_to_ns(msg.header.stamp)
        self._pending[key] = time.monotonic()

        # Prune entries older than 2 s
        cutoff = time.monotonic() - 2.0
        self._pending = {k: v for k, v in self._pending.items() if v > cutoff}

    def _on_echo(self, msg: AckermannDriveStamped):
        recv_mono = time.monotonic()
        key = self._stamp_to_ns(msg.header.stamp)

        send_mono = self._pending.pop(key, None)
        if send_mono is None:
            return  # echo for an unknown or already-pruned send

        one_way_ms = (recv_mono - send_mono) * 1000.0
        self._window.append(one_way_ms)

        self._writer.writerow([
            self._seq,
            key,
            int(recv_mono * 1e9),
            f"{one_way_ms:.3f}",
            f"{msg.drive.steering_angle:.4f}",
            f"{msg.drive.speed:.4f}",
        ])
        self._csv_file.flush()
        self._seq += 1

        self.get_logger().info(
            f"[seq {self._seq}]  one_way={one_way_ms:.1f} ms  "
            f"avg={self._avg():.1f} ms  p99={self._p99():.1f} ms",
            throttle_duration_sec=0.5,
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
        arr = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = "dt_pt_latency"
        status.hardware_id = "f1tenth_bridge"
        avg = self._avg()
        p99 = self._p99()
        status.level = (
            DiagnosticStatus.OK if avg < 20
            else DiagnosticStatus.WARN if avg < 50
            else DiagnosticStatus.ERROR
        )
        status.message = f"avg={avg:.1f}ms  p99={p99:.1f}ms  n={len(self._window)}"
        status.values = [
            KeyValue(key="avg_ms",  value=f"{avg:.2f}"),
            KeyValue(key="p99_ms",  value=f"{p99:.2f}"),
            KeyValue(key="samples", value=str(len(self._window))),
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
        # Guard against double-shutdown (fixes the rcl_shutdown traceback on Ctrl-C)
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
