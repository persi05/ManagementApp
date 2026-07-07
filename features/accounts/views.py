from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from features.accounts.forms import AccountForm, RegisterForm
from features.accounts.models import UserProfile, ensure_profile


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.save()
            profile = ensure_profile(user)
            profile.role = UserProfile.Role.CLIENT
            profile.save()
            login(request, user)
            messages.success(request, 'Konto zostało utworzone.')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def account_settings(request):
    if request.method == 'POST' and request.POST.get('form') == 'profile':
        account_form = AccountForm(request.POST, instance=request.user)
        password_form = PasswordChangeForm(request.user)
        if account_form.is_valid():
            account_form.save()
            messages.success(request, 'Dane konta zostały zapisane.')
            return redirect('accounts:settings')
    elif request.method == 'POST' and request.POST.get('form') == 'password':
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, password_form.user)
            messages.success(request, 'Hasło zostało zmienione.')
            return redirect('accounts:settings')
    else:
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'registration/account_settings.html', {
        'account_form': account_form,
        'password_form': password_form,
    })
