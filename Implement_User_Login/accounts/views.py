from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect


def home(request):
    """Send users to the dashboard or login page."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    return redirect('login')


@login_required
def dashboard(request):
    """Show the dashboard only to authenticated users."""
    return render(request, 'accounts/dashboard.html')


def register(request):
    """Create a new user account."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()

    return render(
        request,
        'accounts/register.html',
        {'form': form},
    )