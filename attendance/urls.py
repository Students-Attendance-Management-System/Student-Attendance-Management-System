from django.urls import path
from . import alert_views, attendance_views, correction_views, report_views, views

app_name = "attendance"

urlpatterns = [
    path(
        "alerts/",
        alert_views.alert_list,
        name="alert_list"
    ),
    path(
        "sessions/<int:session_id>/mark/",
        attendance_views.mark_attendance,
        name="mark_attendance",
    ),
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
    path("reports/", report_views.report_form, name="report_form"),
    path("reports/export/", report_views.export_report, name="export_report"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/admin/", views.admin_dashboard, name="admin_dashboard"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
]