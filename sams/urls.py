from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('users/', include('attendance.account_urls')),
    path('enrollments/', include('attendance.enrollment_urls')),
    path('attendance/', include('attendance.attendance_urls')),
]