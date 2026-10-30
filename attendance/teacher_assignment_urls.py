
from django.urls import path

from . import teacher_assignment_views

urlpatterns = [
    path(
        "",
        teacher_assignment_views.teacher_assignment_list,
        name="teacher_assignment_list",
    ),
    path(
        "create/",
        teacher_assignment_views.teacher_assignment_create,
        name="teacher_assignment_create",
    ),
    path(
        "<int:pk>/delete/",
        teacher_assignment_views.teacher_assignment_delete,
        name="teacher_assignment_delete",
    ),
]
