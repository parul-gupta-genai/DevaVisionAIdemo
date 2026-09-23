"""
Thread-safe shared runtime state for cameras, telemetry and plugin frame buffers.
"""

import threading

DATA_LOCK = threading.Lock()
LATEST_DATA = {}
FRAME_BUFFER = {}
