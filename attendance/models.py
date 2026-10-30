
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Section(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(max_length=50)
    academic_year = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "name", "academic_year"],
                name="unique_course_section_year",
            )
        ]

    def __str__(self):
        return f"{self.course.code} - {self.name}"


class Schedule(models.Model):
    DAYS = [
        ("MON", "Monday"),
        ("TUE", "Tuesday"),
        ("WED", "Wednesday"),
        ("THU", "Thursday"),
        ("FRI", "Friday"),
        ("SAT", "Saturday"),
        ("SUN", "Sunday"),
    ]

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)

    def clean(self):
        super().clean()

        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError(
                    {"end_time": "End time must be after start time."}
                )

            if self.section_id:
                conflicts = Schedule.objects.filter(
                    section_id=self.section_id,
                    day=self.day,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                )

                if self.pk:
                    conflicts = conflicts.exclude(pk=self.pk)

                if conflicts.exists():
                    raise ValidationError(
                        "This section already has an overlapping schedule."
                    )

    def __str__(self):
        return f"{self.section} - {self.get_day_display()}"


class AttendanceSession(models.Model):
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    date = models.DateField()
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conducted_sessions",
    )
    topic = models.CharField(max_length=200, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "section"]

    def __str__(self):
        return f"{self.section} - {self.date}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ("PRESENT", "Present"),
        ("ABSENT", "Absent"),
        ("LATE", "Late"),
    ]

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="records",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PRESENT",
    )
    remarks = models.CharField(max_length=200, blank=True)
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"],
                name="unique_student_attendance_per_session",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.session} - {self.status}"


class Enrollment(models.Model):
    student = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "section"],
                name="unique_student_section_enrollment",
            )
        ]

    
    def clean(self):
        super().clean()

        if not self.student_id:
            return

        from .permissions import (
            ROLE_STUDENT,
            get_role_name,
            is_managed_account,
        )
        student = self.student

        if not student.is_active:
            raise ValidationError(
                {"student": "Deactivated accounts cannot be enrolled."}
            )

        if (
            not is_managed_account(student)
            or get_role_name(student) != ROLE_STUDENT
        ):
            raise ValidationError(
                {"student": "Only users with the Student role can be enrolled."}
            )

    def __str__(self):
        return f"{self.student.username} -> {self.section}"

class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "section"],
                name="unique_teacher_section_assignment",
            )
        ]
        ordering = ["section__course__code", "section__name"]

    def clean(self):
        super().clean()

        if not self.teacher_id:
            return

        from .permissions import ROLE_TEACHER, get_role_name, is_managed_account

        teacher = self.teacher

        if not teacher.is_active:
            raise ValidationError(
                {"teacher": "Deactivated accounts cannot be assigned to sections."}
            )

        if (
            not is_managed_account(teacher)
            or get_role_name(teacher) != ROLE_TEACHER
        ):
            raise ValidationError(
                {"teacher": "Only users with the Teacher role can be assigned."}
            )

    def __str__(self):
        return f"{self.teacher.username} -> {self.section}"

