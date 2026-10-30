from django.urls import path

from . import attendance_views

# Mounted under "attendance/" in sams/urls.py.
urlpatterns = [
    path(
        "",
        attendance_views.attendance_section_list,
        name="attendance_section_list",
    ),
    path(
        "sections/<int:pk>/mark/",
        attendance_views.mark_attendance,
        name="mark_attendance",
    ),
    path(
        "sections/<int:pk>/",
        attendance_views.attendance_report,
        name="attendance_report",
    ),
]
