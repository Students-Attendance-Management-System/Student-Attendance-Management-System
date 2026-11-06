
from .models import AttendanceRecord, Enrollment
from django.utils import timezone


def calculate_attendance_percentage(student, section):
    """
    Calculate a student's attendance percentage in a section.

    Only valid attendance records from sessions within the
    student's enrollment periods are included.

    PRESENT and LATE count as attended.
    ABSENT counts as not attended.
    Missing and invalid records are excluded.
    """

    enrollments = Enrollment.objects.filter(
        student=student,
        section=section,
    ).order_by("enrolled_at")

    records = AttendanceRecord.objects.filter(
        student=student,
        session__section=section,
        status__in=["PRESENT", "ABSENT", "LATE"],
    ).select_related("session")

    counts = {
        "present": 0,
        "absent": 0,
        "late": 0,
    }

    for record in records:
        session_date = record.session.date

        # Count this record only if its session falls within
        # at least one of the student's enrollment periods.
        applicable = False

        for enrollment in enrollments:
            start_date = timezone.localtime(enrollment.enrolled_at).date()
            end_date = (
                timezone.localtime(enrollment.ended_at).date()
                if enrollment.ended_at
                else None
            )

            if session_date < start_date:
                continue

            if end_date is not None and session_date > end_date:
                continue

            applicable = True
            break

        if applicable:
            counts[record.status.lower()] += 1

    total = sum(counts.values())
    attended = counts["present"] + counts["late"]

    percentage = (
        round((attended / total) * 100, 2)
        if total > 0
        else None
    )

    return {
        **counts,
        "total": total,
        "attended": attended,
        "percentage": percentage,
    }
