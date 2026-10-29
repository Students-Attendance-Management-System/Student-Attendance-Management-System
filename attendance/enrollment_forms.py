from django import forms
from django.contrib.auth.models import User

from .models import Enrollment, Section
from .permissions import ROLE_STUDENT, ROLE_TEACHER, managed_users


def enrollable_students():
    """Active accounts that have the Student role (and no Teacher role)."""
    return (
        managed_users()
        .filter(groups__name=ROLE_STUDENT, is_active=True)
        .exclude(groups__name=ROLE_TEACHER)
        .distinct()
        .order_by("username")
    )


class EnrollmentForm(forms.Form):
    student = forms.ModelChoiceField(queryset=User.objects.none())
    section = forms.ModelChoiceField(queryset=Section.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["student"].queryset = enrollable_students()
        self.fields["student"].label_from_instance = (
            lambda user: f"{user.username} ({user.get_full_name() or 'no name'})"
        )

        self.fields["section"].queryset = Section.objects.select_related(
            "course"
        ).order_by("course__code", "academic_year", "name")
        self.fields["section"].label_from_instance = (
            lambda section: (
                f"{section.course.code} - {section.name} "
                f"({section.academic_year})"
            )
        )

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        section = cleaned.get("section")

        if student and section:
            if Enrollment.objects.filter(
                student=student, section=section
            ).exists():
                raise forms.ValidationError(
                    "This student is already enrolled in this section."
                )

        return cleaned

    def save(self):
        enrollment = Enrollment(
            student=self.cleaned_data["student"],
            section=self.cleaned_data["section"],
        )
        # Runs the model's own checks (student role, active account,
        # duplicate rule) as a second safety net.
        enrollment.full_clean()
        enrollment.save()
        return enrollment