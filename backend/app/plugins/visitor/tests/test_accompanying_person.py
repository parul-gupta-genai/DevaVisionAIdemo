import pytest
from app.plugins.visitor.accompanying_person_validator import AccompanyingPersonValidator


def test_visitor_alone_match():
    """Scenario 1: Registered 1 visitor (0 companions), 1 detected -> MATCH."""
    res = AccompanyingPersonValidator.validate_group(
        visitor_name="Rahul Sharma",
        expected_accompanying_persons=0,
        detected_person_count=1,
        tracking_ids=["P001"],
        camera_id="GATE-CAM-01"
    )
    assert res.validation_status == "MATCH"
    assert res.action_required is False
    assert res.registered_person_count == 1
    assert res.detected_person_count == 1
    assert res.additional_person_count == 0


def test_visitor_with_registered_companion_match():
    """Scenario 2: Registered 1 visitor + 1 companion, 2 detected -> MATCH."""
    res = AccompanyingPersonValidator.validate_group(
        visitor_name="Rahul Sharma",
        expected_accompanying_persons=1,
        detected_person_count=2,
        tracking_ids=["P001", "P002"],
        camera_id="GATE-CAM-01"
    )
    assert res.validation_status == "MATCH"
    assert res.action_required is False
    assert res.registered_person_count == 2
    assert res.detected_person_count == 2
    assert res.additional_person_count == 0


def test_unregistered_accompanying_person():
    """Scenario 3: Registered 1 visitor (0 companions), 2 detected -> UNREGISTERED_ACCOMPANYING_PERSON."""
    res = AccompanyingPersonValidator.validate_group(
        visitor_name="Rahul Sharma",
        expected_accompanying_persons=0,
        detected_person_count=2,
        tracking_ids=["P001", "P002"],
        camera_id="GATE-CAM-01"
    )
    assert res.validation_status == "UNREGISTERED_ACCOMPANYING_PERSON"
    assert res.action_required is True
    assert res.registered_person_count == 1
    assert res.detected_person_count == 2
    assert res.additional_person_count == 1


def test_extra_visitor_detected():
    """Scenario 4: Registered 1 visitor + 1 companion (2 total), 3 detected -> EXTRA_VISITOR_DETECTED."""
    res = AccompanyingPersonValidator.validate_group(
        visitor_name="Rahul Sharma",
        expected_accompanying_persons=1,
        detected_person_count=3,
        tracking_ids=["P001", "P002", "P003"],
        camera_id="GATE-CAM-01"
    )
    assert res.validation_status == "EXTRA_VISITOR_DETECTED"
    assert res.action_required is True
    assert res.registered_person_count == 2
    assert res.detected_person_count == 3
    assert res.additional_person_count == 1
