"""
When a zone is armed, and what it is armed against.

The rule that matters most on a real site is the one that was missing
entirely: a restricted area is usually only restricted *some of the time*.
The yard is a walkway during the shift and a restricted zone after 18:00;
the substation is off limits at weekends. Without schedules the only honest
setting is "off", which is what every site ends up doing, and the feature
stops existing.

Days are Python weekday numbers, 0 = Monday .. 6 = Sunday, and times are the
appliance's local wall clock, because "after six" means what the guard's
watch says, not UTC.
"""

import re
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# COCO classes a zone can watch for. Anything the detector does not emit would
# make a zone that can never fire, so the choice is closed rather than free.
CLASS_NAMES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
    5: "bus", 7: "truck",
}
DEFAULT_CLASSES = [0]

MAX_WINDOWS = 8


def minutes_of_day(value: str) -> Optional[int]:
    m = _HHMM.match(str(value).strip())
    if m is None:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def sanitize_schedule(value) -> Optional[List[dict]]:
    """
    Normalizes a schedule to a list of windows, or None meaning always armed.

    Returns None for null/empty input — a zone with no schedule is armed
    around the clock, which is the safe reading of "restricted area". Raises
    ValueError with an operator-readable message on anything malformed, so
    the API can turn it straight into a 422 rather than saving a schedule
    that silently never matches.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("schedule must be a list of time windows, or null for always-on")
    if not value:
        return None
    if len(value) > MAX_WINDOWS:
        raise ValueError(f"at most {MAX_WINDOWS} time windows per zone")

    out: List[dict] = []
    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"window {idx + 1} must be an object with start, end and days")
        start = minutes_of_day(raw.get("start", ""))
        end = minutes_of_day(raw.get("end", ""))
        if start is None or end is None:
            raise ValueError(f"window {idx + 1} needs start and end as 24h HH:MM")
        if start == end:
            # Ambiguous between "never" and "always", and an operator who
            # meant all day would never find out which was chosen.
            raise ValueError(
                f"window {idx + 1} starts and ends at the same time — "
                f"use 00:00 to 23:59 for a whole day")
        days = raw.get("days")
        if days is None or days == []:
            clean_days = list(range(7))
        else:
            if not isinstance(days, (list, tuple)):
                raise ValueError(f"window {idx + 1}: days must be a list of 0-6 (Mon-Sun)")
            clean_days = sorted({int(d) for d in days
                                 if isinstance(d, int) and not isinstance(d, bool)
                                 and 0 <= d <= 6})
            if len(clean_days) != len({int(d) for d in days if isinstance(d, int)}) \
                    or not clean_days:
                raise ValueError(f"window {idx + 1}: days must be integers 0-6 (Mon-Sun)")
        out.append({
            "start": f"{start // 60:02d}:{start % 60:02d}",
            "end": f"{end // 60:02d}:{end % 60:02d}",
            "days": clean_days,
        })
    return out


def _window_active(window: dict, when: datetime) -> bool:
    start = minutes_of_day(window.get("start", "")) or 0
    end = minutes_of_day(window.get("end", "")) or 0
    days = window.get("days") or list(range(7))
    now_m = when.hour * 60 + when.minute
    if start < end:
        return when.weekday() in days and start <= now_m < end
    # Wraps past midnight. The day filter applies to the day the window
    # opened, so a Friday 22:00-06:00 window still covers Saturday 02:00.
    if now_m >= start:
        return when.weekday() in days
    if now_m < end:
        return ((when.weekday() - 1) % 7) in days
    return False


def is_armed(schedule: Optional[Sequence[dict]], when: Optional[datetime] = None) -> bool:
    """True when the zone's rules apply at `when` (local time)."""
    if not schedule:
        return True
    when = when or datetime.now()
    return any(_window_active(w, when) for w in schedule)


def next_transition(schedule: Optional[Sequence[dict]],
                    when: Optional[datetime] = None,
                    horizon_days: int = 8) -> Optional[datetime]:
    """
    When the armed state next flips, for the "armed until 06:00" line in the
    UI. None when the zone is always armed or nothing changes within the
    horizon. Evaluated at window boundaries rather than by stepping minutes.
    """
    if not schedule:
        return None
    now = (when or datetime.now()).replace(second=0, microsecond=0)
    state = is_armed(schedule, now)
    midnight = now.replace(hour=0, minute=0)

    candidates = set()
    for day in range(horizon_days + 1):
        base = midnight + timedelta(days=day)
        for w in schedule:
            for key in ("start", "end"):
                mins = minutes_of_day(w.get(key, ""))
                if mins is None:
                    continue
                candidates.add(base + timedelta(minutes=mins))
    for moment in sorted(c for c in candidates if c > now):
        if (moment - now).days > horizon_days:
            break
        if is_armed(schedule, moment) != state:
            return moment
    return None


def describe_schedule(schedule: Optional[Sequence[dict]]) -> str:
    if not schedule:
        return "Always armed"
    parts = []
    for w in schedule:
        days = w.get("days") or list(range(7))
        label = ("every day" if len(days) == 7
                 else ",".join(DAY_NAMES[d] for d in days))
        parts.append(f"{w.get('start')}-{w.get('end')} {label}")
    return "; ".join(parts)


def sanitize_classes(value) -> List[int]:
    """
    The object classes a zone watches. Unknown ids are dropped rather than
    rejected: a zone configured against a class this detector no longer emits
    should keep working for the classes it does.
    """
    if value is None:
        return list(DEFAULT_CLASSES)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return list(DEFAULT_CLASSES)
    out = sorted({int(v) for v in value
                  if isinstance(v, (int, float)) and not isinstance(v, bool)
                  and int(v) in CLASS_NAMES})
    return out or list(DEFAULT_CLASSES)


def class_label(class_id: int) -> str:
    return CLASS_NAMES.get(int(class_id), f"class {class_id}")


def armed_state(schedule: Optional[Sequence[dict]],
                when: Optional[datetime] = None) -> Tuple[bool, Optional[datetime]]:
    when = when or datetime.now()
    return is_armed(schedule, when), next_transition(schedule, when)
