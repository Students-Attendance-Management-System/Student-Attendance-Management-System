from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .account_views import admin_only
from .enrollment_forms import EnrollmentForm, TransferForm
from .enrollment_services import remove_student, transfer_student
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
        .annotate(
            student_count=Count(
                "enrollments",
                filter=Q(enrollments__status=Enrollment.STATUS_ACTIVE),
            )
        )
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
    # Current roster = active enrollments only.
    enrollments = (
        section.enrollments.filter(status=Enrollment.STATUS_ACTIVE)
        .select_related("student")
        .order_by("student__username")
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


@roster_viewer
def student_history(request, user_id):
    student = get_object_or_404(User, pk=user_id)
    enrollments = (
        Enrollment.objects.filter(student=student)
        .select_related("section__course", "ended_by", "transferred_from__section")
        .order_by("-enrolled_at", "-pk")
    )

    return render(
        request,
        "enrollment/student_history.html",
        {"student_obj": student, "enrollments": enrollments},
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

    try:
        remove_student(
            enrollment, request.user, request.POST.get("reason", "")
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            f"{enrollment.student.username} was removed from the roster. "
            "Their history is kept.",
        )

    return redirect("enrollment_section_roster", pk=section_id)


@admin_only
def transfer_enrollment(request, pk):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "section__course"),
        pk=pk,
    )

    if enrollment.status != Enrollment.STATUS_ACTIVE:
        messages.error(request, "Only active enrollments can be transferred.")
        return redirect("enrollment_section_roster", pk=enrollment.section_id)

    if request.method == "POST":
        form = TransferForm(request.POST, enrollment=enrollment)

        if form.is_valid():
            try:
                new = transfer_student(
                    enrollment,
                    form.cleaned_data["section"],
                    request.user,
                    form.cleaned_data["reason"],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    f"{enrollment.student.username} was transferred to "
                    f"{new.section}.",
                )
                return redirect("enrollment_section_roster", pk=new.section_id)
    else:
        form = TransferForm(enrollment=enrollment)

    return render(
        request,
        "enrollment/transfer_form.html",
        {"form": form, "enrollment": enrollment},
    )