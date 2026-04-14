# Wi-Fi and SSH Guide

The ROSOrin (Jetson Orin) typically connects to your local network via Ethernet or Wi-Fi. Make sure both the robot and your laptop are on the same network.

## Default Access

The default SSH credentials for the ROSOrin are:

- Username: `ubuntu`
- Password: `ubuntu`
- Default IP: `10.0.0.90` (check your router if different)

```bash
ssh ubuntu@10.0.0.90
```

## Finding the Robot IP

If you do not know the robot IP, try:

- Router admin page or DHCP client list
- Local display and keyboard on the robot, then `hostname -I`
- `nmap -sn 10.0.0.0/24` from your laptop

## Connecting to Wi-Fi

If the ROSOrin is not already on your network, SSH in via Ethernet or direct connection and use:

```bash
nmcli dev wifi list
sudo nmcli device wifi connect "<SSID>" password "<PASSWORD>"
```

## Why Same Network Matters

- Your laptop keeps internet access for installs, updates, and uploads.
- SSH becomes a normal LAN workflow.
- The recording client can talk to the robot server directly while saving data on the laptop.

## References

- [Hiwonder ROSOrin documentation](https://docs.hiwonder.com/projects/ROSOrin/en/jetson-orin-nano-version/)
