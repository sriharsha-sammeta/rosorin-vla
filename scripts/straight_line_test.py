"""Send a constant velocity for N seconds and measure how far the car moves.

Usage:
    python scripts/straight_line_test.py --vx 0.15 --duration 5

Put the car at a known start position, run the script, measure the distance
it travels with a tape measure. Compare to the expected value printed below.
"""

from __future__ import annotations

import argparse
import time

from client.robot_client import RobotClient


def main() -> None:
    p = argparse.ArgumentParser(description="Constant-velocity HTTP probe")
    p.add_argument("--robot-ip", default="10.0.0.90")
    p.add_argument("--robot-port", type=int, default=8080)
    p.add_argument("--vx", type=float, default=0.15, help="Forward velocity (m/s)")
    p.add_argument("--vy", type=float, default=0.0)
    p.add_argument("--omega", type=float, default=0.0)
    p.add_argument("--duration", type=float, default=5.0, help="Seconds")
    p.add_argument("--fps", type=float, default=10.0, help="Command rate (Hz)")
    args = p.parse_args()

    client = RobotClient(
        robot_url=f"http://{args.robot_ip}:{args.robot_port}",
        timeout=1.0,
        max_retries=1,
    )
    if not client.is_connected():
        print(f"ERROR: robot not reachable at {args.robot_ip}:{args.robot_port}")
        return

    expected_dx = args.vx * args.duration
    period = 1.0 / args.fps

    print(f"Sending vx={args.vx} vy={args.vy} omega={args.omega} for {args.duration:.1f}s at {args.fps:.0f} Hz")
    print(f"Expected forward distance: {expected_dx * 100:.1f} cm")
    print("Ctrl+C to abort.\n")

    countdown = 3
    for i in range(countdown, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1.0)

    sent = 0
    failed = 0
    t0 = time.monotonic()
    next_send = t0
    try:
        while True:
            now = time.monotonic()
            if now - t0 >= args.duration:
                break
            if now >= next_send:
                try:
                    ok = client.send_velocity(args.vx, args.vy, args.omega)
                    if ok:
                        sent += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
                next_send += period
            time.sleep(0.001)
    finally:
        client.stop()
        elapsed = time.monotonic() - t0
        rate = sent / elapsed if elapsed > 0 else 0
        print()
        print(f"  Elapsed:   {elapsed:.2f}s")
        print(f"  Sent:      {sent} commands ({failed} failed)")
        print(f"  Avg rate:  {rate:.1f} Hz (target {args.fps:.0f})")
        print(f"  Expected:  {expected_dx * 100:.1f} cm forward")
        print(f"  Measured:  ________ cm  <-- fill in")


if __name__ == "__main__":
    main()
