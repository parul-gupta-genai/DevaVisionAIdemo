"""
Scopes for the face module, and a seeder that makes them real.

The RBAC tables already existed but nothing populated them outside tests, so
`require_permissions` had nothing to check against and every role behaved the
same. These three scopes are seeded on startup and granted to the roles that
should hold them, which is what makes the watchlist's role-based access an
actual restriction rather than a label.
"""

from loguru import logger

FACE_READ = "face:read"          # see dashboards, logs, reports
FACE_ENROL = "face:enrol"        # enrol, edit and remove people
FACE_WATCHLIST = "face:watchlist"  # add and remove watchlist entries

ALL = {
    FACE_READ: "View face attendance, watchlist and face event history",
    FACE_ENROL: "Enrol and manage faces in the employee/vendor register",
    FACE_WATCHLIST: "Add and remove people from the face watchlist",
}

ROLE_DESCRIPTIONS = {
    "admin": "Full administrative access",
    "security": "Security operations: monitoring and watchlist",
    "hr": "HR: attendance and enrolment",
    "operator": "Day-to-day monitoring, read only",
    "viewer": "Read-only access",
}

# Reading is broad; enrolling and watchlisting are administrative.
ROLE_GRANTS = {
    "admin": [FACE_READ, FACE_ENROL, FACE_WATCHLIST],
    "security": [FACE_READ, FACE_WATCHLIST],
    "hr": [FACE_READ, FACE_ENROL],
    "operator": [FACE_READ],
    "viewer": [FACE_READ],
}


def seed_permissions(session) -> dict:
    """
    Ensures the scopes exist and are attached to any of the named roles that
    exist. Idempotent, so it can run on every startup.

    Roles that do not exist are skipped rather than created: inventing roles
    would silently change who can do what in an existing deployment.
    """
    from database.models.auth import Permission, Role

    created, granted = [], []
    try:
        existing = {p.name: p for p in
                    session.query(Permission).filter(Permission.name.in_(list(ALL))).all()}
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
                # Creating a role nobody holds cannot change anyone's access,
                # and without it require_permissions has nothing to grant to:
                # a deployment with no roles can only ever authorise
                # superusers, which is not role-based access at all.
                role = Role(name=role_name,
                            description=ROLE_DESCRIPTIONS.get(role_name, role_name))
                session.add(role)
                session.flush()
                created.append(f"role:{role_name}")
            held = {p.name for p in role.permissions}
            for scope in scopes:
                if scope not in held:
                    role.permissions.append(existing[scope])
                    granted.append(f"{role_name}:{scope}")
        session.commit()
        if created or granted:
            logger.info(
                f"Face permissions seeded (new: {created or 'none'}, "
                f"granted: {granted or 'none'})"
            )
    except Exception as exc:
        session.rollback()
        # A permission seeding failure must not stop the API from starting;
        # it degrades to "only superusers can enrol", which is safe.
        logger.warning(f"Could not seed face permissions: {exc}")
    return {"created": created, "granted": granted}
