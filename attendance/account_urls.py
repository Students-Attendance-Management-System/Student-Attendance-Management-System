from django.urls import path

from . import account_views

# Mounted under "users/" in sams/urls.py. URL names are unchanged
# (user_list, user_create, user_update), so the templates keep working.
urlpatterns = [
    path("", account_views.user_list, name="user_list"),
    path("create/", account_views.user_create, name="user_create"),
    path("<int:pk>/edit/", account_views.user_update, name="user_update"),
]