
import time

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Section,
    TeacherAssignment,
)


def make_teacher(username):
    user = User.objects.create_user(username=username, password="TestPass123!")
    group, _ = Group.objects.get_or_create(name="Teacher")
    user.groups.add(group)
    return user


def build_class(student_count, label):
    teacher = make_teacher(f"teacher_{label}")
    course = Course.objects.create(code=f"P{label}", name=f"Perf {label}")
    section = Section.objects.create(
        course=course, name="A", academic_year="2026-27"
    )
    session = AttendanceSession.objects.create(
        section=section, date=timezone.localdate(), teacher=teacher
    )
    TeacherAssignment.objects.create(teacher=teacher, section=section)

    User.objects.bulk_create(
        [User(username=f"s{label}_{i}") for i in range(student_count)]
    )
    students = list(User.objects.filter(username__startswith=f"s{label}_"))
    Enrollment.objects.bulk_create(
        [Enrollment(student=s, section=section) for s in students]
    )
    return teacher, session, students


class SubmissionPerformanceTests(TestCase):

    def submit(self, student_count):
        teacher, session, students = build_class(
            student_count, str(student_count)
        )
        self.client.force_login(teacher)

        url = reverse(
            "attendance:mark_attendance", kwargs={"session_id": session.id}
        )
        data = {f"status_{s.id}": "PRESENT" for s in students}

        query_count = 0

        def count_queries(execute, sql, params, many, context):
            nonlocal query_count
            query_count += 1
            return execute(sql, params, many, context)

        # Count actual SQL executions. Unlike CaptureQueriesContext,
        # this is not affected by the test client's query-log reset.
        with connection.execute_wrapper(count_queries):
            start = time.perf_counter()
            response = self.client.post(url, data)
            first = time.perf_counter() - start

        start = time.perf_counter()
        repeat_response = self.client.post(url, data)
        repeat = time.perf_counter() - start

        rows = AttendanceRecord.objects.filter(session=session).count()

        print(
            f"\n[{student_count} students] first submit: {first*1000:.0f} ms, "
            f"{query_count} queries | repeat submit: {repeat*1000:.0f} ms | "
            f"rows saved: {rows}"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(repeat_response.status_code, 302)
        self.assertEqual(rows, student_count)

    def test_submit_30_students(self):
        self.submit(30)

    def test_submit_60_students(self):
        self.submit(60)

    def test_submit_120_students(self):
        self.submit(120)

    def test_submit_200_students(self):
        self.submit(200)
