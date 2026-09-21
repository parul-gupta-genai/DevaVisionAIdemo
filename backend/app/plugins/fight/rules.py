"""
SOW 2.7 — threshold tuning and when a zone is armed.

Same shape as fire's rules and for the same reason: the thresholds that
matter are few, interact, and are not something anyone tunes one at a time
from a dashboard. Three presets bundle them, and any single one can still be
overridden per zone when a camera turns out to need it.

Schedules are imported from restricted zones rather than reimplemented — the
same concept, already covered by that module's tests, including windows that
wrap past midnight.
"""

from typing import Dict, List, Optional

from app.plugins.zones.rules import (            # noqa: F401
    describe_schedule, is_armed, next_transition, sanitize_schedule,
)

from app.plugins.fight.dynamics import (         # noqa: F401
    ADVISORY_NOTICE, ENGAGE_SEPARATION, FIGHT_THRESHOLD,
)

SEVERITIES = ("critical", "warning", "info")
DEFAULT_SEVERITY = "critical"
DEFAULT_SENSITIVITY = "standard"

# min_score           pair score a frame must reach to count as evidence
# min_frames          frames of evidence needed inside the confirmation window
# confirm_sec         how long it must persist before an incident is real
# engage_separation   how close two people must be, in body heights
# clear_sec           quiet time before the incident is declared over
# alert_cooldown_sec  minimum gap between two alerts for one zone
#
# A quarrel is shorter than a fire, so the confirmation windows here are
# seconds rather than tens of seconds: a scuffle that has to persist for ten
# seconds before anyone is told is a scuffle nobody can intervene in.
SENSITIVITIES: Dict[str, Dict[str, float]] = {
    "high": {
        "min_score": 0.40, "min_frames": 5, "confirm_sec": 0.8,
        "engage_separation": 1.5, "clear_sec": 6.0, "alert_cooldown_sec": 60.0,
    },
    "standard": {
        "min_score": 0.50, "min_frames": 8, "confirm_sec": 1.5,
        "engage_separation": ENGAGE_SEPARATION,
        "clear_sec": 10.0, "alert_cooldown_sec": 120.0,
    },
    "low": {
        "min_score": 0.65, "min_frames": 14, "confirm_sec": 2.5,
        "engage_separation": 1.0, "clear_sec": 15.0, "alert_cooldown_sec": 300.0,
    },
}

TUNING_KEYS = tuple(SENSITIVITIES[DEFAULT_SENSITIVITY].keys())


def tuning(sensitivity: Optional[str],
           overrides: Optional[Dict[str, object]] = None) -> Dict[str, float]:
    """
    Thresholds for a zone: a preset with any per-zone overrides applied.

    Always a fresh dict — the presets are module level and a caller that
    mutated one would retune every other zone on the site. Null overrides are
    ignored rather than read as zero, because that is what a null column
    means coming back from the database.
    """
    preset = SENSITIVITIES.get(str(sensitivity or "").strip().lower())
    if preset is None:
        preset = SENSITIVITIES[DEFAULT_SENSITIVITY]
    out = dict(preset)
    for key, value in (overrides or {}).items():
        if key in TUNING_KEYS and value is not None:
            out[key] = int(value) if key == "min_frames" else float(value)
    return out


def sanitize_sensitivity(value) -> str:
    name = str(value or "").strip().lower()
    return name if name in SENSITIVITIES else DEFAULT_SENSITIVITY


def sanitize_severity(value) -> str:
    name = str(value or "").strip().lower()
    return name if name in SEVERITIES else DEFAULT_SEVERITY


def describe_tuning(sensitivity: Optional[str],
                    overrides: Optional[Dict[str, object]] = None) -> str:
    t = tuning(sensitivity, overrides)
    return (f"{sanitize_sensitivity(sensitivity)}: confirm over "
            f"{t['confirm_sec']:g}s / {int(t['min_frames'])} frames, "
            f"score >= {t['min_score']:g}, "
            f"re-alert after {t['alert_cooldown_sec']:g}s")
