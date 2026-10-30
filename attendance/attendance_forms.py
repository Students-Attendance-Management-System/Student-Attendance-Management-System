from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Attendance


class AttendanceForm(forms.Form):
    """One date field plus one status field for every enrolled student."""

    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, enrollments, **kwargs):
        super().__init__(*args, **kwargs)
        self.enrollments = list(enrollments)

        # Fields are built only from the real roster, so a student who is not
        # enrolled in the section can never be saved.
        for enrollment in self.enrollments:
            self.fields[self.field_name(enrollment.student_id)] = forms.ChoiceField(
                choices=Attendance.STATUS_CHOICES,
                label=enrollment.student.username,
                widget=forms.RadioSelect,
            )

    @staticmethod
    def field_name(student_id):
        return f"status_{student_id}"

    def clean_date(self):
        attendance_date = self.cleaned_data["date"]

        if attendance_date > timezone.localdate():
            raise ValidationError(
                "Attendance cannot be marked for a future date."
            )

        return attendance_date

    def clean(self):
        cleaned_data = super().clean()

        if not self.enrollments:
            raise ValidationError(
                "This section has no enrolled students."
            )

        return cleaned_data

    def student_rows(self):
        """(enrollment, status field) pairs for the template."""
        return [
            (enrollment, self[self.field_name(enrollment.student_id)])
            for enrollment in self.enrollments
        ]