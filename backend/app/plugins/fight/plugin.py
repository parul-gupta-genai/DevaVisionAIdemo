"""
SOW 2.7 — Gesture Analytics: fight / quarrel detection.

AI-based visual analytics for fight and quarrel situations in designated
camera zones.

THIS IS AN AUTOMATED VISUAL ANALYTICS AID. It does not replace human security
intervention. Every indication it raises requires human verification, carries
that statement in its metadata, and can be recorded as confirmed or dismissed
through /api/fight/events/{id}/verify — because an unreviewed indication is
not a finding of fact, and this module names people by track and stores
footage of them.

The plugin is thin and delegates:

  dynamics.py   what the tracked bodies are doing — agitation rather than
                speed, body heights rather than pixels, both parties rather
                than either
  service.py    whether that adds up to an incident, under the client's
                per-zone rules
  adapter.py    the bridge: per-camera state, snapshots, the incident log
  repository.py the client's zones and the log
  router.py     the API the client configures, demonstrates and reviews it with

Every core signal comes from the tracked person boxes the detector already
produces (agitation, proximity, duration) — that part still runs on every
frame of a 25-camera wall with only arithmetic. A trained motion/optical-flow
classifier (ml_classifier.py) adds a second opinion, but only computes on the
rare frames where the box-based heuristic already flagged a candidate — see
adapter.py for why that keeps the per-frame cost the same as before for the
other 99%+ of frames where nothing is happening.
"""

from typing import List

from loguru import logger

from app.engine.base import BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext
from app.plugins.fight import adapter
from app.plugins.fight.dynamics import ADVISORY_NOTICE  # noqa: F401
from app.plugins.fight.service import FIGHT_CLEARED, FIGHT_DETECTED  # noqa: F401


class FightDetectionPlugin(BaseDetectionPlugin):
    """Fight/quarrel visual analytics. An aid, not a verdict."""

    # Was False: the bbox-only heuristic alone reads no pixels. Now True
    # because adapter.py also buffers recent frames to run a trained
    # motion/optical-flow classifier (ml_classifier.py) as a SECOND signal
    # that confirms/vetoes the heuristic's own candidates — see adapter.py's
    # module docstring for how the expensive part (optical flow) is kept
    # rare rather than run on every frame, to preserve the "every frame of a
    # 25-camera wall" scaling this plugin was built for.
    needs_frame = True

    # Holds no per-camera state on the instance; the motion history and the
    # incident state both live in tracker_context's per-camera bucket.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        logger.info("Initialized FightDetectionPlugin (fight/quarrel analytics aid)")

    @property
    def plugin_name(self) -> str:
        return "FightDetectionPlugin"

    def get_required_classes(self) -> List[int]:
        return [0]          # person

    def process_frame(self, frame_data: FrameData,
                      tracker_context: TrackerContext) -> List[DetectionEvent]:
        return adapter.run(self.plugin_name, frame_data, tracker_context)
