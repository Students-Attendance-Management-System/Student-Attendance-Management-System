
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


class AttendanceCorrection(models.Model):
    record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="corrections",
    )
    old_status = models.CharField(
        max_length=10, choices=AttendanceRecord.STATUS_CHOICES
    )
    new_status = models.CharField(
        max_length=10, choices=AttendanceRecord.STATUS_CHOICES
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="attendance_corrections",
    )
    corrected_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255)

    class Meta:
        ordering = ["-corrected_at"]

    def __str__(self):
        return f"{self.record}: {self.old_status} -> {self.new_status}"

class Enrollment(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_TRANSFERRED = "TRANSFERRED"
    STATUS_REMOVED = "REMOVED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_TRANSFERRED, "Transferred"),
        (STATUS_REMOVED, "Removed"),
    ]

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
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ended_enrollments",
    )
    end_reason = models.CharField(max_length=255, blank=True)
    transferred_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_to",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "section"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_student_section_enrollment",
            )
        ]


    def clean(self):
        super().clean()

        # History rows (transferred/removed) are never re-validated.
        if self.status != self.STATUS_ACTIVE or not self.student_id:
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
        return f"{self.student.username} -> {self.section} ({self.status})"

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


class AttendanceThreshold(models.Model):
    """
    Single-row setting. Students whose attendance percentage is below
    this value are shown on the defaulter list.
    """

    DEFAULT_VALUE = 75

    value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_VALUE,
        help_text="Attendance percentage between 0 and 100.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def clean(self):
        super().clean()

        try:
            out_of_range = not (0 <= self.value <= 100)
        except TypeError:
            # Field-level validation already reports values that are not numbers.
            return

        if out_of_range:
            raise ValidationError(
                {"value": "Threshold must be between 0 and 100."}
            )

    def save(self, *args, **kwargs):
        # There is only ever one row, and it can never hold a bad value.
        self.pk = 1
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Return the one threshold row, creating it with the default."""
        threshold, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"value": cls.DEFAULT_VALUE},
        )
        return threshold

    def __str__(self):
        return f"Defaulter threshold: {self.value}%"

