
from django.contrib import messages
from django.shortcuts import redirect, render

from .account_views import admin_only
from .models import TeacherAssignment
from .teacher_assignment_forms import TeacherAssignmentForm


@admin_only
def teacher_assignment_list(request):
    assignments = TeacherAssignment.objects.select_related(
        "teacher",
        "section",
        "section__course",
    ).all()

    return render(
        request,
        "teacher_assignment/assignment_list.html",
        {"assignments": assignments},
    )


@admin_only
def teacher_assignment_create(request):
    if request.method == "POST":
        form = TeacherAssignmentForm(request.POST)

        if form.is_valid():
            assignment = form.save()
            messages.success(
                request,
                f"Teacher '{assignment.teacher.username}' was assigned "
                f"to {assignment.section}.",
            )
            return redirect("teacher_assignment_list")
    else:
        form = TeacherAssignmentForm()

    return render(
        request,
        "teacher_assignment/assignment_form.html",
        {
            "form": form,
            "title": "Assign teacher to section",
        },
    )


@admin_only
def teacher_assignment_delete(request, pk):
    if request.method == "POST":
        assignment = TeacherAssignment.objects.filter(pk=pk).first()

        if assignment is not None:
            teacher_username = assignment.teacher.username
            section_name = str(assignment.section)
            assignment.delete()
            messages.success(
                request,
                f"Assignment for '{teacher_username}' to "
                f"{section_name} was removed.",
            )

    return redirect("teacher_assignment_list")
