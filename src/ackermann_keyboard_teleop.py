#!/usr/bin/env python3

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
        self.declare_parameter("max_speed",     3.0)
        self.declare_parameter("max_steer",     0.4)
        self.declare_parameter("speed_step",    0.1)
        self.declare_parameter("steer_step",    0.05)

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

        # When idle (speed=0, steer=0), stop publishing so the mux /drive
        # slot times out (0.2s) and the joystick at priority 90 reclaims PT.
        if abs(speed) < 0.001 and abs(steer) < 0.001:
            return

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
