"""
One shared implementation for event snapshots.

Before this, only ANPR, PPE and Visitor ever wrote an image, each with its own
inline copy of the logic; fire, intrusion and attendance hardcoded
`snapshot_file: None`, and counting, carton, parking and restriction never
mentioned snapshots at all. So most events reached the dashboard with nothing
to look at.

Writing is deliberately cheap and bounded:
  * the JPEG encode happens on the analytics worker, not the GStreamer thread
  * output is capped in pixel size, so a snapshot of a 4K frame is not 4K
  * each directory is pruned to MAX_PER_DIR so an alerting camera cannot fill
    the disk overnight
  * every failure is swallowed — a snapshot is never worth dropping an event
"""

import os
import time
import uuid
import threading
from typing import Optional, Sequence

import cv2
from loguru import logger

# api/server.py mounts <backend>/snapshots at /snapshots. Anchor writes to
# that directory rather than to the process CWD: the pre-existing writers all
# assumed cwd == backend/, which holds under start.sh but silently drops the
# image somewhere unserved the moment the backend is launched from anywhere
# else. Events still STORE the relative path ("snapshots/<kind>/<f>.jpg"),
# which is what the frontend prefixes with "/" to build a URL.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT_ROOT = os.getenv("SNAPSHOT_ROOT") or os.path.join(_BACKEND_DIR, "snapshots")
MAX_PER_DIR = int(os.getenv("SNAPSHOT_MAX_PER_DIR", "3000"))
JPEG_QUALITY = int(os.getenv("SNAPSHOT_JPEG_QUALITY", "80"))
# Longest edge of a written snapshot. Enough to see what happened, small
# enough that a wall of cameras alerting at once is not a disk problem.
MAX_EDGE = int(os.getenv("SNAPSHOT_MAX_EDGE", "960"))

_prune_lock = threading.Lock()
_writes_since_prune = {}


def _prune(directory: str) -> None:
    """Keeps a snapshot directory bounded, oldest-first."""
    try:
        names = os.listdir(directory)
        if len(names) <= MAX_PER_DIR:
            return
        paths = [os.path.join(directory, n) for n in names if n.endswith(".jpg")]
        paths.sort(key=lambda p: os.path.getmtime(p))
        for p in paths[: len(paths) - MAX_PER_DIR]:
            try:
                os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def save_event_snapshot(
    kind: str,
    camera_id: str,
    frame,
    bbox: Optional[Sequence[float]] = None,
    pad: float = 0.15,
    prune: bool = True,
) -> Optional[str]:
    """
    Writes a JPEG for one event and returns its repo-relative path.

    `bbox` is [x1, y1, x2, y2] in frame coordinates; when given the crop is
    padded by `pad` and written instead of the whole frame, which is what
    makes a snapshot actually useful for PPE, intrusion or a plate. Returns
    None on any failure — callers must treat the snapshot as optional.

    Set `prune=False` for images a database row points at for its own lifetime
    (a visitor's profile photo). Event snapshots are transient and age out;
    a registry photo deleted underneath its record leaves a permanent hole.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    try:
        h, w = frame.shape[:2]
        img = frame

        if bbox is not None and len(bbox) >= 4:
            x1, y1, x2, y2 = (float(v) for v in bbox[:4])
            bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
            x1 = int(max(0, x1 - bw * pad))
            y1 = int(max(0, y1 - bh * pad))
            x2 = int(min(w, x2 + bw * pad))
            y2 = int(min(h, y2 + bh * pad))
            if x2 - x1 >= 16 and y2 - y1 >= 16:
                img = frame[y1:y2, x1:x2]

        ih, iw = img.shape[:2]
        longest = max(ih, iw)
        if longest > MAX_EDGE:
            scale = MAX_EDGE / float(longest)
            img = cv2.resize(
                img, (max(1, int(iw * scale)), max(1, int(ih * scale))),
                interpolation=cv2.INTER_AREA,
            )

        directory = os.path.join(SNAPSHOT_ROOT, kind)
        os.makedirs(directory, exist_ok=True)

        name = f"{str(camera_id)[:8]}_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
        path = os.path.join(directory, name)

        ok = cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            return None

        # Store the path the way the URL is built, not the way the disk is
        # laid out, so an absolute SNAPSHOT_ROOT still yields /snapshots/...
        stored = os.path.relpath(os.path.abspath(path), _BACKEND_DIR)
        if not stored.startswith(".."):
            path = stored

        # Amortised pruning: checking every write would stat the directory
        # thousands of times a minute on a busy wall.
        due = False
        if prune:
            with _prune_lock:
                n = _writes_since_prune.get(kind, 0) + 1
                _writes_since_prune[kind] = n
                due = n >= 200
                if due:
                    _writes_since_prune[kind] = 0
        if due:
            _prune(directory)

        return path
    except Exception as exc:  # never let a snapshot break an event
        logger.debug(f"snapshot ({kind}) failed for {camera_id}: {exc}")
        return None


def frame_for_snapshot(frame_data, tracker_context, camera_id):
    """
    Best available pixels for a snapshot.

    Metadata-only plugins (counting, intrusion, parking, restriction) never
    receive pixels on their own account, so they fall back to the most recent
    frame the engine cached for this camera. That frame is at most a second
    old — close enough for an alert thumbnail, and free.
    """
    if getattr(frame_data, "frame", None) is not None:
        return frame_data.frame
    try:
        return tracker_context.get_latest_frame(camera_id)
    except AttributeError:
        return None
