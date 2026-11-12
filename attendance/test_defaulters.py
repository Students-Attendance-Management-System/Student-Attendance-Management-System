from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .defaulter_forms import ThresholdForm
from .defaulter_services import get_defaulter_report, sections_for_user
from .models import (
    AttendanceRecord,
    AttendanceSession,
    AttendanceThreshold,
    Course,
    Enrollment,
    Section,
    TeacherAssignment,
)
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER


class DefaulterServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        teacher_group, _ = Group.objects.get_or_create(name=ROLE_TEACHER)
        student_group, _ = Group.objects.get_or_create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user(
            username="defaulter_admin",
            password="test-password-123",
        )
        cls.admin.groups.add(admin_group)

        cls.teacher = User.objects.create_user(
            username="defaulter_teacher",
            password="test-password-123",
        )
        cls.teacher.groups.add(teacher_group)

        cls.student = User.objects.create_user(
            username="defaulter_student",
            password="test-password-123",
        )
        cls.student.groups.add(student_group)

        cls.course = Course.objects.create(
            code="DEF101",
            name="Defaulter Test Course",
        )
        cls.section = Section.objects.create(
            course=cls.course,
            name="A",
            academic_year="2026-2027",
        )

        Enrollment.objects.create(
            student=cls.student,
            section=cls.section,
        )

    def add_record(self, student, status):
        session = AttendanceSession.objects.create(
            section=self.section,
            date=timezone.localdate(),
            teacher=self.teacher,
        )
        return AttendanceRecord.objects.create(
            session=session,
            student=student,
            status=status,
        )

    def test_default_threshold_is_75(self):
        threshold = AttendanceThreshold.get_solo()
        self.assertEqual(threshold.value, Decimal("75"))

    def test_present_and_late_count_as_attended(self):
        self.add_record(self.student, "PRESENT")
        self.add_record(self.student, "LATE")
        self.add_record(self.student, "ABSENT")

        report = get_defaulter_report(self.section)

        self.assertEqual(len(report["defaulters"]), 1)
        self.assertEqual(
            report["defaulters"][0]["attended"],
            2,
        )
        self.assertEqual(
            report["defaulters"][0]["percentage"],
            66.67,
        )

    def test_student_below_threshold_is_a_defaulter(self):
        self.add_record(self.student, "PRESENT")
        self.add_record(self.student, "ABSENT")

        report = get_defaulter_report(self.section)

        self.assertEqual(len(report["defaulters"]), 1)
        self.assertEqual(
            report["defaulters"][0]["student"],
            self.student,
        )
        self.assertEqual(
            report["defaulters"][0]["percentage"],
            50.0,
        )

    def test_student_exactly_at_threshold_is_not_a_defaulter(self):
        for status in ["PRESENT", "PRESENT", "PRESENT", "ABSENT"]:
            self.add_record(self.student, status)

        report = get_defaulter_report(self.section, threshold=75)

        self.assertEqual(len(report["defaulters"]), 0)

    def test_student_with_no_records_is_not_a_defaulter(self):
        report = get_defaulter_report(self.section)

        self.assertEqual(len(report["defaulters"]), 0)
        self.assertEqual(report["no_records_count"], 1)

    def test_report_updates_when_attendance_records_change(self):
        self.add_record(self.student, "PRESENT")
        self.add_record(self.student, "ABSENT")

        first_report = get_defaulter_report(self.section)
        self.assertEqual(len(first_report["defaulters"]), 1)

        self.add_record(self.student, "PRESENT")
        self.add_record(self.student, "PRESENT")

        updated_report = get_defaulter_report(self.section)
        self.assertEqual(len(updated_report["defaulters"]), 0)

    def test_report_updates_when_threshold_changes(self):
        self.add_record(self.student, "PRESENT")
        self.add_record(self.student, "ABSENT")

        first_report = get_defaulter_report(self.section)
        self.assertEqual(len(first_report["defaulters"]), 1)

        threshold = AttendanceThreshold.get_solo()
        threshold.value = Decimal("40")
        threshold.save()

        updated_report = get_defaulter_report(self.section)
        self.assertEqual(len(updated_report["defaulters"]), 0)

    def test_only_active_enrollments_and_students_are_counted(self):
        removed_student = User.objects.create_user(
            username="removed_student",
            password="test-password-123",
        )
        inactive_student = User.objects.create_user(
            username="inactive_student",
            password="test-password-123",
            is_active=False,
        )

        Enrollment.objects.create(
            student=removed_student,
            section=self.section,
            status=Enrollment.STATUS_REMOVED,
        )
        Enrollment.objects.create(
            student=inactive_student,
            section=self.section,
        )

        report = get_defaulter_report(self.section)

        self.assertEqual(report["enrolled_count"], 1)


class ThresholdFormTests(TestCase):
    def test_accepts_threshold_boundaries(self):
        for value in ["0", "100"]:
            form = ThresholdForm(data={"value": value})
            self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_threshold_outside_range(self):
        for value in ["-1", "101"]:
            form = ThresholdForm(data={"value": value})
            self.assertFalse(form.is_valid())


class DefaulterAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        teacher_group, _ = Group.objects.get_or_create(name=ROLE_TEACHER)
        student_group, _ = Group.objects.get_or_create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user(
            username="access_admin",
            password="test-password-123",
        )
        cls.admin.groups.add(admin_group)

        cls.teacher = User.objects.create_user(
            username="access_teacher",
            password="test-password-123",
        )
        cls.teacher.groups.add(teacher_group)

        cls.student = User.objects.create_user(
            username="access_student",
            password="test-password-123",
        )
        cls.student.groups.add(student_group)

        cls.course = Course.objects.create(
            code="ACCESS101",
            name="Access Test Course",
        )
        cls.section = Section.objects.create(
            course=cls.course,
            name="A",
            academic_year="2026-2027",
        )
        cls.other_section = Section.objects.create(
            course=cls.course,
            name="B",
            academic_year="2026-2027",
        )

        TeacherAssignment.objects.create(
            teacher=cls.teacher,
            section=cls.section,
        )

    def test_admin_can_view_all_sections(self):
        self.assertEqual(sections_for_user(self.admin).count(), 2)

    def test_teacher_can_view_only_assigned_sections(self):
        sections = sections_for_user(self.teacher)
        self.assertEqual(list(sections), [self.section])

    def test_student_cannot_view_sections(self):
        self.assertEqual(sections_for_user(self.student).count(), 0)

    def test_teacher_cannot_view_unassigned_section(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("defaulter_list", args=[self.other_section.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_view_defaulter_sections(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("defaulter_section_list")
        )

        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_change_threshold(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("defaulter_settings"),
            {"value": "60"},
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_change_threshold(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("defaulter_settings"),
            {"value": "60"},
        )

        self.assertRedirects(
            response,
            reverse("defaulter_section_list"),
        )
        self.assertEqual(
            AttendanceThreshold.get_solo().value,
            Decimal("60"),
        )
        self.assertEqual(
            AttendanceThreshold.get_solo().updated_by,
            self.admin,
        )