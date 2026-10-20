"""Placeholder sign-in (CONTRACTS §13): the configured PILOT_USER with PILOT_USER_ROLES.

Every route gets the user through `get_current_user`, so real sign-in can replace this one
dependency. Run routes need the `user` or `admin` role; admin routes need `admin`.
"""

from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel

from app.api.dependencies import Resources
from app.api.errors import ApiError
from app.settings import Settings

USER_ROLE = "user"
ADMIN_ROLE = "admin"


class SignedInUser(BaseModel):
    """The signed-in user: a name (stored with changes, exports and admin actions) and roles."""

    name: str
    roles: list[str]

    def has_role(self, role: str) -> bool:
        """Return True if the user has this role."""
        return role in self.roles


def read_signed_in_user(settings: Settings) -> SignedInUser:
    """Return the configured user; a blank PILOT_USER or PILOT_USER_ROLES names the setting."""
    return SignedInUser(
        name=settings.require_text("PILOT_USER").strip(), roles=settings.require_roles()
    )


def get_current_user(resources: Resources) -> SignedInUser:
    """Return the signed-in user; refuse a user with neither the user nor the admin role."""
    user = read_signed_in_user(resources.settings)
    if not (user.has_role(USER_ROLE) or user.has_role(ADMIN_ROLE)):
        raise ApiError(
            "FORBIDDEN",
            f"The signed-in user has none of the roles {USER_ROLE} or {ADMIN_ROLE}. "
            "Ask the administrator to add a role to PILOT_USER_ROLES.",
        )
    return user


def require_admin(user: Annotated[SignedInUser, Depends(get_current_user)]) -> SignedInUser:
    """Return the signed-in user if they have the admin role; refuse with 403 otherwise."""
    if not user.has_role(ADMIN_ROLE):
        raise ApiError(
            "FORBIDDEN",
            "This needs the admin role. Ask an administrator to do it, or to add the admin "
            "role to PILOT_USER_ROLES.",
        )
    return user


# Route parameter types: the signed-in user, and the signed-in admin
CurrentUser = Annotated[SignedInUser, Depends(get_current_user)]
CurrentAdmin = Annotated[SignedInUser, Depends(require_admin)]
