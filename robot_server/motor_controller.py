#!/usr/bin/env python3
"""Motor controller wrapper for the ROSOrin (Jetson Orin) kit.

Publishes velocity commands on /cmd_vel and subscribes to
/controller/cmd_vel to observe the actual velocity being executed
(regardless of who sent it — our teleop, iOS app, or joystick).
"""

import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


# ROSOrin linear velocity limits (m/s) per the docs
MAX_LINEAR = 0.6   # -0.6 to 0.6
MAX_ANGULAR = 2.0  # reasonable mecanum yaw rate


def mecanum_ik(vx: float, vy: float, omega: float) -> dict:
    """Return a velocity dict (kept for API compat with server.py).

    On ROSOrin the actual IK is handled by the onboard controller node,
    so we just pass through the body-frame velocities.
    """
    return {"vx": vx, "vy": vy, "omega": omega}


class MotorController(Node):
    """Thread-safe ROS2 motor controller with velocity observation."""

    def __init__(self, max_linear: float = MAX_LINEAR,
                 max_angular: float = MAX_ANGULAR):
        # Initialise rclpy once (safe to call multiple times)
        if not rclpy.ok():
            rclpy.init()

        super().__init__('turbovla_motor_controller')

        self.max_linear = max_linear
        self.max_angular = max_angular
        self._lock = threading.Lock()
        self._last_command_time = time.monotonic()

        # Publish on /controller/cmd_vel — same path the joystick uses.
        # Goes directly to cmd_vel_callback in odom_publisher_node with no
        # clamping/ramping, so replay and inference behave identically to
        # a human driving with the joystick. Safety clamping still happens
        # inside set_velocity() below (±max_linear / ±max_angular).
        self._pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)

        # Subscribe to /controller/cmd_vel to observe the actual velocity
        # being executed, regardless of who sent it (teleop, iOS app, joystick)
        self._observed_vx = 0.0
        self._observed_vy = 0.0
        self._observed_omega = 0.0
        self._observed_time = 0.0
        self._obs_lock = threading.Lock()

        self.create_subscription(
            Twist,
            '/controller/cmd_vel',
            self._velocity_observer_callback,
            1,
        )

        # Spin in a background thread so callbacks are processed
        self._spin_thread = threading.Thread(target=self._spin, daemon=True)
        self._spin_thread.start()

        time.sleep(0.2)
        self.get_logger().info('MotorController ready (pub=/controller/cmd_vel, obs=/controller/cmd_vel)')

    def _spin(self):
        """Background rclpy spin."""
        try:
            rclpy.spin(self)
        except Exception:
            pass

    def _velocity_observer_callback(self, msg: Twist) -> None:
        """Record the latest velocity command seen on /controller/cmd_vel."""
        with self._obs_lock:
            self._observed_vx = msg.linear.x
            self._observed_vy = msg.linear.y
            self._observed_omega = msg.angular.z
            self._observed_time = time.monotonic()
            self._last_command_time = self._observed_time

    def get_observed_velocity(self) -> dict:
        """Return the latest velocity observed on /controller/cmd_vel.

        This captures commands from ANY source: our teleop, iOS app,
        joystick, or any other ROS2 publisher.
        """
        with self._obs_lock:
            return {
                "vx": self._observed_vx,
                "vy": self._observed_vy,
                "omega": self._observed_omega,
                "timestamp": self._observed_time,
            }

    # --- clamping helpers ---

    def _clamp_linear(self, v: float) -> float:
        return max(-self.max_linear, min(self.max_linear, v))

    def _clamp_angular(self, v: float) -> float:
        return max(-self.max_angular, min(self.max_angular, v))

    # --- public API (same signatures the server already calls) ---

    def set_velocity(self, vx: float, vy: float, omega: float) -> dict:
        """Send a body-frame velocity command."""
        vx = self._clamp_linear(vx)
        vy = self._clamp_linear(vy)
        omega = self._clamp_angular(omega)

        msg = Twist()
        msg.linear.x = float(vx)
        msg.linear.y = float(vy)
        msg.angular.z = float(omega)

        with self._lock:
            self._pub.publish(msg)
            self._last_command_time = time.monotonic()

        return {"vx": vx, "vy": vy, "omega": omega}

    def set_raw_wheels(self, wheels: list[list]) -> None:
        """Translate raw wheel duties to a velocity command.

        The ROSOrin doesn't expose per-wheel duty control over ROS2,
        so we approximate: average forward = vx, average strafe = vy.
        For precise control, prefer set_velocity().
        """
        # Simple approximation from 4-wheel duties
        if len(wheels) == 4:
            d = {w[0]: w[1] for w in wheels}
            # Reverse the mecanum IK (approximate)
            vx = (d.get(1, 0) + d.get(2, 0) + d.get(3, 0) + d.get(4, 0)) / 4.0
            vy = (-d.get(1, 0) + d.get(2, 0) + d.get(3, 0) - d.get(4, 0)) / 4.0
            omega = (-d.get(1, 0) + d.get(2, 0) - d.get(3, 0) + d.get(4, 0)) / 4.0
            # Scale from duty (0-100) to m/s (0-0.6)
            scale = self.max_linear / 100.0
            self.set_velocity(vx * scale, vy * scale, omega * scale)
        else:
            self.stop()

    def stop(self) -> None:
        """Stop all motors immediately."""
        msg = Twist()  # all zeros
        with self._lock:
            self._pub.publish(msg)
            self._last_command_time = time.monotonic()

    def center_servos(self) -> None:
        """No-op on ROSOrin (no pan-tilt servo via this interface)."""
        pass

    def set_servos(self, positions: list[list]) -> None:
        """No-op on ROSOrin."""
        self.get_logger().warn('set_servos() not available on ROSOrin')

    def get_battery_mv(self) -> int | None:
        """Battery reading not available via this ROS2 interface."""
        return None

    def get_imu(self) -> tuple | None:
        """IMU not read via this interface (use ROS2 /imu topic instead)."""
        return None

    def beep(self, freq: int = 1900, on_time: float = 0.1,
             off_time: float = 0.0, repeat: int = 1) -> None:
        """No-op on ROSOrin."""
        pass

    def set_rgb(self, colors: list[list]) -> None:
        """No-op on ROSOrin."""
        pass

    @property
    def seconds_since_last_command(self) -> float:
        return time.monotonic() - self._last_command_time

    def destroy(self) -> None:
        """Clean shutdown."""
        self.stop()
        self.destroy_node()
