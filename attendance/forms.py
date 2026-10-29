from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .permissions import (
    MANAGED_ROLES,
    ROLE_STUDENT,
    ROLE_TEACHER,
    get_role_name,
    is_managed_account,
)

# Admin accounts are intentionally NOT creatable or assignable through the UI
# (SRS SAMS-F-003: Admin manages Teacher and Student accounts only).
MANAGED_ROLE_CHOICES = [
    (ROLE_TEACHER, "Teacher"),
    (ROLE_STUDENT, "Student"),
]


def _email_in_use(email, exclude_pk=None):
    queryset = User.objects.filter(email__iexact=email)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


class UserCreateForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label="User ID",
        validators=[User.username_validator],
    )
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=254)
    role = forms.ChoiceField(choices=MANAGED_ROLE_CHOICES)
    password = forms.CharField(
        widget=forms.PasswordInput,
        strip=False,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        strip=False,
        label="Confirm password",
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This user ID is already registered.")

        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()

        if _email_in_use(email):
            raise ValidationError("This email is already in use.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password:
            # Validate against a throwaway user so Django's
            # UserAttributeSimilarityValidator can compare the password
            # with the username, name and email.
            candidate = User(
                username=cleaned_data.get("username", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
                email=cleaned_data.get("email", ""),
            )
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                self.add_error("password", error)

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data

    @transaction.atomic
    def save(self):
        """Create the User and assign its role group together or not at all."""
        data = self.cleaned_data

        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
        )
        # create_user() leaves is_staff / is_superuser False; never changed here.

        # The role groups are created on first use, so no data migration is
        # needed. Names match the RBAC work ("Teacher", "Student").
        group, _ = Group.objects.get_or_create(name=data["role"])
        user.groups.add(group)

        return user


class UserUpdateForm(forms.ModelForm):
    role = forms.ChoiceField(choices=MANAGED_ROLE_CHOICES)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Same required-field rules as account creation.
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True

        if self.instance.pk:
            role = get_role_name(self.instance)

            if role:
                self.fields["role"].initial = role

    def clean_email(self):
        email = self.cleaned_data["email"].strip()

        if _email_in_use(email, exclude_pk=self.instance.pk):
            raise ValidationError("This email is already in use.")

        return email

    def clean(self):
        cleaned_data = super().clean()

        # Defence in depth: the view only offers Teacher/Student accounts,
        # but the form itself must also refuse Admins, superusers and users
        # with no role, so a mistake elsewhere cannot cause privilege changes.
        if self.instance.pk and not is_managed_account(self.instance):
            raise ValidationError(
                "This account cannot be modified through account management."
            )

        return cleaned_data

    def save(self, commit=True):
        if not commit:
            raise ValueError("UserUpdateForm.save() only supports commit=True.")

        with transaction.atomic():
            user = super().save(commit=True)

            # Replace only the Teacher/Student role groups, so exactly one of
            # them remains and any other groups are left alone.
            user.groups.remove(*Group.objects.filter(name__in=MANAGED_ROLES))
            group, _ = Group.objects.get_or_create(name=self.cleaned_data["role"])
            user.groups.add(group)

        return user