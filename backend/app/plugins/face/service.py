"""
Enrolment and recognition logic, kept out of both the router and the plugin.

The router turns HTTP into calls here; the plugin turns video frames into
calls here. Both need identical decisions about what counts as a usable face
and what counts as the same person, so those decisions live in exactly one
place.
"""

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from app.engine.snapshots import save_event_snapshot
from app.plugins.face.config import FaceTuning
from app.plugins.face.repository import FaceRepository


class EnrolmentError(Exception):
    """
    An enrolment that must be refused, with a reason the operator can act on.

    `code` is stable and machine-readable so the enrolment UI can react
    (offer to merge on a duplicate, re-take on a blurred photo) rather than
    only showing a sentence.
    """

    def __init__(self, code: str, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


# --------------------------------------------------------------------- #
# Face engine
# --------------------------------------------------------------------- #
_engine = None
_engine_lock = threading.Lock()
_engine_failures = 0
MAX_ENGINE_ATTEMPTS = 5


def get_face_engine():
    """
    Lazily builds the shared face engine.

    Built once per process on first use — importing this module stays cheap for
    the API process. Repeated failures are capped so a broken install does not
    retry indefinitely.
    """
    global _engine, _engine_failures
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        if _engine_failures >= MAX_ENGINE_ATTEMPTS:
            return None
        try:
            from detection.strategies.insightface import InsightFaceStrategy
            engine = InsightFaceStrategy()
            _engine = engine
            return _engine
        except Exception as exc:
            _engine_failures += 1
            logger.error(f"Face engine init failed: {exc}")
            return None


def sharpness(image: np.ndarray) -> float:
    """Variance of the Laplacian — low values mean motion blur or defocus."""
    try:
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        return float(cv2.Laplacian(grey, cv2.CV_64F).var())
    except Exception:
        return 0.0


def decode_image(data: bytes) -> Optional[np.ndarray]:
    try:
        buf = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def detect_faces(image: np.ndarray) -> List[Dict[str, Any]]:
    engine = get_face_engine()
    if engine is None or image is None or getattr(image, "size", 0) == 0:
        return []
    return engine.detect_and_extract(image)


def _face_metrics(face: Dict[str, Any], image: np.ndarray) -> Dict[str, Any]:
    x1, y1, x2, y2 = [int(v) for v in face["bbox"][:4]]
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(image.shape[1], x2)
    y2 = min(image.shape[0], y2)
    crop = image[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else None
    return {
        "bbox": [x1, y1, x2, y2],
        "width": x2 - x1,
        "height": y2 - y1,
        "det_score": float(face.get("confidence", 0.0)),
        "sharpness": sharpness(crop) if crop is not None and crop.size else 0.0,
        "crop": crop,
    }


class FaceService:
    def __init__(self, db, tuning: Optional[FaceTuning] = None):
        self.repo = FaceRepository(db)
        self.tuning = tuning or FaceTuning.current()

    # ----------------------------------------------------------------- #
    # Enrolment
    # ----------------------------------------------------------------- #
    def validate_enrolment_image(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Accepts an image only if it contains exactly one clearly usable face.

        Each rejection is a distinct code because they need different operator
        responses: no face means re-frame, several faces means crop, a small
        or blurred face means re-take. Collapsing them into "invalid image"
        is what makes an enrolment drive stall.
        """
        if image is None or getattr(image, "size", 0) == 0:
            raise EnrolmentError("unreadable_image", "The uploaded file is not a readable image.")

        if get_face_engine() is None:
            raise EnrolmentError(
                "engine_unavailable",
                "The face recognition engine is not available on this server.",
            )

        faces = detect_faces(image)
        if not faces:
            raise EnrolmentError(
                "no_face", "No face was found in this image.")
        if len(faces) > 1:
            raise EnrolmentError(
                "multiple_faces",
                f"{len(faces)} faces were found; enrol one person per image.",
                {"faces": len(faces)},
            )

        m = _face_metrics(faces[0], image)
        t = self.tuning
        smallest = min(m["width"], m["height"])
        if smallest < t.min_face_px:
            raise EnrolmentError(
                "face_too_small",
                f"The face is {smallest}px across; at least {t.min_face_px}px is needed.",
                {"face_px": smallest, "required_px": t.min_face_px},
            )
        if m["det_score"] < t.min_det_score:
            raise EnrolmentError(
                "low_confidence",
                f"Face confidence {m['det_score']:.2f} is below {t.min_det_score:.2f}.",
                {"det_score": m["det_score"]},
            )
        if m["sharpness"] < t.min_sharpness:
            raise EnrolmentError(
                "blurred",
                f"The image is too blurred (sharpness {m['sharpness']:.0f} "
                f"below {t.min_sharpness:.0f}).",
                {"sharpness": m["sharpness"]},
            )

        m["embedding"] = faces[0]["embedding"]
        return m

    def check_duplicate(self, embedding, exclude_person_id: Optional[str] = None):
        """
        Returns the person this face already belongs to, if any.

        Run before every enrolment: two rows for one human silently splits
        that person's attendance in half and makes a watchlist entry
        unreliable, and it is invisible until somebody reads a report.
        """
        enrolment, similarity = self.repo.nearest_enrolment(
            embedding, exclude_person_id=exclude_person_id)
        if enrolment is None:
            return None, similarity
        if similarity >= self.tuning.duplicate_threshold:
            return self.repo.get_person(enrolment.person_id), similarity
        return None, similarity

    def enrol(
        self,
        image: np.ndarray,
        name: str,
        person_code: Optional[str] = None,
        person_type: str = "EMPLOYEE",
        department: Optional[str] = None,
        designation: Optional[str] = None,
        company: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        enrolled_by: Optional[str] = None,
        source: str = "upload",
        allow_duplicate: bool = False,
        person_id: Optional[str] = None,
    ):
        """
        Enrols one image, either creating a person or adding an angle to one.

        Raises EnrolmentError for anything the operator must fix. Nothing is
        written until every check has passed, so a rejected enrolment cannot
        leave a half-registered person behind.
        """
        metrics = self.validate_enrolment_image(image)
        embedding = metrics["embedding"]

        target = self.repo.get_person(person_id) if person_id else None
        if person_id and target is None:
            raise EnrolmentError("unknown_person", f"No enrolled person {person_id}.")

        if not allow_duplicate:
            clash, similarity = self.check_duplicate(
                embedding, exclude_person_id=target.person_id if target else None)
            if clash is not None:
                raise EnrolmentError(
                    "duplicate_face",
                    f"This face is already enrolled as {clash.name}"
                    + (f" ({clash.person_code})" if clash.person_code else "") + ".",
                    {
                        "person_id": clash.person_id,
                        "name": clash.name,
                        "person_code": clash.person_code,
                        "similarity": round(similarity, 4),
                    },
                )

        if target is None and person_code:
            existing = self.repo.get_person_by_code(person_code)
            if existing is not None:
                raise EnrolmentError(
                    "duplicate_code",
                    f"Code {person_code} is already used by {existing.name}.",
                    {"person_id": existing.person_id, "name": existing.name},
                )

        if person_type not in ("EMPLOYEE", "VENDOR", "CONTRACTOR"):
            raise EnrolmentError(
                "invalid_type", f"Unknown person type '{person_type}'.")

        snapshot = save_event_snapshot(
            "faces", person_code or (target.person_id if target else "enrol"),
            metrics["crop"], prune=False,
        )

        if target is None:
            target = self.repo.create_person(
                name=name.strip(),
                person_code=(person_code or None),
                person_type=person_type,
                department=department,
                designation=designation,
                company=company,
                email=email,
                phone=phone,
                photo=snapshot,
                is_active=True,
            )
        elif snapshot and not target.photo:
            target.photo = snapshot

        self.repo.add_enrolment(
            target.person_id,
            embedding,
            snapshot_path=snapshot,
            det_score=metrics["det_score"],
            face_width=metrics["width"],
            face_height=metrics["height"],
            sharpness=metrics["sharpness"],
            source=source,
            enrolled_by=enrolled_by,
        )
        person = self.repo.recompute_centroid(target.person_id)
        self.repo.log_event(
            "FACE_ENROLLED",
            person_id=target.person_id,
            similarity=None,
            snapshot_path=snapshot,
            metadata={"source": source, "by": enrolled_by,
                      "det_score": metrics["det_score"]},
        )
        return person

    # ----------------------------------------------------------------- #
    # Recognition
    # ----------------------------------------------------------------- #
    def identify(self, embedding) -> Tuple[Optional[Any], float]:
        """Nearest enrolled person above the attendance threshold."""
        return self.repo.match(embedding, self.tuning.match_threshold)

    def usable_face(self, face: Dict[str, Any], image: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Runtime quality gate — the same bar as enrolment minus the sharpness
        rule, because a live frame is never as sharp as a posed photo and
        holding it to that standard recognises nobody.
        """
        m = _face_metrics(face, image)
        if min(m["width"], m["height"]) < self.tuning.min_face_px:
            return None
        if m["det_score"] < self.tuning.min_det_score:
            return None
        return m
