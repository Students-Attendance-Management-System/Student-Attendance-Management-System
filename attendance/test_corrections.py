from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .correction_services import (
    apply_correction,
    correction_deadline,
    is_correction_window_open,
)
from .models import (
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceSession,
    Course,
    Section,
    TeacherAssignment,
)


def make_user(username, role=None, **extra):
    user = User.objects.create_user(
        username=username, password="pass12345", **extra
    )
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


class CorrectionTestBase(TestCase):
    def setUp(self):
        course = Course.objects.create(code="CS101", name="Intro")
        self.section = Section.objects.create(
            course=course, name="A", academic_year="2026"
        )
        self.teacher = make_user("teacher1", "Teacher")
        self.other_teacher = make_user("teacher2", "Teacher")
        self.student = make_user("student1", "Student")
        self.admin = make_user("admin1", is_superuser=True)
        TeacherAssignment.objects.create(
            teacher=self.teacher, section=self.section
        )
        self.session = AttendanceSession.objects.create(
            section=self.section,
            date=timezone.localdate(),
            teacher=self.teacher,
        )
        self.record = AttendanceRecord.objects.create(
            session=self.session, student=self.student, status="ABSENT"
        )

    def make_old_record(self):
        old_session = AttendanceSession.objects.create(
            section=self.section,
            date=timezone.localdate() - timedelta(days=10),
            teacher=self.teacher,
        )
        return AttendanceRecord.objects.create(
            session=old_session, student=self.student, status="ABSENT"
        )


class CorrectionWindowTests(CorrectionTestBase):
    def test_correction_within_window_works(self):
        apply_correction(self.record, "PRESENT", self.teacher, "Marked wrongly")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "PRESENT")

    def test_correction_after_window_is_rejected(self):
        old = self.make_old_record()
        with self.assertRaises(ValidationError):
            apply_correction(old, "PRESENT", self.teacher, "Too late")
        old.refresh_from_db()
        self.assertEqual(old.status, "ABSENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_expired_window_blocks_admin_too(self):
        old = self.make_old_record()
        with self.assertRaises(ValidationError):
            apply_correction(old, "PRESENT", self.admin, "Too late")

    def test_window_boundary(self):
        deadline = correction_deadline(self.session)
        self.assertTrue(is_correction_window_open(self.session, now=deadline))
        self.assertFalse(
            is_correction_window_open(
                self.session, now=deadline + timedelta(seconds=1)
            )
        )

    def test_window_length_comes_from_setting(self):
        with override_settings(ATTENDANCE_CORRECTION_WINDOW_HOURS=24):
            short = correction_deadline(self.session)
        with override_settings(ATTENDANCE_CORRECTION_WINDOW_HOURS=48):
            long = correction_deadline(self.session)
        self.assertEqual(long - short, timedelta(hours=24))


class CorrectionValidationTests(CorrectionTestBase):
    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            apply_correction(self.record, "PRESENT", self.teacher, "   ")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            apply_correction(self.record, "MAYBE", self.teacher, "Reason")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "ABSENT")

    def test_same_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            apply_correction(self.record, "ABSENT", self.teacher, "Reason")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)


class CorrectionAuthorizationTests(CorrectionTestBase):
    def test_unassigned_teacher_cannot_correct(self):
        with self.assertRaises(PermissionDenied):
            apply_correction(self.record, "PRESENT", self.other_teacher, "Reason")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "ABSENT")

    def test_student_cannot_correct(self):
        with self.assertRaises(PermissionDenied):
            apply_correction(self.record, "PRESENT", self.student, "Reason")

    def test_admin_can_correct(self):
        apply_correction(self.record, "LATE", self.admin, "Admin fix")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "LATE")


class CorrectionHistoryTests(CorrectionTestBase):
    def test_correction_is_traceable(self):
        apply_correction(self.record, "PRESENT", self.teacher, "Marked wrongly")
        entry = AttendanceCorrection.objects.get()
        self.assertEqual(entry.record, self.record)
        self.assertEqual(entry.old_status, "ABSENT")
        self.assertEqual(entry.new_status, "PRESENT")
        self.assertEqual(entry.corrected_by, self.teacher)
        self.assertEqual(entry.reason, "Marked wrongly")
        self.assertIsNotNone(entry.corrected_at)

    def test_history_keeps_every_correction(self):
        apply_correction(self.record, "PRESENT", self.teacher, "First")
        apply_correction(self.record, "LATE", self.teacher, "Second")
        history = list(self.record.corrections.all())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].reason, "Second")
        self.assertEqual(history[0].old_status, "PRESENT")
        self.assertEqual(history[1].old_status, "ABSENT")


class CorrectionViewTests(CorrectionTestBase):
    def url(self, record):
        return reverse("attendance:correct_record", args=[record.pk])

    def test_teacher_can_correct_through_view(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            self.url(self.record),
            {"new_status": "PRESENT", "reason": "Marked wrongly"},
        )
        self.assertRedirects(response, self.url(self.record))
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 1)

    def test_view_rejects_post_after_window(self):
        old = self.make_old_record()
        self.client.force_login(self.teacher)
        response = self.client.post(
            self.url(old),
            {"new_status": "PRESENT", "reason": "Too late"},
        )
        self.assertEqual(response.status_code, 200)
        old.refresh_from_db()
        self.assertEqual(old.status, "ABSENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_unassigned_teacher_gets_403(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(self.url(self.record)).status_code, 403)
        response = self.client.post(
            self.url(self.record),
            {"new_status": "PRESENT", "reason": "Reason"},
        )
        self.assertEqual(response.status_code, 403)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "ABSENT")

    def test_student_gets_403(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url(self.record)).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url(self.record))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_session_records_page_for_assigned_teacher(self):
        self.client.force_login(self.teacher)
        url = reverse("attendance:session_records", args=[self.session.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_session_records_page_forbidden_for_other_teacher(self):
        self.client.force_login(self.other_teacher)
        url = reverse("attendance:session_records", args=[self.session.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
