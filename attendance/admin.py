from django.contrib import admin
from .models import Course, Section, Schedule, AttendanceSession, AttendanceRecord


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("section", "date", "teacher", "topic")
    list_filter = ("date", "section")
    search_fields = ("topic", "section__name", "teacher__username")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("session", "student", "status", "marked_at")
    list_filter = ("status", "session__date")
    search_fields = ("student__username", "session__topic")