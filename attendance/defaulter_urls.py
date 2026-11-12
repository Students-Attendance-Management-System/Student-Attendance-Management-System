from django.urls import path

from . import defaulter_views

urlpatterns = [
    path(
        "",
        defaulter_views.defaulter_section_list,
        name="defaulter_section_list",
    ),
    path(
        "sections/<int:pk>/",
        defaulter_views.defaulter_list,
        name="defaulter_list",
    ),
    path(
        "settings/",
        defaulter_views.threshold_settings,
        name="defaulter_settings",
    ),
]
