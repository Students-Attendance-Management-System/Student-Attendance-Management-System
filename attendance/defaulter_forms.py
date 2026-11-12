from django import forms

from .models import AttendanceThreshold


class ThresholdForm(forms.Form):
    value = forms.DecimalField(
        label="Attendance threshold (%)",
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        error_messages={
            "required": "Enter a threshold between 0 and 100.",
            "invalid": "Enter a number between 0 and 100.",
            "min_value": "Threshold cannot be below 0.",
            "max_value": "Threshold cannot be above 100.",
        },
    )

    def save(self, user):
        threshold = AttendanceThreshold.get_solo()
        threshold.value = self.cleaned_data["value"]
        threshold.updated_by = user
        threshold.save()
        return threshold
