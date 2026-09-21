"""
Scopes for fight/quarrel analytics.

Split three ways for a specific reason. Tuning a zone decides what the site is
told about; acknowledging is a shift action; and VERIFYING — recording whether
an indication was a real fight or nothing — is a separate judgement that
belongs to whoever reviewed the footage. Keeping verification apart from
configuration means the person who decides "that was horseplay" cannot also
quietly lower the threshold that raised it.
"""

from loguru import logger

FIGHT_READ = "fight:read"
FIGHT_CONFIG = "fight:config"
FIGHT_ACK = "fight:ack"
FIGHT_VERIFY = "fight:verify"

ALL = {
    FIGHT_READ: "View fight/quarrel zones and incidents",
    FIGHT_CONFIG: "Define fight/quarrel detection zones and thresholds",
    FIGHT_ACK: "Acknowledge fight/quarrel alerts",
    FIGHT_VERIFY: "Record whether an indication was a real fight",
}

ROLE_GRANTS = {
    "admin": [FIGHT_READ, FIGHT_CONFIG, FIGHT_ACK, FIGHT_VERIFY],
    "security": [FIGHT_READ, FIGHT_CONFIG, FIGHT_ACK, FIGHT_VERIFY],
    "operator": [FIGHT_READ, FIGHT_ACK],
    "hr": [FIGHT_READ, FIGHT_VERIFY],
    "viewer": [FIGHT_READ],
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
            logger.info(f"Fight permissions seeded (new: {created or 'none'}, "
                        f"granted: {granted or 'none'})")
    except Exception as exc:
        session.rollback()
        logger.warning(f"Could not seed fight permissions: {exc}")
    return {"created": created, "granted": granted}
