"""
Gate-wise ANPR: direction and access, as pure functions.

The SOW splits ANPR into recognising a plate and deciding what that means at
a particular gate. Recognition already existed; this is the second half — the
part the client actually configures, and the part a guard reads off a screen.

Deliberately dependency-free, for the same reason the zone geometry is: the
plugin calls it on the analytics thread inside the DeepStream process, the
API validator calls it to check what an operator typed, and a test calls it
with no pipeline at all. One implementation means the three can never
disagree about what a rule means.

The `direction` columns on ANPRVehicleTrack and ANPRPlateHistory have existed
since the table was created and nothing has ever written to them.
"""

from typing import Optional, Sequence, Tuple

from app.plugins.anpr.watchlist import is_blacklist, normalise

# ---- gate roles ----------------------------------------------------------
ENTRY = "ENTRY"
EXIT = "EXIT"
BIDIRECTIONAL = "BIDIRECTIONAL"
ROLES = (ENTRY, EXIT, BIDIRECTIONAL)

# What operators actually type, and what the UI sends.
_ROLE_ALIASES = {
    "ENTRY": ENTRY, "IN": ENTRY, "INBOUND": ENTRY, "ENTER": ENTRY,
    "EXIT": EXIT, "OUT": EXIT, "OUTBOUND": EXIT, "LEAVE": EXIT,
    "BIDIRECTIONAL": BIDIRECTIONAL, "BOTH": BIDIRECTIONAL, "BI": BIDIRECTIONAL,
    "TWO-WAY": BIDIRECTIONAL, "TWO WAY": BIDIRECTIONAL,
}

# ---- access decisions ----------------------------------------------------
ALLOW = "ALLOW"
DENY = "DENY"
UNLISTED_POLICIES = (ALLOW, DENY)

# ---- direction inference -------------------------------------------------
VERTICAL = "VERTICAL"
HORIZONTAL = "HORIZONTAL"
# Below this the vehicle has not meaningfully moved. A queueing or parked
# vehicle must produce no direction rather than a guessed one: an unknown
# direction is honest, a wrong one corrupts the gate log the client relies on.
DEFAULT_MIN_TRAVEL_PX = 40.0

# ---- event types ---------------------------------------------------------
VEHICLE_ENTRY = "VEHICLE_ENTRY"
VEHICLE_EXIT = "VEHICLE_EXIT"
VEHICLE_PASS = "VEHICLE_PASS"
ACCESS_DENIED = "ACCESS_DENIED"


def normalise_role(value) -> str:
    """
    Maps whatever the client called it onto a role.

    Anything unrecognised becomes BIDIRECTIONAL rather than raising: a gate
    with a typo in its role should still record vehicles, and recording a
    pass with no direction is safer than asserting the wrong one.
    """
    if not isinstance(value, str):
        return BIDIRECTIONAL
    return _ROLE_ALIASES.get(value.strip().upper(), BIDIRECTIONAL)


def resolve_direction(role: str,
                      first_point: Optional[Sequence[float]],
                      last_point: Optional[Sequence[float]],
                      axis: str = VERTICAL,
                      invert: bool = False,
                      min_travel_px: float = DEFAULT_MIN_TRAVEL_PX) -> Optional[str]:
    """
    Which way a vehicle went through this gate, or None if unknowable.

    A designated gate answers by definition — that is what designating it
    means, and it is how the overwhelming majority of sites are laid out.
    Only a bidirectional gate has to infer anything, and it does so from how
    far the vehicle travelled along the gate's axis between the first and
    last frames it was tracked in.
    """
    role = normalise_role(role)
    if role in (ENTRY, EXIT):
        return role

    if not first_point or not last_point:
        return None
    try:
        idx = 0 if str(axis).upper() == HORIZONTAL else 1
        travel = float(last_point[idx]) - float(first_point[idx])
    except (TypeError, ValueError, IndexError):
        return None

    if abs(travel) < float(min_travel_px):
        return None

    # Growing coordinate — down the frame, or to the right — reads as
    # approaching the camera, i.e. arriving. A camera mounted facing the
    # other way sets invert.
    inbound = travel > 0
    if invert:
        inbound = not inbound
    return ENTRY if inbound else EXIT


def sanitize_rules(value) -> dict:
    """
    Normalises the client's gate access rules.

    Shape: {"allow": [list types], "deny": [list types], "unlisted": ALLOW|DENY}

    An empty allow list means "no restriction", NOT "permit nothing" — a gate
    the client has not finished configuring must keep letting vehicles
    through and logging them, because ANPR is a recording feature until they
    say otherwise. Raises ValueError on anything malformed so the API can
    return 422 rather than saving a rule that behaves unexpectedly.
    """
    if value is None:
        return {"allow": [], "deny": [], "unlisted": ALLOW}
    if not isinstance(value, dict):
        raise ValueError("gate access rules must be an object with allow, deny and unlisted")

    def _types(key) -> list:
        raw = value.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            raise ValueError(f"'{key}' must be a list of watchlist types")
        seen, out = set(), []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError(f"'{key}' must contain watchlist type names")
            name = item.strip().upper()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    unlisted = value.get("unlisted", ALLOW)
    unlisted = str(unlisted).strip().upper() if unlisted is not None else ALLOW
    if unlisted not in UNLISTED_POLICIES:
        raise ValueError("'unlisted' must be ALLOW or DENY")

    return {"allow": _types("allow"), "deny": _types("deny"), "unlisted": unlisted}


def decide_access(list_type: Optional[str], rules: dict) -> Tuple[str, str]:
    """
    Whether this vehicle may pass this gate, and why — in words a guard can
    act on without opening the configuration.
    """
    rules = rules or {"allow": [], "deny": [], "unlisted": ALLOW}
    name = (list_type or "").strip().upper()

    # Blacklisting never needs opting in to. A stolen vehicle must be refused
    # at a gate nobody has configured yet.
    if is_blacklist(name):
        return DENY, f"Blacklisted vehicle ({name.title()})"

    if name and name in (rules.get("deny") or []):
        return DENY, f"{name} is denied at this gate"

    if not name:
        if rules.get("unlisted") == DENY:
            return DENY, "Vehicle is not on any list"
        return ALLOW, "Vehicle is not on any list"

    allow = rules.get("allow") or []
    if allow and name not in allow:
        return DENY, f"{name} is not permitted at this gate"

    return ALLOW, f"{name} permitted"


def event_type_for(direction: Optional[str], decision: str) -> str:
    """The event a completed pass should be logged as."""
    if decision == DENY:
        return ACCESS_DENIED
    if direction == ENTRY:
        return VEHICLE_ENTRY
    if direction == EXIT:
        return VEHICLE_EXIT
    # Allowed, but the gate could not tell which way. Still a real pass and
    # still worth a row; the direction column simply stays null.
    return VEHICLE_PASS


def describe_rules(rules: dict) -> str:
    """One line for the gate list in the UI."""
    rules = sanitize_rules(rules) if not isinstance(rules, dict) else rules
    allow = rules.get("allow") or []
    deny = rules.get("deny") or []
    parts = ["Allows " + (", ".join(allow) if allow else "any list")]
    if deny:
        parts.append("denies " + ", ".join(deny))
    parts.append("unlisted vehicles "
                 + ("denied" if rules.get("unlisted") == DENY else "allowed"))
    return "; ".join(parts)


def plate_key(plate: Optional[str]) -> str:
    """Shared plate normalisation, so gate logs and watchlists agree."""
    return normalise(plate)
