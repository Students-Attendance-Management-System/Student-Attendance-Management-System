"""
Issue #19 - part 4: permissions of the pages added by Issues #16, #17 and #18
(report export, low-attendance alerts, student leave requests).

Reuses the users and sections from test_role_permissions.py.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from .models import (
    AttendanceAlert,
    AttendanceRecord,
    AttendanceSession,
    Enrollment,
    LeaveRequest,
    TeacherAssignment,
)
from .permissions import ROLE_STUDENT
from .test_role_permissions import SectionTestBase


class NewFeatureBase(SectionTestBase):
    """
    Section A: teacher assigned, student enrolled, with a record, a pending
    leave request and an alert. Section B: the same for other_teacher and
    other_student.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        today = timezone.localdate()

        Enrollment.objects.create(student=cls.student, section=cls.section_a)
        Enrollment.objects.create(
            student=cls.other_student, section=cls.section_b
        )

        cls.session_a = AttendanceSession.objects.create(
            section=cls.section_a, date=today, teacher=cls.teacher
        )
        cls.session_b = AttendanceSession.objects.create(
            section=cls.section_b, date=today, teacher=cls.other_teacher
        )
        AttendanceRecord.objects.create(
            session=cls.session_a, student=cls.student, status="PRESENT"
        )
        AttendanceRecord.objects.create(
            session=cls.session_b, student=cls.other_student, status="PRESENT"
        )

        cls.leave_a = LeaveRequest.objects.create(
            student=cls.student,
            section=cls.section_a,
            start_date=today,
            end_date=today,
            reason="Leave A",
        )
        cls.leave_b = LeaveRequest.objects.create(
            student=cls.other_student,
            section=cls.section_b,
            start_date=today,
            end_date=today,
            reason="Leave B",
        )

        cls.alert_a = AttendanceAlert.objects.create(
            student=cls.student,
            section=cls.section_a,
            attendance_percentage=Decimal("50.00"),
            threshold=Decimal("75.00"),
        )
        cls.alert_b = AttendanceAlert.objects.create(
            student=cls.other_student,
            section=cls.section_b,
            attendance_percentage=Decimal("40.00"),
            threshold=Decimal("75.00"),
        )


class LeaveStaffPermissionTests(NewFeatureBase):
    """/leave/staff/ pages (Issue #18: unauthorized users cannot decide)."""

    def list_url(self):
        return reverse("attendance:staff_leave_requests")

    def review_url(self, leave):
        return reverse("attendance:review_leave_request", args=[leave.pk])

    def decide(self, leave, action):
        return self.client.post(self.review_url(leave), {"action": action})

    def assert_still_pending(self, leave):
        leave.refresh_from_db()
        self.assertEqual(leave.status, LeaveRequest.STATUS_PENDING)
        self.assertIsNone(leave.reviewed_by)
        self.assertIsNone(leave.reviewed_at)

    def test_anonymous_is_sent_to_login(self):
        for url in (self.list_url(), self.review_url(self.leave_a)):
            with self.subTest(url=url):
                self.assert_sent_to_login(self.client.get(url), url)

    def test_student_and_no_role_get_403_on_the_list(self):
        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.list_url())
                self.assertEqual(response.status_code, 403)

    def test_teacher_sees_only_requests_of_assigned_sections(self):
        expected = {
            self.teacher: [self.leave_a.pk],
            self.other_teacher: [self.leave_b.pk],
        }

        for user, pks in expected.items():
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.list_url())
                shown = [r.pk for r in response.context["leave_requests"]]
                self.assertEqual(response.status_code, 200)
                self.assertEqual(shown, pks)

    def test_admin_and_superuser_see_every_request(self):
        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.list_url())
                shown = {r.pk for r in response.context["leave_requests"]}
                self.assertEqual(shown, {self.leave_a.pk, self.leave_b.pk})

    def test_review_page_only_accepts_post(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.review_url(self.leave_a))

        self.assertEqual(response.status_code, 405)
        self.assert_still_pending(self.leave_a)

    def test_anonymous_cannot_decide(self):
        url = self.review_url(self.leave_a)

        response = self.client.post(url, {"action": "APPROVED"})

        self.assert_sent_to_login(response, url)
        self.assert_still_pending(self.leave_a)

    def test_student_and_no_role_cannot_decide(self):
        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.decide(self.leave_a, "APPROVED")
                self.assertEqual(response.status_code, 403)

        self.assert_still_pending(self.leave_a)

    def test_unassigned_teacher_cannot_decide(self):
        self.client.force_login(self.other_teacher)

        response = self.decide(self.leave_a, "APPROVED")

        self.assertEqual(response.status_code, 404)
        self.assert_still_pending(self.leave_a)

    def test_assignment_without_teacher_role_cannot_decide(self):
        former_teacher = User.objects.create_user(username="perm_former_2")
        former_teacher.groups.add(Group.objects.get(name=ROLE_STUDENT))
        TeacherAssignment.objects.create(
            teacher=former_teacher, section=self.section_a
        )
        self.client.force_login(former_teacher)

        response = self.decide(self.leave_a, "APPROVED")

        self.assertEqual(response.status_code, 403)
        self.assert_still_pending(self.leave_a)

    def test_assigned_teacher_can_decide(self):
        self.client.force_login(self.teacher)

        response = self.decide(self.leave_a, "APPROVED")

        self.assertRedirects(
            response, self.list_url(), fetch_redirect_response=False
        )
        self.leave_a.refresh_from_db()
        self.assertEqual(self.leave_a.status, LeaveRequest.STATUS_APPROVED)
        self.assertEqual(self.leave_a.reviewed_by, self.teacher)

    def test_admin_can_decide(self):
        self.client.force_login(self.admin)

        self.decide(self.leave_b, "REJECTED")

        self.leave_b.refresh_from_db()
        self.assertEqual(self.leave_b.status, LeaveRequest.STATUS_REJECTED)
        self.assertEqual(self.leave_b.reviewed_by, self.admin)

    def test_a_decision_cannot_be_changed_afterwards(self):
        self.client.force_login(self.teacher)
        self.decide(self.leave_a, "APPROVED")

        self.client.force_login(self.admin)
        self.decide(self.leave_a, "REJECTED")

        self.leave_a.refresh_from_db()
        self.assertEqual(self.leave_a.status, LeaveRequest.STATUS_APPROVED)
        self.assertEqual(self.leave_a.reviewed_by, self.teacher)

    def test_invalid_decision_changes_nothing(self):
        self.client.force_login(self.teacher)

        self.decide(self.leave_a, "HACKED")
        self.decide(self.leave_a, "PENDING")

        self.assert_still_pending(self.leave_a)


class LeaveStudentPermissionTests(NewFeatureBase):
    """/leave/submit/ and /leave/my-requests/ are for Students only."""

    def submit_url(self):
        return reverse("attendance:submit_leave_request")

    def mine_url(self):
        return reverse("attendance:my_leave_requests")

    def submit_data(self, **changes):
        today = timezone.localdate().isoformat()
        data = {
            "section": self.section_a.pk,
            "start_date": today,
            "end_date": today,
            "reason": "Fever",
        }
        data.update(changes)
        return data

    def test_anonymous_is_sent_to_login(self):
        for url in (self.submit_url(), self.mine_url()):
            with self.subTest(url=url):
                self.assert_sent_to_login(self.client.get(url), url)

    def test_only_students_can_open_the_pages(self):
        refused = (
            self.teacher,
            self.admin,
            self.superuser,
            self.no_role_user,
        )

        for user in refused:
            self.client.force_login(user)

            for url in (self.submit_url(), self.mine_url()):
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.student)

        for url in (self.submit_url(), self.mine_url()):
            with self.subTest(user="student", url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_sees_only_their_own_requests(self):
        expected = {
            self.student: [self.leave_a.pk],
            self.other_student: [self.leave_b.pk],
        }

        for user, pks in expected.items():
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.mine_url())
                shown = [r.pk for r in response.context["leave_requests"]]
                self.assertEqual(shown, pks)

    def test_refused_users_cannot_submit_requests(self):
        count_before = LeaveRequest.objects.count()

        for user in (self.teacher, self.admin, self.superuser, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(
                    self.submit_url(), self.submit_data()
                )
                self.assertEqual(response.status_code, 403)

        self.assertEqual(LeaveRequest.objects.count(), count_before)

    def test_student_cannot_forge_owner_status_or_reviewer(self):
        self.client.force_login(self.student)

        response = self.client.post(
            self.submit_url(),
            self.submit_data(
                student=self.other_student.pk,
                status="APPROVED",
                reviewed_by=self.teacher.pk,
            ),
        )

        self.assertRedirects(
            response, self.mine_url(), fetch_redirect_response=False
        )
        leave = LeaveRequest.objects.get(reason="Fever")
        self.assertEqual(leave.student, self.student)
        self.assertEqual(leave.status, LeaveRequest.STATUS_PENDING)
        self.assertIsNone(leave.reviewed_by)

    def test_student_cannot_request_leave_for_a_section_not_enrolled_in(self):
        self.client.force_login(self.student)
        count_before = LeaveRequest.objects.count()

        response = self.client.post(
            self.submit_url(), self.submit_data(section=self.section_b.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), count_before)

    def test_leave_cannot_start_in_the_past(self):
        self.client.force_login(self.student)
        count_before = LeaveRequest.objects.count()
        yesterday = timezone.localdate() - timedelta(days=1)

        response = self.client.post(
            self.submit_url(),
            self.submit_data(start_date=yesterday.isoformat()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), count_before)


class ReportExportPermissionTests(NewFeatureBase):
    """/reports/ pages (SRS SAMS-F-013: Admin and Teacher may export)."""

    def form_url(self):
        return reverse("attendance:report_form")

    def export_url(self, section):
        base = reverse("attendance:export_report")
        return f"{base}?section={section.pk}"

    def body(self, response):
        return response.content.decode("utf-8")

    def test_anonymous_is_sent_to_login(self):
        for name in ("attendance:report_form", "attendance:export_report"):
            url = reverse(name)

            with self.subTest(url=url):
                self.assert_sent_to_login(self.client.get(url), url)

    def test_students_and_no_role_cannot_export(self):
        for user in (self.student, self.other_student, self.no_role_user):
            self.client.force_login(user)

            for section in (self.section_a, self.section_b):
                with self.subTest(user=user.username, section=section.name):
                    response = self.client.get(self.export_url(section))
                    self.assertEqual(response.status_code, 403)

    def test_student_sees_no_sections_on_the_report_form(self):
        self.client.force_login(self.student)

        response = self.client.get(self.form_url())

        queryset = response.context["form"].fields["section"].queryset
        self.assertEqual(queryset.count(), 0)

    def test_assignment_without_teacher_role_cannot_export(self):
        former_teacher = User.objects.create_user(username="perm_former_3")
        former_teacher.groups.add(Group.objects.get(name=ROLE_STUDENT))
        TeacherAssignment.objects.create(
            teacher=former_teacher, section=self.section_a
        )
        self.client.force_login(former_teacher)

        response = self.client.get(self.export_url(self.section_a))

        self.assertEqual(response.status_code, 403)

    def test_teacher_exports_only_their_own_section(self):
        self.client.force_login(self.teacher)

        own = self.client.get(self.export_url(self.section_a))
        other = self.client.get(self.export_url(self.section_b))

        self.assertEqual(own.status_code, 200)
        self.assertIn("text/csv", own["Content-Type"])
        self.assertIn("perm_student", self.body(own))
        self.assertNotIn("perm_other_student", self.body(own))
        self.assertEqual(other.status_code, 403)

    def test_admin_and_superuser_can_export_any_section(self):
        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            for section in (self.section_a, self.section_b):
                with self.subTest(user=user.username, section=section.name):
                    response = self.client.get(self.export_url(section))
                    self.assertEqual(response.status_code, 200)

    def test_unknown_section_is_refused(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("attendance:export_report") + "?section=999999"
        )

        self.assertEqual(response.status_code, 403)

    def test_formula_characters_in_names_are_neutralised(self):
        user = User.objects.create_user(username="=cmd")
        user.groups.add(Group.objects.get(name=ROLE_STUDENT))
        Enrollment.objects.create(student=user, section=self.section_a)
        AttendanceRecord.objects.create(
            session=self.session_a, student=user, status="PRESENT"
        )
        self.client.force_login(self.admin)

        response = self.client.get(self.export_url(self.section_a))

        self.assertIn("'=cmd", self.body(response))


class AlertPermissionTests(NewFeatureBase):
    """/alerts/ shows each role only the alerts it may see."""

    def url(self):
        return reverse("attendance:alert_list")

    def shown(self, response):
        return {alert.pk for alert in response.context["alerts"]}

    def test_anonymous_is_sent_to_login(self):
        self.assert_sent_to_login(self.client.get(self.url()), self.url())

    def test_user_without_role_gets_403(self):
        self.client.force_login(self.no_role_user)

        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_student_sees_only_their_own_alert(self):
        expected = {
            self.student: {self.alert_a.pk},
            self.other_student: {self.alert_b.pk},
        }

        for user, pks in expected.items():
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.url())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.shown(response), pks)

    def test_teacher_sees_only_alerts_of_assigned_sections(self):
        expected = {
            self.teacher: {self.alert_a.pk},
            self.other_teacher: {self.alert_b.pk},
        }

        for user, pks in expected.items():
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.url())
                self.assertEqual(self.shown(response), pks)

    def test_admin_and_superuser_see_every_alert(self):
        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.url())
                self.assertEqual(
                    self.shown(response), {self.alert_a.pk, self.alert_b.pk}
                )

    def test_inactive_alerts_are_not_shown(self):
        self.alert_a.is_active = False
        self.alert_a.save()
        self.client.force_login(self.student)

        response = self.client.get(self.url())

        self.assertEqual(self.shown(response), set())
