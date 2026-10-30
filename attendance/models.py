
from django.core.exceptions import ValidationError
from django.db import models


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

        # Imported here so models.py keeps its simple imports at the top.
        from .permissions import ROLE_STUDENT, get_role_name, is_managed_account

        student = self.student

        if not student.is_active:
            raise ValidationError(
                {"student": "Deactivated accounts cannot be enrolled."}
            )

        if not is_managed_account(student) or get_role_name(student) != ROLE_STUDENT:
            raise ValidationError(
                {"student": "Only users with the Student role can be enrolled."}
            )

    def __str__(self):
        return f"{self.student.username} -> {self.section}"



class Attendance(models.Model):
    PRESENT = "P"
    ABSENT = "A"
    LATE = "L"
    STATUS_CHOICES = [
        (PRESENT, "Present"),
        (ABSENT, "Absent"),
        (LATE, "Late"),
    ]

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)
    marked_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_marked",
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["section", "student", "date"],
                name="unique_attendance_per_student_section_date",
            )
        ]
        ordering = ["-date", "student__username"]

    def clean(self):
        super().clean()

        if self.section_id and self.student_id:
            enrolled = Enrollment.objects.filter(
                section_id=self.section_id,
                student_id=self.student_id,
            ).exists()

            if not enrolled:
                raise ValidationError(
                    {"student": "This student is not enrolled in this section."}
                )

    def __str__(self):
        return f"{self.student.username} - {self.section} - {self.date}: {self.get_status_display()}"