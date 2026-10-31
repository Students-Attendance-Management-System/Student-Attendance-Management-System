
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from .models import TeacherAssignment



def has_role(user, role):
    if not user.is_authenticated or not user.is_active:
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
    assignments = (
        TeacherAssignment.objects.filter(teacher=request.user)
        .select_related("section", "section__course")
        .order_by("section__course__code", "section__name")
    )

    return render(
        request,
        "teacher_assignment/teacher_dashboard.html",
        {"assignments": assignments},
    )


@role_required("Student")
def student_dashboard(request):
    return HttpResponse("Student Dashboard")
