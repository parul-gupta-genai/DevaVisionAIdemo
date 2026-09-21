"""
Scopes for fire and smoke monitoring.

Tuning a fire zone decides what the site will and will not be told about, so
it is kept apart from reading the log. Acknowledging is split out again
because closing a fire alert is a shift action: the operator who checked the
boiler house and found a steam plume should be able to clear the alert
without also being able to lower the sensitivity that raised it.
"""

from loguru import logger

FIRE_READ = "fire:read"
FIRE_CONFIG = "fire:config"
FIRE_ACK = "fire:ack"

ALL = {
    FIRE_READ: "View fire and smoke zones and events",
    FIRE_CONFIG: "Define fire and smoke detection zones and sensitivity",
    FIRE_ACK: "Acknowledge fire and smoke alerts",
}

ROLE_GRANTS = {
    "admin": [FIRE_READ, FIRE_CONFIG, FIRE_ACK],
    "security": [FIRE_READ, FIRE_CONFIG, FIRE_ACK],
    "operator": [FIRE_READ, FIRE_ACK],
    "hr": [FIRE_READ],
    "viewer": [FIRE_READ],
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
                f"Fire permissions seeded (new: {created or 'none'}, "
                f"granted: {granted or 'none'})"
            )
    except Exception as exc:
        session.rollback()
        logger.warning(f"Could not seed fire permissions: {exc}")
    return {"created": created, "granted": granted}
