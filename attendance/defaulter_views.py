from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .account_views import admin_only
from .defaulter_forms import ThresholdForm
from .defaulter_services import get_defaulter_report, sections_for_user
from .enrollment_views import roster_viewer
from .models import AttendanceThreshold, Section
from .permissions import is_sams_admin


@roster_viewer
def defaulter_section_list(request):
    return render(
        request,
        "defaulters/section_list.html",
        {
            "sections": sections_for_user(request.user),
            "threshold": AttendanceThreshold.get_solo().value,
            "can_manage": is_sams_admin(request.user),
        },
    )


@roster_viewer
def defaulter_list(request, pk):
    section = get_object_or_404(
        Section.objects.select_related("course"),
        pk=pk,
    )

    if not sections_for_user(request.user).filter(pk=section.pk).exists():
        raise PermissionDenied

    report = get_defaulter_report(section)

    return render(
        request,
        "defaulters/defaulter_list.html",
        {
            "section": section,
            "report": report,
            "can_manage": is_sams_admin(request.user),
        },
    )


@admin_only
def threshold_settings(request):
    if request.method == "POST":
        form = ThresholdForm(request.POST)

        if form.is_valid():
            threshold = form.save(request.user)
            messages.success(
                request,
                f"Threshold updated to {threshold.value}%.",
            )
            return redirect("defaulter_section_list")
    else:
        form = ThresholdForm(
            initial={"value": AttendanceThreshold.get_solo().value}
        )

    return render(
        request,
        "defaulters/threshold_form.html",
        {"form": form},
    )
