
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    LeaveRequest,
    Section,
    TeacherAssignment,
)
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER


class LeaveRequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create role groups.
        cls.admin_group = Group.objects.create(name=ROLE_ADMIN)
        cls.teacher_group = Group.objects.create(name=ROLE_TEACHER)
        cls.student_group = Group.objects.create(name=ROLE_STUDENT)

        # Create users.
        cls.admin = User.objects.create_user(
            username="leave_admin",
            password="test-password-123",
        )
        cls.admin.groups.add(cls.admin_group)

        cls.teacher = User.objects.create_user(
            username="leave_teacher",
            password="test-password-123",
        )
        cls.teacher.groups.add(cls.teacher_group)

        cls.other_teacher = User.objects.create_user(
            username="other_leave_teacher",
            password="test-password-123",
        )
        cls.other_teacher.groups.add(cls.teacher_group)

        cls.student = User.objects.create_user(
            username="leave_student",
            password="test-password-123",
        )
        cls.student.groups.add(cls.student_group)

        cls.other_student = User.objects.create_user(
            username="other_leave_student",
            password="test-password-123",
        )
        cls.other_student.groups.add(cls.student_group)

        # Create course and sections.
        cls.course = Course.objects.create(
            code="LEAVE101",
            name="Leave Management Test Course",
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

        # Enroll students in Section A.
        Enrollment.objects.create(
            student=cls.student,
            section=cls.section,
            status=Enrollment.STATUS_ACTIVE,
        )

        Enrollment.objects.create(
            student=cls.other_student,
            section=cls.section,
            status=Enrollment.STATUS_ACTIVE,
        )

        # Assign the teacher to Section A only.
        TeacherAssignment.objects.create(
            teacher=cls.teacher,
            section=cls.section,
        )

        cls.start_date = timezone.localdate() + timedelta(days=1)
        cls.end_date = timezone.localdate() + timedelta(days=2)

    def create_leave_request(self, student=None, section=None):
        return LeaveRequest.objects.create(
            student=student or self.student,
            section=section or self.section,
            start_date=self.start_date,
            end_date=self.end_date,
            reason="Personal reasons",
        )

    def test_student_can_submit_leave_request(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("attendance:submit_leave_request"),
            {
                "section": self.section.pk,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "reason": "Personal reasons",
            },
        )

        self.assertRedirects(
            response,
            reverse("attendance:my_leave_requests"),
        )

        leave_request = LeaveRequest.objects.get(student=self.student)

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_PENDING,
        )
        self.assertIsNone(leave_request.reviewed_by)
        self.assertIsNone(leave_request.reviewed_at)

    def test_student_cannot_submit_for_unenrolled_section(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("attendance:submit_leave_request"),
            {
                "section": self.other_section.pk,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "reason": "Personal reasons",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 0)

    def test_invalid_date_range_is_rejected(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("attendance:submit_leave_request"),
            {
                "section": self.section.pk,
                "start_date": self.end_date,
                "end_date": self.start_date,
                "reason": "Personal reasons",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 0)

    def test_student_can_view_own_leave_requests(self):
        self.create_leave_request(student=self.student)
        self.create_leave_request(student=self.other_student)

        self.client.force_login(self.student)

        response = self.client.get(
            reverse("attendance:my_leave_requests")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personal reasons")
        self.assertEqual(len(response.context["leave_requests"]), 1)
        self.assertEqual(
            response.context["leave_requests"][0].student,
            self.student,
        )

    def test_admin_can_view_all_leave_requests(self):
        self.create_leave_request(student=self.student)
        self.create_leave_request(student=self.other_student)

        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("attendance:staff_leave_requests")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["leave_requests"]), 2)

    def test_assigned_teacher_can_view_section_requests(self):
        self.create_leave_request()

        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("attendance:staff_leave_requests")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["leave_requests"]), 1)

    def test_teacher_cannot_view_unassigned_section_requests(self):
        self.create_leave_request(section=self.other_section)

        self.client.force_login(self.other_teacher)

        response = self.client.get(
            reverse("attendance:staff_leave_requests")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["leave_requests"]), 0)

    def test_student_cannot_access_staff_leave_requests(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("attendance:staff_leave_requests")
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_approve_leave_request(self):
        leave_request = self.create_leave_request()

        self.client.force_login(self.admin)

        response = self.client.post(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        self.assertRedirects(
            response,
            reverse("attendance:staff_leave_requests"),
        )

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_APPROVED,
        )
        self.assertEqual(leave_request.reviewed_by, self.admin)
        self.assertIsNotNone(leave_request.reviewed_at)

    def test_assigned_teacher_can_reject_leave_request(self):
        leave_request = self.create_leave_request()

        self.client.force_login(self.teacher)

        self.client.post(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_REJECTED},
        )

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_REJECTED,
        )
        self.assertEqual(leave_request.reviewed_by, self.teacher)
        self.assertIsNotNone(leave_request.reviewed_at)

    def test_student_cannot_approve_or_reject_leave_request(self):
        leave_request = self.create_leave_request()

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        self.assertEqual(response.status_code, 403)

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_PENDING,
        )
        self.assertIsNone(leave_request.reviewed_by)

    def test_teacher_cannot_review_unassigned_section_request(self):
        leave_request = self.create_leave_request(
            section=self.other_section
        )

        self.client.force_login(self.other_teacher)

        response = self.client.post(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        self.assertEqual(response.status_code, 404)

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_PENDING,
        )

    def test_already_reviewed_request_cannot_be_decided_again(self):
        leave_request = self.create_leave_request()

        self.client.force_login(self.admin)

        review_url = reverse(
            "attendance:review_leave_request",
            args=[leave_request.pk],
        )

        self.client.post(
            review_url,
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        leave_request.refresh_from_db()
        original_reviewed_at = leave_request.reviewed_at

        self.client.post(
            review_url,
            {"action": LeaveRequest.STATUS_REJECTED},
        )

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_APPROVED,
        )
        self.assertEqual(leave_request.reviewed_by, self.admin)
        self.assertEqual(
            leave_request.reviewed_at,
            original_reviewed_at,
        )

    def test_get_request_cannot_change_leave_decision(self):
        leave_request = self.create_leave_request()

        self.client.force_login(self.admin)

        response = self.client.get(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        self.assertEqual(response.status_code, 405)

        leave_request.refresh_from_db()

        self.assertEqual(
            leave_request.status,
            LeaveRequest.STATUS_PENDING,
        )

    def test_approval_does_not_modify_attendance_records(self):
        session = AttendanceSession.objects.create(
            section=self.section,
            date=self.start_date,
            teacher=self.teacher,
        )

        attendance_record = AttendanceRecord.objects.create(
            session=session,
            student=self.student,
            status="ABSENT",
        )

        leave_request = self.create_leave_request()

        self.client.force_login(self.admin)

        self.client.post(
            reverse(
                "attendance:review_leave_request",
                args=[leave_request.pk],
            ),
            {"action": LeaveRequest.STATUS_APPROVED},
        )

        attendance_record.refresh_from_db()

        self.assertEqual(attendance_record.status, "ABSENT")
