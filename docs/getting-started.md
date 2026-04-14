# Getting Started

This guide gets a student from "fresh clone" to "recording data" and then to either "trained CNN policy" or "exported LeRobot dataset."

If you are working on the separate CNN workflow, use [CNN Dataset And Training Guide](cnn.md) and [CNN V1 Overview](../design/cnn_v1/overview.html) alongside this page.

## What You Need

- A Hiwonder ROSOrin with Jetson Orin Nano and the vendor image installed
- A Windows, macOS, or Linux laptop with Python 3.10 or newer
- SSH access to the robot
- A Wi-Fi network that both the robot and the laptop can join

## Install Laptop Dependencies

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

The laptop requirements cover the recording client and local dataset writing.

## Install Robot Dependencies

On the ROSOrin:

```bash
python3 -m pip install -r requirements-robot.txt
```

Important:

- `rclpy` and `geometry_msgs` come from the ROS2 workspace, not from `pip`
- `cv2` is usually already present on the ROSOrin image
- this repo assumes you are using the normal ROSOrin software image with ROS2

If you prefer to do that from your laptop, use:

```bash
bash scripts/deploy_server.sh deps
```

## First Run Order

1. Follow [Wi-Fi and SSH Guide](wifi-and-ssh.md) to ensure the robot and laptop are on the same network.
2. Install the robot-side Python packages if needed.
3. Start the robot server.
4. Optionally test teleop-only mode.
5. Start the laptop launcher.
6. Choose `VLA-based` or `CNN-based`.
7. Record accepted episodes.
8. Train the CNN model or export VLA episodes to LeRobot.

## Start the Robot Server

Source the ROS2 workspace, then start the server:

```bash
source ~/ros2_ws/install/setup.bash
python3 robot_server/server.py --port 8080
```

If the repo only exists on your laptop, use the deploy helper from a Bash shell:

```bash
bash scripts/deploy_server.sh start
```

Windows users can run that from Git Bash or WSL.

## Start the Laptop Client

If you want to confirm the robot responds before recording:

```bash
python -m client.teleop --robot-ip 10.0.0.90
```

Then start the launcher:

```bash
python -m client.cli --robot-ip 10.0.0.90
```

The launcher then asks which workflow you want:

- `CNN-based`: image-only CNN dataset recording
- `VLA-based`: the original task-based dataset flow

## Where Recordings Are Saved

The client writes new timestamped folders under:

```text
data/<dataset_name>/
|-- raw/
`-- episodes/
```

Example:

```text
data/rosorin_nav/
|-- raw/session_20260401_101500/
`-- episodes/session_20260401_101500/
```

Each run gets its own `session_YYYYMMDD_HHMMSS` folder, so old recordings stay untouched.

## Train The CNN Policy

Install the training extras on the laptop:

```bash
pip install -r requirements-cnn.txt
```

Train from the CNN episode root:

```bash
python -m cnn_policy.train \
  --episodes-dir data/rosorin_cnn/episodes \
  --run-dir runs/cnn_v1
```

The `--run-dir` value is a base directory. Each training launch creates a fresh timestamped child run so older checkpoints stay untouched.

Evaluate a trained checkpoint:

```bash
python -m cnn_policy.eval \
  --episodes-dir data/rosorin_cnn/episodes \
  --checkpoint <RUN_DIR>/checkpoints/best.pt
```

Drive the robot using the trained checkpoint:

```bash
python -m cnn_policy.drive \
  --robot-ip 10.0.0.90 \
  --checkpoint <RUN_DIR>/checkpoints/best.pt
```

## Export To LeRobot

Install the export extras on the laptop:

```bash
pip install -r requirements-export.txt
```

Then run:

```bash
python scripts/export_lerobot.py \
  --episodes-dir data/rosorin_nav/episodes \
  --output-dir data/rosorin_nav/lerobot \
  --repo-id <HF_DATASET_REPO>
```

The default `--state-source shifted_action` is important. It reconstructs `observation.state` from the previous action so older recordings are still safe to use for training.

## Useful Flags

Shorter collection run:

```bash
python -m client.cli --robot-ip 10.0.0.90 --episodes 10 --episode-time 20
```

Different VLA dataset name:

```bash
python -m client.cli --robot-ip 10.0.0.90 --dataset classroom_nav
```

Different CNN dataset name:

```bash
python -m client.cli --robot-ip 10.0.0.90 --cnn-dataset classroom_cnn
```

Show export options:

```bash
python scripts/export_lerobot.py --help
```

## Change the Default Tasks

The built-in task list lives in `tasks.py`. Edit `DEFAULT_TASKS` to match your classroom task setup before you record.
