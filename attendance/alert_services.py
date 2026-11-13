
from decimal import Decimal

from django.db import transaction

from .defaulter_services import get_defaulter_report
from .models import AttendanceAlert


@transaction.atomic
def refresh_section_alerts(section):
    """
    Refresh low-attendance alerts for all students in a section.

    Creates alerts for new defaulters, updates existing alerts,
    and deactivates alerts when students are no longer defaulters.
    """

    report = get_defaulter_report(section)
    threshold = Decimal(str(report["threshold"]))

    current_defaulters = {}

    for row in report["defaulters"]:
        student = row["student"]
        percentage = Decimal(str(row["percentage"]))

        current_defaulters[student.pk] = percentage

        alert, created = AttendanceAlert.objects.get_or_create(
            student=student,
            section=section,
            defaults={
                "attendance_percentage": percentage,
                "threshold": threshold,
                "is_active": True,
            },
        )

        if not created:
            alert.attendance_percentage = percentage
            alert.threshold = threshold
            alert.is_active = True
            alert.save(
                update_fields=[
                    "attendance_percentage",
                    "threshold",
                    "is_active",
                    "updated_at",
                ]
            )

    # Deactivate alerts for students who are no longer defaulters.
    existing_alerts = AttendanceAlert.objects.filter(
        section=section,
        is_active=True,
    )

    for alert in existing_alerts:
        if alert.student_id not in current_defaulters:
            alert.is_active = False
            alert.threshold = threshold
            alert.save(
                update_fields=["is_active", "threshold", "updated_at"]
            )

    return len(current_defaulters)
