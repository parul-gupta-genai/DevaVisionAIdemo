"""
Vendor colour-kit catalogue for PPE identification.

A "colour kit" is what actually distinguishes one agency's workers from
another's on site: Acme issue a yellow helmet with an orange vest, Beta issue
a blue helmet with a blue vest. Recognising that requires three things the
previous implementation did not have —

  * colours defined per site rather than compiled in, because a "yellow" vest
    under sodium lighting at dusk is not the same set of HSV values as the
    same vest at noon,
  * colours checked per body region, because helmet-and-vest is the pairing
    that identifies a vendor, and sampling the whole person cannot tell
    "yellow helmet, blue vest" from "blue helmet, yellow vest",
  * more than one hue range per colour, because red straddles the wrap-around
    at hue 179/0 and cannot be expressed as a single range at all.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.persistence import Base

# Where on a person's bounding box each item is looked for, as fractions of
# the box height. Deliberately generous: DeepStream's person boxes are loose,
# and a band that is too tight misses the helmet on a person leaning forward.
BODY_REGIONS = {
    "HEAD": (0.00, 0.25),
    "TORSO": (0.22, 0.62),
    "LEGS": (0.55, 1.00),
    "FULL": (0.00, 1.00),
}

ITEM_TYPES = ("HELMET", "VEST", "JACKET", "TROUSERS", "GLOVES", "BOOTS", "OTHER")

VIOLATION_TYPES = (
    "NO_PPE",            # no recognised kit at all
    "WRONG_KIT",         # a kit was recognised, but not one expected here
    "UNKNOWN_VENDOR",    # colours matched nothing in the catalogue
    "INCOMPLETE_KIT",    # vendor identified, a required item missing
)


class PPEColour(Base):
    """
    A named colour as this site's cameras actually see it.

    `hsv_ranges` is a list of [[h_lo,s_lo,v_lo],[h_hi,s_hi,v_hi]] pairs. A list
    rather than one range so red can be expressed as two bands either side of
    the hue wrap; every other colour normally needs only one.
    """

    __tablename__ = "ppe_colours"

    colour_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    # For swatches in the UI; has no part in matching.
    display_hex = Column(String, nullable=True)
    hsv_ranges = Column(JSON, nullable=False)
    # Which camera the ranges were calibrated on, and when — the honest answer
    # to "why does this colour not match on camera 7".
    calibrated_on_camera = Column(String, nullable=True)
    calibrated_at = Column(DateTime, nullable=True)
    calibration_samples = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PPEVendor(Base):
    """A vendor or agency whose people are identified by their kit."""

    __tablename__ = "ppe_vendors"

    vendor_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    code = Column(String, nullable=True, index=True)
    contact = Column(String, nullable=True)
    # Drawn on the overlay for this vendor's people. Not used for matching.
    display_hex = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    kit_items = relationship("PPEKitItem", back_populates="vendor",
                             cascade="all, delete-orphan", passive_deletes=True)


class PPEKitItem(Base):
    """One garment in a vendor's kit: a colour expected in a body region."""

    __tablename__ = "ppe_kit_items"

    item_id = Column(String, primary_key=True, index=True)
    vendor_id = Column(String, ForeignKey("ppe_vendors.vendor_id", ondelete="CASCADE"),
                       nullable=False, index=True)
    colour_id = Column(String, ForeignKey("ppe_colours.colour_id", ondelete="RESTRICT"),
                       nullable=False, index=True)
    item_type = Column(String, nullable=False, default="VEST")
    body_region = Column(String, nullable=False, default="TORSO")

    # A required item missing makes the kit incomplete; an optional one only
    # adds confidence. Helmets are typically required, gloves typically not.
    is_required = Column(Boolean, nullable=False, default=True)
    # Fraction of the region's pixels that must carry the colour. Kept per
    # item because a helmet fills far less of its band than a vest does.
    min_coverage = Column(Float, nullable=False, default=0.12)

    created_at = Column(DateTime, server_default=func.now())

    vendor = relationship("PPEVendor", back_populates="kit_items")
    colour = relationship("PPEColour")

    __table_args__ = (
        UniqueConstraint("vendor_id", "item_type", "body_region",
                         name="uq_kit_vendor_item_region"),
    )


class PPECameraConfig(Base):
    """
    Per-camera enforcement.

    A vendor's people being on the wrong camera is the violation the client
    cares about — a cleaning contractor in the switchyard — so which vendors
    are expected is a property of the camera, not a global setting.
    """

    __tablename__ = "ppe_camera_config"

    config_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=False, unique=True, index=True)
    # Vendor ids expected here. Empty/NULL means any catalogued vendor.
    expected_vendor_ids = Column(JSON, nullable=True)

    enforce = Column(Boolean, nullable=False, default=True)
    # Which of VIOLATION_TYPES raise an alert on this camera.
    alert_on = Column(JSON, nullable=True)
    severity = Column(String, nullable=False, default="warning")
    # Seconds between repeat alerts for the same person on this camera.
    alert_cooldown_sec = Column(Float, nullable=False, default=30.0)
    # Ignore people smaller than this (far from the camera, too few pixels to
    # judge colour on). In pixels of box height.
    min_person_px = Column(Integer, nullable=False, default=80)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PPEViolation(Base):
    """A recorded PPE violation, with the evidence that produced it."""

    __tablename__ = "ppe_violations"

    violation_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=True, index=True)
    camera_name = Column(String, nullable=True)
    violation_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    # Vendor the person was identified as, when one could be identified.
    vendor_id = Column(String, ForeignKey("ppe_vendors.vendor_id", ondelete="SET NULL"),
                       nullable=True, index=True)
    vendor_name = Column(String, nullable=True)
    track_id = Column(String, nullable=True)
    snapshot_path = Column(String, nullable=True)
    # The measured coverage per region, kept so a disputed violation can be
    # examined rather than argued about.
    evidence = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    vendor = relationship("PPEVendor")
