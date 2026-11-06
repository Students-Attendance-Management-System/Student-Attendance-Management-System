from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .enrollment_forms import EnrollmentForm
from .models import Course, Enrollment, Section
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER

PASSWORD = "Sams#Secure2026!"

# A fast hasher keeps the suite quick; it is only active during these tests.
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role=None, **extra):
    user = User.objects.create_user(
        username=username,
        password=PASSWORD,
        email=f"{username}@example.com",
        **extra,
    )
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class EnrollmentTestBase(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="CS101", name="Intro to Computing"
        )
        self.section = Section.objects.create(
            course=self.course, name="A", academic_year="2026-27"
        )
        self.other_section = Section.objects.create(
            course=self.course, name="B", academic_year="2026-27"
        )

        self.admin = make_user("admin1", ROLE_ADMIN)
        self.teacher = make_user("teacher1", ROLE_TEACHER)
        self.student = make_user("student1", ROLE_STUDENT)
        self.student2 = make_user("student2", ROLE_STUDENT)


class EnrollmentModelTests(EnrollmentTestBase):
    def test_valid_student_can_be_enrolled(self):
        enrollment = Enrollment(student=self.student, section=self.section)
        enrollment.full_clean()
        enrollment.save()

        self.assertEqual(Enrollment.objects.count(), 1)

    def test_same_student_can_join_different_sections(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        Enrollment.objects.create(
            student=self.student, section=self.other_section
        )

        self.assertEqual(self.student.enrollments.count(), 2)

    def test_teacher_cannot_be_enrolled(self):
        enrollment = Enrollment(student=self.teacher, section=self.section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_admin_cannot_be_enrolled(self):
        enrollment = Enrollment(student=self.admin, section=self.section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_superuser_cannot_be_enrolled(self):
        root = User.objects.create_superuser(
            "root", "root@example.com", PASSWORD
        )
        enrollment = Enrollment(student=root, section=self.section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_user_without_role_cannot_be_enrolled(self):
        nobody = make_user("norole")
        enrollment = Enrollment(student=nobody, section=self.section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_deactivated_student_cannot_be_enrolled(self):
        gone = make_user("gone", ROLE_STUDENT, is_active=False)
        enrollment = Enrollment(student=gone, section=self.section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_duplicate_enrollment_fails_validation(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        duplicate = Enrollment(student=self.student, section=self.section)

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_duplicate_enrollment_blocked_by_database(self):
        Enrollment.objects.create(student=self.student, section=self.section)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student, section=self.section
                )

        self.assertEqual(Enrollment.objects.count(), 1)


class EnrollmentFormTests(EnrollmentTestBase):
    def test_valid_form_creates_enrollment(self):
        form = EnrollmentForm(
            {"student": self.student.pk, "section": self.section.pk}
        )

        self.assertTrue(form.is_valid())
        form.save()
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student, section=self.section
            ).exists()
        )

    def test_duplicate_gives_friendly_message(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        form = EnrollmentForm(
            {"student": self.student.pk, "section": self.section.pk}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("already enrolled", str(form.non_field_errors()))

    def test_teacher_is_not_a_valid_choice(self):
        form = EnrollmentForm(
            {"student": self.teacher.pk, "section": self.section.pk}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("student", form.errors)

    def test_deactivated_student_is_not_a_valid_choice(self):
        gone = make_user("gone", ROLE_STUDENT, is_active=False)
        form = EnrollmentForm(
            {"student": gone.pk, "section": self.section.pk}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("student", form.errors)

    def test_unknown_section_is_invalid(self):
        form = EnrollmentForm({"student": self.student.pk, "section": 99999})

        self.assertFalse(form.is_valid())
        self.assertIn("section", form.errors)

    def test_missing_fields_are_invalid(self):
        form = EnrollmentForm({})

        self.assertFalse(form.is_valid())
        self.assertIn("student", form.errors)
        self.assertIn("section", form.errors)


class EnrollmentViewTests(EnrollmentTestBase):
    def enroll_url(self):
        return reverse("enroll_student")

    def roster_url(self, section):
        return reverse("enrollment_section_roster", args=[section.pk])

    # --- Access control -------------------------------------------------

    def test_anonymous_users_are_sent_to_login(self):
        for url in (
            reverse("enrollment_section_list"),
            self.roster_url(self.section),
            self.enroll_url(),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_student_gets_403_everywhere(self):
        self.client.force_login(self.student)

        for url in (
            reverse("enrollment_section_list"),
            self.roster_url(self.section),
            self.enroll_url(),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_teacher_can_view_sections_and_rosters(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("enrollment_section_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(self.roster_url(self.section))
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_enroll_or_remove(self):
        enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        self.client.force_login(self.teacher)

        self.assertEqual(self.client.get(self.enroll_url()).status_code, 403)

        response = self.client.post(
            self.enroll_url(),
            {"student": self.student2.pk, "section": self.section.pk},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("unenroll_student", args=[enrollment.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Enrollment.objects.count(), 1)

    # --- Enrolling ------------------------------------------------------

    def test_admin_can_enroll_student(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.enroll_url(),
            {"student": self.student.pk, "section": self.section.pk},
        )

        self.assertRedirects(response, self.roster_url(self.section))
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student, section=self.section
            ).exists()
        )

    def test_admin_duplicate_enrollment_is_rejected(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        self.client.force_login(self.admin)

        response = self.client.post(
            self.enroll_url(),
            {"student": self.student.pk, "section": self.section.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already enrolled")
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_admin_cannot_enroll_a_teacher(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.enroll_url(),
            {"student": self.teacher.pk, "section": self.section.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_admin_cannot_enroll_in_unknown_section(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.enroll_url(),
            {"student": self.student.pk, "section": 99999},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 0)

    # --- Rosters --------------------------------------------------------

    def test_roster_shows_only_students_of_that_section(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        Enrollment.objects.create(
            student=self.student2, section=self.other_section
        )
        self.client.force_login(self.admin)

        response = self.client.get(self.roster_url(self.section))

        self.assertContains(response, "student1")
        self.assertNotContains(response, "student2")

    def test_empty_roster_shows_message(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.roster_url(self.section))

        self.assertContains(response, "No students are enrolled")

    def test_roster_for_unknown_section_is_404(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("enrollment_section_roster", args=[99999])
        )

        self.assertEqual(response.status_code, 404)

    def test_section_list_shows_student_counts(self):
        Enrollment.objects.create(student=self.student, section=self.section)
        Enrollment.objects.create(student=self.student2, section=self.section)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("enrollment_section_list"))
        counts = {s.name: s.student_count for s in response.context["sections"]}

        self.assertEqual(counts, {"A": 2, "B": 0})

    # --- Removing -------------------------------------------------------

    def test_admin_can_remove_enrollment(self):
        enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("unenroll_student", args=[enrollment.pk])
        )

        self.assertRedirects(response, self.roster_url(self.section))
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.STATUS_REMOVED)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_remove_requires_post(self):
        enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("unenroll_student", args=[enrollment.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Enrollment.objects.count(), 1)