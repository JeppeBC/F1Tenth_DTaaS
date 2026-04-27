#!/usr/bin/env python3
"""
ackermann_keyboard_teleop.py
-----------------------------
Purpose-built keyboard teleop for F1Tenth / Ackermann vehicles.
Publishes AckermannDriveStamped continuously at a fixed rate (50 Hz)
so the sim and PT receive smooth, non-stepping commands.

Controls
--------
  w / s   — increase / decrease speed  (+/- speed_step m/s)
  a / d   — steer left / right         (+/- steer_step rad)
  space   — full stop (speed=0, steer=0)
  r       — reset to zero
  q       — quit

Speed and steering values are held between keypresses — the car keeps
moving at the last commanded value until you change it.

Parameters  (--ros-args -p name:=value)
----------
  publish_topic   default: /teleop
  publish_hz      default: 50
  max_speed       default: 5.0   m/s
  max_steer       default: 3.14  rad  (~23 deg, typical F1Tenth limit)
  speed_step      default: 0.1   m/s per keypress
  steer_step      default: 0.1   rad per keypress

Run
---
  ros2 run f1tenth_gym_ros ackermann_keyboard_teleop
"""

import sys
import select
import termios
import tty
import threading
import rclpy
from rclpy.node import Node
from ackermann_msgs.msg import AckermannDriveStamped, AckermannDrive

BANNER = """
Ackermann keyboard teleop
--------------------------
  w / s   : faster / slower
  a / d   : steer left / right
  SPACE   : full stop
  r       : reset steering to centre
  q       : quit
--------------------------
"""


def get_key(timeout=0.05):
    """Read a single keypress without blocking longer than timeout seconds."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class AckermannKeyboardTeleop(Node):
    def __init__(self):
        super().__init__("ackermann_keyboard_teleop")

        self.declare_parameter("publish_topic", "/teleop")
        self.declare_parameter("publish_hz",    50.0)
        self.declare_parameter("max_speed",     5.0)
        self.declare_parameter("max_steer",     3.14)
        self.declare_parameter("speed_step",    0.1)
        self.declare_parameter("steer_step",    0.1)

        topic   = self.get_parameter("publish_topic").value
        hz      = self.get_parameter("publish_hz").value
        self._max_speed  = self.get_parameter("max_speed").value
        self._max_steer  = self.get_parameter("max_steer").value
        self._speed_step = self.get_parameter("speed_step").value
        self._steer_step = self.get_parameter("steer_step").value

        self._pub = self.create_publisher(AckermannDriveStamped, topic, 10)
        self._timer = self.create_timer(1.0 / hz, self._publish)

        self._speed = 0.0
        self._steer = 0.0
        self._lock  = threading.Lock()
        self._running = True

        # Keyboard input runs in a separate thread so it doesn't block spin()
        self._kb_thread = threading.Thread(target=self._keyboard_loop, daemon=True)
        self._kb_thread.start()

        print(BANNER)
        self._print_state()

    # ------------------------------------------------------------------
    def _keyboard_loop(self):
        while self._running and rclpy.ok():
            key = get_key(timeout=0.05)
            if key is None:
                continue
            with self._lock:
                if key == 'w':
                    self._speed = min(self._speed + self._speed_step, self._max_speed)
                elif key == 's':
                    self._speed = max(self._speed - self._speed_step, -self._max_speed)
                elif key == 'a':
                    self._steer = min(self._steer + self._steer_step, self._max_steer)
                elif key == 'd':
                    self._steer = max(self._steer - self._steer_step, -self._max_steer)
                elif key == ' ':
                    self._speed = 0.0
                    self._steer = 0.0
                elif key == 'r':
                    self._steer = 0.0
                elif key in ('q', '\x03'):   # q or Ctrl-C
                    self._speed = 0.0
                    self._steer = 0.0
                    self._running = False
                    rclpy.shutdown()
                    return
                else:
                    continue
            self._print_state()

    def _print_state(self):
        with self._lock:
            s, a = self._speed, self._steer
        bar_len = 20
        s_frac = (s + self._max_speed) / (2 * self._max_speed)
        a_frac = (a + self._max_steer) / (2 * self._max_steer)
        s_bar = ('=' * int(s_frac * bar_len)).ljust(bar_len)
        a_bar = ('=' * int(a_frac * bar_len)).ljust(bar_len)
        print(
            f"\r  speed [{s_bar}] {s:+.2f} m/s   "
            f"steer [{a_bar}] {a:+.3f} rad   ",
            end='', flush=True
        )

    # ------------------------------------------------------------------
    def _publish(self):
        with self._lock:
            speed = self._speed
            steer = self._steer
        msg = AckermannDriveStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "dt_send"   # marks message for latency logger
        msg.drive = AckermannDrive(
            speed=speed,
            steering_angle=steer,
        )
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = AckermannKeyboardTeleop()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Send a zero command before shutting down so the car/sim stops cleanly
        try:
            stop = AckermannDriveStamped()
            stop.header.stamp = node.get_clock().now().to_msg()
            stop.header.frame_id = "dt_send"
            node._pub.publish(stop)
        except Exception:
            pass
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
