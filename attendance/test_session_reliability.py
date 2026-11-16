
from datetime import timedelta

from django.conf import settings
from django.test import TestCase

from django.urls import reverse

from .test_role_permissions import SectionTestBase


class SessionReliabilityTests(SectionTestBase):
    """Issue #22: Session expiry and extended-use reliability."""

    def test_session_timeout_is_30_minutes(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 30 * 60)

    def test_session_expires_after_inactivity(self):
        self.client.force_login(self.student)

        session = self.client.session
        session.set_expiry(timedelta(seconds=-1))
        session.save()

        response = self.client.get(
            reverse("attendance:student_dashboard")
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            response.wsgi_request.user.is_authenticated
        )

    def test_expired_session_cannot_access_leave_submission(self):
        self.client.force_login(self.student)

        session = self.client.session
        session.set_expiry(timedelta(seconds=-1))
        session.save()

        response = self.client.post(
            reverse("attendance:submit_leave_request"),
            {},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            response.wsgi_request.user.is_authenticated
        )

    def test_active_session_survives_multiple_requests(self):
        self.client.force_login(self.student)

        urls = [
            reverse("attendance:student_dashboard"),
            reverse("attendance:my_leave_requests"),
            reverse("attendance:student_dashboard"),
        ]

        for url in urls:
            response = self.client.get(url)

            self.assertTrue(
                response.wsgi_request.user.is_authenticated,
                msg=f"User lost authentication while accessing {url}",
            )
