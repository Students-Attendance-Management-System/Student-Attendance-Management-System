import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render

from .report_forms import ReportFilterForm
from .report_services import get_attendance_report


def _safe(value):
    """Stop spreadsheet apps from running cells that start with a formula character."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@login_required
def report_form(request):
    return render(request, "reports/report_form.html", {
        "form": ReportFilterForm(request.user),
    })


@login_required
def export_report(request):
    form = ReportFilterForm(request.user, request.GET)

    if not form.is_valid():
        if "section" in form.errors:
            raise PermissionDenied  # not allowed, or doesn't exist
        return HttpResponseBadRequest("; ".join(
            e for errs in form.errors.values() for e in errs
        ))

    section = form.cleaned_data["section"]
    start = form.cleaned_data["start_date"]
    end = form.cleaned_data["end_date"]
    rows = get_attendance_report(section, start, end)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="attendance_{section.pk}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        "Username", "Name", "Section", "From", "To",
        "Present", "Late", "Absent", "Total", "Percentage",
    ])
    for r in rows:
        s = r["student"]
        writer.writerow([
            _safe(s.username),
            _safe(s.get_full_name()),
            _safe(section),
            start or "", end or "",
            r["present"], r["late"], r["absent"], r["total"],
            r["percentage"] if r["percentage"] is not None else "N/A",
        ])
    return response