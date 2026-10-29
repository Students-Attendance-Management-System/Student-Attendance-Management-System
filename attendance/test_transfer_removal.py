import datetime
from unittest import skipIf

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from .enrollment_services import remove_student, transfer_student
from .models import Course, Enrollment, Section
from .permissions import ROLE_STUDENT
from .test_enrollment import EnrollmentTestBase, make_user

try:
    from .models import AttendanceRecord, AttendanceSession
except ImportError:  # Issue #9 (attendance models) not on this branch yet
    AttendanceRecord = None
    AttendanceSession = None


class TransferRemovalServiceTests(EnrollmentTestBase):
    def setUp(self):
        super().setUp()
        self.enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )

    def test_transfer_moves_student_and_keeps_old_row(self):
        new = transfer_student(
            self.enrollment, self.other_section, self.admin, "Clash"
        )
        old = Enrollment.objects.get(pk=self.enrollment.pk)

        self.assertEqual(old.status, Enrollment.STATUS_TRANSFERRED)
        self.assertEqual(old.ended_by, self.admin)
        self.assertIsNotNone(old.ended_at)
        self.assertEqual(old.end_reason, "Clash")
        self.assertEqual(new.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(new.section, self.other_section)
        self.assertEqual(new.transferred_from, old)
        self.assertEqual(Enrollment.objects.filter(student=self.student).count(), 2)
        self.assertEqual(
            Enrollment.objects.filter(
                student=self.student, status=Enrollment.STATUS_ACTIVE
            ).count(),
            1,
        )

    def test_transfer_back_to_original_section_is_allowed(self):
        first = transfer_student(self.enrollment, self.other_section, self.admin)
        transfer_student(first, self.section, self.admin)

        self.assertEqual(Enrollment.objects.filter(student=self.student).count(), 3)
        self.assertEqual(
            Enrollment.objects.filter(
                student=self.student, status=Enrollment.STATUS_ACTIVE
            ).count(),
            1,
        )

    def test_transfer_to_different_course_is_rejected(self):
        other_course = Course.objects.create(code="CS202", name="Other")
        foreign = Section.objects.create(
            course=other_course, name="A", academic_year="2026-27"
        )

        with self.assertRaises(ValidationError):
            transfer_student(self.enrollment, foreign, self.admin)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_transfer_to_same_section_is_rejected(self):
        with self.assertRaises(ValidationError):
            transfer_student(self.enrollment, self.section, self.admin)

        self.assertEqual(Enrollment.objects.count(), 1)

    def test_transfer_to_section_with_active_enrollment_is_rejected(self):
        Enrollment.objects.create(student=self.student, section=self.other_section)

        with self.assertRaises(ValidationError):
            transfer_student(self.enrollment, self.other_section, self.admin)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)

    def test_ended_enrollment_cannot_be_transferred_again(self):
        transfer_student(self.enrollment, self.other_section, self.admin)

        with self.assertRaises(ValidationError):
            transfer_student(self.enrollment, self.other_section, self.admin)

        self.assertEqual(Enrollment.objects.count(), 2)

    def test_failed_transfer_rolls_back_everything(self):
        self.student.is_active = False
        self.student.save()

        with self.assertRaises(ValidationError):
            transfer_student(self.enrollment, self.other_section, self.admin)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)
        self.assertIsNone(self.enrollment.ended_at)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_remove_marks_removed_and_keeps_row(self):
        remove_student(self.enrollment, self.admin, "Withdrew")
        self.enrollment.refresh_from_db()

        self.assertEqual(self.enrollment.status, Enrollment.STATUS_REMOVED)
        self.assertEqual(self.enrollment.ended_by, self.admin)
        self.assertEqual(self.enrollment.end_reason, "Withdrew")
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_removed_student_can_be_enrolled_again(self):
        remove_student(self.enrollment, self.admin)

        again = Enrollment(student=self.student, section=self.section)
        again.full_clean()
        again.save()

        self.assertEqual(Enrollment.objects.filter(student=self.student).count(), 2)
        self.assertEqual(
            Enrollment.objects.filter(
                student=self.student, status=Enrollment.STATUS_ACTIVE
            ).count(),
            1,
        )

    def test_removed_enrollment_cannot_be_removed_again(self):
        remove_student(self.enrollment, self.admin)

        with self.assertRaises(ValidationError):
            remove_student(self.enrollment, self.admin)

    def test_deactivated_student_can_still_be_removed(self):
        self.student.is_active = False
        self.student.save()

        remove_student(self.enrollment, self.admin)
        self.enrollment.refresh_from_db()

        self.assertEqual(self.enrollment.status, Enrollment.STATUS_REMOVED)

    def test_non_admins_cannot_transfer_or_remove(self):
        for actor in (self.teacher, self.student):
            with self.assertRaises(PermissionDenied):
                transfer_student(self.enrollment, self.other_section, actor)
            with self.assertRaises(PermissionDenied):
                remove_student(self.enrollment, actor)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(Enrollment.objects.count(), 1)


@skipIf(AttendanceRecord is None, "AttendanceRecord (Issue #9) is not on this branch yet")
class AttendancePreservedTests(EnrollmentTestBase):
    def _make_record(self):
        session = AttendanceSession.objects.create(
            section=self.section, date=datetime.date.today()
        )
        return AttendanceRecord.objects.create(
            session=session, student=self.student, status="PRESENT"
        )

    def test_attendance_survives_transfer(self):
        enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        record = self._make_record()

        transfer_student(enrollment, self.other_section, self.admin)

        self.assertTrue(AttendanceRecord.objects.filter(pk=record.pk).exists())

    def test_attendance_survives_removal(self):
        enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        record = self._make_record()

        remove_student(enrollment, self.admin)

        self.assertTrue(AttendanceRecord.objects.filter(pk=record.pk).exists())


class TransferRemovalViewTests(EnrollmentTestBase):
    def setUp(self):
        super().setUp()
        self.enrollment = Enrollment.objects.create(
            student=self.student, section=self.section
        )
        self.transfer_url = reverse("transfer_enrollment", args=[self.enrollment.pk])
        self.remove_url = reverse("unenroll_student", args=[self.enrollment.pk])

    def roster_url(self, section):
        return reverse("enrollment_section_roster", args=[section.pk])

    def assert_unchanged(self):
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_ACTIVE)
        self.assertEqual(Enrollment.objects.count(), 1)

    # --- Unauthorized access -------------------------------------------

    def test_anonymous_users_are_sent_to_login(self):
        for response in (
            self.client.get(self.transfer_url),
            self.client.post(self.transfer_url, {"section": self.other_section.pk}),
            self.client.post(self.remove_url),
        ):
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("/accounts/login/"))

        self.assert_unchanged()

    def test_teacher_and_student_get_403(self):
        for user in (self.teacher, self.student):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.transfer_url).status_code, 403)
            self.assertEqual(
                self.client.post(
                    self.transfer_url, {"section": self.other_section.pk}
                ).status_code,
                403,
            )
            self.assertEqual(self.client.post(self.remove_url).status_code, 403)

        self.assert_unchanged()

    # --- Transfer -------------------------------------------------------

    def test_admin_can_transfer(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.transfer_url,
            {"section": self.other_section.pk, "reason": "Timetable"},
        )

        self.assertRedirects(response, self.roster_url(self.other_section))
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_TRANSFERRED)
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student,
                section=self.other_section,
                status=Enrollment.STATUS_ACTIVE,
            ).exists()
        )

    def test_transfer_to_other_course_rejected_by_view(self):
        other_course = Course.objects.create(code="CS202", name="Other")
        foreign = Section.objects.create(
            course=other_course, name="A", academic_year="2026-27"
        )
        self.client.force_login(self.admin)

        response = self.client.post(self.transfer_url, {"section": foreign.pk})

        self.assertEqual(response.status_code, 200)
        self.assert_unchanged()

    def test_transfer_form_lists_only_same_course_sections(self):
        other_course = Course.objects.create(code="CS202", name="Other")
        Section.objects.create(course=other_course, name="A", academic_year="2026-27")
        self.client.force_login(self.admin)

        response = self.client.get(self.transfer_url)
        pks = [s.pk for s in response.context["form"].fields["section"].queryset]

        self.assertEqual(pks, [self.other_section.pk])

    def test_ended_enrollment_cannot_be_transferred_via_view(self):
        remove_student(self.enrollment, self.admin)
        self.client.force_login(self.admin)

        response = self.client.post(
            self.transfer_url, {"section": self.other_section.pk}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Enrollment.objects.count(), 1)

    # --- Removal --------------------------------------------------------

    def test_admin_removal_keeps_history_and_updates_roster(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.remove_url, {"reason": "Withdrew"})

        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.STATUS_REMOVED)
        self.assertEqual(Enrollment.objects.count(), 1)

        roster = self.client.get(self.roster_url(self.section))
        self.assertEqual(len(roster.context["enrollments"]), 0)

    # --- Rosters, counts, history ---------------------------------------

    def test_roster_and_counts_show_only_active_after_transfer(self):
        transfer_student(self.enrollment, self.other_section, self.admin)
        self.client.force_login(self.admin)

        old_roster = self.client.get(self.roster_url(self.section))
        new_roster = self.client.get(self.roster_url(self.other_section))
        listing = self.client.get(reverse("enrollment_section_list"))
        counts = {s.name: s.student_count for s in listing.context["sections"]}

        self.assertEqual(len(old_roster.context["enrollments"]), 0)
        self.assertEqual(len(new_roster.context["enrollments"]), 1)
        self.assertEqual(counts, {"A": 0, "B": 1})

    def test_history_page_shows_all_rows_to_teacher_but_not_student(self):
        transfer_student(self.enrollment, self.other_section, self.admin)
        url = reverse("enrollment_student_history", args=[self.student.pk])

        self.client.force_login(self.teacher)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["enrollments"]), 2)

        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 403)