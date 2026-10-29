from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UserCreateForm, UserUpdateForm
from .permissions import get_role_name, managed_users, require_sams_admin


def admin_only(view_func):
    """
    Anonymous users are redirected to the login page (login_required).
    Logged-in users who are not SAMS admins get 403 (PermissionDenied).
    """

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        require_sams_admin(request.user)
        return view_func(request, *args, **kwargs)

    return wrapper


@admin_only
def user_list(request):
    users = list(managed_users())

    # Attach the role name once per user so the template stays simple.
    for account in users:
        account.role_name = get_role_name(account)

    return render(
        request,
        "user_management/user_list.html",
        {"users": users},
    )


@admin_only
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)

        if form.is_valid():
            user = form.save()
            messages.success(
                request, f"Account '{user.username}' was created."
            )
            return redirect("user_list")
    else:
        form = UserCreateForm()

    return render(
        request,
        "user_management/user_form.html",
        {"form": form, "title": "Create account", "is_create": True},
    )


@admin_only
def user_update(request, pk):
    # 404 for Admins, superusers, role-less users, or unknown IDs:
    # they are not editable through account management.
    user = get_object_or_404(managed_users(), pk=pk)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=user)

        if form.is_valid():
            form.save()
            messages.success(
                request, f"Account '{user.username}' was updated."
            )
            return redirect("user_list")
    else:
        form = UserUpdateForm(instance=user)

    return render(
        request,
        "user_management/user_form.html",
        {
            "form": form,
            "title": f"Edit account: {user.username}",
            "is_create": False,
            "account": user,
        },
    )