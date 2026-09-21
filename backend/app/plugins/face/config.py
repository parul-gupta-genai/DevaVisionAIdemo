"""
Face-recognition tuning.

Every knob the SOW's "face-recognition tuning" covers lives here, is settable
from the environment, and is re-read on each access so it can be adjusted
during UAT without a restart. Values are clamped rather than trusted: a
threshold of 0 would match every face to the first person in the register, and
that must not be reachable by typo.
"""

import os
from dataclasses import dataclass


def _f(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.getenv(name, default))))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(os.getenv(name, default)))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class FaceTuning:
    # --- matching -------------------------------------------------------
    # Cosine similarity a live face must reach to be called a known person.
    # ArcFace embeddings put genuine matches well above 0.5 and impostors
    # near 0.2; 0.45 is deliberately conservative for attendance, where a
    # false accept is somebody else's timesheet.
    match_threshold: float
    # A watchlist hit is an accusation, so it must clear a higher bar than
    # "who clocked in".
    watchlist_threshold: float
    # Two enrolments closer than this are treated as the same human, which is
    # how a duplicate enrolment is caught.
    duplicate_threshold: float

    # --- what counts as a usable face -----------------------------------
    min_face_px: int          # shortest edge of the face box
    min_det_score: float      # detector confidence
    min_sharpness: float      # variance of Laplacian; rejects motion blur

    # --- event shaping ---------------------------------------------------
    # A person standing in view must not generate an event per frame.
    debounce_sec: float
    # Gap after which the next sighting is a fresh check-in rather than a
    # continuation of the current presence.
    session_gap_sec: float
    # A watchlist hit repeats only after this long on the same camera.
    watchlist_cooldown_sec: float
    # Minimum time between a check-in and an accepted check-out, so somebody
    # turning around at the door does not clock out.
    min_presence_sec: float

    # --- cost ------------------------------------------------------------
    # Frames between recognition passes on a camera. Face recognition is by
    # far the most expensive analytic (~180ms/call on CPU), so it is sampled
    # hard and only enabled on the cameras that need it.
    frame_interval: int
    # Most faces per pass; a crowd scene must not become an unbounded stall.
    max_faces_per_pass: int

    @classmethod
    def current(cls) -> "FaceTuning":
        return cls(
            match_threshold=_f("FACE_MATCH_THRESHOLD", 0.45, 0.20, 0.95),
            watchlist_threshold=_f("FACE_WATCHLIST_THRESHOLD", 0.55, 0.20, 0.99),
            duplicate_threshold=_f("FACE_DUPLICATE_THRESHOLD", 0.70, 0.30, 0.99),
            min_face_px=_i("FACE_MIN_PX", 60, 20, 400),
            min_det_score=_f("FACE_MIN_DET_SCORE", 0.60, 0.10, 0.99),
            min_sharpness=_f("FACE_MIN_SHARPNESS", 25.0, 0.0, 10000.0),
            debounce_sec=_f("FACE_DEBOUNCE_SEC", 30.0, 0.0, 3600.0),
            session_gap_sec=_f("FACE_SESSION_GAP_SEC", 1800.0, 60.0, 86400.0),
            watchlist_cooldown_sec=_f("FACE_WATCHLIST_COOLDOWN_SEC", 60.0, 0.0, 3600.0),
            min_presence_sec=_f("FACE_MIN_PRESENCE_SEC", 60.0, 0.0, 86400.0),
            frame_interval=_i("FACE_FRAME_INTERVAL", 15, 1, 300),
            max_faces_per_pass=_i("FACE_MAX_FACES", 5, 1, 50),
        )

    def as_dict(self) -> dict:
        return {
            "match_threshold": self.match_threshold,
            "watchlist_threshold": self.watchlist_threshold,
            "duplicate_threshold": self.duplicate_threshold,
            "min_face_px": self.min_face_px,
            "min_det_score": self.min_det_score,
            "min_sharpness": self.min_sharpness,
            "debounce_sec": self.debounce_sec,
            "session_gap_sec": self.session_gap_sec,
            "watchlist_cooldown_sec": self.watchlist_cooldown_sec,
            "min_presence_sec": self.min_presence_sec,
            "frame_interval": self.frame_interval,
            "max_faces_per_pass": self.max_faces_per_pass,
        }


# Which cameras are the attendance gates, and which way they count. A camera
# named or configured as an exit records check-outs; anything else records a
# check-in on first sight and a check-out on last sight of the day.
def checkin_camera_ids() -> set:
    return {c.strip() for c in os.getenv("FACE_CHECKIN_CAMERAS", "").split(",") if c.strip()}


def checkout_camera_ids() -> set:
    return {c.strip() for c in os.getenv("FACE_CHECKOUT_CAMERAS", "").split(",") if c.strip()}
