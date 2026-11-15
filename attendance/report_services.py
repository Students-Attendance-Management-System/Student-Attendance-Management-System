from django.core.exceptions import PermissionDenied

from .attendance_services import calculate_attendance_percentage
from .defaulter_services import sections_for_user
from .models import Enrollment


def get_report_section(user, section_id):
    """Return the section only if this user may report on it."""
    section = sections_for_user(user).filter(pk=section_id).first()
    if section is None:
        raise PermissionDenied("You cannot export reports for this section.")
    return section


def get_attendance_report(section, start_date=None, end_date=None):
    enrollments = (
        Enrollment.objects.filter(
            section=section,
            status=Enrollment.STATUS_ACTIVE,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("student__username")
    )

    rows = []
    for enrollment in enrollments:
        result = calculate_attendance_percentage(
            enrollment.student, section, start_date, end_date
        )
        rows.append({"student": enrollment.student, **result})
    return rows