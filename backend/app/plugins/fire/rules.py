"""
SOW 2.8 — rule configuration: how hard a zone is to trigger, and when.

Sensitivity is the knob that gets turned during commissioning, and it is the
one that decides whether the system survives contact with the site. A boiler
house or a battery store wants every wisp reported; a car park lit by sodium
lamps, or a yard where welding happens all shift, wants almost nothing. Six
separate thresholds is not a thing anyone will tune from a dashboard, so
they are bundled into three named presets, and any single threshold can still
be overridden per zone when a camera turns out to need it.

Schedules are imported from restricted zones rather than reimplemented. They
are the same concept — a rule that only applies at certain hours — and zones'
suite already covers the calendar edge cases, including windows that wrap
past midnight. A second copy would be a second set of bugs.
"""

from typing import Dict, List, Optional, Sequence

# Shared with SOW 2.9. Re-exported so callers here have one import, and
# asserted identical by the tests so it cannot quietly fork into a copy.
from app.plugins.zones.rules import (            # noqa: F401
    describe_schedule,
    is_armed,
    next_transition,
    sanitize_schedule,
)

from app.plugins.fire.detector import (
    FIRE,
    KINDS,
    MIN_FIRE_AREA_FRAC,
    SMOKE,
    STATUTORY_NOTICE,                             # noqa: F401
)

SEVERITIES = ("critical", "warning", "info")

# Fire is not a warning. An open flame on a live camera is the one thing on
# this appliance that should reach a person immediately, so it defaults to the
# top severity while smoke — which is also steam, dust, exhaust and fog —
# starts a rung lower.
DEFAULT_SEVERITY = {FIRE: "critical", SMOKE: "warning"}

DEFAULT_SENSITIVITY = "standard"

# min_score        detector score a region must reach to count as evidence
# min_frames       frames of evidence needed inside the confirmation window
# confirm_sec      how long evidence must persist before an incident is real
# min_area_frac    smallest region worth considering, as a fraction of frame
# clear_sec        quiet time before an incident is declared over
# alert_cooldown_sec  minimum gap between two alerts for one zone
SENSITIVITIES: Dict[str, Dict[str, float]] = {
    "high": {
        "min_score": 0.45, "min_frames": 2, "confirm_sec": 1.0,
        "min_area_frac": MIN_FIRE_AREA_FRAC * 0.5,
        "clear_sec": 12.0, "alert_cooldown_sec": 60.0,
    },
    "standard": {
        "min_score": 0.50, "min_frames": 3, "confirm_sec": 2.0,
        "min_area_frac": MIN_FIRE_AREA_FRAC,
        "clear_sec": 20.0, "alert_cooldown_sec": 120.0,
    },
    "low": {
        "min_score": 0.60, "min_frames": 6, "confirm_sec": 4.0,
        "min_area_frac": MIN_FIRE_AREA_FRAC * 2.0,
        "clear_sec": 30.0, "alert_cooldown_sec": 300.0,
    },
}

TUNING_KEYS = tuple(SENSITIVITIES[DEFAULT_SENSITIVITY].keys())


def tuning(sensitivity: Optional[str],
           overrides: Optional[Dict[str, object]] = None) -> Dict[str, float]:
    """
    The thresholds for a zone: a preset, with any per-zone overrides applied.

    Always returns a fresh dict — the presets are module-level and a caller
    that mutated one would retune every other zone on the site. Null
    overrides are ignored rather than treated as zero, because "leave this
    one alone" is what a null column means coming back from the database.
    """
    preset = SENSITIVITIES.get(str(sensitivity or "").strip().lower())
    if preset is None:
        preset = SENSITIVITIES[DEFAULT_SENSITIVITY]
    out = dict(preset)
    for key, value in (overrides or {}).items():
        if key in TUNING_KEYS and value is not None:
            out[key] = float(value) if key != "min_frames" else int(value)
    return out


def sanitize_sensitivity(value) -> str:
    name = str(value or "").strip().lower()
    return name if name in SENSITIVITIES else DEFAULT_SENSITIVITY


def sanitize_kinds(value) -> List[str]:
    """
    What a zone watches for. Unknown entries are dropped, and a zone left
    watching for nothing falls back to both — a zone that can never fire is
    worse than a zone that watches too much, because nobody notices it.
    """
    if value is None:
        return list(KINDS)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return list(KINDS)
    seen, out = set(), []
    for raw in value:
        name = str(raw or "").strip().lower()
        if name in KINDS and name not in seen:
            seen.add(name)
            out.append(name)
    return out or list(KINDS)


def default_severity(kind: str) -> str:
    return DEFAULT_SEVERITY.get(str(kind or "").strip().lower(), "warning")


def sanitize_severity(value) -> str:
    name = str(value or "").strip().lower()
    return name if name in SEVERITIES else "warning"


def describe_tuning(sensitivity: Optional[str],
                    overrides: Optional[Dict[str, object]] = None) -> str:
    t = tuning(sensitivity, overrides)
    return (f"{sanitize_sensitivity(sensitivity)}: confirm over "
            f"{t['confirm_sec']:g}s / {int(t['min_frames'])} frames, "
            f"score >= {t['min_score']:g}, "
            f"re-alert after {t['alert_cooldown_sec']:g}s")
