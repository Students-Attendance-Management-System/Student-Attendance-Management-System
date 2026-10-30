from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .account_views import admin_only
from .enrollment_forms import EnrollmentForm
from .models import Enrollment, Section
from .permissions import ROLE_TEACHER, get_role_name, is_sams_admin


def can_view_rosters(user):
    """SAMS admins and active Teachers may view rosters."""
    if is_sams_admin(user):
        return True

    return user.is_active and get_role_name(user) == ROLE_TEACHER


def roster_viewer(view_func):
    """Login required; only admins and Teachers get in (others get 403)."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_view_rosters(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


@roster_viewer
def section_list(request):
    sections = (
        Section.objects.select_related("course")
        .annotate(student_count=Count("enrollments"))
        .order_by("course__code", "academic_year", "name")
    )

    return render(
        request,
        "enrollment/section_list.html",
        {
            "sections": sections,
            "can_manage": is_sams_admin(request.user),
        },
    )


@roster_viewer
def section_roster(request, pk):
    section = get_object_or_404(
        Section.objects.select_related("course"), pk=pk
    )
    enrollments = section.enrollments.select_related("student").order_by(
        "student__username"
    )

    return render(
        request,
        "enrollment/section_roster.html",
        {
            "section": section,
            "enrollments": enrollments,
            "can_manage": is_sams_admin(request.user),
        },
    )


@admin_only
def enroll_student(request):
    if request.method == "POST":
        form = EnrollmentForm(request.POST)

        if form.is_valid():
            try:
                enrollment = form.save()
            except ValidationError as error:
                form.add_error(None, error)
            except IntegrityError:
                form.add_error(
                    None, "This student is already enrolled in this section."
                )
            else:
                messages.success(
                    request,
                    f"{enrollment.student.username} was enrolled in "
                    f"{enrollment.section}.",
                )
                return redirect(
                    "enrollment_section_roster", pk=enrollment.section_id
                )
    else:
        initial = {}
        section_id = request.GET.get("section")
        if section_id and section_id.isdigit():
            initial["section"] = int(section_id)
        form = EnrollmentForm(initial=initial)

    return render(request, "enrollment/enroll_form.html", {"form": form})


@admin_only
@require_POST
def unenroll_student(request, pk):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "section__course"),
        pk=pk,
    )
    section_id = enrollment.section_id
    username = enrollment.student.username
    enrollment.delete()

    messages.success(request, f"{username} was removed from the roster.")
    return redirect("enrollment_section_roster", pk=section_id)