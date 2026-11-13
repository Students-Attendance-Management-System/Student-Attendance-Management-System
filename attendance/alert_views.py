
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .models import AttendanceAlert
from .permissions import (
    ROLE_STUDENT,
    ROLE_TEACHER,
    get_role_name,
    is_sams_admin,
)


@login_required
def alert_list(request):
    user = request.user

    if not user.is_active:
        raise PermissionDenied

    alerts = AttendanceAlert.objects.filter(
        is_active=True
    ).select_related(
        "student",
        "section",
        "section__course",
    )

    if is_sams_admin(user):
        pass

    elif get_role_name(user) == ROLE_TEACHER:
        alerts = alerts.filter(
            section__teacher_assignments__teacher=user
        ).distinct()

    elif get_role_name(user) == ROLE_STUDENT:
        alerts = alerts.filter(student=user)

    else:
        raise PermissionDenied

    return render(
    request,
    "alerts/alert_list.html",
    {
        "alerts": alerts,
        "is_student": get_role_name(user) == ROLE_STUDENT,
    },
)

