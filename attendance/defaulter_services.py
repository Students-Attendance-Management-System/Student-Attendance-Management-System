from decimal import Decimal

from .attendance_services import calculate_attendance_percentage
from .models import AttendanceThreshold, Enrollment, Section
from .permissions import ROLE_TEACHER, get_role_name, is_sams_admin


def sections_for_user(user):
    """Admins see all sections; teachers see assigned sections."""
    sections = Section.objects.select_related("course").order_by(
        "course__code", "academic_year", "name"
    )

    if is_sams_admin(user):
        return sections

    if (
        user.is_authenticated
        and user.is_active
        and get_role_name(user) == ROLE_TEACHER
    ):
        return sections.filter(
            teacher_assignments__teacher=user
        ).distinct()

    return sections.none()


def get_defaulter_report(section, threshold=None):
    """Calculate the current defaulter report using existing attendance logic."""
    if threshold is None:
        threshold = AttendanceThreshold.get_solo().value

    threshold = Decimal(str(threshold))

    enrollments = (
        Enrollment.objects.filter(
            section=section,
            status=Enrollment.STATUS_ACTIVE,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("student__username")
    )

    defaulters = []
    enrolled_count = 0
    no_records_count = 0

    for enrollment in enrollments:
        enrolled_count += 1

        result = calculate_attendance_percentage(
            enrollment.student, section
        )

        percentage = result["percentage"]

        if percentage is None:
            no_records_count += 1
            continue

        if Decimal(str(percentage)) < threshold:
            defaulters.append({
                "student": enrollment.student,
                **result,
            })

    defaulters.sort(
        key=lambda row: (
            row["percentage"],
            row["student"].username,
        )
    )

    return {
        "threshold": threshold,
        "defaulters": defaulters,
        "enrolled_count": enrolled_count,
        "no_records_count": no_records_count,
    }
