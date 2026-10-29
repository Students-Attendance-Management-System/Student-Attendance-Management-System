from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


def make_user(username, role=None, password="TestPass123!"):
    user = User.objects.create_user(username=username, password=password)
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


class SessionExpiryTests(TestCase):

    def setUp(self):
        make_user("admin1", role="Admin")
        self.url = reverse("attendance:admin_dashboard")
        self.login_redirect = f"{settings.LOGIN_URL}?next={self.url}"

    def test_session_timeout_is_configured(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_active_session_can_access_protected_page(self):
        self.client.login(username="admin1", password="TestPass123!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_expired_session_cannot_access_protected_page(self):
        self.client.login(username="admin1", password="TestPass123!")
        Session.objects.update(
            expire_date=timezone.now() - timedelta(minutes=1)
        )
        response = self.client.get(self.url)
        self.assertRedirects(
            response, self.login_redirect, fetch_redirect_response=False
        )

    def test_invalid_session_cookie_is_rejected(self):
        self.client.cookies[settings.SESSION_COOKIE_NAME] = "not-a-real-session"
        response = self.client.get(self.url)
        self.assertRedirects(
            response, self.login_redirect, fetch_redirect_response=False
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, self.login_redirect, fetch_redirect_response=False
        )


class AdminOnlyAccessTests(TestCase):

    def setUp(self):
        make_user("admin1", role="Admin")
        make_user("teacher1", role="Teacher")
        make_user("student1", role="Student")
        self.url = reverse("attendance:admin_dashboard")

    def test_admin_can_access_admin_page(self):
        self.client.login(username="admin1", password="TestPass123!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_access_admin_page(self):
        self.client.login(username="teacher1", password="TestPass123!")
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            reverse("attendance:dashboard"),
            fetch_redirect_response=False,
        )

    def test_student_cannot_access_admin_page(self):
        self.client.login(username="student1", password="TestPass123!")
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            reverse("attendance:dashboard"),
            fetch_redirect_response=False,
        )