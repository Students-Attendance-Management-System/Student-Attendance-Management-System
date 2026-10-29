from django.urls import path

from . import enrollment_views

# Mounted under "enrollments/" in sams/urls.py.
urlpatterns = [
    path("", enrollment_views.section_list, name="enrollment_section_list"),
    path(
        "sections/<int:pk>/roster/",
        enrollment_views.section_roster,
        name="enrollment_section_roster",
    ),
    path("enroll/", enrollment_views.enroll_student, name="enroll_student"),
    path(
        "<int:pk>/remove/",
        enrollment_views.unenroll_student,
        name="unenroll_student",
    ),
    path(
        "<int:pk>/transfer/",
        enrollment_views.transfer_enrollment,
        name="transfer_enrollment",
    ),
    path(
        "students/<int:user_id>/history/",
        enrollment_views.student_history,
        name="enrollment_student_history",
    ),
]