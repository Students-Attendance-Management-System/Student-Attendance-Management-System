
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import LeaveRequest, TeacherAssignment
from .permissions import (
    ROLE_TEACHER,
    get_role_name,
    is_sams_admin,
)


def reviewable_requests(user):
    """Return requests that the current staff member may review."""

    if is_sams_admin(user):
        return LeaveRequest.objects.all()

    if get_role_name(user) == ROLE_TEACHER:
        assigned_sections = TeacherAssignment.objects.filter(
            teacher=user
        ).values_list("section_id", flat=True)

        return LeaveRequest.objects.filter(
            section_id__in=assigned_sections
        )

    raise PermissionDenied


@login_required
def staff_leave_requests(request):
    leave_requests = (
        reviewable_requests(request.user)
        .select_related(
            "student",
            "section__course",
            "reviewed_by",
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "leave/staff_leave_requests.html",
        {"leave_requests": leave_requests},
    )


@login_required
@require_POST
def review_leave_request(request, pk):
    action = request.POST.get("action")

    if action not in (
        LeaveRequest.STATUS_APPROVED,
        LeaveRequest.STATUS_REJECTED,
    ):
        messages.error(request, "Invalid review decision.")
        return redirect("attendance:staff_leave_requests")

    with transaction.atomic():
        leave_request = get_object_or_404(
            reviewable_requests(request.user).select_for_update(),
            pk=pk,
        )

        if leave_request.status != LeaveRequest.STATUS_PENDING:
            messages.error(
                request,
                "This leave request has already been reviewed.",
            )
            return redirect("attendance:staff_leave_requests")

        leave_request.status = action
        leave_request.reviewed_by = request.user
        leave_request.reviewed_at = timezone.now()

        leave_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
            ]
        )

    messages.success(
        request,
        f"Leave request has been {action.lower()}.",
    )

    return redirect("attendance:staff_leave_requests")
