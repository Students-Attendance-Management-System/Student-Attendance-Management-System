
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from .leave_forms import LeaveRequestForm
from .models import LeaveRequest
from .permissions import ROLE_STUDENT, get_role_name


@login_required
def submit_leave_request(request):
    if get_role_name(request.user) != ROLE_STUDENT:
        raise PermissionDenied

    if request.method == "POST":
        form = LeaveRequestForm(
            request.POST,
            student=request.user,
        )

        if form.is_valid():
            leave_request = form.save(commit=False)

            # Never trust the student identity from submitted form data.
            leave_request.student = request.user
            leave_request.status = LeaveRequest.STATUS_PENDING
            leave_request.reviewed_by = None
            leave_request.reviewed_at = None

            leave_request.save()

            messages.success(
                request,
                "Your leave request has been submitted successfully.",
            )

            return redirect("attendance:my_leave_requests")

    else:
        form = LeaveRequestForm(student=request.user)

    return render(
        request,
        "leave/submit_leave_request.html",
        {"form": form},
    )


@login_required
def my_leave_requests(request):
    if get_role_name(request.user) != ROLE_STUDENT:
        raise PermissionDenied

    leave_requests = (
        LeaveRequest.objects.filter(student=request.user)
        .select_related("section__course", "reviewed_by")
        .order_by("-created_at")
    )

    return render(
        request,
        "leave/my_leave_requests.html",
        {"leave_requests": leave_requests},
    )
