"""
End-to-end regression test (Issue #23).

Follows one realistic path through SAMS, using the real login page and the
real views wherever they exist:

    admin logs in -> enrolls students -> teacher logs in -> marks attendance
    -> percentages are calculated -> defaulter list and CSV report agree
    -> teacher corrects a record -> everything updates -> a student is
    kept out.

SAMS has no screen for creating courses, sections, teacher assignments or
attendance sessions, so the test creates those directly in the database.
Every other step goes through the same URLs a real user would use.
"""

import csv
import io
from datetime import timedelta

from django.contrib.auth.models import Group, User
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

PASSWORD = "regression-pass-123"


class EndToEndAttendanceWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        teacher_group, _ = Group.objects.get_or_create(name=ROLE_TEACHER)
        student_group, _ = Group.objects.get_or_create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user("flow_admin", password=PASSWORD)
        cls.admin.groups.add(admin_group)

        cls.teacher = User.objects.create_user(
            "flow_teacher", password=PASSWORD
        )
        cls.teacher.groups.add(teacher_group)

        # Anita will end exactly on 75%, Rahul well below it.
        cls.anita = User.objects.create_user("flow_anita", password=PASSWORD)
        cls.anita.groups.add(student_group)
        cls.rahul = User.objects.create_user("flow_rahul", password=PASSWORD)
        cls.rahul.groups.add(student_group)

        cls.course = Course.objects.create(
            code="FLOW101", name="Workflow Testing"
        )
        cls.section = Section.objects.create(
            course=cls.course, name="A", academic_year="2026-27"
        )
        TeacherAssignment.objects.create(
            teacher=cls.teacher, section=cls.section
        )

    # ---- small helpers ---------------------------------------------

    def log_in_through_login_page(self, user):
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)

    def percentage(self, student):
        return calculate_attendance_percentage(student, self.section)[
            "percentage"
        ]

    def csv_rows(self):
        response = self.client.get(
            reverse("attendance:export_report"),
            {"section": self.section.pk},
        )
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        return {
            row["Username"]: row
            for row in csv.DictReader(io.StringIO(text))
        }

    def defaulter_usernames(self):
        response = self.client.get(
            reverse("defaulter_list", args=[self.section.pk])
        )
        self.assertEqual(response.status_code, 200)
        return [
            row["student"].username
            for row in response.context["report"]["defaulters"]
        ]

    # ---- the workflow ----------------------------------------------

    def test_full_attendance_workflow(self):
        # 1. Admin logs in and enrolls both students through the enroll page.
        self.log_in_through_login_page(self.admin)
        for student in (self.anita, self.rahul):
            response = self.client.post(
                reverse("enroll_student"),
                {"student": student.pk, "section": self.section.pk},
            )
            self.assertEqual(response.status_code, 302)

        enrolled = Enrollment.objects.filter(
            section=self.section, status=Enrollment.STATUS_ACTIVE
        )
        self.assertEqual(
            sorted(e.student.username for e in enrolled),
            ["flow_anita", "flow_rahul"],
        )

        # Make the enrollments old enough for the sessions below to count.
        enrolled.update(enrolled_at=timezone.now() - timedelta(days=30))

        # 2. Four class sessions have taken place (no screen creates these).
        today = timezone.localdate()
        sessions = [
            AttendanceSession.objects.create(
                section=self.section,
                date=today - timedelta(days=days_ago),
                teacher=self.teacher,
                topic=f"Lecture {number}",
            )
            for number, days_ago in enumerate((4, 3, 2, 1), start=1)
        ]

        # 3. The assigned teacher logs in and marks attendance per session.
        self.log_in_through_login_page(self.teacher)
        marks = [
            ("PRESENT", "ABSENT"),
            ("PRESENT", "ABSENT"),
            ("LATE", "ABSENT"),
            ("ABSENT", "PRESENT"),
        ]
        for session, (anita_status, rahul_status) in zip(sessions, marks):
            response = self.client.post(
                reverse("attendance:mark_attendance", args=[session.pk]),
                {
                    f"status_{self.anita.pk}": anita_status,
                    f"status_{self.rahul.pk}": rahul_status,
                },
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(AttendanceRecord.objects.count(), 8)

        # 4. Percentages: Present and Late count as attended.
        self.assertEqual(self.percentage(self.anita), 75.0)  # 3 of 4
        self.assertEqual(self.percentage(self.rahul), 25.0)  # 1 of 4

        # 5. Defaulter list (default threshold 75%): 75.0 is not below it.
        self.assertEqual(self.defaulter_usernames(), ["flow_rahul"])

        # 6. The CSV report shows the same numbers.
        rows = self.csv_rows()
        self.assertEqual(rows["flow_anita"]["Percentage"], "75.0")
        self.assertEqual(rows["flow_anita"]["Total"], "4")
        self.assertEqual(rows["flow_rahul"]["Percentage"], "25.0")

        # 7. The teacher corrects Anita's ABSENT record to PRESENT.
        absent_record = AttendanceRecord.objects.get(
            session=sessions[3], student=self.anita
        )
        response = self.client.post(
            reverse("attendance:correct_record", args=[absent_record.pk]),
            {"new_status": "PRESENT", "reason": "Arrived after roll call"},
        )
        self.assertEqual(response.status_code, 302)

        absent_record.refresh_from_db()
        self.assertEqual(absent_record.status, "PRESENT")

        # 8. Everything updates: calculation, defaulters and CSV.
        self.assertEqual(self.percentage(self.anita), 100.0)
        self.assertEqual(self.defaulter_usernames(), ["flow_rahul"])
        self.assertEqual(self.csv_rows()["flow_anita"]["Percentage"], "100.0")

        # 9. A student is kept out of the staff pages.
        self.log_in_through_login_page(self.rahul)
        self.assertEqual(
            self.client.get(
                reverse("defaulter_list", args=[self.section.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("attendance:export_report"),
                {"section": self.section.pk},
            ).status_code,
            403,
        )
