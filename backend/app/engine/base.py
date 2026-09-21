from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from dataclasses import dataclass, field
import numpy as np

class DetectionEvent(BaseModel):
    plugin_name: str
    event_type: str
    camera_id: str
    timestamp: float
    confidence: float
    metadata: Dict[str, Any] = {}
    snapshot_path: Optional[str] = None

@dataclass
class NormalizedDetection:
    camera_id: str = ""
    edge_id: str = "deepstream"
    frame_id: int = 0
    timestamp: float = 0.0
    class_id: int = 0
    class_name: str = ""
    confidence: float = 1.0
    bbox: List[float] = field(default_factory=list)  # [x_min, y_min, x_max, y_max]
    track_id: Optional[int] = None

@dataclass
class FrameData:
    frame: np.ndarray
    detections: List[NormalizedDetection]
    camera_id: str
    timestamp: float
    # Aligned FACE embeddings (detect -> 5-point align -> ArcFace), directly
    # comparable with the enrolled Visitor.face_embedding vectors. Populated
    # by whichever plugin does face extraction, NOT by the DeepStream SGIE.
    faces: List[Any] = field(default_factory=list)
    # Whole-person appearance vectors from the DeepStream face SGIE, which
    # runs ArcFace over an unaligned person bbox. These are a coarse re-ID
    # signal only — they are NOT face embeddings and must never be matched
    # against enrolled face vectors.
    appearance_embeddings: List[Any] = field(default_factory=list)
    camera_url: str = ""
    # (height, width) of the mux frame — always available, even when `frame`
    # pixels were not copied because no enabled plugin needs them.
    frame_shape: tuple = (720, 1280)
    # Per-source frame counter (used for plugin sampling schedules).
    frame_num: int = 0

class TrackerContext:
    # A simple context object passed to plugins allowing them to store
    # and retrieve plugin-specific and camera-specific state globally.
    def __init__(self):
        self._state: Dict[str, Dict[str, Any]] = {}
        # camera_id -> most recent frame pixels seen for that camera. Lets a
        # metadata-only plugin attach a snapshot to an alert without forcing
        # a full-rate frame copy it does not otherwise need.
        self._latest_frame: Dict[str, Any] = {}

    def set_latest_frame(self, camera_id: str, frame) -> None:
        self._latest_frame[camera_id] = frame

    def get_latest_frame(self, camera_id: str):
        return self._latest_frame.get(camera_id)

    def get_state(self, plugin_name: str, camera_id: str) -> Dict[str, Any]:
        # Nested setdefault: atomic per level under the GIL, so two camera
        # workers hitting a plugin's very first frame can't clobber each
        # other's freshly created state dict.
        return self._state.setdefault(plugin_name, {}).setdefault(camera_id, {})

class BaseDetectionPlugin(ABC):
    """
    Base class that all Detection Plugins must inherit from.
    """

    # True if process_frame reads frame_data.frame pixels. The probe only
    # copies the (expensive) full frame when an enabled plugin on that camera
    # needs it — metadata-only plugins never trigger a copy.
    needs_frame: bool = False

    # False if the plugin keeps instance-level mutable state that is not
    # keyed by camera (or wraps a non-thread-safe model). Such plugins run
    # under a per-plugin lock when cameras are processed in parallel.
    thread_safe: bool = True

    def __init__(self, app_config=None):
        self.config = app_config
        pass
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Return the unique name of this plugin."""
        pass

    @abstractmethod
    def get_required_classes(self) -> List[int]:
        """Return the YOLO class indices this plugin requires."""
        pass
        
    @abstractmethod
    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        """
        Process a single frame's detections and return any generated events.
        """
        pass

    def initialize(self) -> None:
        """
        Lifecycle hook called once when the plugin is loaded into the engine.
        Override to load heavy models or establish connections.
        """
        pass

    def health(self) -> Dict[str, Any]:
        """
        Lifecycle hook to report plugin-specific health metrics.
        """
        return {"status": "ok"}
