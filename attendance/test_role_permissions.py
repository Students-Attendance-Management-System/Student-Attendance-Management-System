from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import AttendanceThreshold, Course, Section, TeacherAssignment
from .permissions import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER


class RolePermissionTestBase(TestCase):
    """Shared users and roles for the Issue #19 permission tests."""

    @classmethod
    def setUpTestData(cls):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        teacher_group, _ = Group.objects.get_or_create(name=ROLE_TEACHER)
        student_group, _ = Group.objects.get_or_create(name=ROLE_STUDENT)

        cls.admin = User.objects.create_user(username="perm_admin")
        cls.admin.groups.add(admin_group)

        cls.superuser = User.objects.create_superuser(
            username="perm_superuser", password="unused-password"
        )

        cls.inactive_admin = User.objects.create_user(
            username="perm_inactive_admin", is_active=False
        )
        cls.inactive_admin.groups.add(admin_group)

        cls.teacher = User.objects.create_user(username="perm_teacher")
        cls.teacher.groups.add(teacher_group)

        cls.other_teacher = User.objects.create_user(
            username="perm_other_teacher"
        )
        cls.other_teacher.groups.add(teacher_group)

        cls.student = User.objects.create_user(username="perm_student")
        cls.student.groups.add(student_group)

        cls.other_student = User.objects.create_user(
            username="perm_other_student"
        )
        cls.other_student.groups.add(student_group)

        cls.no_role_user = User.objects.create_user(username="perm_no_role")

    def assert_sent_to_login(self, response, url):
        """Anonymous users must be redirected to the login page."""
        self.assertRedirects(
            response,
            f"{settings.LOGIN_URL}?next={url}",
            fetch_redirect_response=False,
        )


class AccountPagesPermissionTests(RolePermissionTestBase):
    """/users/ pages are for Admins only (SRS SAMS-SR-003)."""

    def account_urls(self):
        return {
            "user_list": reverse("user_list"),
            "user_create": reverse("user_create"),
            "user_update": reverse("user_update", args=[self.teacher.pk]),
        }

    def test_anonymous_is_sent_to_login(self):
        for name, url in self.account_urls().items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assert_sent_to_login(response, url)

    def test_inactive_admin_is_treated_like_anonymous(self):
        self.client.force_login(self.inactive_admin)

        for name, url in self.account_urls().items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assert_sent_to_login(response, url)

    def test_non_admin_roles_get_403(self):
        non_admins = {
            "student": self.student,
            "teacher": self.teacher,
            "no_role": self.no_role_user,
        }

        for role, user in non_admins.items():
            self.client.force_login(user)

            for name, url in self.account_urls().items():
                with self.subTest(role=role, page=name):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)

    def test_admin_and_superuser_can_open_all_pages(self):
        for role, user in {
            "admin": self.admin,
            "superuser": self.superuser,
        }.items():
            self.client.force_login(user)

            for name, url in self.account_urls().items():
                with self.subTest(role=role, page=name):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)

    def test_admin_cannot_edit_unmanaged_accounts(self):
        """Admins, superusers, role-less users and unknown IDs give 404."""
        self.client.force_login(self.admin)

        targets = {
            "admin account": self.admin.pk,
            "superuser account": self.superuser.pk,
            "role-less account": self.no_role_user.pk,
            "unknown id": 999999,
        }

        for label, pk in targets.items():
            with self.subTest(target=label):
                response = self.client.get(reverse("user_update", args=[pk]))
                self.assertEqual(response.status_code, 404)

    def test_refused_users_cannot_create_accounts(self):
        users_before = User.objects.count()

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(
                    reverse("user_create"),
                    {"username": "intruder", "password1": "x", "password2": "x"},
                )
                self.assertEqual(response.status_code, 403)

        self.assertEqual(User.objects.count(), users_before)
        self.assertFalse(User.objects.filter(username="intruder").exists())

    def test_anonymous_cannot_create_accounts(self):
        users_before = User.objects.count()

        response = self.client.post(
            reverse("user_create"),
            {"username": "intruder", "password1": "x", "password2": "x"},
        )

        self.assert_sent_to_login(response, reverse("user_create"))
        self.assertEqual(User.objects.count(), users_before)

    def test_refused_users_cannot_edit_accounts(self):
        url = reverse("user_update", args=[self.other_teacher.pk])

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(url, {"username": "hacked"})
                self.assertEqual(response.status_code, 403)

        self.other_teacher.refresh_from_db()
        self.assertEqual(self.other_teacher.username, "perm_other_teacher")


class SectionTestBase(RolePermissionTestBase):
    """Adds two sections; each teacher is assigned to one of them."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.course = Course.objects.create(
            code="PERM101", name="Permission Testing"
        )
        cls.section_a = Section.objects.create(
            course=cls.course, name="A", academic_year="2026-27"
        )
        cls.section_b = Section.objects.create(
            course=cls.course, name="B", academic_year="2026-27"
        )

        cls.assignment_a = TeacherAssignment.objects.create(
            teacher=cls.teacher, section=cls.section_a
        )
        cls.assignment_b = TeacherAssignment.objects.create(
            teacher=cls.other_teacher, section=cls.section_b
        )


class DashboardPermissionTests(SectionTestBase):
    """Dashboards: wrong roles are redirected to /dashboard/ (by design)."""

    def role_dashboards(self):
        return {
            "admin": reverse("attendance:admin_dashboard"),
            "teacher": reverse("attendance:teacher_dashboard"),
            "student": reverse("attendance:student_dashboard"),
        }

    def test_anonymous_is_sent_to_login(self):
        urls = list(self.role_dashboards().values())
        urls.append(reverse("attendance:dashboard"))

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_sent_to_login(response, url)

    def test_inactive_user_is_treated_like_anonymous(self):
        self.client.force_login(self.inactive_admin)
        url = reverse("attendance:admin_dashboard")

        response = self.client.get(url)

        self.assert_sent_to_login(response, url)

    def test_each_role_opens_only_its_own_dashboard(self):
        users = {
            "admin": self.admin,
            "teacher": self.teacher,
            "student": self.student,
        }
        dashboards = self.role_dashboards()

        for role, user in users.items():
            self.client.force_login(user)

            for dashboard_role, url in dashboards.items():
                with self.subTest(user=role, page=dashboard_role):
                    response = self.client.get(url)

                    if dashboard_role == role:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertRedirects(
                            response,
                            reverse("attendance:dashboard"),
                            fetch_redirect_response=False,
                        )

    def test_superuser_counts_as_admin_only(self):
        self.client.force_login(self.superuser)
        dashboards = self.role_dashboards()

        self.assertEqual(
            self.client.get(dashboards["admin"]).status_code, 200
        )

        for role in ("teacher", "student"):
            with self.subTest(page=role):
                response = self.client.get(dashboards[role])
                self.assertRedirects(
                    response,
                    reverse("attendance:dashboard"),
                    fetch_redirect_response=False,
                )

    def test_dashboard_redirects_each_role_to_its_own_page(self):
        expected = {
            self.admin: "attendance:admin_dashboard",
            self.superuser: "attendance:admin_dashboard",
            self.teacher: "attendance:teacher_dashboard",
            self.student: "attendance:student_dashboard",
        }

        for user, target in expected.items():
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.get(reverse("attendance:dashboard"))
                self.assertRedirects(
                    response, reverse(target), fetch_redirect_response=False
                )

    def test_user_without_role_is_refused_everywhere(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse("attendance:dashboard"))
        self.assertEqual(response.status_code, 403)

        for role, url in self.role_dashboards().items():
            with self.subTest(page=role):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    reverse("attendance:dashboard"),
                    fetch_redirect_response=False,
                )

    def test_teacher_dashboard_lists_only_own_sections(self):
        url = reverse("attendance:teacher_dashboard")

        self.client.force_login(self.teacher)
        shown = [a.section_id for a in self.client.get(url).context["assignments"]]
        self.assertEqual(shown, [self.section_a.pk])

        self.client.force_login(self.other_teacher)
        shown = [a.section_id for a in self.client.get(url).context["assignments"]]
        self.assertEqual(shown, [self.section_b.pk])


class TeacherAssignmentPagesPermissionTests(SectionTestBase):
    """/teacher-assignments/ pages are for Admins only (SRS SAMS-SR-003)."""

    def assignment_urls(self):
        return {
            "list": reverse("teacher_assignment_list"),
            "create": reverse("teacher_assignment_create"),
        }

    def test_anonymous_is_sent_to_login(self):
        urls = list(self.assignment_urls().values())
        urls.append(reverse("teacher_assignment_delete", args=[self.assignment_a.pk]))

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_sent_to_login(response, url)

    def test_non_admin_roles_get_403(self):
        delete_url = reverse(
            "teacher_assignment_delete", args=[self.assignment_a.pk]
        )
        urls = list(self.assignment_urls().values()) + [delete_url]

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            for url in urls:
                with self.subTest(user=user.username, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)

    def test_admin_and_superuser_can_open_list_and_create(self):
        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            for name, url in self.assignment_urls().items():
                with self.subTest(user=user.username, page=name):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_teacher_cannot_give_themselves_a_section(self):
        count_before = TeacherAssignment.objects.count()
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("teacher_assignment_create"),
            {"teacher": self.teacher.pk, "section": self.section_b.pk},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TeacherAssignment.objects.count(), count_before)
        self.assertFalse(
            TeacherAssignment.objects.filter(
                teacher=self.teacher, section=self.section_b
            ).exists()
        )

    def test_refused_users_cannot_delete_assignments(self):
        url = reverse("teacher_assignment_delete", args=[self.assignment_b.pk])

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 403)

        self.assertTrue(
            TeacherAssignment.objects.filter(pk=self.assignment_b.pk).exists()
        )

    def test_anonymous_cannot_delete_assignments(self):
        url = reverse("teacher_assignment_delete", args=[self.assignment_a.pk])

        response = self.client.post(url)

        self.assert_sent_to_login(response, url)
        self.assertTrue(
            TeacherAssignment.objects.filter(pk=self.assignment_a.pk).exists()
        )

    def test_admin_get_on_delete_url_deletes_nothing(self):
        self.client.force_login(self.admin)
        url = reverse("teacher_assignment_delete", args=[self.assignment_a.pk])

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse("teacher_assignment_list"),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            TeacherAssignment.objects.filter(pk=self.assignment_a.pk).exists()
        )

    def test_admin_post_deletes_the_assignment(self):
        self.client.force_login(self.admin)
        url = reverse("teacher_assignment_delete", args=[self.assignment_a.pk])

        self.client.post(url)

        self.assertFalse(
            TeacherAssignment.objects.filter(pk=self.assignment_a.pk).exists()
        )


class DefaulterReportPermissionTests(SectionTestBase):
    """Defaulter reports: Admin all sections, Teacher assigned sections."""

    def test_anonymous_is_sent_to_login(self):
        urls = [
            reverse("defaulter_section_list"),
            reverse("defaulter_list", args=[self.section_a.pk]),
            reverse("defaulter_settings"),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_sent_to_login(response, url)

    def test_student_and_no_role_get_403_everywhere(self):
        urls = [
            reverse("defaulter_section_list"),
            reverse("defaulter_list", args=[self.section_a.pk]),
            reverse("defaulter_settings"),
        ]

        for user in (self.student, self.no_role_user):
            self.client.force_login(user)

            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_teacher_sees_only_assigned_section_report(self):
        self.client.force_login(self.teacher)

        own = self.client.get(reverse("defaulter_list", args=[self.section_a.pk]))
        other = self.client.get(reverse("defaulter_list", args=[self.section_b.pk]))

        self.assertEqual(own.status_code, 200)
        self.assertEqual(other.status_code, 403)

    def test_teacher_section_list_contains_only_assigned_sections(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("defaulter_section_list"))

        shown = [section.pk for section in response.context["sections"]]
        self.assertEqual(shown, [self.section_a.pk])

    def test_admin_and_superuser_can_open_every_report(self):
        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            for section in (self.section_a, self.section_b):
                with self.subTest(user=user.username, section=section.name):
                    response = self.client.get(
                        reverse("defaulter_list", args=[section.pk])
                    )
                    self.assertEqual(response.status_code, 200)

    def test_unknown_section_gives_404(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("defaulter_list", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_only_admins_can_open_threshold_settings(self):
        url = reverse("defaulter_settings")

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)

        for user in (self.admin, self.superuser):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_refused_users_cannot_change_the_threshold(self):
        url = reverse("defaulter_settings")
        before = AttendanceThreshold.get_solo().value

        for user in (self.student, self.teacher, self.no_role_user):
            self.client.force_login(user)

            with self.subTest(user=user.username):
                response = self.client.post(url, {"value": "10"})
                self.assertEqual(response.status_code, 403)

        self.assertEqual(AttendanceThreshold.get_solo().value, before)

    def test_anonymous_cannot_change_the_threshold(self):
        url = reverse("defaulter_settings")
        before = AttendanceThreshold.get_solo().value

        response = self.client.post(url, {"value": "10"})

        self.assert_sent_to_login(response, url)
        self.assertEqual(AttendanceThreshold.get_solo().value, before)

    def test_admin_can_change_the_threshold(self):
        self.client.force_login(self.admin)

        self.client.post(reverse("defaulter_settings"), {"value": "60"})

        self.assertEqual(AttendanceThreshold.get_solo().value, Decimal("60"))