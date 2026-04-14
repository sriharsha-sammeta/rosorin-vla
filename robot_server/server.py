#!/usr/bin/env python3
"""
ROSOrin Robot Server — lightweight HTTP API for remote control.

Runs on the Jetson Orin. Exposes camera, motors, and health over HTTP.
The recording client on the laptop connects to this server.

Prerequisites (run in separate terminals):
    1. sudo systemctl stop start_app_node.service
    2. ros2 launch controller controller.launch.py
    3. ros2 launch peripherals depth_camera.launch.py

Endpoints:
    GET  /stream    — MJPEG live stream (for dashboard)
    GET  /snapshot  — Single JPEG frame with X-Timestamp header
    POST /motor     — Send wheel duties: {"wheels": [[1,d1],[2,d2],[3,d3],[4,d4]]}
    POST /velocity  — Send body velocity: {"vx": 0, "vy": 0, "omega": 0}
    POST /stop      — Emergency stop all motors
    GET  /health    — Battery, CPU temp, camera status
    POST /servo     — Set servos: {"servos": [[1,1500],[2,1500]]}
    POST /buzzer    — Play tone: {"freq": 1900, "duration": 0.1}
    GET  /          — Simple status page

Usage:
    python3 server.py [--port 8080]
"""
import os
import sys
import time
import json
import signal
import argparse
import threading
from io import BytesIO

import cv2
from flask import Flask, Response, request, jsonify

# Import our modules from the same directory
from motor_controller import MotorController, mecanum_ik
from health_monitor import HealthMonitor


# --- Camera Capture via ROS2 Topic ---

class CameraCapture:
    """Subscribes to a ROS2 image topic and caches JPEG frames.

    The ROSOrin's depth camera has no /dev/video* device — it is only
    accessible through the ROS2 depth_camera node which publishes on
    /depth_cam/rgb0/image_raw.  Launch it first:
        ros2 launch peripherals depth_camera.launch.py
    """

    def __init__(self, ros_node, topic: str = "/depth_cam/rgb0/image_raw",
                 jpeg_quality: int = 70):
        self._node = ros_node
        self._topic = topic
        self.jpeg_quality = jpeg_quality

        self._frame: bytes | None = None
        self._raw_frame = None
        self._timestamp: float = 0.0
        self._frame_index: int = 0
        self._lock = threading.Lock()
        self._running = False

        try:
            from cv_bridge import CvBridge
            self._bridge = CvBridge()
        except ImportError:
            self._bridge = None
            print("[Camera] WARNING: cv_bridge not found, using manual conversion")

    def start(self) -> bool:
        """Subscribe to the ROS2 image topic. Returns True on success."""
        from sensor_msgs.msg import Image as RosImage

        self._sub = self._node.create_subscription(
            RosImage,
            self._topic,
            self._image_callback,
            1,
        )
        self._running = True
        print(f"[Camera] Subscribed to {self._topic}")
        print(f"[Camera] Waiting for first frame...")

        # Wait up to 10s for the first frame
        deadline = time.monotonic() + 10.0
        while self._timestamp == 0 and time.monotonic() < deadline:
            time.sleep(0.1)

        if self._timestamp == 0:
            print(f"[Camera] ERROR: No frames received on {self._topic} after 10s")
            print(f"[Camera] Make sure depth camera is launched:")
            print(f"[Camera]   ros2 launch peripherals depth_camera.launch.py")
            return False

        print(f"[Camera] Receiving frames on {self._topic}")
        return True

    def stop(self) -> None:
        """Stop receiving frames."""
        self._running = False

    def _image_callback(self, msg) -> None:
        """ROS2 image topic callback."""
        if not self._running:
            return

        try:
            if self._bridge is not None:
                frame = self._bridge.imgmsg_to_cv2(msg, "bgr8")
            else:
                import numpy as np
                frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(
                    msg.height, msg.width, -1)
                if msg.encoding == "rgb8":
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"[Camera] Conversion error: {e}")
            return

        # Encode to JPEG
        ok, jpeg = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        )
        if not ok:
            return

        with self._lock:
            self._frame = jpeg.tobytes()
            self._raw_frame = frame
            self._timestamp = time.monotonic()
            self._frame_index += 1

    def get_jpeg(self) -> tuple[bytes | None, float, int]:
        """Get latest JPEG frame, timestamp, and frame index."""
        with self._lock:
            return self._frame, self._timestamp, self._frame_index

    def get_raw(self):
        """Get latest raw BGR numpy frame."""
        with self._lock:
            return self._raw_frame

    @property
    def is_alive(self) -> bool:
        """Whether camera is capturing frames."""
        if not self._running:
            return False
        with self._lock:
            if self._timestamp == 0:
                return False
            return (time.monotonic() - self._timestamp) < 2.0


# --- Motor Watchdog ---

class MotorWatchdog:
    """Stops motors if no command received within timeout."""

    def __init__(self, motor_controller: MotorController, timeout: float = 0.5):
        self.mc = motor_controller
        self.timeout = timeout
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _watchdog_loop(self) -> None:
        while self._running:
            if self.mc.seconds_since_last_command > self.timeout:
                self.mc.stop()
            time.sleep(0.05)  # Check every 50ms


# --- Flask App ---

def create_app(mc: MotorController, camera: CameraCapture,
               health: HealthMonitor) -> Flask:
    """Create Flask app with all endpoints."""
    app = Flask(__name__)

    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.route('/')
    def index():
        h = health.get_health()
        return jsonify({
            "name": "ROSOrin Robot Server (ROS2)",
            "camera": camera.is_alive,
            "health": h,
            "endpoints": ["/stream", "/snapshot", "/motor", "/velocity",
                          "/stop", "/health", "/servo", "/buzzer"],
        })

    @app.route('/stream')
    def stream():
        """MJPEG live stream for dashboard viewing."""
        def generate():
            while True:
                jpeg, _, _ = camera.get_jpeg()
                if jpeg is None:
                    time.sleep(0.033)
                    continue
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       jpeg + b'\r\n')
                time.sleep(0.033)  # ~30fps max

        return Response(generate(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/snapshot')
    def snapshot():
        """Single JPEG frame with timing headers for recording."""
        jpeg, timestamp, frame_idx = camera.get_jpeg()
        if jpeg is None:
            return Response("No frame available", status=503)

        response = Response(jpeg, mimetype='image/jpeg')
        response.headers['X-Timestamp'] = f"{timestamp:.6f}"
        response.headers['X-Frame-Index'] = str(frame_idx)
        response.headers['Cache-Control'] = 'no-cache, no-store'
        return response

    @app.route('/motor', methods=['POST', 'OPTIONS'])
    def motor():
        """Send raw wheel duties: {"wheels": [[1,d1],[2,d2],[3,d3],[4,d4]]}"""
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json(silent=True)
        if not data or 'wheels' not in data:
            return jsonify({"ok": False, "error": "Missing 'wheels' field"}), 400

        try:
            mc.set_raw_wheels(data['wheels'])
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/velocity', methods=['POST', 'OPTIONS'])
    def velocity():
        """Send body velocity: {"vx": 0, "vy": 0, "omega": 0}"""
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False, "error": "Missing JSON body"}), 400

        vx = float(data.get('vx', 0))
        vy = float(data.get('vy', 0))
        omega = float(data.get('omega', 0))

        try:
            wheels = mc.set_velocity(vx, vy, omega)
            return jsonify({"ok": True, "wheels": wheels})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/stop', methods=['POST', 'OPTIONS'])
    def stop():
        """Emergency stop all motors."""
        if request.method == 'OPTIONS':
            return '', 204
        mc.stop()
        return jsonify({"ok": True})

    @app.route('/health')
    def health_endpoint():
        """System health: battery, CPU temp, camera status."""
        h = health.get_health()
        h['camera_ok'] = camera.is_alive
        h['uptime_s'] = time.monotonic()
        return jsonify(h)

    @app.route('/servo', methods=['POST', 'OPTIONS'])
    def servo():
        """Set servo positions: {"servos": [[1,1500],[2,1500]]}"""
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json(silent=True)
        if not data or 'servos' not in data:
            return jsonify({"ok": False, "error": "Missing 'servos' field"}), 400

        try:
            mc.set_servos(data['servos'])
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/buzzer', methods=['POST', 'OPTIONS'])
    def buzzer():
        """Play buzzer tone: {"freq": 1900, "duration": 0.1}"""
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json(silent=True) or {}
        freq = int(data.get('freq', 1900))
        duration = float(data.get('duration', 0.1))

        try:
            mc.beep(freq, duration)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return app


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="ROSOrin Robot Server")
    parser.add_argument('--port', type=int, default=8080, help='HTTP port')
    parser.add_argument('--camera-topic', default='/depth_cam/rgb0/image_raw',
                        help='ROS2 image topic for camera frames')
    parser.add_argument('--watchdog-timeout', type=float, default=0.5,
                        help='Seconds before watchdog stops motors')
    parser.add_argument('--max-linear', type=float, default=0.6,
                        help='Maximum linear velocity (m/s)')
    parser.add_argument('--jpeg-quality', type=int, default=70,
                        help='JPEG compression quality (0-100)')
    args = parser.parse_args()

    # Kill anything on our port
    os.system(f"sudo fuser -k {args.port}/tcp 2>/dev/null")
    time.sleep(0.3)

    print("=" * 50)
    print("  ROSOrin Robot Server")
    print("=" * 50)

    # Initialize motor controller
    print("[Init] Motor controller...")
    mc = MotorController(max_linear=args.max_linear)

    # Initialize camera (subscribes to ROS2 image topic)
    print(f"[Init] Camera on {args.camera_topic}...")
    camera = CameraCapture(
        ros_node=mc,
        topic=args.camera_topic,
        jpeg_quality=args.jpeg_quality,
    )
    if not camera.start():
        print("[FATAL] No camera frames. Make sure the depth camera node is running:")
        print("  ros2 launch peripherals depth_camera.launch.py")
        sys.exit(1)

    # Initialize health monitor
    print("[Init] Health monitor...")
    health = HealthMonitor(mc, poll_interval=5.0)
    health.start()

    # Initialize motor watchdog
    print("[Init] Motor watchdog (timeout={:.1f}s)...".format(args.watchdog_timeout))
    watchdog = MotorWatchdog(mc, timeout=args.watchdog_timeout)
    watchdog.start()

    # Create Flask app
    app = create_app(mc, camera, health)

    # Graceful shutdown
    def shutdown(*_):
        print("\n[Shutdown] Stopping motors...")
        mc.stop()
        mc.destroy()
        print("[Shutdown] Stopping camera...")
        camera.stop()
        print("[Shutdown] Stopping watchdog...")
        watchdog.stop()
        print("[Shutdown] Stopping health monitor...")
        health.stop()
        print("[Shutdown] Done.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start server
    import socket
    hostname = socket.gethostname()
    ip_addrs = []
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if 2 in addrs:  # AF_INET
                for addr in addrs[2]:
                    ip = addr.get('addr', '')
                    if ip and ip != '127.0.0.1':
                        ip_addrs.append(ip)
    except ImportError:
        pass

    print()
    print("┌──────────────────────────────────────────┐")
    print("│  ROSOrin Robot Server                    │")
    print("├──────────────────────────────────────────┤")
    for ip in ip_addrs:
        print(f"│  http://{ip}:{args.port:<5}                  │")
    print("│                                          │")
    print("│  Endpoints:                              │")
    print("│    /stream   — MJPEG live stream         │")
    print("│    /snapshot — Single frame + timestamp  │")
    print("│    /motor    — Send wheel duties          │")
    print("│    /velocity — Send body velocity        │")
    print("│    /stop     — Emergency stop            │")
    print("│    /health   — Battery + system health   │")
    print("│    /servo    — Pan-tilt control          │")
    print("│    /buzzer   — Audio feedback            │")
    print("│                                          │")
    print("│  Ctrl+C to stop                          │")
    print("└──────────────────────────────────────────┘")
    print()

    # Run Flask (single-threaded is fine for our use case,
    # but threaded=True allows concurrent snapshot + motor requests)
    app.run(host='0.0.0.0', port=args.port, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
