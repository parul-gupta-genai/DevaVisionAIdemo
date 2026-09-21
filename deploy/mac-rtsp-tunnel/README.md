> **⚠️ DEPRECATED**: This is a macOS-specific setup. The project has moved to Windows.
> For Windows SSH tunnels, use `ssh -N -R ...` in PowerShell or set up a Windows Task Scheduler job.

# Mac → Jetson RTSP Reverse Tunnel

Exposes the camera at `192.168.1.121:554` (Mac's LAN) on the remote Jetson at
`127.0.0.1:8556` over SSH, so DevaVisionAI ingests it as
`rtsp://admin:Snap%401222@127.0.0.1:8556/stream1`.

Prerequisite (already done): `~/.ssh/id_ed25519_jetson` keypair, public key in
the Jetson's `~/.ssh/authorized_keys`.

## Install as a persistent service (survives reboots)

```bash
mkdir -p ~/.devavisionai
cp deploy/mac-rtsp-tunnel/rtsp-tunnel.sh ~/.devavisionai/rtsp-tunnel.sh
chmod +x ~/.devavisionai/rtsp-tunnel.sh
cp deploy/mac-rtsp-tunnel/com.devavisionai.rtsp-tunnel.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.devavisionai.rtsp-tunnel.plist
```

## Manage

```bash
# status
launchctl print gui/$(id -u)/com.devavisionai.rtsp-tunnel | head -20
# stop / start
launchctl bootout gui/$(id -u)/com.devavisionai.rtsp-tunnel
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.devavisionai.rtsp-tunnel.plist
# logs
tail -f ~/.devavisionai/rtsp-tunnel.log
```

launchd's `KeepAlive` restarts the tunnel automatically if the connection
drops; `ExitOnForwardFailure` makes a failed port-bind exit (and retry) instead
of hanging; `caffeinate -s` prevents system sleep while on AC power. The
Jetson-side pipeline re-adds the camera automatically ~30s after the tunnel
comes back (camera reconnect logic in `deepstream_pyds/main.py`).
