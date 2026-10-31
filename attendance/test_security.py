from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AttendanceRecord, AttendanceSession, Course, Section
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER
from .views import has_role


class RoleSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher_group = Group.objects.create(name=ROLE_TEACHER)
        cls.student_group = Group.objects.create(name=ROLE_STUDENT)
        cls.admin_group = Group.objects.create(name=ROLE_ADMIN)

        cls.teacher = User.objects.create_user(username="security_teacher")
        cls.teacher.groups.add(cls.teacher_group)

        cls.student = User.objects.create_user(username="security_student")
        cls.student.groups.add(cls.student_group)

        cls.admin = User.objects.create_user(username="security_admin")
        cls.admin.groups.add(cls.admin_group)

        cls.inactive_teacher = User.objects.create_user(
            username="inactive_teacher",
            is_active=False,
        )
        cls.inactive_teacher.groups.add(cls.teacher_group)

    def test_active_users_have_only_their_assigned_role(self):
        self.assertTrue(has_role(self.teacher, ROLE_TEACHER))
        self.assertFalse(has_role(self.teacher, ROLE_ADMIN))
        self.assertTrue(has_role(self.student, ROLE_STUDENT))

    def test_inactive_user_has_no_application_role_access(self):
        self.assertFalse(has_role(self.inactive_teacher, ROLE_TEACHER))

    def test_admin_role_is_not_granted_to_normal_teacher(self):
        self.assertFalse(has_role(self.teacher, ROLE_ADMIN))


class AttendanceInputValidationTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="SEC101",
            name="Security Testing",
        )
        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-27",
        )
        self.student = User.objects.create_user(
            username="attendance_student",
        )
        self.session = AttendanceSession.objects.create(
            section=self.section,
            date="2026-10-30",
        )

    def test_invalid_attendance_status_fails_model_validation(self):
        record = AttendanceRecord(
            session=self.session,
            student=self.student,
            status="UNEXPECTED",
        )

        with self.assertRaises(ValidationError):
            record.full_clean()


@override_settings(DEBUG=False)
class SafeErrorResponseTests(TestCase):
    def test_unknown_page_returns_safe_404(self):
        response = self.client.get("/security-test-page-that-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Traceback", status_code=404)
        self.assertNotContains(response, "SECRET_KEY", status_code=404)

    def test_student_gets_safe_forbidden_response_on_admin_page(self):
        student_group = Group.objects.create(name=ROLE_STUDENT)
        student = User.objects.create_user(username="restricted_student")
        student.groups.add(student_group)

        self.client.force_login(student)
        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Traceback", status_code=403)
        self.assertNotContains(response, "SECRET_KEY", status_code=403)