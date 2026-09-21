import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import ClassVar, List, Optional

# DeepStream mux space — all analytics geometry lives in these coordinates.
MUX_W, MUX_H = 1280, 720
MIN_COUNTING_LINE_LEN = 8

# The value that ships in the repo. It is public, so any JWT signed with it is
# forgeable by anyone — it must never reach create_access_token().
INSECURE_SECRET_KEY = "supersecretkey_change_in_production"


def _secret_key_file() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, ".secret_key")


def _read_secret_key_file() -> Optional[str]:
    try:
        with open(_secret_key_file(), "r") as fh:
            saved = fh.read().strip()
        return saved or None
    except OSError:
        return None


def resolve_secret_key(configured: str) -> str:
    """
    Guarantees the JWT signing key is never the public placeholder.

    Order: an explicitly configured SECRET_KEY (env or .env) wins; otherwise a
    previously generated key is reused; otherwise a strong one is generated and
    persisted with 0600 permissions.

    Deliberately does NOT abort startup on the placeholder. Both the API and
    the DeepStream process import this module, and hard-failing would take a
    live deployment down on restart to fix a missing .env. Generating instead
    is equally fail-closed for the actual vulnerability — the published key is
    never used — and the cost is only that tokens do not survive a key change.
    """
    from loguru import logger

    if configured and configured != INSECURE_SECRET_KEY:
        return configured

    saved = _read_secret_key_file()
    if saved:
        return saved

    generated = secrets.token_urlsafe(64)
    path = _secret_key_file()
    try:
        # O_EXCL: the API and DeepStream processes start together and would
        # otherwise race, each persisting a different key and invalidating the
        # other's tokens. The loser reads the winner's file.
        # Write to a temp file and rename into place. O_EXCL alone left a
        # window where the loser of the race opened a created-but-still-empty
        # file, read nothing, and carried on with a DIFFERENT in-memory key —
        # so the API and DeepStream processes would sign incompatible tokens.
        # rename(2) is atomic, so a reader sees either no file or a complete one.
        tmp_path = f"{path}.{os.getpid()}.tmp"
        fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, generated.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp_path, path)      # fails if another process won
        finally:
            os.unlink(tmp_path)
        logger.warning(
            "SECRET_KEY was unset (or still the public placeholder). Generated "
            f"a new signing key and stored it in {path}. Existing access tokens "
            "are now invalid; clients refresh automatically. Set SECRET_KEY in "
            ".env to control this yourself."
        )
        return generated
    except FileExistsError:
        saved = _read_secret_key_file()
        if saved:
            return saved
    except OSError as exc:
        logger.error(f"Could not persist a generated SECRET_KEY to {path}: {exc}")

    logger.warning(
        "Using an in-memory SECRET_KEY: it is secure, but every restart "
        "invalidates all access tokens. Set SECRET_KEY in .env to fix this."
    )
    return generated


def sanitize_counting_line(entry, idx: int) -> Optional[dict]:
    """
    Normalizes one COUNTING_LINES entry to {id, name, start, end} in mux
    space, or returns None if the entry is unusable. Single source of truth
    shared by the API validator (strict: None -> HTTP 422) and the counting
    plugin (lenient: None -> skip), so the two can never drift apart.
    Accepts UI dicts and legacy bare ((x1,y1),(x2,y2)) pairs.
    """
    try:
        if isinstance(entry, dict):
            start, end = entry.get("start"), entry.get("end")
            line_id = str(entry.get("id") or f"line-{idx + 1}")
            name = str(entry.get("name") or f"Line {idx + 1}")
        else:
            start, end = entry[0], entry[1]
            line_id, name = f"line-{idx + 1}", f"Line {idx + 1}"
        ax, ay = float(start[0]), float(start[1])
        bx, by = float(end[0]), float(end[1])
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    ax = min(max(ax, 0), MUX_W); bx = min(max(bx, 0), MUX_W)
    ay = min(max(ay, 0), MUX_H); by = min(max(by, 0), MUX_H)
    if max(abs(ax - bx), abs(ay - by)) < MIN_COUNTING_LINE_LEN:
        return None
    return {
        "id": line_id[:64],
        "name": name[:40],
        "start": [int(round(ax)), int(round(ay))],
        "end": [int(round(bx)), int(round(by))],
    }

class AppConfig(BaseSettings):
    """
    Application configuration.
    Loads from environment variables or a .env file.
    No hardcoded values should exist in business logic.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # Auth Settings
    # Never read this field directly before resolve_secret_key() has run — see
    # the module bottom. The default below is a public placeholder.
    SECRET_KEY: str = Field(
        default=INSECURE_SECRET_KEY,
        description="JWT Secret Key"
    )
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    
    # AI Agent / LLM Settings
    LLM_PROVIDER: str = Field(default="groq", description="LLM provider: groq, ollama, openai")
    GROQ_API_KEY: str = Field(default="", description="Groq API Key")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile", description="Groq Model")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama API URL")
    OLLAMA_MODEL: str = Field(default="llama3.2:3b", description="Ollama Model")
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API Key")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI Model")

    # Voice Assistant Settings
    VOICE_STT_ENGINE: str = Field(default="browser", description="Voice STT engine")
    VOICE_TTS_ENGINE: str = Field(default="browser", description="Voice TTS engine")
    VOICE_LANGUAGE: str = Field(default="hi-IN", description="Voice language")
    VOICE_GENDER: str = Field(default="female", description="Voice gender: female, male, all")
    VOICE_SPEED: float = Field(default=1.0, description="Voice speech speed")
    VOICE_PITCH: float = Field(default=1.0, description="Voice speech pitch")
    VOICE_VOLUME: float = Field(default=1.0, description="Voice speech volume")
    VOICE_NAME: str = Field(default="", description="Selected browser / system voice name")
    VOICE_RIVA_SERVER: str = Field(default="localhost:50051", description="Riva server URL")
    VOICE_KOKORO_VOICE: str = Field(default="hf_alpha", description="Kokoro speaker ID")
    VOICE_RIVA_VOICE: str = Field(default="Hindi.Female-1", description="Riva voice ID")
    
    
    # Database Settings
    DATABASE_URL: str = Field(
        default="postgresql://admin:admin@localhost:5433/cctv",
        description="PostgreSQL Connection String"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis Connection String"
    )
    
    # Camera Settings (comma separated if multiple)
    CAMERA_URLS: str = Field(
        default="CHECK IN.mp4,CHECK OUT.mp4",
        description="Comma-separated list of RTSP URLs, video file paths, or camera indices."
    )
    
    @property
    def camera_list(self) -> List[str]:
        return [url.strip() for url in self.CAMERA_URLS.split(",") if url.strip()]
        
    CAMERA_RECONNECT_MAX_RETRIES: int = Field(default=-1)
    CAMERA_RECONNECT_DELAY_SECONDS: float = Field(default=5.0)
    FRAME_BUFFER_SIZE: int = Field(default=3)
    
    # AI Pipeline Settings
    VIDEO_BACKEND: str = Field(
        default="gstreamer",
        description="Video ingestion backend (opencv, gstreamer)."
    )
    FRAME_SKIP: int = Field(default=3)
    MODEL_PATH: str = Field(default="detection/yolo11n.pt")
    CONFIDENCE_THRESHOLD: float = Field(default=0.4)
    INFERENCE_BACKEND: str = Field(
        default="onnx",
        description="Inference strategy: openvino, coreml, onnx, tensorrt, or pytorch."
    )
    TRACKER_BACKEND: str = Field(
        default="bytetrack",
        description="Tracker strategy: bytetrack or botsort."
    )
    FACE_BACKEND: str = Field(
        default="insightface",
        description="Face embedding strategy: insightface."
    )
    
    UNTRACKED_CAMERAS: List[str] = Field(
        default=[],
        description="List of camera substrings that should bypass ByteTrack to avoid confidence thresholds filtering out low-conf objects."
    )
    
    CAMERA_CONFIDENCE_THRESHOLDS: dict = Field(
        default={},
        description="Camera-specific confidence thresholds. Overrides CONFIDENCE_THRESHOLD if matched."
    )
    
    def get_confidence_for_camera(self, camera_id: str) -> float:
        for cam, conf in self.CAMERA_CONFIDENCE_THRESHOLDS.items():
            if cam in camera_id:
                return conf
        return self.CONFIDENCE_THRESHOLD
        
    def should_bypass_tracker(self, camera_id: str) -> bool:
        for cam in self.UNTRACKED_CAMERAS:
            if cam in camera_id:
                return True
        return False
    
    # Spatial Analytics Settings
    LOITERING_THRESHOLD_SECONDS: float = Field(default=10.0)
    
    # Gesture Detection Settings
    GESTURE_ENABLED: bool = Field(default=True)
    GESTURE_FPS: int = Field(default=8)
    GESTURE_CONFIDENCE: float = Field(default=0.2)
    GESTURE_MAX_HANDS: int = Field(default=4)
    GESTURE_ASSOCIATE_WITH_PERSON: bool = Field(default=True)
    
    HAND_RAISE_ENABLED_CAMERAS: List[str] = Field(
        default=["default"],
        description="List of camera URLs that are allowed to trigger HAND_RAISE_DETECTED alerts."
    )
    
    def is_hand_raise_enabled(self, camera_id: str) -> bool:
        return camera_id in self.HAND_RAISE_ENABLED_CAMERAS or "default" in self.HAND_RAISE_ENABLED_CAMERAS
    
    # Dictionary of camera_id to list of polygon points [(x,y), (x,y), ...]
    # NOTE: all analytics geometry lives in the DeepStream mux space (1280x720).
    RESTRICTED_ZONES: dict = Field(
        default={
            # Default test zone (a large square in the center of a 1280x720 frame)
            "default": [(267, 200), (1000, 200), (1000, 533), (267, 533)]
        }
    )
    
    def get_zone_for_camera(self, camera_id: str) -> list:
        """
        Superseded by app.plugins.zones.repository.zone_registry, which is the
        source of truth for restricted zones (named, scheduled, per-rule, and
        stored in restricted_zones). Kept because the RESTRICTED_ZONES dict is
        still persisted and hot-published, and an explicit per-camera entry is
        still honoured as a fallback for a site that set one.

        Note the "default" fallback below: it gave every camera on the site a
        live restricted zone across the middle of the frame whether or not
        anybody had asked for one. The zone registry deliberately does NOT
        honour it — see _legacy_zone there.
        """
        for cam, zone in self.RESTRICTED_ZONES.items():
            if cam != "default" and cam in camera_id:
                return zone
        return self.RESTRICTED_ZONES.get("default")
        

    # Dictionary of camera_id to line segment ((x1, y1), (x2, y2))
    CHECKIN_LINES: dict = Field(
        default={
            # Default vertical line down the middle of a 1280x720 frame
            "default": ((640, 0), (640, 720))
        }
    )
    
    def get_checkin_line_for_camera(self, camera_id: str) -> tuple:
        return self.CHECKIN_LINES.get(camera_id, self.CHECKIN_LINES.get("default"))
        
    # Dictionary of camera_id to list of people-counting lines drawn in the UI.
    # Each line: {"id": str, "name": str, "start": [x, y], "end": [x, y]} in the
    # 1280x720 mux space. A crossing counts as IN when the track ends up on the
    # right-hand side while walking from start to end (the overlay arrow shows
    # the IN direction); drawing the line the other way flips IN/OUT.
    COUNTING_LINES: dict = Field(
        default={
            "default": []
        }
    )

    def get_counting_lines_for_camera(self, camera_id: str) -> list:
        # Exact-key lookup (like CHECKIN_LINES): the editor saves and reads
        # by exact camera id, so substring matching could silently count on
        # another camera's geometry. An explicit [] means counting is off.
        lines = self.COUNTING_LINES.get(camera_id)
        if lines is not None:
            return lines
        return self.COUNTING_LINES.get("default", [])

    # Dictionary of camera_id to list of parking spots (each spot is a list of polygon points)
    # Defaults sit in the lower-center of the 1280x720 frame — the old 1080p
    # coordinates were entirely outside the frame, so no spot could ever
    # register as occupied.
    PARKING_SPOTS: dict = Field(
        default={
            # 3 dummy spots
            "default": [
                [(400, 500), (600, 500), (600, 700), (400, 700)],   # Spot 1
                [(620, 500), (820, 500), (820, 700), (620, 700)],   # Spot 2
                [(840, 500), (1040, 500), (1040, 700), (840, 700)], # Spot 3
            ]
        }
    )
    
    def get_parking_spots_for_camera(self, camera_id: str) -> list:
        for cam, spots in self.PARKING_SPOTS.items():
            if cam != "default" and cam in camera_id:
                return spots
        return self.PARKING_SPOTS.get("default")
        
    @staticmethod
    def _get_state_file_path() -> str:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "camera_plugins_state.json")

    # Per-camera runtime config persisted across restarts (both the backend and
    # the DeepStream process load this module, so both see the same state).
    PERSISTED_DICT_KEYS: ClassVar[tuple] = ("CAMERA_PLUGINS", "RESTRICTED_ZONES", "PARKING_SPOTS", "CHECKIN_LINES", "COUNTING_LINES", "CAMERA_FPS")

    @staticmethod
    def _load_state_file() -> dict:
        import json
        import os
        try:
            state_file = AppConfig._get_state_file_path()
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    @staticmethod
    def load_plugins_state() -> dict:
        state = AppConfig._load_state_file()
        # New format nests everything under labeled keys; the legacy file was
        # the bare CAMERA_PLUGINS dict itself.
        if "CAMERA_PLUGINS" in state:
            return state.get("CAMERA_PLUGINS") or {}
        return state

    def apply_persisted_state(self):
        """Merges persisted per-camera geometry (zones/spots/lines/fps) over the defaults."""
        state = self._load_state_file()
        for key in (k for k in self.PERSISTED_DICT_KEYS if k != "CAMERA_PLUGINS"):
            saved = state.get(key)
            if isinstance(saved, dict) and saved:
                merged = getattr(self, key).copy()
                merged.update(saved)
                setattr(self, key, merged)

    def save_plugins_state(self):
        import json
        try:
            state_file = self._get_state_file_path()
            payload = {key: getattr(self, key) for key in self.PERSISTED_DICT_KEYS}
            with open(state_file, "w") as f:
                json.dump(payload, f)
        except Exception:
            pass

    # Load from state file instead of defaulting to empty to prevent amnesia on hot-reload
    CAMERA_PLUGINS: dict = Field(
        default_factory=load_plugins_state
    )
    CAMERA_FPS: dict = Field(
        default_factory=dict,
        description="Per-camera target processing FPS (e.g. {'cam_01': 20})"
    )
    
    # Line Crossing Config
    LINE_CROSSING_Y: int = Field(default=600, description="Y-coordinate for the line crossing")
    LINE_CROSSING_X_START: int = Field(default=750, description="Starting X coordinate of the line (e.g. left edge of the door)")
    LINE_CROSSING_X_END: int = Field(default=1150, description="Ending X coordinate of the line (e.g. right edge of the door)")
    LINE_CROSSING_DIRECTION: str = Field(default="down", description="Direction to count: up, down, or both")
    
    # How many frames apart a plugin is allowed to run: 1 = every frame.
    # The engine reads this to skip expensive plugins, and the DeepStream
    # probe reads it (via DetectionEngine.frame_needed_for) to decide whether
    # copying the frame surface is worth it at all. Plugins whose logic needs
    # consecutive positions (line crossing, centroid tracking) must stay at 1.
    #
    # NOTE: the schedule is `frame_num % interval == 0` so the probe and the
    # worker agree without shared state. Frames dropped by the analytics
    # dispatcher under load therefore skip a plugin's turn entirely — heavy
    # sampling plus heavy drop compounds, so watch the [analytics] drop stat
    # before raising these.
    # Budgeted for a full wall (~25 cameras) on one Orin NX, not for a single
    # camera. Analytics do not need video framerate: 2-10 Hz is well above
    # what any of these detections actually resolve, and the difference is the
    # difference between a system that keeps up and one that falls over.
    # Plugins that track movement across CONSECUTIVE frames (people counting,
    # carton centroids, the visitor tripwire) must stay at 1 — the API
    # rejects any attempt to sample them.
    # Tuned for a 25-camera deployment at roughly:
    #   people counting  25 cams | fire        25 cams | PPE     12 cams
    #   visitor/employee  4 cams | attendance   4 cams | ANPR     2 cams
    #   carton            2 cams | restriction  2 cams
    # Measured per-call costs on an Orin NX drive the intervals below; the
    # resulting analytics budget is ~1 core of 8. Plugins that track movement
    # across CONSECUTIVE frames (counting, carton, the visitor tripwire) must
    # stay at 1 — the API rejects any attempt to sample them.
    PLUGIN_SAMPLING: dict = Field(
        default={
            # Must stay under core.state.EVENT_TTL_SECONDS (1.0s) or the live
            # FIRE_STATS overlay it feeds is pruned between ticks and the
            # boxes plus the "THREAT: FIRE DETECTED" banner blink out while a
            # fire is burning. At 25fps an interval of 30 fires every 1.2s —
            # just too slow. 15 gives ~0.6s, with margin for a dropped frame.
            "FireDetectionPlugin": 15,
            # MUST stay at 1. Agitation, direction reversal and separation are
            # all differences between consecutive observations of one person;
            # sampled, a struggle reads as unrelated jumps and the tracker-id
            # jump filter throws them away. It is metadata-only — no pixel
            # copy, no OpenCV — so every-frame is affordable: roughly 0.05ms
            # per camera per frame against the ~4.9ms whole analytics pass.
            "FightDetectionPlugin": 1,
            # 12 cams x 2 Hz x 6ms = 0.14 cores. The per-person HSV masks are
            # the second most expensive thing after ANPR.
            "PPEDetectionPlugin": 15,
            # MUST stay at 1: attendance re-derives identity every run from an
            # HSV histogram match and evaluates a turnstile line crossing from
            # consecutive centroids. Sampled at 0.5s intervals a walking
            # employee's histogram drifts far enough to mint a NEW id, whose
            # previous_centroids is empty, so the crossing is never evaluated
            # and no CHECK IN is written — or it mis-matches an existing id and
            # writes a false one. It is in _UNSAMPLEABLE_PLUGINS for this reason.
            "AttendanceDetectionPlugin": 1,
            # 2 cams x 6 Hz x 17.8ms = 0.21 cores — by far the priciest call,
            # but only on the 1-2 entry/exit cameras. 6 Hz still gives the
            # temporal fusion ~15 reads inside a 2.5s vehicle track.
            "ANPRPlugin": 5,
            # Face recognition is the most expensive analytic in the system:
            # InsightFace runs on CPU inside the DeepStream process (cuDNN
            # will not initialise beside the TensorRT context) at ~180ms a
            # pass. At interval 15 that is ~2 Hz, and the plugin additionally
            # skips any frame with no person in it and any frame where another
            # camera already holds the engine — so 3-4 attendance cameras cost
            # well under half a core, and it must not be enabled site-wide.
            "FaceRecognitionPlugin": 15,
            "ParkingAnalyticsPlugin": 15,      # ~2 Hz; occupancy changes slowly
            "IntrusionDetectionPlugin": 5,     # ~6 Hz; zone containment
            "RestrictionZonePlugin": 5,        # ~6 Hz; zone containment
        },
        description="Plugin name -> frames between runs (1 = every frame).",
    )

    # How often a plugin needs the FRAME PIXELS, which is not always how often
    # it runs. The visitor tripwire must evaluate every frame to catch a
    # crossing, but only needs pixels occasionally to grab a face — and the
    # RGBA->BGR copy is the single most expensive thing the probe does
    # (~1.5ms x 25 cameras x 30fps would be over a core on its own).
    # Unset keys fall back to PLUGIN_SAMPLING.
    PLUGIN_FRAME_SAMPLING: dict = Field(
        default={
            # Runs every frame for the tripwire, but only needs pixels
            # occasionally to grab a face — 4 cams x 6 Hz x 1.5ms of copy.
            "VisitorPlugin": 5,
        },
        description="Plugin name -> frames between frame-pixel copies.",
    )

    @staticmethod
    def _positive_interval(source: dict, plugin_name: str, default: int = 1) -> int:
        try:
            return max(1, int(source.get(plugin_name, default)))
        except (TypeError, ValueError, AttributeError):
            return max(1, default)

    def get_sampling_interval(self, plugin_name: str) -> int:
        """Frames between runs for a plugin; always >= 1, never raises."""
        return self._positive_interval(self.PLUGIN_SAMPLING or {}, plugin_name, 1)

    # Frames between the low-rate pixel supply that keeps an event snapshot
    # available on every camera, including metadata-only ones. 0 disables.
    SNAPSHOT_FRAME_INTERVAL: int = Field(default=30)

    def get_snapshot_frame_interval(self) -> int:
        try:
            return max(0, int(self.SNAPSHOT_FRAME_INTERVAL))
        except (TypeError, ValueError):
            return 30

    def get_frame_interval(self, plugin_name: str) -> int:
        """
        Frames between frame-pixel copies for a plugin. Defaults to its run
        interval, so a plugin that only runs every N frames never causes a
        copy on the frames in between.
        """
        run_interval = self.get_sampling_interval(plugin_name)
        return self._positive_interval(
            self.PLUGIN_FRAME_SAMPLING or {}, plugin_name, run_interval
        )

    def get_allowed_plugins(self, camera_id: str) -> list:
        return self.CAMERA_PLUGINS.get(camera_id, [])

config = AppConfig()
config.apply_persisted_state()
# Must happen before anything can sign or verify a JWT.
config.SECRET_KEY = resolve_secret_key(config.SECRET_KEY)

import redis
# Global redis client for inter-process communication
redis_client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
