#!/usr/bin/env python3
"""
dt_pt_listener.py  —  runs ON the physical F1Tenth car
-------------------------------------------------------
Receives UDP drive commands from dt_pt_bridge (WSL2/DT side) and
publishes them on /dt_drive — a SEPARATE topic from the Bluetooth
controller's /teleop — so the two sources never conflict.
 
A lightweight priority mux then decides which source controls the car:
  - Bluetooth controller (joy_teleop → /teleop) = HIGH priority
  - DT keyboard (UDP → /dt_drive)               = LOW priority
 
If the Bluetooth controller has been silent for more than `bt_timeout`
seconds, the mux switches to DT commands automatically. As soon as the
controller sends anything, it takes back control instantly.
 
This means:
  - Bluetooth always overrides keyboard (you can take manual control)
  - Keyboard drives the car when the controller is idle
  - No interference between the two sources
 
Published to /drive (what the VESC driver listens on).
 
Usage
-----
  export ROS_DOMAIN_ID=1
  python3 dt_pt_listener.py --port 9870 --echo-back
 
Parameters
----------
  --host        bind address (default 0.0.0.0)
  --port        UDP port     (default 9870)
  --echo-back   send UDP echo back to sender for RTT measurement
  --bt-timeout  seconds of Bluetooth silence before DT takes over (default 1.0)
  --output-topic topic the mux publishes to (default /drive)
"""
 
import argparse
import socket
import struct
import threading
import time
 
import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped, AckermannDrive
 
 
PACKET_FMT  = "<qff"
PACKET_SIZE = struct.calcsize(PACKET_FMT)   # 16 bytes
 
 
class DtPtListener(Node):
    def __init__(self, host: str, port: int, echo_back: bool,
                 bt_timeout: float, output_topic: str):
        super().__init__("dt_pt_listener")
 
        self._echo_back  = echo_back
        self._bt_timeout = bt_timeout
 
        # Publisher: final muxed output → VESC driver
        self._pub_out = self.create_publisher(
            AckermannDriveStamped, output_topic, 10
        )
 
        # Publisher: DT commands on their own topic (for inspection/logging)
        self._pub_dt = self.create_publisher(
            AckermannDriveStamped, "/dt_drive", 10
        )
 
        # Subscriber: Bluetooth controller
        self._sub_bt = self.create_subscription(
            AckermannDriveStamped, "/teleop",
            self._bt_callback, 10,
        )
 
        # State
        self._last_bt_time = 0.0        # monotonic time of last BT message
        self._last_dt_msg  = None       # most recent DT command
        self._lock         = threading.Lock()
 
        # UDP receive thread
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self.get_logger().info(
            f"Listening for DT commands on {host}:{port}  "
            f"(bt_timeout={bt_timeout}s, output={output_topic})"
        )
 
        self._udp_thread = threading.Thread(
            target=self._udp_recv_loop, daemon=True
        )
        self._udp_thread.start()
 
        # Mux timer — publishes the winning command at 50 Hz
        self._mux_timer = self.create_timer(0.02, self._mux_publish)
 
        self._active_source = "none"
 
    # ------------------------------------------------------------------
    # Bluetooth callback — just update timestamp, pass through immediately
    # ------------------------------------------------------------------
    def _bt_callback(self, msg: AckermannDriveStamped):
        with self._lock:
            self._last_bt_time = time.monotonic()
        # BT message goes straight to output — no mux delay
        self._pub_out.publish(msg)
        self._log_source("bluetooth")
 
    # ------------------------------------------------------------------
    # UDP receive — runs in background thread
    # ------------------------------------------------------------------
    def _udp_recv_loop(self):
        while rclpy.ok():
            try:
                data, addr = self._sock.recvfrom(64)
            except OSError:
                continue
 
            if len(data) < PACKET_SIZE:
                continue
 
            stamp_ns, steer, speed = struct.unpack_from(PACKET_FMT, data)
 
            msg = AckermannDriveStamped()
            msg.header.stamp.sec    = stamp_ns // 1_000_000_000
            msg.header.stamp.nanosec = stamp_ns % 1_000_000_000
            msg.header.frame_id     = "dt_recv"
            msg.drive = AckermannDrive(
                steering_angle=float(steer),
                speed=float(speed),
            )
 
            with self._lock:
                self._last_dt_msg = msg
 
            # Always publish to /dt_drive for logging regardless of mux state
            self._pub_dt.publish(msg)
 
            if self._echo_back:
                try:
                    self._sock.sendto(data, addr)
                except OSError:
                    pass
 
    # ------------------------------------------------------------------
    # Mux — runs at 50 Hz, publishes DT command only when BT is idle
    # ------------------------------------------------------------------
    def _mux_publish(self):
        now = time.monotonic()
        with self._lock:
            bt_age = now - self._last_bt_time
            dt_msg = self._last_dt_msg
 
        # BT controller is active — it already published directly, skip
        if bt_age < self._bt_timeout:
            return
 
        # BT is idle — publish most recent DT command if we have one
        if dt_msg is not None:
            self._pub_out.publish(dt_msg)
            self._log_source("dt_keyboard")
 
    # ------------------------------------------------------------------
    def _log_source(self, source: str):
        if source != self._active_source:
            self._active_source = source
            self.get_logger().info(
                f"Control source → {source.upper()}"
            )
 
    def destroy_node(self):
        self._sock.close()
        super().destroy_node()
 
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",         default="0.0.0.0")
    parser.add_argument("--port",         type=int,   default=9870)
    parser.add_argument("--echo-back",    action="store_true")
    parser.add_argument("--bt-timeout",   type=float, default=1.0,
                        help="Seconds of BT silence before DT takes over")
    parser.add_argument("--output-topic", default="/drive",
                        help="Topic to publish muxed commands on")
    args, ros_args = parser.parse_known_args()
 
    rclpy.init(args=ros_args)
    node = DtPtListener(
        args.host, args.port, args.echo_back,
        args.bt_timeout, args.output_topic,
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