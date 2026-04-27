#!/usr/bin/env python3
"""
latency_logger.py  (with self-diagnostics)
------------------------------------------
Subscribes to /teleop_echo (published by dt_pt_bridge whenever it
forwards a command to the PT over UDP).

Every 5 seconds it prints a status report so you can see exactly
what is and isn't arriving, rather than silently waiting.

If /teleop_echo is silent:
  - Check dt_pt_bridge is running:   ros2 node list | grep bridge
  - Check /drive has traffic:        ros2 topic hz /drive
  - Check /teleop_echo exists:       ros2 topic list | grep echo
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
        self._writer   = csv.writer(self._csv_file)
        self._writer.writerow([
            "seq", "send_time_ns", "recv_time_ns",
            "one_way_ms", "steering_angle", "speed"
        ])
        self._csv_file.flush()

        self._seq    = 0
        self._window: deque[float] = deque(maxlen=WINDOW)

        # Clock anchoring (both bridge and logger are on the same machine)
        self._anchor_ros  = None
        self._anchor_mono = None

        # Counters for the watchdog
        self._echo_total    = 0   # all /teleop_echo messages received
        self._echo_accepted = 0   # those with frame_id == 'dt_send'
        self._last_watchdog = time.monotonic()

        self._sub_echo = self.create_subscription(
            AckermannDriveStamped, "/teleop_echo",
            self._on_echo, 10,
        )

        self._pub_diag   = self.create_publisher(DiagnosticArray, "/diagnostics", 5)
        self._diag_timer = self.create_timer(1.0,  self._publish_diagnostics)
        self._watch_timer = self.create_timer(5.0, self._watchdog)

        self.get_logger().info(f"Logging latency to {csv_path}")
        self.get_logger().info(
            "Waiting for /teleop_echo  (frame_id='dt_send')  from dt_pt_bridge..."
        )

    # ------------------------------------------------------------------
    def _stamp_ns(self, stamp) -> int:
        return stamp.sec * 1_000_000_000 + stamp.nanosec

    def _on_echo(self, msg: AckermannDriveStamped):
        self._echo_total += 1

        if msg.header.frame_id != "dt_send":
            self.get_logger().warn(
                f"Ignoring /teleop_echo with frame_id='{msg.header.frame_id}' "
                f"(expected 'dt_send'). Check dt_pt_bridge is running.",
                throttle_duration_sec=5.0,
            )
            return

        self._echo_accepted += 1
        recv_mono = time.monotonic()
        send_ns   = self._stamp_ns(msg.header.stamp)

        # Anchor on first accepted message
        if self._anchor_ros is None:
            self._anchor_ros  = send_ns
            self._anchor_mono = recv_mono
            self.get_logger().info(
                "Clock anchor set — latency measurement active."
            )
            return  # skip first sample (no baseline yet)

        elapsed_since_anchor = (send_ns - self._anchor_ros) / 1e9
        send_mono_equiv      = self._anchor_mono + elapsed_since_anchor
        one_way_ms           = (recv_mono - send_mono_equiv) * 1000.0

        # Sanity gate
        if one_way_ms < 0 or one_way_ms > 5000:
            self.get_logger().warn(
                f"Rejected sample: one_way_ms={one_way_ms:.1f} (out of range)",
                throttle_duration_sec=2.0,
            )
            return

        self._window.append(one_way_ms)
        recv_ns = int(recv_mono * 1e9)

        self._writer.writerow([
            self._seq, send_ns, recv_ns,
            f"{one_way_ms:.3f}",
            f"{msg.drive.steering_angle:.4f}",
            f"{msg.drive.speed:.4f}",
        ])
        self._csv_file.flush()
        self._seq += 1

        self.get_logger().info(
            f"[seq {self._seq:4d}]  "
            f"one_way={one_way_ms:6.2f} ms  "
            f"avg={self._avg():6.2f} ms  "
            f"p99={self._p99():6.2f} ms",
            throttle_duration_sec=0.5,
        )

    # ------------------------------------------------------------------
    def _watchdog(self):
        """Prints a status report every 5 s so the user knows what's happening."""
        now = time.monotonic()
        elapsed = now - self._last_watchdog
        self._last_watchdog = now

        if self._echo_total == 0:
            self.get_logger().warn(
                "\n"
                "  ╔══════════════════════════════════════════════════╗\n"
                "  ║  NO /teleop_echo messages received yet.          ║\n"
                "  ║  Check the following:                            ║\n"
                "  ║  1. dt_pt_bridge is running:                     ║\n"
                "  ║     ros2 node list | grep bridge                 ║\n"
                "  ║  2. /drive has traffic (keyboard teleop active): ║\n"
                "  ║     ros2 topic hz /drive                         ║\n"
                "  ║  3. relay is running (/teleop → /drive):         ║\n"
                "  ║     ros2 topic info /drive --verbose             ║\n"
                "  ╚══════════════════════════════════════════════════╝"
            )
        elif self._echo_accepted == 0:
            self.get_logger().warn(
                f"  Received {self._echo_total} /teleop_echo msgs but NONE had "
                f"frame_id='dt_send'. The bridge may not be stamping correctly. "
                f"Run: ros2 topic echo /teleop_echo --once"
            )
        else:
            self.get_logger().info(
                f"  Status: {self._echo_accepted} samples recorded  "
                f"avg={self._avg():.2f} ms  p99={self._p99():.2f} ms"
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
        status.message = f"avg={avg:.1f}ms  p99={p99:.1f}ms  n={len(self._window)}"
        status.values  = [
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
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
