from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model


User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.username = 'teststudent'
        self.password = 'TestPass123!'

        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'accounts/login.html',
        )

    def test_valid_login(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': self.username,
                'password': self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse('dashboard'),
        )

    def test_invalid_login(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': self.username,
                'password': 'WrongPassword123!',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Invalid username or password',
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard')}",
        )

    def test_logged_in_user_can_open_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'accounts/dashboard.html',
        )

    def test_logout(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('logout'))

        self.assertRedirects(response, reverse('login'))

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_registration_page_loads(self):
        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'accounts/register.html',
        )

    def test_registration_creates_account(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newstudent',
                'password1': 'AnotherPass123!',
                'password2': 'AnotherPass123!',
            },
        )

        self.assertTrue(
            User.objects.filter(username='newstudent').exists()
        )
        self.assertRedirects(
            response,
            reverse('dashboard'),
        )