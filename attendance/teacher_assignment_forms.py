
from django import forms
from django.contrib.auth.models import User

from .models import Section, TeacherAssignment
from .permissions import ROLE_TEACHER


class TeacherAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ["teacher", "section"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["teacher"].queryset = (
            User.objects.filter(
                is_active=True,
                is_superuser=False,
                groups__name=ROLE_TEACHER,
            )
            .exclude(groups__name="Admin")
            .distinct()
            .order_by("username")
        )

        self.fields["teacher"].label = "Teacher"
        self.fields["section"].queryset = (
            Section.objects.select_related("course").order_by(
                "course__code", "name"
            )
        )
        self.fields["section"].label = "Course section"

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get("teacher")
        section = cleaned_data.get("section")

        if teacher and section and TeacherAssignment.objects.filter(
            teacher=teacher,
            section=section,
        ).exists():
            raise forms.ValidationError(
                "This teacher is already assigned to this section."
            )

        return cleaned_data
