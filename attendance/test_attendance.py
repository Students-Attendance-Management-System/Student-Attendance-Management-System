from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attendance, Course, Enrollment, Section


def make_user(username, role=None):
    user = User.objects.create_user(
        username=username,
        password="TestPass123!",
        first_name=username.capitalize(),
    )
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


class AttendanceTestBase(TestCase):

    def setUp(self):
        self.teacher = make_user("teacher1", "Teacher")
        self.admin = make_user("admin1", "Admin")
        self.student = make_user("student1", "Student")
        self.student2 = make_user("student2", "Student")
        self.outsider = make_user("outsider", "Student")

        course = Course.objects.create(code="CS101", name="Computer Science")
        self.section = Section.objects.create(
            course=course, name="A", academic_year="2026-2027"
        )
        Enrollment.objects.create(student=self.student, section=self.section)
        Enrollment.objects.create(student=self.student2, section=self.section)

        self.today = timezone.localdate()
        self.mark_url = reverse("mark_attendance", args=[self.section.pk])
        self.report_url = reverse("attendance_report", args=[self.section.pk])

    def payload(self, status1="P", status2="A", attendance_date=None):
        attendance_date = attendance_date or self.today
        return {
            "date": attendance_date.isoformat(),
            f"status_{self.student.pk}": status1,
            f"status_{self.student2.pk}": status2,
        }


class MarkAttendanceTests(AttendanceTestBase):

    def test_roster_is_displayed_for_the_section(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.mark_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student1")
        self.assertContains(response, "student2")
        self.assertNotContains(response, "outsider")

    def test_attendance_can_be_recorded_for_enrolled_students(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.mark_url, self.payload())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.count(), 2)

        record = Attendance.objects.get(student=self.student)
        self.assertEqual(record.status, "P")
        self.assertEqual(record.marked_by, self.teacher)
        self.assertEqual(
            Attendance.objects.get(student=self.student2).status, "A"
        )

    def test_invalid_status_is_rejected(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.mark_url, self.payload(status1="X"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_missing_status_is_rejected(self):
        self.client.force_login(self.teacher)
        data = self.payload()
        del data[f"status_{self.student2.pk}"]
        response = self.client.post(self.mark_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_future_date_is_rejected(self):
        self.client.force_login(self.teacher)
        tomorrow = self.today + timedelta(days=1)
        response = self.client.post(
            self.mark_url, self.payload(attendance_date=tomorrow)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_invalid_date_is_rejected(self):
        self.client.force_login(self.teacher)
        data = self.payload()
        data["date"] = "not-a-date"
        response = self.client.post(self.mark_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_student_not_enrolled_in_section_is_not_saved(self):
        self.client.force_login(self.teacher)
        data = self.payload()
        data[f"status_{self.outsider.pk}"] = "P"
        self.client.post(self.mark_url, data)

        self.assertFalse(
            Attendance.objects.filter(student=self.outsider).exists()
        )
        self.assertEqual(Attendance.objects.count(), 2)

    def test_resubmitting_same_date_updates_instead_of_duplicating(self):
        self.client.force_login(self.teacher)
        self.client.post(self.mark_url, self.payload("P", "A"))
        self.client.post(self.mark_url, self.payload("L", "P"))

        self.assertEqual(Attendance.objects.count(), 2)
        self.assertEqual(
            Attendance.objects.get(student=self.student).status, "L"
        )
        self.assertEqual(
            Attendance.objects.get(student=self.student2).status, "P"
        )

    def test_model_rejects_student_not_enrolled(self):
        record = Attendance(
            section=self.section,
            student=self.outsider,
            date=self.today,
            status="P",
        )
        with self.assertRaises(ValidationError):
            record.full_clean()


class AttendanceAccessTests(AttendanceTestBase):

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.mark_url)
        self.assertRedirects(
            response,
            f"/accounts/login/?next={self.mark_url}",
            fetch_redirect_response=False,
        )

    def test_student_cannot_open_mark_page(self):
        self.client.force_login(self.student)
        response = self.client.get(self.mark_url)
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_submit_attendance(self):
        self.client.force_login(self.student)
        response = self.client.post(self.mark_url, self.payload())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_admin_cannot_mark_attendance(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.mark_url, self.payload())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_deactivated_teacher_cannot_mark_attendance(self):
        self.teacher.is_active = False
        self.teacher.save()
        self.client.force_login(self.teacher)
        response = self.client.get(self.mark_url)

        self.assertNotEqual(response.status_code, 200)

    def test_student_cannot_view_attendance_report(self):
        self.client.force_login(self.student)
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 403)


class AttendanceRetrievalTests(AttendanceTestBase):

    def test_saved_attendance_is_retrieved_correctly(self):
        self.client.force_login(self.teacher)
        self.client.post(self.mark_url, self.payload("P", "A"))

        response = self.client.get(
            f"{self.report_url}?date={self.today.isoformat()}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student1")
        self.assertContains(response, "Present")
        self.assertContains(response, "student2")
        self.assertContains(response, "Absent")

    def test_report_for_date_without_records_says_so(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.report_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No attendance has been recorded")

    def test_admin_can_view_report(self):
        self.client.force_login(self.teacher)
        self.client.post(self.mark_url, self.payload())

        self.client.force_login(self.admin)
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)

    def test_marking_page_prefills_saved_statuses(self):
        self.client.force_login(self.teacher)
        self.client.post(self.mark_url, self.payload("L", "A"))

        response = self.client.get(
            f"{self.mark_url}?date={self.today.isoformat()}"
        )
        form = response.context["form"]

        self.assertEqual(
            form.initial[f"status_{self.student.pk}"], "L"
        )
        self.assertEqual(
            form.initial[f"status_{self.student2.pk}"], "A"
        )