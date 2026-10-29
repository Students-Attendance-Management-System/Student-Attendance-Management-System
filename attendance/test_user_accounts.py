from unittest import mock

from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import UserCreateForm, UserUpdateForm
from .permissions import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TEACHER,
    get_role_name,
    is_managed_account,
    is_sams_admin,
    managed_users,
)

PASSWORD = "Sams#Secure2026!"

# A fast hasher keeps the suite quick; it is only active during these tests.
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role=None, **extra):
    user = User.objects.create_user(
        username=username,
        password=PASSWORD,
        email=extra.pop("email", f"{username}@example.com"),
        **extra,
    )
    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def group_names(user):
    return set(user.groups.values_list("name", flat=True))


def create_data(**overrides):
    data = {
        "username": "new_user",
        "first_name": "New",
        "last_name": "User",
        "email": "new_user@example.com",
        "role": ROLE_TEACHER,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }
    data.update(overrides)
    return data


def update_data(**overrides):
    data = {
        "first_name": "Tara",
        "last_name": "Teach",
        "email": "t_one@example.com",
        "role": ROLE_TEACHER,
        "is_active": "on",
    }
    data.update(overrides)
    return data


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class AccountTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Admin = member of the "Admin" group (same convention as Issue #2).
        cls.admin = make_user("boss_admin", ROLE_ADMIN, first_name="Boss")
        cls.superuser = User.objects.create_superuser(
            username="root_super",
            email="root@example.com",
            password=PASSWORD,
        )
        cls.teacher = make_user(
            "t_one", ROLE_TEACHER, first_name="Tara", last_name="Teach"
        )
        cls.student = make_user(
            "s_one", ROLE_STUDENT, first_name="Sam", last_name="Student"
        )
        # Active user who belongs to no role group and is not a superuser.
        cls.no_role = make_user("no_role")

    def login_as(self, user):
        self.client.force_login(user)

    def edit_url(self, user):
        return reverse("user_update", args=[user.pk])


class PermissionHelperTests(AccountTestBase):
    def test_is_sams_admin(self):
        self.assertTrue(is_sams_admin(self.admin))
        self.assertTrue(is_sams_admin(self.superuser))
        self.assertFalse(is_sams_admin(self.teacher))
        self.assertFalse(is_sams_admin(self.student))
        self.assertFalse(is_sams_admin(self.no_role))
        self.assertFalse(is_sams_admin(AnonymousUser()))

    def test_inactive_admin_and_superuser_are_not_admins(self):
        self.admin.is_active = False
        self.superuser.is_active = False
        self.assertFalse(is_sams_admin(self.admin))
        self.assertFalse(is_sams_admin(self.superuser))

    def test_role_name(self):
        self.assertEqual(get_role_name(self.teacher), ROLE_TEACHER)
        self.assertEqual(get_role_name(self.student), ROLE_STUDENT)
        self.assertIsNone(get_role_name(self.admin))
        self.assertIsNone(get_role_name(self.no_role))

    def test_managed_accounts_are_teachers_and_students_only(self):
        self.assertTrue(is_managed_account(self.teacher))
        self.assertTrue(is_managed_account(self.student))
        self.assertFalse(is_managed_account(self.admin))
        self.assertFalse(is_managed_account(self.superuser))
        self.assertFalse(is_managed_account(self.no_role))

        self.assertEqual(
            {u.username for u in managed_users()}, {"t_one", "s_one"}
        )

    def test_admin_group_member_with_teacher_group_is_not_managed(self):
        both = make_user("both_roles", ROLE_TEACHER)
        both.groups.add(Group.objects.get(name=ROLE_ADMIN))

        self.assertFalse(is_managed_account(both))
        self.assertNotIn("both_roles", {u.username for u in managed_users()})


class AccessControlTests(AccountTestBase):
    def test_anonymous_users_are_redirected_to_login(self):
        urls = [
            reverse("user_list"),
            reverse("user_create"),
            self.edit_url(self.teacher),
        ]
        users_before = User.objects.count()

        for url in urls:
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertRedirects(
                        response,
                        f"{reverse('login')}?next={url}",
                        fetch_redirect_response=False,
                    )

        self.assertEqual(User.objects.count(), users_before)

    def test_non_admins_get_403_on_every_page(self):
        urls = [
            reverse("user_list"),
            reverse("user_create"),
            self.edit_url(self.student),
        ]

        for user in (self.teacher, self.student, self.no_role):
            self.login_as(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            self.client.logout()

    def test_non_admin_cannot_create_account(self):
        for user in (self.teacher, self.student, self.no_role):
            self.login_as(user)
            with self.subTest(user=user.username):
                response = self.client.post(
                    reverse("user_create"), create_data(username="sneaky")
                )
                self.assertEqual(response.status_code, 403)
                self.assertFalse(User.objects.filter(username="sneaky").exists())
            self.client.logout()

    def test_non_admin_cannot_modify_account(self):
        self.login_as(self.teacher)
        response = self.client.post(
            self.edit_url(self.student),
            update_data(first_name="Hacked", role=ROLE_TEACHER),
        )
        self.assertEqual(response.status_code, 403)

        self.student.refresh_from_db()
        self.assertNotEqual(self.student.first_name, "Hacked")
        self.assertEqual(group_names(self.student), {ROLE_STUDENT})

    def test_user_cannot_escalate_own_role(self):
        self.login_as(self.student)
        response = self.client.post(
            self.edit_url(self.student),
            update_data(
                first_name="Sam",
                last_name="Student",
                email="s_one@example.com",
                role=ROLE_TEACHER,
            ),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(group_names(self.student), {ROLE_STUDENT})

    def test_admin_group_member_and_superuser_are_allowed(self):
        for user in (self.admin, self.superuser):
            self.login_as(user)
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client.get(reverse("user_list")).status_code, 200
                )
            self.client.logout()


class UserListTests(AccountTestBase):
    def test_list_shows_only_teachers_and_students_with_roles(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        roles = {u.username: u.role_name for u in response.context["users"]}
        self.assertEqual(roles, {"t_one": "Teacher", "s_one": "Student"})
        self.assertNotContains(response, "boss_admin")
        self.assertNotContains(response, "root_super")
        self.assertNotContains(response, "no_role")

    def test_list_marks_deactivated_accounts(self):
        self.student.is_active = False
        self.student.save()

        self.login_as(self.admin)
        response = self.client.get(reverse("user_list"))
        self.assertContains(response, "Deactivated")


class UserCreateTests(AccountTestBase):
    def setUp(self):
        self.login_as(self.admin)
        self.url = reverse("user_create")

    def test_create_form_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_admin_can_create_teacher(self):
        response = self.client.post(self.url, create_data())
        self.assertRedirects(response, reverse("user_list"))

        user = User.objects.get(username="new_user")
        self.assertEqual(group_names(user), {ROLE_TEACHER})
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.email, "new_user@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)  # stored hashed

    def test_admin_can_create_student(self):
        self.client.post(
            self.url,
            create_data(
                username="new_student",
                email="new_student@example.com",
                role=ROLE_STUDENT,
            ),
        )
        user = User.objects.get(username="new_student")
        self.assertEqual(group_names(user), {ROLE_STUDENT})

    def test_role_group_is_created_on_first_use_and_reused(self):
        Group.objects.filter(name=ROLE_TEACHER).delete()
        self.assertFalse(Group.objects.filter(name=ROLE_TEACHER).exists())

        self.client.post(self.url, create_data())
        self.client.post(
            self.url,
            create_data(username="second_teacher", email="second@example.com"),
        )

        # Created once on first use, then reused for the second account.
        # (Deleting a group also removes its memberships, so t_one is not in it.)
        self.assertEqual(Group.objects.filter(name=ROLE_TEACHER).count(), 1)
        self.assertEqual(
            {u.username for u in User.objects.filter(groups__name=ROLE_TEACHER)},
            {"new_user", "second_teacher"},
        )

    def test_success_message_is_shown(self):
        response = self.client.post(self.url, create_data(), follow=True)
        self.assertContains(response, "was created")

    def test_new_account_can_log_in(self):
        # TC-Auth-03: a newly created account can log in immediately.
        self.client.post(self.url, create_data())
        self.assertTrue(
            Client().login(username="new_user", password=PASSWORD)
        )

    def test_admin_role_cannot_be_assigned_through_form(self):
        for role in ("Admin", "ADMIN", "Superuser", ""):
            with self.subTest(role=role):
                response = self.client.post(self.url, create_data(role=role))
                self.assertEqual(response.status_code, 200)
                self.assertIn("role", response.context["form"].errors)
                self.assertFalse(
                    User.objects.filter(username="new_user").exists()
                )

    def test_privilege_fields_in_post_are_ignored(self):
        self.client.post(
            self.url,
            create_data(is_staff="on", is_superuser="on", is_active=""),
        )
        user = User.objects.get(username="new_user")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertNotIn(ROLE_ADMIN, group_names(user))

    def test_duplicate_username_rejected_case_insensitively(self):
        response = self.client.post(
            self.url,
            create_data(username="T_ONE", email="other@example.com"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.filter(username__iexact="t_one").count(), 1)

    def test_duplicate_email_rejected_case_insensitively(self):
        response = self.client.post(
            self.url, create_data(email="T_ONE@EXAMPLE.COM")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="new_user").exists())

    def test_invalid_username_characters_rejected(self):
        response = self.client.post(self.url, create_data(username="bad user"))
        self.assertIn("username", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="bad user").exists())

    def test_too_long_username_rejected(self):
        response = self.client.post(self.url, create_data(username="a" * 151))
        self.assertIn("username", response.context["form"].errors)

    def test_invalid_email_rejected(self):
        response = self.client.post(self.url, create_data(email="not-an-email"))
        self.assertIn("email", response.context["form"].errors)

    def test_required_fields_rejected_when_missing(self):
        for field in (
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "password",
            "confirm_password",
        ):
            with self.subTest(field=field):
                data = create_data()
                data.pop(field)
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(
                    User.objects.filter(username="new_user").exists()
                )

    def test_weak_passwords_rejected(self):
        for weak in ("12345678", "Ab1!", "password"):
            with self.subTest(password=weak):
                response = self.client.post(
                    self.url,
                    create_data(password=weak, confirm_password=weak),
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("password", response.context["form"].errors)
                self.assertFalse(
                    User.objects.filter(username="new_user").exists()
                )

    def test_password_similar_to_username_rejected(self):
        response = self.client.post(
            self.url,
            create_data(
                username="alice_teacher",
                email="alice@example.com",
                password="alice_teacher1",
                confirm_password="alice_teacher1",
            ),
        )
        self.assertIn("password", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="alice_teacher").exists())

    def test_password_mismatch_rejected(self):
        response = self.client.post(
            self.url, create_data(confirm_password="Different#Pass2026!")
        )
        self.assertIn("confirm_password", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="new_user").exists())

    def test_user_and_role_are_created_atomically(self):
        form = UserCreateForm(create_data())
        self.assertTrue(form.is_valid(), form.errors)

        with mock.patch.object(
            Group.objects, "get_or_create", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                form.save()

        # The User row must have been rolled back with the failed role step.
        self.assertFalse(User.objects.filter(username="new_user").exists())


class UserUpdateTests(AccountTestBase):
    def setUp(self):
        self.login_as(self.admin)
        self.url = self.edit_url(self.teacher)

    def test_edit_form_page_loads_with_current_values(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tara")
        self.assertEqual(
            response.context["form"].fields["role"].initial, ROLE_TEACHER
        )

    def test_admin_can_update_details_and_role(self):
        response = self.client.post(
            self.url,
            update_data(
                first_name="Updated",
                last_name="Name",
                email="updated@example.com",
                role=ROLE_STUDENT,
            ),
        )
        self.assertRedirects(response, reverse("user_list"))

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.first_name, "Updated")
        self.assertEqual(self.teacher.last_name, "Name")
        self.assertEqual(self.teacher.email, "updated@example.com")
        self.assertEqual(group_names(self.teacher), {ROLE_STUDENT})

    def test_role_change_leaves_unrelated_groups_alone(self):
        library = Group.objects.create(name="Library")
        self.teacher.groups.add(library)

        self.client.post(self.url, update_data(role=ROLE_STUDENT))

        self.assertEqual(group_names(self.teacher), {"Library", ROLE_STUDENT})

    def test_saving_normalises_to_exactly_one_role_group(self):
        self.teacher.groups.add(Group.objects.get(name=ROLE_STUDENT))
        self.assertEqual(
            group_names(self.teacher), {ROLE_TEACHER, ROLE_STUDENT}
        )

        self.client.post(self.url, update_data(role=ROLE_TEACHER))

        self.assertEqual(group_names(self.teacher), {ROLE_TEACHER})

    def test_keeping_own_email_is_allowed(self):
        response = self.client.post(self.url, update_data())
        self.assertRedirects(response, reverse("user_list"))

    def test_username_and_privilege_fields_cannot_be_changed(self):
        self.client.post(
            self.url,
            update_data(
                username="hacker",
                is_staff="on",
                is_superuser="on",
            ),
        )
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.username, "t_one")
        self.assertFalse(self.teacher.is_staff)
        self.assertFalse(self.teacher.is_superuser)

    def test_duplicate_email_rejected(self):
        response = self.client.post(
            self.url, update_data(email="S_ONE@example.com")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.email, "t_one@example.com")

    def test_admin_role_cannot_be_assigned_through_update(self):
        for role in ("Admin", "ADMIN", "Superuser", ""):
            with self.subTest(role=role):
                response = self.client.post(self.url, update_data(role=role))
                self.assertEqual(response.status_code, 200)
                self.assertIn("role", response.context["form"].errors)
                self.assertEqual(group_names(self.teacher), {ROLE_TEACHER})

    def test_required_fields_rejected_when_blank(self):
        for field in ("first_name", "last_name", "email", "role"):
            with self.subTest(field=field):
                response = self.client.post(self.url, update_data(**{field: ""}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)

    def test_invalid_email_rejected(self):
        response = self.client.post(self.url, update_data(email="nope"))
        self.assertIn("email", response.context["form"].errors)

    def test_protected_accounts_cannot_be_edited(self):
        both = make_user("both_roles", ROLE_TEACHER)
        both.groups.add(Group.objects.get(name=ROLE_ADMIN))

        for target in (self.admin, self.superuser, self.no_role, both):
            with self.subTest(user=target.username):
                url = self.edit_url(target)
                self.assertEqual(self.client.get(url).status_code, 404)

                response = self.client.post(
                    url, update_data(first_name="Hacked", email="x@example.com")
                )
                self.assertEqual(response.status_code, 404)

                target.refresh_from_db()
                self.assertNotEqual(target.first_name, "Hacked")

    def test_unknown_user_returns_404(self):
        response = self.client.get(reverse("user_update", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_update_form_itself_refuses_protected_accounts(self):
        both = make_user("both_roles", ROLE_TEACHER)
        both.groups.add(Group.objects.get(name=ROLE_ADMIN))

        for target in (self.admin, self.superuser, self.no_role, both):
            with self.subTest(user=target.username):
                form = UserUpdateForm(
                    data=update_data(email="x@example.com"), instance=target
                )
                self.assertFalse(form.is_valid())


class DeactivationTests(AccountTestBase):
    def setUp(self):
        self.login_as(self.admin)
        self.url = self.edit_url(self.student)
        self.data = update_data(
            first_name="Sam",
            last_name="Student",
            email="s_one@example.com",
            role=ROLE_STUDENT,
        )

    def test_deactivated_account_cannot_log_in_but_data_is_kept(self):
        # TC-Auth-03: after deactivation, login is denied.
        self.assertTrue(Client().login(username="s_one", password=PASSWORD))

        data = dict(self.data)
        data.pop("is_active")  # an unticked checkbox is simply absent
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse("user_list"))

        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertFalse(Client().login(username="s_one", password=PASSWORD))

        # SRS F-003 / SO-001: the account and its role are preserved.
        self.assertTrue(User.objects.filter(username="s_one").exists())
        self.assertEqual(group_names(self.student), {ROLE_STUDENT})

    def test_deactivated_account_still_appears_in_list(self):
        data = dict(self.data)
        data.pop("is_active")
        self.client.post(self.url, data)

        response = self.client.get(reverse("user_list"))
        self.assertIn(
            "s_one", {u.username for u in response.context["users"]}
        )

    def test_account_can_be_reactivated(self):
        self.student.is_active = False
        self.student.save()
        self.assertFalse(Client().login(username="s_one", password=PASSWORD))

        self.client.post(self.url, self.data)  # includes is_active=on

        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
        self.assertTrue(Client().login(username="s_one", password=PASSWORD))