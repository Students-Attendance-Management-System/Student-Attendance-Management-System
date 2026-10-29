
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from datetime import date
from .models import Course, Section, AttendanceSession, AttendanceRecord

class LoginTests(TestCase):

    def setUp(self):
        User.objects.create_user(
            username="testuser",
            password="TestPass123!"
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login(self):
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "TestPass123!"},
            follow=True
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_login(self):
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "wrongpassword"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")

    
from datetime import time
from django.core.exceptions import ValidationError
from django.test import TestCase
from .models import Course, Section, Schedule


class CourseManagementTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="CS101",
            name="Computer Science",
        )
        self.section = Section.objects.create(
            course=self.course,
            name="A",
            academic_year="2026-2027",
        )

    def test_create_course(self):
        self.assertEqual(self.course.name, "Computer Science")

    def test_create_section(self):
        self.assertEqual(self.section.course, self.course)

    def test_duplicate_section_rejected(self):
        with self.assertRaises(Exception):
            Section.objects.create(
                course=self.course,
                name="A",
                academic_year="2026-2027",
            )

    def test_schedule_end_time_must_be_after_start(self):
        schedule = Schedule(
            section=self.section,
            day="MON",
            start_time=time(11, 0),
            end_time=time(10, 0),
        )
        with self.assertRaises(ValidationError):
            schedule.full_clean()

    def test_overlapping_schedule_rejected(self):
        Schedule.objects.create(
            section=self.section,
            day="MON",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        schedule = Schedule(
            section=self.section,
            day="MON",
            start_time=time(9, 30),
            end_time=time(10, 30),
        )
        with self.assertRaises(ValidationError):
            schedule.full_clean()


class AttendanceSessionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            password="TestPass123!",
        )
        self.student = User.objects.create_user(
            username="student",
            password="TestPass123!",
        )
        self.course = Course.objects.create(
            code="CS201",
            name="Database Systems",
        )
        self.section = Section.objects.create(
            course=self.course,
            name="B",
            academic_year="2026-2027",
        )
        self.session = AttendanceSession.objects.create(
            section=self.section,
            date=date(2026, 10, 29),
            teacher=self.teacher,
            topic="Introduction to Databases",
            details="First lecture",
        )

    def test_session_metadata_saved(self):
        self.assertEqual(self.session.section, self.section)
        self.assertEqual(self.session.date, date(2026, 10, 29))
        self.assertEqual(self.session.teacher, self.teacher)
        self.assertEqual(self.session.topic, "Introduction to Databases")

    def test_attendance_record_linked_to_session(self):
        record = AttendanceRecord.objects.create(
            session=self.session,
            student=self.student,
            status="PRESENT",
        )
        self.assertEqual(record.session, self.session)
        self.assertEqual(self.session.records.count(), 1)

    def test_duplicate_attendance_record_rejected(self):
        AttendanceRecord.objects.create(
            session=self.session,
            student=self.student,
            status="PRESENT",
        )
        with self.assertRaises(Exception):
            AttendanceRecord.objects.create(
                session=self.session,
                student=self.student,
                status="ABSENT",
            )
