
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect


def has_role(user, role):
    """Check whether a user belongs to a particular role group."""
    if not user.is_authenticated:
        return False

    if role == "Admin" and user.is_superuser:
        return True

    return user.groups.filter(name=role).exists()


def role_required(role):
    """Allow only users assigned to the required role."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not has_role(request.user, role):
                messages.error(
                    request,
                    "You are not authorized to access that page."
                )
                return redirect("attendance:dashboard")

            return view_func(request, *args, **kwargs)

        return login_required(wrapped_view)

    return decorator


@login_required
def dashboard(request):
    """Redirect users to the dashboard for their assigned role."""
    if has_role(request.user, "Admin"):
        return redirect("attendance:admin_dashboard")

    if has_role(request.user, "Teacher"):
        return redirect("attendance:teacher_dashboard")

    if has_role(request.user, "Student"):
        return redirect("attendance:student_dashboard")

    return HttpResponseForbidden(
        "No role has been assigned to your account."
    )


@role_required("Admin")
def admin_dashboard(request):
    return HttpResponse("Admin Dashboard")


@role_required("Teacher")
def teacher_dashboard(request):
    return HttpResponse("Teacher Dashboard")


@role_required("Student")
def student_dashboard(request):
    return HttpResponse("Student Dashboard")
