from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AttendanceCorrection, AttendanceRecord, TeacherAssignment
from .permissions import ROLE_TEACHER, get_role_name, is_sams_admin


def correction_deadline(session):
    """The window starts when the session's date ends (midnight, next day)
    and stays open for ATTENDANCE_CORRECTION_WINDOW_HOURS."""
    day_end = timezone.make_aware(
        datetime.combine(session.date + timedelta(days=1), time.min)
    )
    return day_end + timedelta(hours=settings.ATTENDANCE_CORRECTION_WINDOW_HOURS)


def is_correction_window_open(session, now=None):
    now = now or timezone.now()
    return now <= correction_deadline(session)


def can_correct(user, record):
    """Admins, or the Teacher assigned to the record's section."""
    if is_sams_admin(user):
        return True

    if not user.is_authenticated or not user.is_active:
        return False

    if get_role_name(user) != ROLE_TEACHER:
        return False

    return TeacherAssignment.objects.filter(
        teacher=user, section=record.session.section
    ).exists()


@transaction.atomic
def apply_correction(record, new_status, user, reason, now=None):
    """Change a saved status and log it. Raises PermissionDenied if the user
    is not allowed, ValidationError if the window is closed or input is bad."""
    if not can_correct(user, record):
        raise PermissionDenied

    if not is_correction_window_open(record.session, now):
        raise ValidationError(
            "The correction window for this session has closed."
        )

    valid = {value for value, _ in AttendanceRecord.STATUS_CHOICES}
    if new_status not in valid:
        raise ValidationError("Invalid attendance status.")

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required for a correction.")

    if new_status == record.status:
        raise ValidationError("The new status is the same as the current one.")

    correction = AttendanceCorrection.objects.create(
        record=record,
        old_status=record.status,
        new_status=new_status,
        corrected_by=user,
        reason=reason,
    )
    record.status = new_status
    record.save(update_fields=["status", "marked_at"])
    return correction
