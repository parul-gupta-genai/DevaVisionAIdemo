"""
Blacklist / whitelist matching for ANPR.

The stored list and the OCR read almost never agree character-for-character.
An operator types "UP 16 B 3895"; the reader returns "UP16B3895" on a good
frame and "UP1683895" on a poor one, because B/8, O/0, I/1 and S/5 are the
same handful of pixels at plate resolution. Matching on string equality — what
this did before — therefore misses most of the vehicles the list exists to
catch, and does so silently.

So matching happens on three levels:

  exact           normalised strings are identical
  ocr_equivalent  they agree once the known OCR confusions are collapsed
  fuzzy           one further character differs

and the two list types are deliberately NOT treated the same way:

  A blacklist exists to avoid missing a vehicle. A false positive costs a
  guard a second look, so tolerant matching is on by default.

  A whitelist exists to authorise. A false positive opens a barrier for the
  wrong vehicle, which is worse than making a legitimate driver wait, so it
  requires an exact match by default.

Both are configurable, but that asymmetry is the safe default and is applied
per list type rather than globally.
"""

import os
import threading
import time
from typing import Dict, List, Optional, Tuple

from loguru import logger

from app.plugins.anpr.validator import PlateValidator

# Collapse every character that OCR confuses onto one representative, so a
# confusable pair hashes to the same key and matching stays a dict lookup on
# the hot path instead of a scan over the whole list.
_COLLAPSE = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "T": "1",
    "Z": "2", "B": "8", "S": "5",
    "A": "4", "G": "6", "J": "3",
}

BLACKLIST_TYPES = {"BLACKLIST", "STOLEN", "STOLEN VEHICLE", "EXPIRED ACCESS", "POLICE"}
WHITELIST_TYPES = {"WHITELIST", "VIP", "EMPLOYEE", "CONTRACTOR", "VISITOR"}


def normalise(plate: Optional[str]) -> str:
    """Upper-case, strip separators, drop the HSRP 'IND' marker."""
    if not plate:
        return ""
    return PlateValidator.clean_plate_string(str(plate))


def canonical(plate: Optional[str]) -> str:
    """The OCR-confusion-insensitive key for a plate."""
    return "".join(_COLLAPSE.get(c, c) for c in normalise(plate))


def _within_one_edit(a: str, b: str) -> bool:
    """
    True when a and b differ by at most one substitution, insertion or
    deletion. Bounded at one on purpose: at two edits a six-character plate
    starts colliding with genuinely different plates.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs <= 1
    # One is longer: check it is the other with a single character inserted.
    longer, shorter = (a, b) if la > lb else (b, a)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return True
    return False


def is_blacklist(list_type: Optional[str]) -> bool:
    return (list_type or "").strip().upper() in BLACKLIST_TYPES


def is_whitelist(list_type: Optional[str]) -> bool:
    return (list_type or "").strip().upper() in WHITELIST_TYPES


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


class PlateWatchlist:
    """
    A cached, periodically refreshed index of the plate lists.

    Cached because the match happens when a vehicle track finalises, on the
    analytics thread, and a database round trip there would stall the camera
    that saw the vehicle. The list is small (hundreds of plates) and changes
    rarely, so a short TTL is ample and a stale-by-seconds blacklist is a far
    better trade than a stalled pipeline.
    """

    def __init__(self, ttl_sec: float = 30.0):
        self.ttl_sec = ttl_sec
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        # canonical key -> entries (several plates can collapse to one key)
        self._index: Dict[str, List[dict]] = {}
        self._exact: Dict[str, List[dict]] = {}
        self._count = 0

    # ------------------------------------------------------------------ #
    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._loaded_at) < self.ttl_sec:
            return
        # Only one thread reloads; the others keep using the current index
        # rather than queueing behind the query.
        if not self._lock.acquire(blocking=False):
            return
        try:
            if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
                return
            from database.session import SessionLocal
            from app.plugins.anpr.models import ANPRWatchlist

            db = SessionLocal()
            try:
                rows = db.query(ANPRWatchlist).all()
                index: Dict[str, List[dict]] = {}
                exact: Dict[str, List[dict]] = {}
                wall = time.time()
                live = 0
                for r in rows:
                    # An entry past its expiry must stop firing. This was
                    # stored but never checked, so a temporary pass stayed
                    # valid forever.
                    if r.expiry and float(r.expiry) < wall:
                        continue
                    plate = normalise(r.plate_number)
                    if not plate:
                        continue
                    entry = {
                        "id": r.id,
                        "plate_number": plate,
                        "list_type": (r.list_type or "").strip().upper(),
                        "priority": r.priority or 0,
                        "reason": r.reason,
                        "notes": r.notes,
                        "expiry": r.expiry,
                        "notification_rules": r.notification_rules,
                    }
                    exact.setdefault(plate, []).append(entry)
                    index.setdefault(canonical(plate), []).append(entry)
                    live += 1
                for bucket in (index, exact):
                    for key in bucket:
                        bucket[key].sort(key=lambda e: -e["priority"])
                self._index, self._exact, self._count = index, exact, live
                self._loaded_at = time.monotonic()
            finally:
                db.close()
        except Exception as exc:
            # A failed refresh must leave the previous index in place: an
            # unreachable database should not silently disable the blacklist.
            logger.error(f"ANPR watchlist refresh failed: {exc}")
        finally:
            self._lock.release()

    def invalidate(self) -> None:
        """Forces the next match to reload — called after an edit."""
        self._loaded_at = 0.0

    @property
    def size(self) -> int:
        return self._count

    # ------------------------------------------------------------------ #
    def match(self, plate: str) -> Tuple[Optional[dict], Optional[str]]:
        """
        Best list entry for a plate read, and how it was matched.

        Returns (entry, kind) with kind in {exact, ocr_equivalent, fuzzy},
        or (None, None). Blacklist entries win ties: if a plate somehow sits
        on both lists, refusing entry is the safer resolution.
        """
        self.refresh()
        read = normalise(plate)
        if not read:
            return None, None

        for entry in self._exact.get(read, []):
            return entry, "exact"

        allow_ocr = _flag("ANPR_LIST_OCR_TOLERANT", True)
        allow_fuzzy = _flag("ANPR_LIST_FUZZY", True)

        candidates: List[Tuple[dict, str]] = []
        if allow_ocr:
            for entry in self._index.get(canonical(read), []):
                candidates.append((entry, "ocr_equivalent"))
        if allow_fuzzy and not candidates:
            key = canonical(read)
            for other_key, entries in self._index.items():
                if _within_one_edit(key, other_key):
                    for entry in entries:
                        candidates.append((entry, "fuzzy"))

        # A whitelist must not authorise on an approximate read: opening a
        # barrier for the wrong vehicle is worse than asking a legitimate
        # driver to wait. A blacklist may, because missing one is worse.
        strict_whitelist = _flag("ANPR_WHITELIST_EXACT_ONLY", True)
        usable = [
            (e, k) for e, k in candidates
            if not (strict_whitelist and k != "exact" and is_whitelist(e["list_type"]))
        ]
        if not usable:
            return None, None

        usable.sort(key=lambda pair: (
            0 if is_blacklist(pair[0]["list_type"]) else 1,   # blacklist first
            {"exact": 0, "ocr_equivalent": 1, "fuzzy": 2}[pair[1]],
            -pair[0]["priority"],
        ))
        return usable[0]


# One shared index per process.
plate_watchlist = PlateWatchlist()
