"""Replay a recorded episode on the robot."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .robot_client import RobotClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay a recorded episode on the ROSOrin")
    parser.add_argument("--episode-dir", required=True,
                        help="Path to episode folder (contains data.parquet)")
    parser.add_argument("--robot-ip", default="10.0.0.90")
    parser.add_argument("--robot-port", type=int, default=8080)
    parser.add_argument("--velocity-range", type=float, default=0.6,
                        help="Max velocity used during normalization (m/s)")
    parser.add_argument("--speed-scale", type=float, default=1.0,
                        help="Scale factor for replay speed (0.5 = half speed)")
    parser.add_argument("--fps", type=int, default=10,
                        help="Replay rate (should match recording FPS)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions without sending to robot")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    episode_dir = Path(args.episode_dir)
    parquet_path = episode_dir / "data.parquet"

    if not parquet_path.exists():
        print(f"  ERROR: {parquet_path} not found")
        sys.exit(1)

    # Load episode data
    df = pd.read_parquet(parquet_path)
    actions = np.stack(df["action"].values)
    task = df["task"].iloc[0] if "task" in df.columns else "unknown"

    print()
    print("=" * 50)
    print("  ROSOrin Episode Replay")
    print("=" * 50)
    print(f"  Episode:  {episode_dir.name}")
    print(f"  Task:     {task}")
    print(f"  Frames:   {len(actions)}")
    print(f"  Duration: {len(actions) / args.fps:.1f}s at {args.fps} Hz")
    print(f"  Scale:    {args.speed_scale}x")
    if args.dry_run:
        print("  MODE:     DRY RUN (no commands sent)")
    print()

    # Denormalize actions back to m/s
    velocities = actions * args.velocity_range * args.speed_scale

    if args.dry_run:
        print("  Action preview (first 20 frames):")
        for i in range(min(20, len(velocities))):
            v = velocities[i]
            print(f"    {i:4d}: vx={v[0]:+.3f}  vy={v[1]:+.3f}  omega={v[2]:+.3f}")
        print(f"\n  ... ({len(velocities)} frames total)")
        return

    # Connect to robot
    robot_url = f"http://{args.robot_ip}:{args.robot_port}"
    client = RobotClient(robot_url=robot_url, timeout=1.0, max_retries=2)

    print("  Connecting to robot...")
    if not client.is_connected():
        print(f"  ERROR: Cannot reach robot at {robot_url}")
        return
    print("  Connected!")

    # Handle Ctrl+C gracefully
    stop_flag = False
    def on_signal(*_):
        nonlocal stop_flag
        stop_flag = True
    signal.signal(signal.SIGINT, on_signal)

    print(f"\n  Replaying in 3 seconds... (Ctrl+C to abort)")
    for i in range(3, 0, -1):
        print(f"    {i}...")
        time.sleep(1)
        if stop_flag:
            print("  Aborted.")
            return

    print("  REPLAYING...\n")
    period = 1.0 / args.fps
    start_time = time.monotonic()

    for i, vel in enumerate(velocities):
        if stop_flag:
            break

        vx, vy, omega = float(vel[0]), float(vel[1]), float(vel[2])

        try:
            client.send_velocity(vx, vy, omega)
        except Exception as e:
            print(f"\r  [WARN] Frame {i}: send failed: {e}   ", end="", flush=True)

        elapsed = time.monotonic() - start_time
        expected = (i + 1) * period
        status = "FWD" if vx > 0.01 else "BWD" if vx < -0.01 else "STOP"
        print(f"\r  [{i+1:4d}/{len(velocities)}] [{status:<4}] "
              f"vx={vx:+.3f} vy={vy:+.3f} omega={omega:+.3f}  "
              f"t={elapsed:.1f}s", end="", flush=True)

        # Sleep to maintain target FPS
        sleep_time = expected - (time.monotonic() - start_time)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Stop robot
    try:
        client.stop()
    except Exception:
        pass

    print(f"\n\n  Replay complete. {len(velocities)} frames in {time.monotonic() - start_time:.1f}s")


if __name__ == "__main__":
    main()
