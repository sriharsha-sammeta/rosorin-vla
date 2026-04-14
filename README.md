# ROSOrin VLA

ROSOrin VLA is a recording and training stack for the Hiwonder ROSOrin (Jetson Orin + ROS2) with mecanum wheels.

It is split into two simple parts:

- The robot runs a lightweight HTTP server that bridges Flask to ROS2 `/controller/cmd_vel` for motor control and exposes camera, health, and servo endpoints.
- The laptop runs the keyboard teleop client, records episodes, and saves data locally under `data/`.

## What This Repo Includes

- `robot_server/`: Flask + ROS2 server that runs on the ROSOrin
- `client/`: keyboard teleop plus the launcher for VLA and CNN recording
- `cnn_policy/`: public CNN training, evaluation, and driving entrypoints
- `storage/`: raw backup writer, accepted-episode writer, and LeRobot exporter
- `scripts/deploy_server.sh`: helper script to copy the server to the robot and start it
- `scripts/export_lerobot.py`: converter from this repo's episode format to a LeRobot-compatible dataset
- `scripts/upload_hf_session.py`: interactive Hugging Face uploader for one recorded session
- `design/cnn_v1/overview.html`: visual architecture explainer for the CNN pipeline

This repo does not currently ship a dashboard app or a VLA training stack. It focuses on clean data collection, LeRobot export, and a separate CNN baseline.

## Quick Start

### 1. Set up the laptop

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-laptop.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-laptop.txt
```

### 2. Connect to the ROSOrin

SSH into the robot (default credentials: `ubuntu` / `ubuntu`):

```bash
ssh ubuntu@10.0.0.90
```

Make sure your laptop and the ROSOrin are on the same network.

### 3. Install robot-side Python packages

The ROSOrin image provides `rclpy`, `geometry_msgs`, and `cv2` via the ROS2 workspace. Install the lightweight extras:

```bash
python3 -m pip install -r requirements-robot.txt
```

or from your laptop through the helper script:

```bash
bash scripts/deploy_server.sh deps
```

### 4. Start the robot server

On the ROSOrin, first stop the default app service and start the chassis controller:

```bash
sudo systemctl stop start_app_node.service
ros2 launch controller controller.launch.py
```

Then in a **second terminal**, start our server:

```bash
python3 robot_server/server.py --port 8080
```

The ROS2 workspace is auto-sourced by the ROSOrin's `.zshrc` — no manual sourcing needed. The controller node must be running — it subscribes to `/controller/cmd_vel` and drives the motors.

If the repo only exists on your laptop, use the helper script from Git Bash, WSL, or another Bash shell:

```bash
bash scripts/deploy_server.sh start
```

### 5. Start the laptop client

If you want to test driving before recording, use teleop-only mode:

```bash
python -m client.teleop --robot-ip 10.0.0.90
```

Then, when you are ready to collect data, start the launcher:

```bash
python -m client.cli --robot-ip 10.0.0.90
```

The launcher will then ask whether you want:

- `CNN-based`
- `VLA-based`

Choose `VLA-based` for the original left/right/front/behind task flow. Choose `CNN-based` for the image-only CNN dataset flow.

### 6. Train the CNN baseline

Install the CNN training extras on the laptop:

```bash
pip install -r requirements-cnn.txt
```

Then train from the CNN episode root:

```bash
python -m cnn_policy.train \
  --episodes-dir data/rosorin_cnn/episodes \
  --run-dir runs/cnn_v1
```

After training starts, note the printed run directory, for example `runs/cnn_v1/run_YYYYMMDD_HHMMSS`. Use that concrete folder as `<RUN_DIR>` in the next commands.

Evaluate a checkpoint:

```bash
python -m cnn_policy.eval \
  --episodes-dir data/rosorin_cnn/episodes \
  --checkpoint <RUN_DIR>/checkpoints/best.pt
```

Drive the robot from the trained CNN:

```bash
python -m cnn_policy.drive \
  --robot-ip 10.0.0.90 \
  --checkpoint <RUN_DIR>/checkpoints/best.pt
```

### 7. Upload One Recorded Session To Hugging Face

If you want a picker that shows the saved sessions, episode counts, and then uploads the selected one to a dataset repo named after that session:

```bash
python scripts/upload_hf_session.py
```

### 8. Export to LeRobot format

After you record accepted episodes, install the export extras:

```bash
pip install -r requirements-export.txt
```

Then convert your saved episodes:

```bash
python scripts/export_lerobot.py \
  --episodes-dir data/rosorin_nav/episodes \
  --output-dir data/rosorin_nav/lerobot \
  --repo-id <HF_DATASET_REPO>
```

By default the exporter uses `--state-source shifted_action`, which repairs older sessions where `observation.state` was incorrectly saved as the same-step action label.

### 9. Inspect what was recorded

```bash
python scripts/inspect_episode.py --episodes-dir data/rosorin_nav/episodes
```

## Docs

- [Getting Started](docs/getting-started.md)
- [Wi-Fi and SSH Guide](docs/wifi-and-ssh.md)
- [Data Collection Guide](docs/data-collection.md)
- [CNN Dataset And Training Guide](docs/cnn.md)
- [CNN V1 Overview](design/cnn_v1/overview.html)
- [Troubleshooting](docs/troubleshooting.md)

## Repo Layout

```text
.
|-- client/
|-- cnn_policy/
|-- design/
|-- robot_server/
|-- scripts/
|-- storage/
|-- data/                    # created automatically when you record or export
|-- requirements-laptop.txt
|-- requirements-robot.txt
|-- requirements-cnn.txt
|-- requirements-export.txt
`-- docs/
```

## Official Commands

Laptop:

```bash
python -m client.cli --robot-ip 10.0.0.90
python -m client.teleop --robot-ip 10.0.0.90
python -m cnn_policy.train --episodes-dir data/rosorin_cnn/episodes --run-dir runs/cnn_v1
python -m cnn_policy.eval --episodes-dir data/rosorin_cnn/episodes --checkpoint <FILE>
python -m cnn_policy.drive --robot-ip 10.0.0.90 --checkpoint <FILE>
python scripts/upload_hf_session.py
python scripts/inspect_episode.py --episodes-dir data/rosorin_nav/episodes
python scripts/export_lerobot.py --episodes-dir data/rosorin_nav/episodes --output-dir data/rosorin_nav/lerobot --repo-id <HF_DATASET_REPO>
```

Robot (two terminals needed — ROS2 is auto-sourced by .zshrc):

```bash
# Terminal 1: stop default app and start chassis controller
sudo systemctl stop start_app_node.service
ros2 launch controller controller.launch.py

# Terminal 2: start our server
python3 robot_server/server.py --port 8080
```

Laptop helper for deploying the server:

```bash
bash scripts/deploy_server.sh deps
bash scripts/deploy_server.sh start
```

## Hardware

- Hiwonder ROSOrin with Jetson Orin Nano
- Mecanum wheel chassis (wheelbase 0.177m, track width 0.172m)
- ROS2 controller publishing on `/controller/cmd_vel` (geometry_msgs/Twist)
- USB camera or depth camera (`/usb_cam/image_raw` or `/depth_cam/rgb0/image_raw`)
- Linear velocity range: -0.6 to 0.6 m/s

## Notes for Open-Source Users

- Runtime data is not tracked in this repo. Recording runs create timestamped folders under `data/<dataset_name>/`.
- Accepted episodes are stored as one folder per episode with `video.mp4` plus `data.parquet`.
- The recorder saves `observation.state` as the previous normalized action, not the current action, to avoid target leakage during training.
- `rclpy` and `geometry_msgs` come from the ROSOrin ROS2 workspace, not from `pip`.

## References

- [Hiwonder ROSOrin documentation](https://docs.hiwonder.com/projects/ROSOrin/en/jetson-orin-nano-version/)
- [Hugging Face LeRobot datasets docs](https://huggingface.co/docs/lerobot/main/en/lerobot-dataset-v3)
