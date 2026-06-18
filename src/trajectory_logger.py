#!/usr/bin/env python3

import csv
import math
import pathlib

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

DEFAULT_OUTPUT_DIR = "/tmp/trajectory"
DEFAULT_RUN_LABEL  = "run"
DEFAULT_DT_TOPIC   = "/ego_racecar/sim_odom"
DEFAULT_PT_TOPIC   = "/odom"


class TrajectoryLogger(Node):
    def __init__(self):
        super().__init__("trajectory_logger")

        self.declare_parameter("output_dir", DEFAULT_OUTPUT_DIR)
        self.declare_parameter("run_label",  DEFAULT_RUN_LABEL)
        self.declare_parameter("dt_topic",   DEFAULT_DT_TOPIC)
        self.declare_parameter("pt_topic",   DEFAULT_PT_TOPIC)

        out_dir   = pathlib.Path(self.get_parameter("output_dir").value)
        run_label = self.get_parameter("run_label").value
        dt_topic  = self.get_parameter("dt_topic").value
        pt_topic  = self.get_parameter("pt_topic").value

        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / f"trajectory_{run_label}.csv"

        self._csv_file = open(csv_path, "w", newline="")
        self._writer   = csv.writer(self._csv_file)
        self._writer.writerow([
            "timestamp_ns", "source", "x", "y", "heading_rad", "speed_mps"
        ])
        self._csv_file.flush()

        self._dt_count = 0
        self._pt_count = 0

        self._sub_dt = self.create_subscription(
            Odometry, dt_topic, self._dt_callback, 10
        )
        self._sub_pt = self.create_subscription(
            Odometry, pt_topic, self._pt_callback, 10
        )

        self._watchdog_timer = self.create_timer(5.0, self._watchdog)

        self.get_logger().info(
            f"Trajectory logger ready\n"
            f"  DT topic : {dt_topic}\n"
            f"  PT topic : {pt_topic}\n"
            f"  Output   : {csv_path}\n"
            f"  Run label: {run_label}"
        )

    def _write(self, source: str, msg: Odometry):
        stamp_ns = (
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        )
        x       = msg.pose.pose.position.x
        y       = msg.pose.pose.position.y
        qz      = msg.pose.pose.orientation.z
        qw      = msg.pose.pose.orientation.w
        heading = 2.0 * math.atan2(qz, qw)
        speed   = msg.twist.twist.linear.x

        self._writer.writerow([
            stamp_ns, source,
            f"{x:.4f}", f"{y:.4f}",
            f"{heading:.4f}", f"{speed:.4f}",
        ])
        self._csv_file.flush()

    def _dt_callback(self, msg: Odometry):
        self._write("DT", msg)
        self._dt_count += 1

    def _pt_callback(self, msg: Odometry):
        self._write("PT", msg)
        self._pt_count += 1

    def _watchdog(self):
        if self._dt_count == 0 and self._pt_count == 0:
            self.get_logger().warn(
                "No data from either source yet.\n"
                "  ros2 topic hz /ego_racecar/odom\n"
                "  ros2 topic hz /odom"
            )
        elif self._dt_count == 0:
            self.get_logger().warn(
                "No DT data — is gym_bridge running?\n"
                "  ros2 topic hz /ego_racecar/odom"
            )
        elif self._pt_count == 0:
            self.get_logger().warn(
                "No PT data — is /odom bleeding from car on domain 0?\n"
                "  ros2 topic hz /odom  (on WSL2)"
            )
        else:
            self.get_logger().info(
                f"Logging — DT: {self._dt_count}  PT: {self._pt_count} samples"
            )

    def destroy_node(self):
        self._csv_file.close()
        self.get_logger().info(
            f"Done — DT: {self._dt_count}  PT: {self._pt_count} samples saved"
        )
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TrajectoryLogger()
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
