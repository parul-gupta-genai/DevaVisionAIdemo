"""
Scopes for restricted zones.

Drawing a zone and setting its schedule decides what the site treats as an
intrusion, so it is separated from reading the log. Acknowledging is split
out again because closing an alert is a shift-supervisor action, not a
configuration one — an operator should be able to clear an alert they
handled without also being able to move the zone that raised it.
"""

from loguru import logger

ZONES_READ = "zones:read"
ZONES_CONFIG = "zones:config"
ZONES_ACK = "zones:ack"

ALL = {
    ZONES_READ: "View restricted zones and zone events",
    ZONES_CONFIG: "Define restricted zones, rules and schedules",
    ZONES_ACK: "Acknowledge restricted-zone alerts",
}

ROLE_GRANTS = {
    "admin": [ZONES_READ, ZONES_CONFIG, ZONES_ACK],
    "security": [ZONES_READ, ZONES_CONFIG, ZONES_ACK],
    "operator": [ZONES_READ, ZONES_ACK],
    "hr": [ZONES_READ],
    "viewer": [ZONES_READ],
}


def seed_permissions(session) -> dict:
    """Idempotent; roles are created by the face module's seeder."""
    from database.models.auth import Permission, Role

    created, granted = [], []
    try:
        existing = {
            p.name: p for p in
            session.query(Permission).filter(Permission.name.in_(list(ALL))).all()
        }
        for name, description in ALL.items():
            if name not in existing:
                perm = Permission(name=name, description=description)
                session.add(perm)
                existing[name] = perm
                created.append(name)
        session.flush()

        for role_name, scopes in ROLE_GRANTS.items():
            role = session.query(Role).filter(Role.name == role_name).first()
            if role is None:
                continue
            held = {p.name for p in role.permissions}
            for scope in scopes:
                if scope not in held:
                    role.permissions.append(existing[scope])
                    granted.append(f"{role_name}:{scope}")
        session.commit()
        if created or granted:
            logger.info(
                f"Zone permissions seeded (new: {created or 'none'}, "
                f"granted: {granted or 'none'})"
            )
    except Exception as exc:
        session.rollback()
        logger.warning(f"Could not seed zone permissions: {exc}")
    return {"created": created, "granted": granted}
