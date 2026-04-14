# Troubleshooting

## Cannot SSH to the robot

- Confirm your laptop and the ROSOrin are on the same network.
- Try `ping 10.0.0.90` first.
- Check your router's DHCP lease list for the robot IP.
- Default credentials are `ubuntu` / `ubuntu`.

## The robot server fails to start

Make sure you source the ROS2 workspace first:

```bash
source ~/ros2_ws/install/setup.bash
python3 robot_server/server.py --port 8080
```

If `rclpy` or `geometry_msgs` is missing, the ROS2 workspace is not sourced.

## The robot server fails with `cv2` missing

Most ROSOrin images already provide OpenCV via the ROS2 workspace. If yours does not, install it:

```bash
pip3 install opencv-python
```

## The camera does not open

- Make sure another robot-side demo is not already using the same camera device.
- Reboot the robot if the camera was left in a bad state by another app.
- Check the server logs for camera-open errors.

## The robot stops moving by itself

That is usually the motor watchdog doing its job. If the server stops receiving commands for about half a second, it stops the motors for safety.

Common causes:

- Wi-Fi dropped
- the laptop client crashed
- the server is not actually running

## `python -m client.cli --help` works, but the full client still fails

That usually means one of the laptop runtime dependencies is missing. Reinstall them:

```bash
pip install -r requirements-laptop.txt
```

Also make sure you are running the client locally on the laptop desktop session, not inside SSH.

## Accepted episodes save badly or look inconsistent

Check these first:

- make sure the robot was actually receiving commands
- make sure the server was not dropping camera frames

The recorder now skips frames when motor commands fail instead of silently saving mismatched labels, but unstable Wi-Fi can still reduce collection quality.

## The CNN trainer says it is using only one session

That warning means training can still run, but true validation is skipped because there is only one recording session available.

Fix:

- collect at least one more `session_YYYYMMDD_HHMMSS` under `data/rosorin_cnn/episodes/`
- then train from the full CNN episodes root instead of one specific session folder

## LeRobot export fails

Check these common causes:

- `pip install -r requirements-export.txt` was never run
- `ffmpeg` is not installed or not on your `PATH`
- an episode folder is missing either `video.mp4` or `data.parquet`
- the MP4 frame count does not match the Parquet row count

If you are exporting older recordings, keep the default:

```bash
--state-source shifted_action
```

## The helper script does not run on Windows

`bash scripts/deploy_server.sh start` and `bash scripts/deploy_server.sh deps` need a Bash shell. Use Git Bash or WSL, or SSH into the robot and run the commands directly there.

## Battery and power notes

- Low battery causes strange behavior before it causes a full shutdown.
- Charge the pack if motion becomes inconsistent or the robot reboots unexpectedly.
- Start longer recording sessions only after checking battery health.
