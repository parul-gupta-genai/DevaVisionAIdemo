import threading
import time
from typing import List, Dict, Any
from loguru import logger
from database.session import SessionLocal
from config.config import config

from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext
from app.engine.plugin_manager import PluginManager
from database.models.models import CameraEvent

class DetectionEngine:
    """
    Manages and orchestrates detection plugins dynamically.
    Lazy loads plugins to save RAM/GPU and garbage collects when disabled.

    Thread-model: run_plugins may be called concurrently for DIFFERENT
    cameras (the AnalyticsDispatcher serializes per camera). Plugin state in
    TrackerContext is per-(plugin, camera); plugins whose class declares
    thread_safe=False additionally run under a per-plugin lock because they
    keep instance-level state shared across cameras.
    """
    def __init__(self):
        from config.config import config
        self.plugin_manager = PluginManager(app_config=config)
        self.available_plugin_classes = {
            c.__name__: c for c in self.plugin_manager.discover_plugin_classes()
        }

        self.active_plugins: Dict[str, BaseDetectionPlugin] = {}
        self.tracker_context = TrackerContext()

        self._plugins_lock = threading.Lock()
        self._plugin_run_locks: Dict[str, threading.Lock] = {}
        # (camera_id, plugin) -> frame_num of its last actual run. Drives the
        # deadline-based sampling schedule; see run_plugins.
        self._last_run_frame: Dict[tuple, int] = {}
        # Same, for the probe-side copy decision in frame_needed_for.
        self._last_frame_supplied: Dict[tuple, int] = {}
        # Rolling per-plugin cost (ms, EMA) — surfaced by the dispatcher's
        # stats log and the plugin manager UI.
        self.plugin_ms_ema: Dict[str, float] = {}

        # Pre-instantiate all discovered plugins on startup for low latency
        for plugin_name, plugin_class in self.available_plugin_classes.items():
            try:
                plugin_instance = plugin_class(app_config=config)
                plugin_instance.initialize()
                self.active_plugins[plugin_name] = plugin_instance
            except Exception as e:
                logger.warning(f"Plugin {plugin_name} initialization deferred: {e}")

        logger.info(f"Initialized DetectionEngine with {len(self.active_plugins)} active plugins.")

    def _sync_plugins(self, allowed_plugins: List[str]):
        """Dynamically instantiates or garbage collects plugins based on the active config."""
        from config.config import config

        if not allowed_plugins:
            return

        missing = [
            p for p in allowed_plugins
            if p not in self.active_plugins and p in self.available_plugin_classes
        ]
        if not missing:
            return

        with self._plugins_lock:
            for plugin_name in missing:
                if plugin_name in self.active_plugins:
                    continue
                try:
                    plugin_class = self.available_plugin_classes[plugin_name]
                    plugin_instance = plugin_class(app_config=config)
                    plugin_instance.initialize()
                    self.active_plugins[plugin_name] = plugin_instance
                except Exception as e:
                    logger.error(f"Failed to lazy load {plugin_name}: {e}")

    def get_all_required_classes(self, camera_id: str) -> List[int]:
        classes = set()
        for p in list(self.active_plugins.values()):
            classes.update(p.get_required_classes())
        return list(classes)

    @staticmethod
    def _sampling_interval(plugin_name: str) -> int:
        """Frames between runs for a plugin (1 = every frame), hot-reloadable."""
        return config.get_sampling_interval(plugin_name)

    def frame_needed_for(self, camera_id: str, frame_num: int) -> bool:
        """
        True when the probe must copy frame pixels for this camera on this
        frame: some enabled plugin declares needs_frame and is due per its
        FRAME schedule. Metadata-only cameras never pay for the copy.

        The frame schedule is separate from the run schedule: a plugin can run
        every frame (the visitor tripwire must, to catch a crossing) while
        only needing pixels occasionally. At 25 cameras the RGBA->BGR copy is
        the probe's dominant cost, so this distinction matters.
        """
        allowed = config.get_allowed_plugins(camera_id)
        if not allowed:
            return False

        # The per-plugin schedule is evaluated FIRST and unconditionally. It
        # advances the same deadline markers run_plugins uses, so the two stay
        # in lockstep; returning early from the snapshot branch below left the
        # plugin markers unstamped for that frame, put the two schedules one
        # frame out of phase, and a needs_frame plugin then ran on a frame the
        # probe had been told not to copy — i.e. with no pixels at all.
        for name in allowed:
            plugin = self.active_plugins.get(name)
            cls = plugin.__class__ if plugin else self.available_plugin_classes.get(name)
            if cls is None or not getattr(cls, "needs_frame", False):
                continue
            # Mirror run_plugins' deadline schedule so the probe copies pixels
            # on the frames the plugin will actually run on. A modulo test
            # here would drift out of phase with the deadline test there the
            # moment the dispatcher drops a frame.
            interval = config.get_frame_interval(name)
            if interval <= 1:
                return True
            last_run = self._last_frame_supplied.get((camera_id, name))
            if last_run is None or frame_num - last_run >= interval or frame_num < last_run:
                self._last_frame_supplied[(camera_id, name)] = frame_num
                return True

        # Keep a recent frame available for event snapshots even on cameras
        # whose plugins are all metadata-only. Without this, intrusion,
        # counting, parking and restriction alerts reach the dashboard with
        # no image at all. One copy per SNAPSHOT_FRAME_INTERVAL frames is
        # ~1Hz per camera — 25 cameras is under 0.05 cores.
        snap_interval = config.get_snapshot_frame_interval()
        if snap_interval > 0:
            last_snap = self._last_frame_supplied.get((camera_id, "__snapshot__"))
            if (last_snap is None or frame_num - last_snap >= snap_interval
                    or frame_num < last_snap):
                self._last_frame_supplied[(camera_id, "__snapshot__")] = frame_num
                return True
        return False

    def run_plugins(self, frame_data: FrameData) -> Dict[str, Any]:
        all_events = {}
        if not self.active_plugins:
            return all_events

        from config.config import config
        # Check if camera has specific enabled plugins list
        camera_id = frame_data.camera_id
        allowed = config.get_allowed_plugins(camera_id)

        # A plugin whose startup init failed is missing from active_plugins;
        # without this, toggling it on live can never activate it.
        self._sync_plugins(allowed)

        frame_num = getattr(frame_data, "frame_num", 0)

        # Cache the pixels so any plugin — including metadata-only ones that
        # never ask for a frame — can attach a snapshot to an alert.
        if frame_data.frame is not None:
            self.tracker_context.set_latest_frame(camera_id, frame_data.frame)

        # Snapshot: _sync_plugins may insert concurrently from another camera
        # worker; iterating the live dict would raise dict-changed-size.
        for p_name, p_instance in list(self.active_plugins.items()):
            # If camera has an explicit list of plugins configured, skip any plugin not in that list
            if allowed is not None and p_name not in allowed:
                continue
            # Deadline-based, NOT `frame_num % interval`. The dispatcher's
            # mailbox keeps only the latest frame per camera, so an absolute
            # modulo schedule loses a plugin's turn entirely whenever its one
            # eligible frame is the one that got dropped — under exactly the
            # load the dispatcher exists for, sampled plugins were starved
            # toward zero executions while the probe kept paying for the copy.
            # Tracking the last frame each plugin actually ran on defers the
            # turn to the next surviving frame instead of skipping it.
            interval = self._sampling_interval(p_name)
            if interval > 1:
                last_run = self._last_run_frame.get((camera_id, p_name))
                if last_run is not None and frame_num - last_run < interval:
                    continue
                # A source restart resets frame_num; don't wait for it to
                # climb back past a stale marker.
                if last_run is not None and frame_num < last_run:
                    self._last_run_frame.pop((camera_id, p_name), None)
            self._last_run_frame[(camera_id, p_name)] = frame_num

            started = time.perf_counter()
            try:
                if getattr(p_instance, "thread_safe", True):
                    events = p_instance.process_frame(frame_data, self.tracker_context)
                else:
                    run_lock = self._plugin_run_locks.setdefault(p_name, threading.Lock())
                    with run_lock:
                        events = p_instance.process_frame(frame_data, self.tracker_context)
                if events:
                    all_events[p_name] = [e.dict() if hasattr(e, "dict") else e for e in events]
            except Exception as e:
                logger.error(f"Plugin {p_name} error: {e}")
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                prev = self.plugin_ms_ema.get(p_name, elapsed_ms)
                self.plugin_ms_ema[p_name] = prev * 0.9 + elapsed_ms * 0.1

        return all_events
