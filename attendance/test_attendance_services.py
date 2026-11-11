
import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .attendance_services import calculate_attendance_percentage
from .models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Section,
)


class AttendancePercentageTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="percentage_student")

        self.course = Course.objects.create(
            code="PCT101",
            name="Percentage Testing",
        )

        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-27",
        )

        self.enrollment = Enrollment.objects.create(
            student=self.student,
            section=self.section,
        )

        self.today = timezone.localdate()

    def create_record(self, status, session_date=None):
        session = AttendanceSession.objects.create(
            section=self.section,
            date=session_date or self.today,
        )

        return AttendanceRecord.objects.create(
            session=session,
            student=self.student,
            status=status,
        )

    def test_percentage_counts_present_and_late_as_attended(self):
        self.create_record("PRESENT")
        self.create_record("LATE")
        self.create_record("ABSENT")
        self.create_record("ABSENT")

        result = calculate_attendance_percentage(
            self.student, self.section
        )

        self.assertEqual(result["present"], 1)
        self.assertEqual(result["late"], 1)
        self.assertEqual(result["absent"], 2)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["attended"], 2)
        self.assertEqual(result["percentage"], 50.0)

    def test_no_records_returns_none_percentage(self):
        result = calculate_attendance_percentage(
            self.student, self.section
        )

        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["percentage"])

    def test_invalid_status_is_ignored(self):
        record = self.create_record("PRESENT")

        # Simulate unexpected data already stored in the database.
        AttendanceRecord.objects.filter(pk=record.pk).update(
            status="UNEXPECTED"
        )

        result = calculate_attendance_percentage(
            self.student, self.section
        )

        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["percentage"])

    def test_percentage_updates_after_attendance_correction(self):
        record = self.create_record("ABSENT")

        first_result = calculate_attendance_percentage(
            self.student, self.section
        )
        self.assertEqual(first_result["percentage"], 0.0)

        record.status = "PRESENT"
        record.save()

        updated_result = calculate_attendance_percentage(
            self.student, self.section
        )
        self.assertEqual(updated_result["percentage"], 100.0)

    def test_record_before_enrollment_is_excluded(self):
        yesterday = self.today - datetime.timedelta(days=1)
        self.create_record("PRESENT", yesterday)
        self.create_record("ABSENT", self.today)

        result = calculate_attendance_percentage(
            self.student, self.section
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["absent"], 1)
        self.assertEqual(result["percentage"], 0.0)

    def test_record_after_removal_is_excluded(self):
        yesterday = self.today - datetime.timedelta(days=1)
        ended_at = timezone.now() - datetime.timedelta(days=1)

        Enrollment.objects.filter(pk=self.enrollment.pk).update(
            enrolled_at=ended_at - datetime.timedelta(days=5),
            ended_at=ended_at,
            status=Enrollment.STATUS_REMOVED,
        )

        self.create_record("PRESENT", yesterday)
        self.create_record("ABSENT", self.today)

        result = calculate_attendance_percentage(
            self.student, self.section
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["present"], 1)
        self.assertEqual(result["percentage"], 100.0)
