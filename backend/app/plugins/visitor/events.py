from enum import Enum

class VisitorEventType(str, Enum):
    VISITOR_REGISTERED = "VISITOR_REGISTERED"
    EMPLOYEE_REGISTERED = "EMPLOYEE_REGISTERED"
    VISITOR_SYNCED = "VISITOR_SYNCED"
    VISITOR_RECOGNIZED = "VISITOR_RECOGNIZED"
    EMPLOYEE_RECOGNIZED = "EMPLOYEE_RECOGNIZED"
    VISITOR_ENTERED = "VISITOR_ENTERED"
    VISITOR_EXITED = "VISITOR_EXITED"
    VISIT_STARTED = "VISIT_STARTED"
    VISIT_COMPLETED = "VISIT_COMPLETED"
    LOW_CONFIDENCE_MATCH = "LOW_CONFIDENCE_MATCH"
    UNKNOWN_PERSON = "UNKNOWN_PERSON"
    # A visitor already on file, coming back after a real gap. Distinct from
    # VISITOR_RECOGNIZED, which said nothing about whether it was their first
    # appearance or their twentieth.
    RETURNING_VISITOR = "RETURNING_VISITOR"
    # Somebody nobody enrolled, seen before. The fourth appearance of an
    # unregistered person is worth knowing about; calling it UNKNOWN_PERSON
    # again throws that away.
    REPEAT_UNKNOWN_PERSON = "REPEAT_UNKNOWN_PERSON"
    # An arrival the Visitor Management System told us to expect.
    VISITOR_ARRIVED = "VISITOR_ARRIVED"
    PHOTO_UPDATED = "PHOTO_UPDATED"
