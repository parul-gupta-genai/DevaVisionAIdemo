"""
SOW 2.7 — the motion layer for fight / quarrel detection.

Works entirely from tracked person boxes. No pixels are read, so this is cheap
enough to run on every frame of a 25-camera wall, and it inherits whatever the
tracker already knows about identity.

The whole design turns on one question: what separates a fight from the other
things two people do near each other? "Close together and moving fast" is the
obvious answer and it is wrong — it fires on a handshake, on a queue at a
turnstile, on colleagues talking with their hands, and on anyone running for a
bus. Those are most of what a camera ever sees, so a detector built that way
is switched off in its first week.

Three signals are used together, and each one exists to kill a specific false
positive:

  AGITATION rather than speed. A fight is not travel: it lurches, reverses and
  changes direction constantly. Speed is multiplied by how much the direction
  turns between samples, so someone sprinting in a straight line — fast, but
  going somewhere — scores near zero while someone thrashing on the spot
  scores high.

  BODY HEIGHTS rather than pixels. Every distance and speed is divided by the
  person's own box height, so the same struggle scores the same near the
  camera and far from it, and a zone's threshold means one thing across the
  whole frame.

  BOTH parties, not either. A pair scores the MINIMUM of the two agitations,
  so one person waving their arms beside a bystander is not a fight. It takes
  two.

This is an automated visual analytics aid. It does not replace human security
intervention, and no alert it raises should be treated as a verified assault.
"""

import math
from typing import Dict, List, Optional, Sequence, Tuple

ADVISORY_NOTICE = (
    "Automated visual analytics aid. Fight/quarrel detection is indicative "
    "only and does not replace human security intervention or verification."
)

# Rolling window per track, in samples. About 0.85s at the ~14fps the
# appliance runs, which is long enough to see a struggle reverse direction
# several times and short enough that it decays quickly once it stops.
WINDOW_SAMPLES = 12

# A person cannot move more than this many of their own body heights between
# two consecutive frames. Anything larger is the tracker reusing an id, not a
# human being — and at 14fps an unfiltered id swap across the frame reads as
# roughly 90 body-heights per second, which would otherwise be the most
# violent thing the system has ever seen.
MAX_STEP_BH = 1.5

# Agitation a single person must reach to count as fighting rather than
# moving. Walking scores ~0.0, running in a straight line ~0.0, standing with
# tracker jitter ~0.05, a struggle ~2.5.
AGITATION_THRESHOLD = 1.0

# How close two people must be, measured in body heights between their box
# centres, to be treated as involved with each other.
ENGAGE_SEPARATION = 1.2

# Two people at very different depths look adjacent in a flat image while
# being metres apart. A large mismatch in box height is the only depth cue
# available, so it is charged as extra separation.
DEPTH_TOLERANCE = 1.25
DEPTH_PENALTY = 1.0

# Normalised pair score at which the pair is worth reporting. Scores are
# min(agitation) scaled so that twice the single-person threshold reads 1.0.
FIGHT_THRESHOLD = 0.5

# Ceiling on tracks held per camera. Nothing upstream tells us a track has
# gone for good, so the oldest are evicted rather than accumulated.
MAX_TRACKS = 64


def _centre(bbox) -> Tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _height(bbox) -> float:
    return max(1.0, float(bbox[3] - bbox[1]))


def separation(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    """
    Distance between two people in body heights, plus a depth charge.

    Body heights rather than pixels so the same gap means the same thing at
    both ends of the frame; the depth charge because two people one behind
    the other are adjacent in the image and nowhere near each other in life.
    """
    ax, ay = _centre(box_a)
    bx, by = _centre(box_b)
    ha, hb = _height(box_a), _height(box_b)
    gap = math.hypot(ax - bx, ay - by) / ((ha + hb) / 2.0)
    ratio = max(ha, hb) / max(1.0, min(ha, hb))
    return gap + max(0.0, ratio - DEPTH_TOLERANCE) * DEPTH_PENALTY


def update_track(track: dict, bbox: Sequence[float], now: float) -> float:
    """
    Adds one observation to a track and returns its current agitation.

    `track` is this track's own mutable dict. Returns 0.0 until there is
    enough history to say anything, so a person who has only just appeared is
    never the reason an alert fires.
    """
    cx, cy = _centre(bbox)
    h = _height(bbox)
    samples: List[Tuple[float, float, float, float]] = track.setdefault("samples", [])

    if samples:
        pt, px, py, ph = samples[-1]
        if now <= pt:
            return track.get("agitation", 0.0)
        step_bh = math.hypot(cx - px, cy - py) / ((h + ph) / 2.0)
        if step_bh > MAX_STEP_BH:
            # Not a person moving: a track id landing on a different body.
            # Start again rather than average a teleport into the history.
            samples.clear()
            track["agitation"] = 0.0
            samples.append((now, cx, cy, h))
            return 0.0

    samples.append((now, cx, cy, h))
    if len(samples) > WINDOW_SAMPLES:
        del samples[:-WINDOW_SAMPLES]

    track["agitation"] = _agitation(samples)
    return track["agitation"]


def _agitation(samples) -> float:
    """
    Speed in body-heights per second, weighted by how much the direction
    turns. Straight-line travel of any speed scores near zero; the same
    distance covered while reversing scores high.
    """
    if len(samples) < 3:
        return 0.0

    vectors, speeds = [], []
    for (t0, x0, y0, h0), (t1, x1, y1, h1) in zip(samples, samples[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        scale = (h0 + h1) / 2.0
        dx, dy = (x1 - x0) / scale, (y1 - y0) / scale
        vectors.append((dx, dy))
        speeds.append(math.hypot(dx, dy) / dt)
    if len(vectors) < 2:
        return 0.0

    turns = []
    for (ax, ay), (bx, by) in zip(vectors, vectors[1:]):
        na, nb = math.hypot(ax, ay), math.hypot(bx, by)
        if na <= 0 or nb <= 0:
            continue
        cos = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
        # 0.0 when heading stays the same, 1.0 on a complete reversal.
        turns.append((1.0 - cos) / 2.0)
    if not turns:
        return 0.0

    mean_speed = sum(speeds) / len(speeds)
    mean_turn = sum(turns) / len(turns)
    return mean_speed * mean_turn


def evaluate_pairs(state: dict, boxes: Sequence[Tuple[object, Sequence[float]]],
                   now: float) -> Dict[Tuple[object, object], float]:
    """
    Updates every track and scores each engaged pair, 0..1.

    `boxes` is [(track_id, bbox), ...] for one frame. The returned score is
    the MINIMUM of the two agitations, normalised — because a fight takes two,
    and scoring the maximum would make any agitated person standing near a
    bystander an incident.
    """
    tracks: Dict[object, dict] = state.setdefault("tracks", {})

    live = []
    for track_id, bbox in boxes or []:
        if bbox is None or len(bbox) < 4:
            continue
        track = tracks.setdefault(track_id, {})
        track["seen"] = now
        agitation = update_track(track, bbox, now)
        live.append((track_id, bbox, agitation))

    _evict(tracks)

    scores: Dict[Tuple[object, object], float] = {}
    for i in range(len(live)):
        ta, ba, aa = live[i]
        for j in range(i + 1, len(live)):
            tb, bb, ab = live[j]
            if separation(ba, bb) > ENGAGE_SEPARATION:
                continue
            pair = (ta, tb) if str(ta) <= str(tb) else (tb, ta)
            joint = min(aa, ab) / (2.0 * AGITATION_THRESHOLD)
            scores[pair] = max(scores.get(pair, 0.0), min(1.0, joint))
    return scores


def _evict(tracks: Dict[object, dict]) -> None:
    """Nothing upstream says a track is gone, so drop the least recent."""
    if len(tracks) <= MAX_TRACKS:
        return
    for track_id, _ in sorted(tracks.items(),
                              key=lambda kv: kv[1].get("seen", 0.0)
                              )[:len(tracks) - MAX_TRACKS]:
        tracks.pop(track_id, None)
