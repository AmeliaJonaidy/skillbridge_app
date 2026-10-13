from django.shortcuts import render

# Create your views here.
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib.auth.models import User
from .models import UserProfile


def home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    return render(request, 'accounts/home.html', {'role': role})


def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=identifier, password=password)
        if user is None and '@' in identifier:
            email_user = User.objects.filter(email__iexact=identifier).first()
            if email_user:
                user = authenticate(request, username=email_user.username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        form.add_error(None, 'Invalid username/email or password.')
    return render(request, 'accounts/login.html', {'form': form})


def signup_view(request):
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        UserProfile.objects.create(user=user, role=request.POST.get('role', 'candidate'))
        login(request, user)
        return redirect('home')
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
