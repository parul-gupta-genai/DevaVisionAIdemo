"""
Telemetry cache for system resources, GPU/CPU temperatures, and hardware metrics.
"""

import time
import threading


class TelemetryCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "gpu_usage": 0.0,
            "temperature": 0.0,
            "timestamp": time.time()
        }

    def update(self, key_or_dict, value=None):
        with self._lock:
            if isinstance(key_or_dict, dict):
                self._data.update(key_or_dict)
            elif value is not None:
                self._data[key_or_dict] = value
            self._data["timestamp"] = time.time()

    def get_all(self):
        with self._lock:
            return dict(self._data)


telemetry_cache = TelemetryCache()
