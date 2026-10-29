
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import Course, Section, TeacherAssignment
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER


class TeacherAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = Group.objects.create(name=ROLE_ADMIN)
        cls.teacher_group = Group.objects.create(name=ROLE_TEACHER)
        cls.student_group = Group.objects.create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user(
            username="assignment_admin",
            password="test-password-123",
        )
        cls.admin.groups.add(cls.admin_group)

        cls.teacher = User.objects.create_user(
            username="assignment_teacher",
            password="test-password-123",
        )
        cls.teacher.groups.add(cls.teacher_group)

        cls.student = User.objects.create_user(
            username="assignment_student",
            password="test-password-123",
        )
        cls.student.groups.add(cls.student_group)

        cls.course = Course.objects.create(
            code="TEST101",
            name="Test Course",
        )
        cls.section = Section.objects.create(
            course=cls.course,
            name="A",
            academic_year="2026-2027",
        )

    def test_admin_can_create_assignment(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("teacher_assignment_create"),
            {
                "teacher": self.teacher.pk,
                "section": self.section.pk,
            },
        )

        self.assertRedirects(
            response,
            reverse("teacher_assignment_list"),
        )
        self.assertTrue(
            TeacherAssignment.objects.filter(
                teacher=self.teacher,
                section=self.section,
            ).exists()
        )

    def test_admin_can_view_assignment_list(self):
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            section=self.section,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("teacher_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "assignment_teacher")
        self.assertContains(response, "TEST101")

    def test_duplicate_assignment_is_rejected(self):
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            section=self.section,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("teacher_assignment_create"),
            {
                "teacher": self.teacher.pk,
                "section": self.section.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "already assigned",
            status_code=200,
        )
        self.assertEqual(TeacherAssignment.objects.count(), 1)

    def test_student_cannot_view_assignment_list(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("teacher_assignment_list"))

        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_create_assignment(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("teacher_assignment_create"),
            {
                "teacher": self.teacher.pk,
                "section": self.section.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_inactive_teacher_cannot_be_assigned(self):
        self.teacher.is_active = False
        self.teacher.save()

        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("teacher_assignment_create"),
            {
                "teacher": self.teacher.pk,
                "section": self.section.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_admin_can_remove_assignment(self):
        assignment = TeacherAssignment.objects.create(
            teacher=self.teacher,
            section=self.section,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse(
                "teacher_assignment_delete",
                args=[assignment.pk],
            )
        )

        self.assertRedirects(
            response,
            reverse("teacher_assignment_list"),
        )
        self.assertFalse(
            TeacherAssignment.objects.filter(pk=assignment.pk).exists()
        )

    def test_teacher_cannot_remove_assignment(self):
        assignment = TeacherAssignment.objects.create(
            teacher=self.teacher,
            section=self.section,
        )
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse(
                "teacher_assignment_delete",
                args=[assignment.pk],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            TeacherAssignment.objects.filter(pk=assignment.pk).exists()
        )
