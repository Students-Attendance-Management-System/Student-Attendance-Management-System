from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Enrollment
from .permissions import require_sams_admin


def _require_active(enrollment):
    if enrollment.status != Enrollment.STATUS_ACTIVE:
        raise ValidationError("Only active enrollments can be changed.")


def _close(enrollment, status, actor, reason):
    enrollment.status = status
    enrollment.ended_at = timezone.now()
    enrollment.ended_by = actor
    enrollment.end_reason = (reason or "").strip()
    enrollment.save(
        update_fields=["status", "ended_at", "ended_by", "end_reason"]
    )


def remove_student(enrollment, actor, reason=""):
    """Mark an active enrollment as Removed. The row (and attendance) is kept."""
    require_sams_admin(actor)

    with transaction.atomic():
        current = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
        _require_active(current)
        _close(current, Enrollment.STATUS_REMOVED, actor, reason)

    return current


def transfer_student(enrollment, target_section, actor, reason=""):
    """
    Close the active enrollment as Transferred and open a new active one in
    the target section (same course only). All-or-nothing.
    """
    require_sams_admin(actor)

    with transaction.atomic():
        current = (
            Enrollment.objects.select_for_update()
            .select_related("section", "student")
            .get(pk=enrollment.pk)
        )
        _require_active(current)

        if target_section.pk == current.section_id:
            raise ValidationError("The student is already in this section.")

        if target_section.course_id != current.section.course_id:
            raise ValidationError(
                "Transfers are only allowed between sections of the same course."
            )

        if Enrollment.objects.filter(
            student_id=current.student_id,
            section=target_section,
            status=Enrollment.STATUS_ACTIVE,
        ).exists():
            raise ValidationError(
                "This student is already enrolled in the target section."
            )

        new = Enrollment(
            student=current.student,
            section=target_section,
            transferred_from=current,
        )
        _close(current, Enrollment.STATUS_TRANSFERRED, actor, reason)
        # Any failure here rolls back the whole transaction (old row too).
        new.full_clean()
        new.save()

    return new