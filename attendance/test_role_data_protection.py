"""
Issue #19 - part 3: attendance, corrections, enrollment pages and
student-data protection.

Reuses the users and sections from test_role_permissions.py.

The class SuspectedDefectTests at the bottom states what the SRS says SHOULD
happen (SAMS-SR-004, SAMS-F-001, SAMS-SR-005, SAMS-SR-001). A failing test
there is a defect that must be documented and then fixed or marked.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from .correction_services import apply_correction
from .models import (
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceSession,
    Enrollment,
    TeacherAssignment,
)
from .permissions import ROLE_STUDENT
from .test_role_permissions import SectionTestBase


class DataTestBase(SectionTestBase):
    """
    Section A (teacher assigned): student enrolled, one session with a record.
    Section B (other_teacher assigned): other_student enrolled, one session
    with a record.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        today = timezone.localdate()

        cls.enrollment_a = Enrollment.objects.create(
            student=cls.student, section=cls.section_a
        )
        cls.enrollment_b = Enrollment.objects.create(
            student=cls.other_student, section=cls.section_b
        )

        cls.session_a = AttendanceSession.objects.create(
            section=cls.section_a, date=today, teacher=cls.teacher
        )
        cls.session_a_empty = AttendanceSession.objects.create(
            section=cls.section_a, date=today, teacher=cls.teacher
        )
        cls.session_b = AttendanceSession.objects.create(
            section=cls.section_b, date=today, teacher=cls.other_teacher
        )
        cls.session_a_old = AttendanceSession.objects.create(
            section=cls.section_a,
            date=today - timedelta(days=10),
            teacher=cls.teacher,
        )

        cls.record_a = AttendanceRecord.objects.create(
            session=cls.session_a, student=cls.student, status="PRESENT"
        )
        cls.record_b = AttendanceRecord.objects.create(
            session=cls.session_b, student=cls.other_student, status="PRESENT"
        )
        cls.record_a_old = AttendanceRecord.objects.create(
            session=cls.session_a_old, student=cls.student, status="PRESENT"
        )

    def mark_url(self, session):
        return reverse("attendance:mark_attendance", args=[session.pk])

    def records_url(self, session):
        return reverse("attendance:session_records", args=[session.pk])

    def correct_url(self, record):
        return reverse("attendance:correct_record", args=[record.pk])


class AuthenticationBehaviourTests(SectionTestBase):
    """Login, logout and inactive accounts (SRS SAMS-F-001, SAMS-F-003)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.password = "S3cure-test-pass"
        cls.login_admin = User.objects.create_user(
            username="perm_login_admin", password=cls.password
        )
        cls.login_admin.groups.add(Group.objects.get(name="Admin"))

        cls.login_inactive = User.objects.create_user(
            username="perm_login_inactive",
            password=cls.password,
            is_active=False,
        )

    def test_login_with_next_returns_to_the_requested_page(self):
        target = reverse("user_list")

        response = self.client.post(
            f"{reverse('login')}?next={target}",
            {"username": "perm_login_admin", "password": self.password},
        )

        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_wrong_password_does_not_log_in(self):
        response = self.client.post(
            reverse("login"),
            {"username": "perm_login_admin", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_cannot_log_in(self):
        response = self.client.post(
            reverse("login"),
            {"username": "perm_login_inactive", "password": self.password},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_out_user_loses_access(self):
        url = reverse("user_list")

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.logout()
        self.assert_sent_to_login(self.client.get(url), url)


class AttendanceMarkPermissionTests(DataTestBase):
    """/sessions/<id>/mark/ (SRS SAMS-F-005, SAMS-SR-002, SAMS-SR-004)."""

    def test_anonymous_is_sent_to_login(self):
        url = self.mark_url(self.session_a)
        self.assert_sent_to_login(self.client.get(url), url)

    def test_student_and_no_role_get_403(self):
        url = self.mark_url(self.session_a)

        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_unassigned_teacher_gets_403(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(self.mark_url(self.session_a))

        self.assertEqual(response.status_code, 403)

    def test_assigned_teacher_admin_and_superuser_can_open(self):
        for user in (self.teacher, self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.mark_url(self.session_a))
                self.assertEqual(response.status_code, 200)

    def test_refused_users_cannot_save_attendance(self):
        url = self.mark_url(self.session_a_empty)
        data = {f"status_{self.student.pk}": "ABSENT"}
        count_before = AttendanceRecord.objects.count()

        for user in (self.other_teacher, self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.post(url, data).status_code, 403)

        self.assertEqual(AttendanceRecord.objects.count(), count_before)

    def test_anonymous_cannot_save_attendance(self):
        url = self.mark_url(self.session_a_empty)
        count_before = AttendanceRecord.objects.count()

        response = self.client.post(
            url, {f"status_{self.student.pk}": "ABSENT"}
        )

        self.assert_sent_to_login(response, url)
        self.assertEqual(AttendanceRecord.objects.count(), count_before)

    def test_assigned_teacher_can_save_attendance(self):
        self.client.force_login(self.teacher)
        url = self.mark_url(self.session_a_empty)

        response = self.client.post(
            url, {f"status_{self.student.pk}": "ABSENT"}
        )

        self.assertRedirects(response, url, fetch_redirect_response=False)
        record = AttendanceRecord.objects.get(
            session=self.session_a_empty, student=self.student
        )
        self.assertEqual(record.status, "ABSENT")

    def test_teacher_cannot_mark_a_student_from_another_section(self):
        """Changing the student ID in the form must not create a record."""
        self.client.force_login(self.teacher)
        url = self.mark_url(self.session_a_empty)

        response = self.client.post(
            url, {f"status_{self.other_student.pk}": "ABSENT"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AttendanceRecord.objects.filter(
                session=self.session_a_empty, student=self.other_student
            ).exists()
        )

    def test_existing_record_is_not_overwritten_by_marking(self):
        self.client.force_login(self.teacher)

        self.client.post(
            self.mark_url(self.session_a),
            {f"status_{self.student.pk}": "ABSENT"},
        )

        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, "PRESENT")


class SessionRecordsPermissionTests(DataTestBase):
    """/sessions/<id>/records/ shows who was present or absent."""

    def test_anonymous_is_sent_to_login(self):
        url = self.records_url(self.session_a)
        self.assert_sent_to_login(self.client.get(url), url)

    def test_student_and_no_role_get_403(self):
        url = self.records_url(self.session_a)

        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_unassigned_teacher_gets_403(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(self.records_url(self.session_a))

        self.assertEqual(response.status_code, 403)

    def test_assigned_teacher_admin_and_superuser_can_open(self):
        for user in (self.teacher, self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.records_url(self.session_a))
                self.assertEqual(response.status_code, 200)

    def test_unknown_session_gives_404(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("attendance:session_records", args=[999999])
        )

        self.assertEqual(response.status_code, 404)


class CorrectionPermissionTests(DataTestBase):
    """/records/<id>/correct/ (SRS SAMS-SR-002, test TC-Sec-02)."""

    valid_data = {"new_status": "ABSENT", "reason": "Marked wrongly"}

    def test_anonymous_is_sent_to_login(self):
        url = self.correct_url(self.record_a)
        self.assert_sent_to_login(self.client.get(url), url)

    def test_student_and_no_role_get_403(self):
        url = self.correct_url(self.record_a)

        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_unassigned_teacher_gets_403(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(self.correct_url(self.record_a))

        self.assertEqual(response.status_code, 403)

    def test_assigned_teacher_admin_and_superuser_can_open(self):
        for user in (self.teacher, self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(self.correct_url(self.record_a))
                self.assertEqual(response.status_code, 200)

    def test_unknown_record_gives_404(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("attendance:correct_record", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_refused_users_cannot_change_a_record(self):
        """Including the student whose own record it is."""
        url = self.correct_url(self.record_a)

        for user in (self.student, self.other_teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(url, self.valid_data)
                self.assertEqual(response.status_code, 403)

        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_anonymous_cannot_change_a_record(self):
        url = self.correct_url(self.record_a)

        response = self.client.post(url, self.valid_data)

        self.assert_sent_to_login(response, url)
        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_assigned_teacher_can_correct_and_it_is_logged(self):
        self.client.force_login(self.teacher)
        url = self.correct_url(self.record_a)

        response = self.client.post(url, self.valid_data)

        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, "ABSENT")
        correction = AttendanceCorrection.objects.get()
        self.assertEqual(correction.old_status, "PRESENT")
        self.assertEqual(correction.corrected_by, self.teacher)

    def test_correction_is_refused_after_the_window_closes(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            self.correct_url(self.record_a_old), self.valid_data
        )

        self.assertEqual(response.status_code, 200)
        self.record_a_old.refresh_from_db()
        self.assertEqual(self.record_a_old.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_service_layer_also_refuses_unauthorized_users(self):
        """Even if the view were bypassed, the service says no."""
        for user in (self.student, self.other_teacher, self.no_role_user):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied):
                    apply_correction(
                        self.record_a, "ABSENT", user, "Not allowed"
                    )

        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.count(), 0)


class EnrollmentPagesPermissionTests(DataTestBase):
    """/enrollments/ pages (SRS SAMS-F-006, SAMS-F-007)."""

    def view_urls(self):
        return {
            "section_list": reverse("enrollment_section_list"),
            "roster": reverse(
                "enrollment_section_roster", args=[self.section_a.pk]
            ),
            "history": reverse(
                "enrollment_student_history", args=[self.student.pk]
            ),
        }

    def admin_urls(self):
        return {
            "enroll": reverse("enroll_student"),
            "transfer": reverse(
                "transfer_enrollment", args=[self.enrollment_a.pk]
            ),
        }

    def remove_url(self):
        return reverse("unenroll_student", args=[self.enrollment_a.pk])

    def test_anonymous_is_sent_to_login(self):
        urls = list(self.view_urls().values()) + list(
            self.admin_urls().values()
        )

        for url in urls:
            with self.subTest(url=url):
                self.assert_sent_to_login(self.client.get(url), url)

        remove = self.remove_url()
        self.assert_sent_to_login(self.client.post(remove), remove)

    def test_student_and_no_role_get_403_everywhere(self):
        urls = list(self.view_urls().values()) + list(
            self.admin_urls().values()
        )

        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

            with self.subTest(user=user.username, url="remove"):
                response = self.client.post(self.remove_url())
                self.assertEqual(response.status_code, 403)

    def test_teacher_can_view_but_not_manage(self):
        self.client.force_login(self.teacher)

        for name, url in self.view_urls().items():
            with self.subTest(page=name):
                self.assertEqual(self.client.get(url).status_code, 200)

        for name, url in self.admin_urls().items():
            with self.subTest(page=name):
                self.assertEqual(self.client.get(url).status_code, 403)

        self.assertEqual(self.client.post(self.remove_url()).status_code, 403)

    def test_admin_and_superuser_can_open_every_page(self):
        urls = list(self.view_urls().values()) + list(
            self.admin_urls().values()
        )

        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_remove_page_only_accepts_post(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.remove_url())

        self.assertEqual(response.status_code, 405)
        self.enrollment_a.refresh_from_db()
        self.assertEqual(self.enrollment_a.status, Enrollment.STATUS_ACTIVE)

    def test_unknown_ids_give_404(self):
        self.client.force_login(self.admin)

        urls = [
            reverse("enrollment_section_roster", args=[999999]),
            reverse("enrollment_student_history", args=[999999]),
            reverse("transfer_enrollment", args=[999999]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_refused_users_cannot_remove_an_enrollment(self):
        for user in (self.teacher, self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(
                    self.remove_url(), {"reason": "not allowed"}
                )
                self.assertEqual(response.status_code, 403)

        self.enrollment_a.refresh_from_db()
        self.assertEqual(self.enrollment_a.status, Enrollment.STATUS_ACTIVE)

    def test_refused_users_cannot_enroll_anyone(self):
        count_before = Enrollment.objects.count()
        data = {
            "student": self.other_student.pk,
            "section": self.section_a.pk,
        }

        for user in (self.teacher, self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(reverse("enroll_student"), data)
                self.assertEqual(response.status_code, 403)

        self.assertEqual(Enrollment.objects.count(), count_before)

    def test_refused_users_cannot_transfer_a_student(self):
        url = reverse("transfer_enrollment", args=[self.enrollment_a.pk])
        count_before = Enrollment.objects.count()

        for user in (self.teacher, self.student, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(
                    url,
                    {"section": self.section_b.pk, "reason": "not allowed"},
                )
                self.assertEqual(response.status_code, 403)

        self.enrollment_a.refresh_from_db()
        self.assertEqual(self.enrollment_a.section, self.section_a)
        self.assertEqual(self.enrollment_a.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(Enrollment.objects.count(), count_before)


class StudentDataProtectionTests(DataTestBase):
    """
    Direct URL access to student data, trying own IDs and other students' IDs
    (SRS SAMS-SR-004, test TC-Sec-04).
    """

    def student_data_urls(self):
        return {
            "records (own section)": self.records_url(self.session_a),
            "records (other section)": self.records_url(self.session_b),
            "correct (own record)": self.correct_url(self.record_a),
            "correct (other record)": self.correct_url(self.record_b),
            "mark (own section)": self.mark_url(self.session_a),
            "mark (other section)": self.mark_url(self.session_b),
            "roster (own section)": reverse(
                "enrollment_section_roster", args=[self.section_a.pk]
            ),
            "roster (other section)": reverse(
                "enrollment_section_roster", args=[self.section_b.pk]
            ),
            "history (self)": reverse(
                "enrollment_student_history", args=[self.student.pk]
            ),
            "history (other student)": reverse(
                "enrollment_student_history", args=[self.other_student.pk]
            ),
            "defaulters (own section)": reverse(
                "defaulter_list", args=[self.section_a.pk]
            ),
            "defaulters (other section)": reverse(
                "defaulter_list", args=[self.section_b.pk]
            ),
        }

    def test_anonymous_cannot_open_any_student_data_page(self):
        for name, url in self.student_data_urls().items():
            with self.subTest(page=name):
                self.assert_sent_to_login(self.client.get(url), url)

    def test_students_get_403_on_every_student_data_page(self):
        for user in (self.student, self.other_student, self.no_role_user):
            self.client.force_login(user)

            for name, url in self.student_data_urls().items():
                with self.subTest(user=user.username, page=name):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_teacher_is_refused_on_another_teachers_section_data(self):
        """Only pages that already check the assignment are listed here."""
        self.client.force_login(self.teacher)

        urls = {
            "records": self.records_url(self.session_b),
            "correct": self.correct_url(self.record_b),
            "mark": self.mark_url(self.session_b),
            "defaulters": reverse("defaulter_list", args=[self.section_b.pk]),
        }

        for name, url in urls.items():
            with self.subTest(page=name):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_can_open_every_student_data_page(self):
        self.client.force_login(self.admin)

        for name, url in self.student_data_urls().items():
            with self.subTest(page=name):
                self.assertEqual(self.client.get(url).status_code, 200)


class SuspectedDefectTests(DataTestBase):
    """
    Each test states the behaviour the SRS requires. A failure means the
    defect is real.
    """

    def test_d1_missing_session_on_mark_page_is_not_a_server_error(self):
        """D-1: /sessions/<missing id>/mark/ must not give a 500 (SR-001)."""
        self.client.raise_request_exception = False
        url = reverse("attendance:mark_attendance", args=[999999])

        for user in (self.student, self.teacher, self.admin):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(url)
                self.assertIn(response.status_code, (403, 404))

    def test_d2_assignment_without_teacher_role_cannot_see_records(self):
        """D-2: records page must also check the Teacher role (SR-004)."""
        former_teacher = User.objects.create_user(username="perm_former")
        former_teacher.groups.add(Group.objects.get(name=ROLE_STUDENT))
        TeacherAssignment.objects.create(
            teacher=former_teacher, section=self.section_a
        )
        self.client.force_login(former_teacher)

        response = self.client.get(self.records_url(self.session_a))

        self.assertEqual(response.status_code, 403)

    def test_d3a_teacher_cannot_open_roster_of_unassigned_section(self):
        """D-3a: teachers see only assigned sections (SR-004)."""
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("enrollment_section_roster", args=[self.section_b.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_d3b_teacher_cannot_open_history_of_unrelated_student(self):
        """D-3b: other_student is only enrolled in a section teacher lacks."""
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("enrollment_student_history", args=[self.other_student.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_d3c_teacher_enrollment_list_shows_only_assigned_sections(self):
        """D-3c: the section list should match the teacher's assignments."""
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("enrollment_section_list"))

        shown = [section.pk for section in response.context["sections"]]
        self.assertEqual(shown, [self.section_a.pk])

    def test_d4_login_without_next_does_not_land_on_a_missing_page(self):
        """D-4: after login the user must reach a real page (SAMS-F-001)."""
        password = "S3cure-test-pass"
        user = User.objects.create_user(
            username="perm_direct_login", password=password
        )
        user.groups.add(Group.objects.get(name=ROLE_STUDENT))

        response = self.client.post(
            reverse("login"),
            {"username": "perm_direct_login", "password": password},
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.client.get(response.url).status_code, 404)

    def test_d5_sessions_expire_after_30_minutes_of_inactivity(self):
        """D-5: SRS SAMS-SR-005 asks for a 30 minute timeout."""
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 30 * 60)
