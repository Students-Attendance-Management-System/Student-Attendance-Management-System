"""
Course, section and schedule rules (Issue #23, workflow C).

SAMS has no course screens yet (no course views, forms or URLs, and Course is
not registered in the Django admin), so these tests check the model rules
directly. They add to, and do not repeat, CourseManagementTests in tests.py,
which already covers creating a course/section, duplicate sections,
end-before-start schedules and overlapping schedules.
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Course, Schedule, Section


class CourseModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="CS201",
            name="Data Structures",
            description="Arrays, lists, trees and graphs.",
        )

    def test_valid_course_passes_validation(self):
        course = Course(code="CS202", name="Operating Systems")

        course.full_clean()  # must not raise

    def test_description_is_optional(self):
        course = Course(code="CS203", name="Networks", description="")

        course.full_clean()  # must not raise

    def test_blank_code_is_rejected(self):
        course = Course(code="", name="Databases")

        with self.assertRaises(ValidationError) as ctx:
            course.full_clean()

        self.assertIn("code", ctx.exception.message_dict)

    def test_blank_name_is_rejected(self):
        course = Course(code="CS204", name="")

        with self.assertRaises(ValidationError) as ctx:
            course.full_clean()

        self.assertIn("name", ctx.exception.message_dict)

    def test_code_longer_than_20_characters_is_rejected(self):
        course = Course(code="C" * 21, name="Too Long Code")

        with self.assertRaises(ValidationError) as ctx:
            course.full_clean()

        self.assertIn("code", ctx.exception.message_dict)

    def test_name_longer_than_100_characters_is_rejected(self):
        course = Course(code="CS205", name="N" * 101)

        with self.assertRaises(ValidationError) as ctx:
            course.full_clean()

        self.assertIn("name", ctx.exception.message_dict)

    def test_duplicate_code_fails_validation(self):
        course = Course(code="CS201", name="Another Name")

        with self.assertRaises(ValidationError) as ctx:
            course.full_clean()

        self.assertIn("code", ctx.exception.message_dict)

    def test_duplicate_code_is_blocked_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Course.objects.create(code="CS201", name="Another Name")

        self.assertEqual(Course.objects.filter(code="CS201").count(), 1)

    def test_updating_course_details_is_saved(self):
        self.course.name = "Advanced Data Structures"
        self.course.description = "Now includes balanced trees."
        self.course.save()

        self.course.refresh_from_db()

        self.assertEqual(self.course.code, "CS201")
        self.assertEqual(self.course.name, "Advanced Data Structures")
        self.assertEqual(
            self.course.description, "Now includes balanced trees."
        )

    def test_cannot_update_code_to_one_already_used(self):
        other = Course.objects.create(code="CS210", name="Algorithms")
        other.code = "CS201"

        with self.assertRaises(ValidationError) as ctx:
            other.full_clean()

        self.assertIn("code", ctx.exception.message_dict)

    def test_string_form_shows_code_and_name(self):
        self.assertEqual(str(self.course), "CS201 - Data Structures")

    def test_deleting_a_course_deletes_its_sections(self):
        Section.objects.create(
            course=self.course, name="A", academic_year="2026-27"
        )

        self.course.delete()

        self.assertEqual(Section.objects.count(), 0)


class SectionModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="CS301", name="Software Engineering"
        )
        self.other_course = Course.objects.create(
            code="CS302", name="Machine Learning"
        )
        self.section = Section.objects.create(
            course=self.course, name="A", academic_year="2026-27"
        )

    def test_blank_name_is_rejected(self):
        section = Section(
            course=self.course, name="", academic_year="2026-27"
        )

        with self.assertRaises(ValidationError) as ctx:
            section.full_clean()

        self.assertIn("name", ctx.exception.message_dict)

    def test_blank_academic_year_is_rejected(self):
        section = Section(course=self.course, name="B", academic_year="")

        with self.assertRaises(ValidationError) as ctx:
            section.full_clean()

        self.assertIn("academic_year", ctx.exception.message_dict)

    def test_section_must_belong_to_a_course(self):
        section = Section(name="B", academic_year="2026-27")

        with self.assertRaises(ValidationError) as ctx:
            section.full_clean()

        self.assertIn("course", ctx.exception.message_dict)

    def test_duplicate_section_fails_validation(self):
        section = Section(
            course=self.course, name="A", academic_year="2026-27"
        )

        with self.assertRaises(ValidationError):
            section.full_clean()

    def test_same_section_name_is_allowed_in_another_year(self):
        section = Section(
            course=self.course, name="A", academic_year="2027-28"
        )

        section.full_clean()  # must not raise

    def test_same_section_name_is_allowed_in_another_course(self):
        section = Section(
            course=self.other_course, name="A", academic_year="2026-27"
        )

        section.full_clean()  # must not raise

    def test_string_form_shows_course_code_and_section_name(self):
        self.assertEqual(str(self.section), "CS301 - A")


class ScheduleRuleTests(TestCase):
    def setUp(self):
        course = Course.objects.create(code="CS401", name="Compilers")
        self.section = Section.objects.create(
            course=course, name="A", academic_year="2026-27"
        )
        self.monday_nine = Schedule.objects.create(
            section=self.section,
            day="MON",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    def test_equal_start_and_end_time_is_rejected(self):
        schedule = Schedule(
            section=self.section,
            day="TUE",
            start_time=time(9, 0),
            end_time=time(9, 0),
        )

        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()

        self.assertIn("end_time", ctx.exception.message_dict)

    def test_back_to_back_classes_do_not_overlap(self):
        schedule = Schedule(
            section=self.section,
            day="MON",
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

        schedule.full_clean()  # must not raise

    def test_same_time_on_a_different_day_is_allowed(self):
        schedule = Schedule(
            section=self.section,
            day="TUE",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        schedule.full_clean()  # must not raise

    def test_editing_a_schedule_does_not_conflict_with_itself(self):
        self.monday_nine.end_time = time(10, 30)

        self.monday_nine.full_clean()  # must not raise

    def test_unknown_day_is_rejected(self):
        schedule = Schedule(
            section=self.section,
            day="XYZ",
            start_time=time(13, 0),
            end_time=time(14, 0),
        )

        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()

        self.assertIn("day", ctx.exception.message_dict)
