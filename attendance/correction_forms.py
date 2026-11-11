from django import forms

from .models import AttendanceRecord


class CorrectionForm(forms.Form):
    new_status = forms.ChoiceField(
        choices=AttendanceRecord.STATUS_CHOICES,
        label="New status",
    )
    reason = forms.CharField(
        max_length=255,
        label="Reason for correction",
    )
