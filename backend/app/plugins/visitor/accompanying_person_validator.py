import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from loguru import logger


class GroupValidationResult(BaseModel):
    validation_status: str = Field(
        ...,
        description="MATCH | UNREGISTERED_ACCOMPANYING_PERSON | EXTRA_VISITOR_DETECTED | UNKNOWN_PERSON"
    )
    visitor_name: Optional[str] = None
    visitor_id: Optional[str] = None
    visit_id: Optional[str] = None
    prereg_id: Optional[str] = None
    registered_person_count: int = 1
    detected_person_count: int = 1
    additional_person_count: int = 0
    tracking_ids: List[str] = Field(default_factory=list)
    camera_id: str = "CAM-01"
    timestamp: float = Field(default_factory=time.time)
    action_required: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class AccompanyingPersonValidator:
    """
    Validates detected group sizes at Gate / Entry ROIs against registered visitor expectations.
    
    Rule:
      Registered Person Count = 1 (Primary Visitor) + Expected Accompanying Persons
      Detected Person Count = Total vision-tracked persons entering in Gate ROI
      Additional Person Count = max(0, Detected Person Count - Registered Person Count)
      
    Status:
      - MATCH: Detected Person Count <= Registered Person Count
      - UNREGISTERED_ACCOMPANYING_PERSON: Primary visitor registered 0 companions, but 1+ extra entered
      - EXTRA_VISITOR_DETECTED: Primary visitor registered N companions, but N+k extra entered
    """

    @staticmethod
    def validate_group(
        visitor_name: str,
        expected_accompanying_persons: int,
        detected_person_count: int,
        tracking_ids: List[str],
        camera_id: str = "GATE-CAM-01",
        visitor_id: Optional[str] = None,
        visit_id: Optional[str] = None,
        prereg_id: Optional[str] = None
    ) -> GroupValidationResult:
        registered_count = 1 + max(0, expected_accompanying_persons)
        detected_count = max(1, detected_person_count)
        additional_count = max(0, detected_count - registered_count)

        if additional_count == 0:
            status = "MATCH"
            action_required = False
        elif expected_accompanying_persons == 0:
            status = "UNREGISTERED_ACCOMPANYING_PERSON"
            action_required = True
        else:
            status = "EXTRA_VISITOR_DETECTED"
            action_required = True

        logger.info(
            f"AccompanyingPersonValidator: [{status}] Visitor: {visitor_name} "
            f"(Registered: {registered_count}, Detected: {detected_count}, Additional: {additional_count})"
        )

        return GroupValidationResult(
            validation_status=status,
            visitor_name=visitor_name,
            visitor_id=visitor_id,
            visit_id=visit_id,
            prereg_id=prereg_id,
            registered_person_count=registered_count,
            detected_person_count=detected_count,
            additional_person_count=additional_count,
            tracking_ids=tracking_ids,
            camera_id=camera_id,
            timestamp=time.time(),
            action_required=action_required,
            details={
                "expected_accompanying_persons": expected_accompanying_persons,
                "message": (
                    f"Group match confirmed for {visitor_name}"
                    if status == "MATCH"
                    else f"Attention: {visitor_name} arrived with {additional_count} unregistered companion(s)"
                )
            }
        )
