"""
Scopes for the ANPR plate lists.

Reading which vehicles are expected is an operational need; deciding which
vehicle is barred from site, or which one the barrier opens for, is not.
Before this the whole ANPR router sat behind "is logged in", so any account
could add its own plate to the whitelist.
"""

from loguru import logger

ANPR_READ = "anpr:read"
ANPR_WATCHLIST = "anpr:watchlist"   # add/edit/remove blacklist and whitelist
# Designating a gate and setting who may pass it is a site-access decision,
# not a list edit: it can deny a vehicle that is on no list at all.
ANPR_GATES = "anpr:gates"

ALL = {
    ANPR_READ: "View ANPR reads, events and plate lists",
    ANPR_WATCHLIST: "Manage the ANPR blacklist and whitelist",
    ANPR_GATES: "Configure ANPR gates and their access rules",
}

ROLE_GRANTS = {
    "admin": [ANPR_READ, ANPR_WATCHLIST, ANPR_GATES],
    "security": [ANPR_READ, ANPR_WATCHLIST, ANPR_GATES],
    "hr": [ANPR_READ],
    "operator": [ANPR_READ],
    "viewer": [ANPR_READ],
}


def seed_permissions(session) -> dict:
    """
    Ensures the ANPR scopes exist and are attached to the roles above.
    Idempotent; safe to run on every startup.
    """
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
                # Roles are created by the face module's seeder; if it has not
                # run, skip rather than duplicate that logic here.
                continue
            held = {p.name for p in role.permissions}
            for scope in scopes:
                if scope not in held:
                    role.permissions.append(existing[scope])
                    granted.append(f"{role_name}:{scope}")
        session.commit()
        if created or granted:
            logger.info(
                f"ANPR permissions seeded (new: {created or 'none'}, "
                f"granted: {granted or 'none'})"
            )
    except Exception as exc:
        session.rollback()
        logger.warning(f"Could not seed ANPR permissions: {exc}")
    return {"created": created, "granted": granted}
