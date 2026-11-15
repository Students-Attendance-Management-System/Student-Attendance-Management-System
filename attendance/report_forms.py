from django import forms

from .defaulter_services import sections_for_user


class ReportFilterForm(forms.Form):
    section = forms.ModelChoiceField(queryset=None)
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only sections this user may see, so the server enforces access.
        self.fields["section"].queryset = sections_for_user(user)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and start > end:
            raise forms.ValidationError("Start date must be on or before end date.")
        return cleaned