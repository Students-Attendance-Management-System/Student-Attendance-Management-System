import csv
import io
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .attendance_services import calculate_attendance_percentage
from .models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Section,
    TeacherAssignment,
)
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER
from .report_services import get_attendance_report, get_report_section


def parse_csv(response):
    text = response.content.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


class ReportTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        teacher_group, _ = Group.objects.get_or_create(name=ROLE_TEACHER)
        student_group, _ = Group.objects.get_or_create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user(
            username="report_admin", password="test-password-123"
        )
        cls.admin.groups.add(admin_group)

        cls.teacher = User.objects.create_user(
            username="report_teacher", password="test-password-123"
        )
        cls.teacher.groups.add(teacher_group)

        cls.other_teacher = User.objects.create_user(
            username="report_other_teacher", password="test-password-123"
        )
        cls.other_teacher.groups.add(teacher_group)

        cls.student = User.objects.create_user(
            username="report_student", password="test-password-123"
        )
        cls.student.groups.add(student_group)

        cls.course = Course.objects.create(
            code="REP101", name="Report Test Course"
        )
        cls.section = Section.objects.create(
            course=cls.course, name="A", academic_year="2026-2027"
        )
        cls.other_section = Section.objects.create(
            course=cls.course, name="B", academic_year="2026-2027"
        )

        TeacherAssignment.objects.create(
            teacher=cls.teacher, section=cls.section
        )
        TeacherAssignment.objects.create(
            teacher=cls.other_teacher, section=cls.other_section
        )

        cls.enrollment = Enrollment.objects.create(
            student=cls.student, section=cls.section
        )
        # Make the enrollment start well in the past so older sessions count.
        Enrollment.objects.filter(pk=cls.enrollment.pk).update(
            enrolled_at=timezone.now() - timedelta(days=60)
        )

    def add_record(self, student, status, days_ago=0, section=None):
        session = AttendanceSession.objects.create(
            section=section or self.section,
            date=timezone.localdate() - timedelta(days=days_ago),
            teacher=self.teacher,
        )
        return AttendanceRecord.objects.create(
            session=session, student=student, status=status
        )

    def export(self, user, **params):
        self.client.force_login(user)
        return self.client.get(reverse("attendance:export_report"), params)


class ReportServiceTests(ReportTestBase):
    def test_rows_match_percentage_calculation(self):
        self.add_record(self.student, "PRESENT", days_ago=3)
        self.add_record(self.student, "LATE", days_ago=2)
        self.add_record(self.student, "ABSENT", days_ago=1)

        rows = get_attendance_report(self.section)
        expected = calculate_attendance_percentage(self.student, self.section)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["student"], self.student)
        self.assertEqual(rows[0]["percentage"], expected["percentage"])
        self.assertEqual(rows[0]["percentage"], 66.67)
        self.assertEqual(rows[0]["total"], 3)

    def test_date_range_limits_sessions_counted(self):
        self.add_record(self.student, "ABSENT", days_ago=20)
        self.add_record(self.student, "PRESENT", days_ago=2)
        self.add_record(self.student, "PRESENT", days_ago=1)

        start = timezone.localdate() - timedelta(days=5)
        rows = get_attendance_report(self.section, start_date=start)

        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(rows[0]["percentage"], 100.0)

    def test_end_date_limits_sessions_counted(self):
        self.add_record(self.student, "PRESENT", days_ago=20)
        self.add_record(self.student, "ABSENT", days_ago=1)

        end = timezone.localdate() - timedelta(days=10)
        rows = get_attendance_report(self.section, end_date=end)

        self.assertEqual(rows[0]["total"], 1)
        self.assertEqual(rows[0]["percentage"], 100.0)

    def test_student_with_no_records_has_no_percentage(self):
        rows = get_attendance_report(self.section)

        self.assertEqual(rows[0]["total"], 0)
        self.assertIsNone(rows[0]["percentage"])

    def test_removed_and_inactive_students_are_excluded(self):
        removed = User.objects.create_user(
            username="report_removed", password="test-password-123"
        )
        inactive = User.objects.create_user(
            username="report_inactive",
            password="test-password-123",
            is_active=False,
        )
        Enrollment.objects.create(
            student=removed,
            section=self.section,
            status=Enrollment.STATUS_REMOVED,
        )
        Enrollment.objects.create(student=inactive, section=self.section)

        rows = get_attendance_report(self.section)

        self.assertEqual([r["student"] for r in rows], [self.student])

    def test_get_report_section_enforces_access(self):
        self.assertEqual(
            get_report_section(self.admin, self.other_section.pk),
            self.other_section,
        )
        self.assertEqual(
            get_report_section(self.teacher, self.section.pk), self.section
        )

        with self.assertRaises(PermissionDenied):
            get_report_section(self.teacher, self.other_section.pk)

        with self.assertRaises(PermissionDenied):
            get_report_section(self.student, self.section.pk)


class ReportExportTests(ReportTestBase):
    def test_admin_export_returns_csv_with_correct_data(self):
        self.add_record(self.student, "PRESENT", days_ago=3)
        self.add_record(self.student, "LATE", days_ago=2)
        self.add_record(self.student, "ABSENT", days_ago=1)

        response = self.export(self.admin, section=self.section.pk)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", response["Content-Disposition"])

        rows = parse_csv(response)
        self.assertEqual(
            list(rows[0].keys()),
            [
                "Username", "Name", "Section", "From", "To",
                "Present", "Late", "Absent", "Total", "Percentage",
            ],
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["Username"], "report_student")
        self.assertEqual(row["Present"], "1")
        self.assertEqual(row["Late"], "1")
        self.assertEqual(row["Absent"], "1")
        self.assertEqual(row["Total"], "3")
        self.assertEqual(row["Percentage"], "66.67")

    def test_export_shows_na_when_no_records(self):
        response = self.export(self.admin, section=self.section.pk)

        rows = parse_csv(response)
        self.assertEqual(rows[0]["Total"], "0")
        self.assertEqual(rows[0]["Percentage"], "N/A")

    def test_export_respects_date_range(self):
        self.add_record(self.student, "ABSENT", days_ago=20)
        self.add_record(self.student, "PRESENT", days_ago=2)

        start = (timezone.localdate() - timedelta(days=5)).isoformat()
        response = self.export(
            self.admin, section=self.section.pk, start_date=start
        )

        row = parse_csv(response)[0]
        self.assertEqual(row["Total"], "1")
        self.assertEqual(row["Percentage"], "100.0")
        self.assertEqual(row["From"], start)

    def test_assigned_teacher_can_export_own_section(self):
        response = self.export(self.teacher, section=self.section.pk)

        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_export_unassigned_section(self):
        response = self.export(self.teacher, section=self.other_section.pk)

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_export(self):
        response = self.export(self.student, section=self.section.pk)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("attendance:export_report"), {"section": self.section.pk}
        )

        self.assertEqual(response.status_code, 302)

    def test_nonexistent_section_is_forbidden(self):
        response = self.export(self.admin, section=999999)

        self.assertEqual(response.status_code, 403)

    def test_start_date_after_end_date_is_rejected(self):
        response = self.export(
            self.admin,
            section=self.section.pk,
            start_date="2026-11-10",
            end_date="2026-11-01",
        )

        self.assertEqual(response.status_code, 400)

    def test_formula_like_values_are_neutralised(self):
        evil = User.objects.create_user(
            username="=cmd", password="test-password-123"
        )
        Enrollment.objects.create(student=evil, section=self.section)

        response = self.export(self.admin, section=self.section.pk)

        usernames = [r["Username"] for r in parse_csv(response)]
        self.assertIn("'=cmd", usernames)
        self.assertNotIn("=cmd", usernames)


class ReportFormPageTests(ReportTestBase):
    def test_form_page_loads_for_admin(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("attendance:report_form"))

        self.assertEqual(response.status_code, 200)

    def test_form_lists_only_permitted_sections(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("attendance:report_form"))

        queryset = response.context["form"].fields["section"].queryset
        self.assertEqual(list(queryset), [self.section])