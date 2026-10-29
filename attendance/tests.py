
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


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
