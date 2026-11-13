from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from .alert_services import refresh_section_alerts

from .correction_forms import CorrectionForm
from .correction_services import (
    apply_correction,
    can_correct,
    correction_deadline,
    is_correction_window_open,
)
from .models import AttendanceRecord


@login_required
def correct_record(request, record_id):
    record = get_object_or_404(
        AttendanceRecord.objects.select_related(
            "session", "session__section", "session__section__course", "student"
        ),
        pk=record_id,
    )

    if not can_correct(request.user, record):
        raise PermissionDenied

    form = CorrectionForm(
        request.POST or None, initial={"new_status": record.status}
    )

    if request.method == "POST" and form.is_valid():
        try:
            apply_correction(
                record,
                form.cleaned_data["new_status"],
                request.user,
                form.cleaned_data["reason"],
            )
            refresh_section_alerts(record.session.section)
            
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Attendance corrected.")
            return redirect("attendance:correct_record", record_id=record.pk)

    return render(
        request,
        "corrections/correct_record.html",
        {
            "record": record,
            "form": form,
            "window_open": is_correction_window_open(record.session),
            "deadline": correction_deadline(record.session),
            "corrections": record.corrections.select_related("corrected_by"),
        },
    )


from .models import AttendanceSession, TeacherAssignment
from .permissions import is_sams_admin


@login_required
def session_records(request, session_id):
    session = get_object_or_404(
        AttendanceSession.objects.select_related("section", "section__course"),
        pk=session_id,
    )

    allowed = is_sams_admin(request.user) or TeacherAssignment.objects.filter(
        teacher=request.user, section=session.section
    ).exists()
    if not allowed:
        raise PermissionDenied

    return render(
        request,
        "corrections/session_records.html",
        {
            "session": session,
            "records": session.records.select_related("student").order_by(
                "student__username"
            ),
            "window_open": is_correction_window_open(session),
            "deadline": correction_deadline(session),
        },
    )
