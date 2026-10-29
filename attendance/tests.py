
from datetime import time

from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Course, Section, Schedule


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="testuser",
            password="TestPass123!",
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "testuser",
                "password": "TestPass123!",
            },
            follow=True,
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_login(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "testuser",
                "password": "wrongpassword",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")


class CourseManagementTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="CS101",
            name="Computer Science",
        )
        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-2027",
        )

    def test_create_course(self):
        self.assertEqual(self.course.name, "Computer Science")

    def test_create_section(self):
        self.assertEqual(self.section.course, self.course)

    def test_duplicate_section_rejected(self):
        with self.assertRaises(Exception):
            Section.objects.create(
                course=self.course,
                name="A",
                academic_year="2026-2027",
            )

    def test_schedule_end_time_must_be_after_start(self):
        schedule = Schedule(
            section=self.section,
            day="MON",
            start_time=time(11, 0),
            end_time=time(10, 0),
        )
        with self.assertRaises(ValidationError):
            schedule.full_clean()

    def test_overlapping_schedule_rejected(self):
        Schedule.objects.create(
            section=self.section,
            day="MON",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        schedule = Schedule(
            section=self.section,
            day="MON",
            start_time=time(9, 30),
            end_time=time(10, 30),
        )
        with self.assertRaises(ValidationError):
            schedule.full_clean()


class RoleBasedAccessTests(TestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        self.student_group, _ = Group.objects.get_or_create(name="Student")

        self.admin = User.objects.create_user(
            username="admin_user",
            password="TestPass123!",
        )
        self.admin.groups.add(self.admin_group)

        self.teacher = User.objects.create_user(
            username="teacher_user",
            password="TestPass123!",
        )
        self.teacher.groups.add(self.teacher_group)

        self.student = User.objects.create_user(
            username="student_user",
            password="TestPass123!",
        )
        self.student.groups.add(self.student_group)

    def test_admin_can_access_admin_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("attendance:admin_dashboard")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Dashboard")

    def test_teacher_is_redirected_from_admin_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("attendance:admin_dashboard")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("attendance:dashboard"),
        )

    def test_student_cannot_access_admin_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("attendance:admin_dashboard")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("attendance:dashboard"),
        )

    def test_teacher_can_access_teacher_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("attendance:teacher_dashboard")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teacher Dashboard")

    def test_student_can_access_student_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("attendance:student_dashboard")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Dashboard")

    def test_unassigned_user_cannot_access_admin_dashboard(self):
        user = User.objects.create_user(
            username="unassigned_user",
            password="TestPass123!",
        )
        self.client.force_login(user)
        response = self.client.get(
            reverse("attendance:admin_dashboard"),
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "No role has been assigned to your account.",
            status_code=403,
        )
