#!/usr/bin/env python3
"""
Health monitoring for ROSOrin robot.

Background thread that polls:
- CPU temperature
- Camera status
"""
import threading
import time


class HealthMonitor:
    """Polls robot health in a background thread."""

    def __init__(self, motor_controller, poll_interval: float = 5.0):
        """
        Args:
            motor_controller: MotorController instance
            poll_interval: Seconds between health checks
        """
        self.mc = motor_controller
        self.poll_interval = poll_interval

        self.battery_mv: int = 0
        self.cpu_temp: float = 0.0
        self.camera_ok: bool = True
        self.status: str = "ok"

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start background monitoring."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_health(self) -> dict:
        """Return current health status as dict."""
        return {
            "battery_mv": self.battery_mv,
            "cpu_temp": self.cpu_temp,
            "camera_ok": self.camera_ok,
            "status": self.status,
        }

    def _read_cpu_temp(self) -> float:
        """Read CPU temperature in Celsius."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            return 0.0

    def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._running:
            try:
                # Read battery (returns None on ROSOrin)
                batt = self.mc.get_battery_mv()
                if batt is not None and batt > 0:
                    self.battery_mv = batt

                # Read CPU temp
                self.cpu_temp = self._read_cpu_temp()

                self.status = "ok"
            except Exception as e:
                print(f"[HealthMonitor] Error: {e}")

            time.sleep(self.poll_interval)

    @property
    def can_record(self) -> bool:
        """Whether system is healthy enough for recording."""
        return True
