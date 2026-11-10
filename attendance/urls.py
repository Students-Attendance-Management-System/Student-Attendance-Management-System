
from django.urls import path

from . import correction_views, views

app_name = "attendance"

urlpatterns = [
    path(
        "sessions/<int:session_id>/records/",
        correction_views.session_records,
        name="session_records",
    ),
    path(
        "records/<int:record_id>/correct/",
        correction_views.correct_record,
        name="correct_record",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path(
        "dashboard/admin/",
        views.admin_dashboard,
        name="admin_dashboard",
    ),
    path(
        "dashboard/teacher/",
        views.teacher_dashboard,
        name="teacher_dashboard",
    ),
    path(
        "dashboard/student/",
        views.student_dashboard,
        name="student_dashboard",
    ),
]
