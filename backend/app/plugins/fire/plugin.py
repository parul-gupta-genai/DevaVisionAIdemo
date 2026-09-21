"""
SOW 2.8 — Fire & Smoke Situation Analysis.

AI-based visual detection of fire and smoke on designated CCTV feeds. This is
an early-warning and monitoring aid: it watches pixels, and it is explicitly
NOT a statutory fire detection, alarm or suppression system. See
detector.STATUTORY_NOTICE, which is carried on every incident this plugin
emits and on every API response that reports one.

The plugin itself is deliberately thin. It owns the engine-facing contract —
the class name the camera configuration keys on, the frame requirement, the
event vocabulary — and delegates:

  detector.py   what a frame looks like (fire colour + flicker, smoke as an
                arriving unsaturated veil that kills local detail)
  service.py    whether that adds up to an incident (confirmation, cooldown,
                clearing) under the client's per-zone rules
  adapter.py    the bridge: per-camera state, snapshots, the event log
  repository.py the client's zones and the incident log
  router.py     the API the client configures and reviews it through

Event vocabulary, and why each one is shaped the way it is:

  FIRE_STATS     per-frame overlay. In both persistence ignore lists, so it
                 lights the live view without writing a row per frame. Carries
                 the unconfirmed candidates too, so an operator can watch
                 evidence build rather than only see the verdict.
  FIRE_DETECTED  a confirmed fire. Unchanged name: the alert engine escalates
                 it, the events feed renders it and /api/fire/events keys on
                 it, and all three keep working.
  SMOKE_DETECTED a confirmed smoke plume. Severity-driven rather than always
                 critical, because smoke is also steam, dust and exhaust.
  FIRE_CLEARED   the all-clear, with how long the incident ran. Logged, never
                 alarmed: nobody should be paged because a fire went out.
"""

from typing import List

from loguru import logger

from app.engine.base import BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext
from app.plugins.fire import adapter
from app.plugins.fire.detector import STATUTORY_NOTICE  # noqa: F401
from app.plugins.fire.service import (
    FIRE_CLEARED, FIRE_DETECTED, SMOKE_DETECTED,  # noqa: F401
)
from app.plugins.fire.yolo_fire_detector import YoloFireDetector


class FireDetectionPlugin(BaseDetectionPlugin):
    """Visual fire and smoke early warning. Not a fire alarm system."""

    # Reads raw pixels. Must be a class attribute: the engine reads it off the
    # class to decide the per-camera pixel-copy cadence, without instantiating.
    needs_frame = True

    # Holds no mutable per-camera state on the instance — the analyzer, the
    # incident state and the zone mask all live in tracker_context's
    # per-camera bucket, so the six dispatcher workers cannot interleave one
    # camera's background model into another's.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        self._yolo: YoloFireDetector = YoloFireDetector()
        logger.info("Initialized FireDetectionPlugin (fire + smoke early warning)")

    def initialize(self) -> None:
        """Pre-load the YOLO fire model so the first camera frame is not slow."""
        self._yolo.warm()

    @property
    def plugin_name(self) -> str:
        return "FireDetectionPlugin"

    def get_required_classes(self) -> List[int]:
        # Fire and smoke are found in the pixels, not in the detector's object
        # classes, so nothing needs to be retained on this plugin's account.
        return []

    def process_frame(self, frame_data: FrameData,
                      tracker_context: TrackerContext) -> List[DetectionEvent]:
        return adapter.run(self.plugin_name, frame_data, tracker_context,
                           yolo_detector=self._yolo)
