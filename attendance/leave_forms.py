
from django import forms
from django.utils import timezone

from .models import LeaveRequest, Enrollment, Section


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["section", "start_date", "end_date", "reason"]

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)

        if student is not None:
            self.fields["section"].queryset = Section.objects.filter(
                enrollments__student=student,
                enrollments__status=Enrollment.STATUS_ACTIVE,
            ).select_related("course").distinct().order_by(
                "course__code", "name"
            )

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and start_date < timezone.localdate():
            self.add_error(
                "start_date",
                "Leave start date cannot be in the past.",
            )

        if start_date and end_date and end_date < start_date:
            self.add_error(
                "end_date",
                "End date cannot be before start date.",
            )

        return cleaned_data

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()

        if not reason:
            raise forms.ValidationError(
                "Please provide a reason for leave."
            )

        return reason
