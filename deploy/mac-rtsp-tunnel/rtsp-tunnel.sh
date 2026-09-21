#!/bin/bash
# DevaVisionAI RTSP reverse tunnel
# Exposes the LAN camera 192.168.1.121:554 (Mac network) on the remote
# Jetson Orin NX at 127.0.0.1:8556, so its DeepStream pipeline can ingest
#   rtsp://admin:<pw>@127.0.0.1:8556/stream1
# Managed by launchd (com.devavisionai.rtsp-tunnel) which restarts it on exit.
# caffeinate -s keeps the Mac from sleeping while the tunnel is up (AC power).

exec /usr/bin/caffeinate -s /usr/bin/ssh -N \
  -i /Users/ibm/.ssh/id_ed25519_jetson \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -o ConnectTimeout=15 \
  -o StrictHostKeyChecking=accept-new \
  -R 127.0.0.1:8556:192.168.1.121:554 \
  user@106.201.231.217
