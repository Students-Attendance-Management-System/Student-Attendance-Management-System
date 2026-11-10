
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from .attendance_services import submit_attendance
from .models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Section,
    TeacherAssignment,
)


def make_user(username, role):
    user = User.objects.create_user(
        username=username,
        password="TestPass123!",
    )
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


class AttendanceSubmissionTests(TestCase):

    def setUp(self):
        self.admin = make_user("admin", "Admin")
        self.teacher = make_user("teacher", "Teacher")
        self.other_teacher = make_user("other_teacher", "Teacher")
        self.student1 = make_user("student1", "Student")
        self.student2 = make_user("student2", "Student")
        self.unenrolled_student = make_user("student3", "Student")

        self.course = Course.objects.create(
            code="CS101",
            name="Intro to Computing",
        )

        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-27",
        )

        self.session = AttendanceSession.objects.create(
            section=self.section,
            date=timezone.localdate(),
            teacher=self.teacher,
            topic="Introduction",
        )

        TeacherAssignment.objects.create(
            teacher=self.teacher,
            section=self.section,
        )

        Enrollment.objects.create(
            student=self.student1,
            section=self.section,
        )

        Enrollment.objects.create(
            student=self.student2,
            section=self.section,
        )

    def test_valid_attendance_submission(self):
        result = submit_attendance(
            self.teacher,
            self.session.id,
            {
                self.student1.id: "PRESENT",
                self.student2.id: "ABSENT",
            },
        )

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(
            AttendanceRecord.objects.filter(
                session=self.session
            ).count(),
            2,
        )

    def test_duplicate_attendance_records_are_not_created(self):
        submit_attendance(
            self.teacher,
            self.session.id,
            {self.student1.id: "PRESENT"},
        )

        submit_attendance(
            self.teacher,
            self.session.id,
            {self.student1.id: "PRESENT"},
        )

        self.assertEqual(
            AttendanceRecord.objects.filter(
                session=self.session,
                student=self.student1,
            ).count(),
            1,
        )

    def test_repeated_submission_does_not_overwrite_existing_record(self):
        submit_attendance(
            self.teacher,
            self.session.id,
            {self.student1.id: "PRESENT"},
        )

        submit_attendance(
            self.teacher,
            self.session.id,
            {self.student1.id: "ABSENT"},
        )

        record = AttendanceRecord.objects.get(
            session=self.session,
            student=self.student1,
        )

        self.assertEqual(record.status, "PRESENT")

    def test_invalid_student_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_attendance(
                self.teacher,
                self.session.id,
                {self.unenrolled_student.id: "PRESENT"},
            )

        self.assertEqual(
            AttendanceRecord.objects.filter(
                session=self.session
            ).count(),
            0,
        )

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_attendance(
                self.teacher,
                self.session.id,
                {self.student1.id: "INVALID"},
            )

        self.assertEqual(
            AttendanceRecord.objects.filter(
                session=self.session
            ).count(),
            0,
        )

    def test_unassigned_teacher_cannot_submit_attendance(self):
        with self.assertRaises(PermissionDenied):
            submit_attendance(
                self.other_teacher,
                self.session.id,
                {self.student1.id: "PRESENT"},
            )

        self.assertEqual(
            AttendanceRecord.objects.filter(
                session=self.session
            ).count(),
            0,
        )

    def test_admin_can_submit_attendance(self):
        result = submit_attendance(
            self.admin,
            self.session.id,
            {self.student1.id: "PRESENT"},
        )

        self.assertEqual(result["created"], 1)
        self.assertTrue(
            AttendanceRecord.objects.filter(
                session=self.session,
                student=self.student1,
            ).exists()
        )
