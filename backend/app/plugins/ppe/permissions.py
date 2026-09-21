"""
Scopes for the PPE vendor catalogue.

Reading which vendor a person belongs to is operational; defining what counts
as a vendor's kit decides who gets flagged for a violation, so it is not.
"""

from loguru import logger

PPE_READ = "ppe:read"
PPE_CONFIG = "ppe:config"      # colours, vendors, kits, camera assignment

ALL = {
    PPE_READ: "View PPE vendor identification and violations",
    PPE_CONFIG: "Configure PPE colours, vendor kits and camera enforcement",
}

ROLE_GRANTS = {
    "admin": [PPE_READ, PPE_CONFIG],
    "security": [PPE_READ, PPE_CONFIG],
    "hr": [PPE_READ],
    "operator": [PPE_READ],
    "viewer": [PPE_READ],
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
                f"PPE permissions seeded (new: {created or 'none'}, "
                f"granted: {granted or 'none'})"
            )
    except Exception as exc:
        session.rollback()
        logger.warning(f"Could not seed PPE permissions: {exc}")
    return {"created": created, "granted": granted}
