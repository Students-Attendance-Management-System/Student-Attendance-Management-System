
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


class AttendanceBoundaryTests(TestCase):
    """
    Boundary and edge cases for calculate_attendance_percentage (Issue #23).

    These extend AttendancePercentageTests above without repeating it:
    percentages right around 75%, rounding, enrollment-period edges and
    records that must not be counted.
    """

    def setUp(self):
        self.student = User.objects.create_user(username="boundary_student")
        self.other_student = User.objects.create_user(
            username="boundary_other"
        )

        self.course = Course.objects.create(
            code="BND101",
            name="Boundary Testing",
        )
        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-27",
        )
        self.other_section = Section.objects.create(
            course=self.course,
            name="B",
            academic_year="2026-27",
        )

        self.today = timezone.localdate()

    def enroll(self, student=None, section=None, started=None, ended=None):
        """Create an enrollment with chosen start/end moments."""
        enrollment = Enrollment.objects.create(
            student=student or self.student,
            section=section or self.section,
        )
        values = {}
        if started is not None:
            values["enrolled_at"] = started
        if ended is not None:
            values["ended_at"] = ended
            values["status"] = Enrollment.STATUS_REMOVED
        if values:
            Enrollment.objects.filter(pk=enrollment.pk).update(**values)
        return enrollment

    def mark(self, status, session_date=None, student=None, section=None):
        session = AttendanceSession.objects.create(
            section=section or self.section,
            date=session_date or self.today,
        )
        return AttendanceRecord.objects.create(
            session=session,
            student=student or self.student,
            status=status,
        )

    def mark_many(self, attended, absent):
        for _ in range(attended):
            self.mark("PRESENT")
        for _ in range(absent):
            self.mark("ABSENT")

    def result(self, **kwargs):
        return calculate_attendance_percentage(
            self.student, self.section, **kwargs
        )

    # ---- percentage boundaries -------------------------------------

    def test_exactly_75_percent(self):
        self.enroll()
        self.mark_many(attended=3, absent=1)

        self.assertEqual(self.result()["percentage"], 75.0)

    def test_just_below_75_percent(self):
        self.enroll()
        self.mark_many(attended=20, absent=7)  # 20 of 27

        self.assertEqual(self.result()["percentage"], 74.07)

    def test_just_above_75_percent(self):
        self.enroll()
        self.mark_many(attended=28, absent=9)  # 28 of 37

        self.assertEqual(self.result()["percentage"], 75.68)

    def test_percentage_is_rounded_to_two_decimals(self):
        self.enroll()
        self.mark_many(attended=2, absent=1)

        self.assertEqual(self.result()["percentage"], 66.67)

    def test_all_late_counts_as_fully_attended(self):
        self.enroll()
        for _ in range(3):
            self.mark("LATE")

        result = self.result()

        self.assertEqual(result["late"], 3)
        self.assertEqual(result["present"], 0)
        self.assertEqual(result["attended"], 3)
        self.assertEqual(result["percentage"], 100.0)

    # ---- records that must not be counted --------------------------

    def test_other_students_records_are_ignored(self):
        self.enroll()
        self.enroll(student=self.other_student)
        self.mark("PRESENT")
        self.mark("ABSENT", student=self.other_student)

        result = self.result()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["percentage"], 100.0)

    def test_other_sections_records_are_ignored(self):
        self.enroll()
        self.enroll(section=self.other_section)
        self.mark("PRESENT")
        self.mark("ABSENT", section=self.other_section)

        result = self.result()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["percentage"], 100.0)

    def test_record_without_any_enrollment_is_ignored(self):
        self.mark("PRESENT")

        result = self.result()

        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["percentage"])

    # ---- enrollment-period edges -----------------------------------

    def test_session_on_the_day_enrollment_ended_is_counted(self):
        self.enroll(
            started=timezone.now() - datetime.timedelta(days=5),
            ended=timezone.now(),
        )
        self.mark("PRESENT", self.today)

        self.assertEqual(self.result()["total"], 1)

    def test_session_the_day_after_enrollment_ended_is_not_counted(self):
        self.enroll(
            started=timezone.now() - datetime.timedelta(days=5),
            ended=timezone.now(),
        )
        tomorrow = self.today + datetime.timedelta(days=1)
        self.mark("ABSENT", tomorrow)

        result = self.result()

        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["percentage"])

    def test_gap_between_two_enrollment_periods_is_not_counted(self):
        now = timezone.now()
        # First period: 10 days ago to 5 days ago (student was removed).
        self.enroll(
            started=now - datetime.timedelta(days=10),
            ended=now - datetime.timedelta(days=5),
        )
        # Second period: re-enrolled 2 days ago, still active.
        self.enroll(started=now - datetime.timedelta(days=2))

        self.mark("PRESENT", self.today - datetime.timedelta(days=7))
        self.mark("ABSENT", self.today - datetime.timedelta(days=3))  # gap
        self.mark("ABSENT", self.today)

        result = self.result()

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["present"], 1)
        self.assertEqual(result["absent"], 1)
        self.assertEqual(result["percentage"], 50.0)

    # ---- date range edges ------------------------------------------

    def test_date_range_includes_its_first_and_last_day(self):
        self.enroll(started=timezone.now() - datetime.timedelta(days=10))
        day1 = self.today - datetime.timedelta(days=3)
        day2 = self.today - datetime.timedelta(days=2)
        day3 = self.today - datetime.timedelta(days=1)
        self.mark("PRESENT", day1)
        self.mark("ABSENT", day2)
        self.mark("PRESENT", day3)

        only_middle = self.result(start_date=day2, end_date=day2)
        first_two = self.result(start_date=day1, end_date=day2)

        self.assertEqual(only_middle["total"], 1)
        self.assertEqual(only_middle["percentage"], 0.0)
        self.assertEqual(first_two["total"], 2)
        self.assertEqual(first_two["percentage"], 50.0)
