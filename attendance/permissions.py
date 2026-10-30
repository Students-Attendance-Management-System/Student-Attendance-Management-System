from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

# Role names are Django Group names. They deliberately match the literals used
# by the role-based-access-control work (Issue #2): "Admin", "Teacher", "Student".
ROLE_ADMIN = "Admin"
ROLE_TEACHER = "Teacher"
ROLE_STUDENT = "Student"

# Admin accounts are not created or edited through account management
# (SRS SAMS-F-003: the Admin manages Teacher and Student accounts).
MANAGED_ROLES = (ROLE_TEACHER, ROLE_STUDENT)


def _group_names(user):
    # .all() so a prefetch_related("groups") on the queryset is reused.
    return {group.name for group in user.groups.all()}


def is_sams_admin(user):
    """Active superuser, or active member of the "Admin" group."""
    if not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    return ROLE_ADMIN in _group_names(user)


def require_sams_admin(user):
    if not is_sams_admin(user):
        raise PermissionDenied


def get_role_name(user):
    """Return "Teacher" or "Student" for a managed account, otherwise None."""
    names = _group_names(user)

    for role in MANAGED_ROLES:
        if role in names:
            return role

    return None


def is_managed_account(user):
    """
    True only for Teacher/Student accounts that may be listed and edited.
    Superusers, anyone in the Admin group, and users with no role are excluded.
    """
    if user.is_superuser:
        return False

    names = _group_names(user)

    return ROLE_ADMIN not in names and bool(names & set(MANAGED_ROLES))


def managed_users():
    """Queryset form of is_managed_account(); the single source of truth."""
    return (
        User.objects.filter(
            is_superuser=False,
            groups__name__in=MANAGED_ROLES,
        )
        .exclude(groups__name=ROLE_ADMIN)
        .distinct()
        .prefetch_related("groups")
        .order_by("username")
    )