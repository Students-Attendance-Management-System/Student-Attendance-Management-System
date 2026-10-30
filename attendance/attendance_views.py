from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .attendance_forms import AttendanceForm
from .enrollment_views import roster_viewer
from .models import Attendance, Section
from .permissions import ROLE_TEACHER, get_role_name


def can_mark_attendance(user, section=None):
    """
    Only active Teachers may mark attendance.

    `section` is accepted so a "teacher is assigned to this section" check can
    be added here later without touching the views.
    """
    return user.is_active and get_role_name(user) == ROLE_TEACHER


def teacher_only(view_func):
    """Login required; only Teachers get in (others get 403)."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_mark_attendance(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def _selected_date(request):
    value = request.GET.get("date")

    if value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass

    return timezone.localdate()


@roster_viewer
def attendance_section_list(request):
    sections = (
        Section.objects.select_related("course")
        .annotate(student_count=Count("enrollments"))
        .order_by("course__code", "academic_year", "name")
    )

    return render(
        request,
        "attendance/section_list.html",
        {
            "sections": sections,
            "can_mark": can_mark_attendance(request.user),
        },
    )


@teacher_only
def mark_attendance(request, pk):
    section = get_object_or_404(
        Section.objects.select_related("course"), pk=pk
    )
    enrollments = section.enrollments.select_related("student").order_by(
        "student__username"
    )
    selected_date = _selected_date(request)

    if request.method == "POST":
        form = AttendanceForm(request.POST, enrollments=enrollments)

        if form.is_valid():
            attendance_date = form.cleaned_data["date"]

            with transaction.atomic():
                for enrollment in form.enrollments:
                    Attendance.objects.update_or_create(
                        section=section,
                        student=enrollment.student,
                        date=attendance_date,
                        defaults={
                            "status": form.cleaned_data[
                                form.field_name(enrollment.student_id)
                            ],
                            "marked_by": request.user,
                        },
                    )

            messages.success(
                request,
                f"Attendance for {attendance_date} was saved.",
            )
            return redirect(
                f"{reverse('attendance_report', args=[section.pk])}"
                f"?date={attendance_date.isoformat()}"
            )
    else:
        existing = {
            record.student_id: record.status
            for record in Attendance.objects.filter(
                section=section, date=selected_date
            )
        }
        initial = {"date": selected_date}

        for enrollment in enrollments:
            initial[AttendanceForm.field_name(enrollment.student_id)] = (
                existing.get(enrollment.student_id, Attendance.PRESENT)
            )

        form = AttendanceForm(initial=initial, enrollments=enrollments)

    return render(
        request,
        "attendance/mark_form.html",
        {
            "section": section,
            "form": form,
            "selected_date": selected_date,
        },
    )


@roster_viewer
def attendance_report(request, pk):
    section = get_object_or_404(
        Section.objects.select_related("course"), pk=pk
    )
    selected_date = _selected_date(request)
    records = (
        Attendance.objects.filter(section=section, date=selected_date)
        .select_related("student", "marked_by")
        .order_by("student__username")
    )

    return render(
        request,
        "attendance/report.html",
        {
            "section": section,
            "selected_date": selected_date,
            "records": records,
            "can_mark": can_mark_attendance(request.user),
        },
    )