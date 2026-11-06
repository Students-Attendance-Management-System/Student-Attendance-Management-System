
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('users/', include('attendance.account_urls')),
    path('enrollments/', include('attendance.enrollment_urls')),
    path(
        'teacher-assignments/',
        include('attendance.teacher_assignment_urls'),
    ),
    path('', include('attendance.urls')),
]
