from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    AttendanceRecord,
    AttendanceSession,
    Enrollment,
    TeacherAssignment,
)
from .permissions import (
    ROLE_STUDENT,
    ROLE_TEACHER,
    get_role_name,
    is_managed_account,
    is_sams_admin,
)


def get_markable_session(user, session_id):
    """Return a session only if the user is allowed to mark its attendance."""

    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("You are not allowed to mark attendance.")

    session = AttendanceSession.objects.select_related(
        "section",
        "teacher",
    ).filter(pk=session_id).first()

    if session is None:
        raise ValidationError("Attendance session does not exist.")

    if is_sams_admin(user):
        return session

    if (
        not is_managed_account(user)
        or get_role_name(user) != ROLE_TEACHER
    ):
        raise PermissionDenied("Only assigned teachers can mark attendance.")

    assigned = TeacherAssignment.objects.filter(
        teacher=user,
        section=session.section,
    ).exists()

    if not assigned:
        raise PermissionDenied(
            "You are not assigned to this section."
        )

    return session


def get_session_students(session):
    """Return active students enrolled in the session's section."""

    return (
        Enrollment.objects.filter(
            section=session.section,
            status=Enrollment.STATUS_ACTIVE,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("student__username")
    )


@transaction.atomic
def submit_attendance(user, session_id, attendance_data):
    """
    Save attendance for a session.

    attendance_data must be a dictionary:
        {student_id: "PRESENT" / "ABSENT" / "LATE"}

    Existing records are never overwritten. Repeated submissions are safe.
    """

    session = get_markable_session(user, session_id)

    if not isinstance(attendance_data, dict) or not attendance_data:
        raise ValidationError("No attendance data was submitted.")

    valid_statuses = {
        choice[0] for choice in AttendanceRecord.STATUS_CHOICES
    }

    normalized_data = {}

    for student_id, status in attendance_data.items():
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            raise ValidationError("Invalid student ID.")

        if status not in valid_statuses:
            raise ValidationError(
                f"Invalid attendance status for student {student_id}."
            )

        normalized_data[student_id] = status

    enrollments = get_session_students(session)
    eligible_student_ids = {
        enrollment.student_id for enrollment in enrollments
    }

    submitted_student_ids = set(normalized_data)

    if not submitted_student_ids.issubset(eligible_student_ids):
        raise ValidationError(
            "Attendance can only be submitted for active students "
            "enrolled in this section."
        )

    created_count = 0
    skipped_count = 0

    for student_id, status in normalized_data.items():
        record, created = AttendanceRecord.objects.get_or_create(
            session=session,
            student_id=student_id,
            defaults={"status": status},
        )

        if created:
            created_count += 1
        else:
            skipped_count += 1

    return {
        "created": created_count,
        "skipped": skipped_count,
    }